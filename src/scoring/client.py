import asyncio
import logging

import ollama
from pydantic import BaseModel

from src.config import get_settings
from src.scoring.prompt import PRIORITIES, SCORE_TOOL, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 1


class ScoringResult(BaseModel):
    touchgo_interest: int
    event_importance: int
    source_confidence: int
    urgency: int
    priority: str
    reasoning: str


class ScoringError(Exception):
    """Raised when scoring fails after all retry attempts."""


def parse_scoring_response(response) -> ScoringResult:
    tool_calls = response.message.tool_calls
    if tool_calls:
        for tool_call in tool_calls:
            if tool_call.function.name == "score_news_item":
                data = tool_call.function.arguments
                priority = data.get("priority")
                if priority not in PRIORITIES:
                    raise ValueError(f"invalid priority from model: {priority!r}")
                for key in ("touchgo_interest", "event_importance", "source_confidence", "urgency"):
                    if key not in data:
                        raise ValueError(f"missing required field {key!r} in model response")
                    if not 0 <= int(data[key]) <= 10:
                        raise ValueError(
                            f"field {key!r} out of range (must be 0-10): {data[key]!r}"
                        )
                return ScoringResult(
                    touchgo_interest=int(data["touchgo_interest"]),
                    event_importance=int(data["event_importance"]),
                    source_confidence=int(data["source_confidence"]),
                    urgency=int(data["urgency"]),
                    priority=priority,
                    reasoning=str(data.get("reasoning", "")),
                )
    raise ValueError("no tool call named score_news_item in Ollama response")


async def score_item(
    title: str,
    text: str,
    source_type: str,
    examples: str = "",
    client: ollama.AsyncClient | None = None,
) -> ScoringResult:
    active_client = client or ollama.AsyncClient(
        host=get_settings().ollama_host, timeout=get_settings().ollama_timeout_seconds
    )
    # Bound the article body sent to the model: caps token cost and avoids risking
    # the context window on an arbitrarily long scraped article.
    truncated_text = text[:4000]
    examples_block = (
        "Exemples de feedback humain récent (indicatif, à pondérer avec jugement) :\n"
        f"<exemples_feedback>\n{examples}\n</exemples_feedback>\n\n"
        if examples
        else ""
    )
    user_message = (
        f"{examples_block}Type de source : {source_type}\n\n"
        f"Titre : {title}\n\nTexte :\n<article>\n{truncated_text}\n</article>"
    )

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await active_client.chat(
                model=get_settings().ollama_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                tools=[SCORE_TOOL],
            )
            return parse_scoring_response(response)
        except Exception as exc:  # noqa: BLE001 - any failure takes the same retry/backoff path
            last_error = exc
            logger.warning("Scoring attempt %d/%d failed: %s", attempt, MAX_ATTEMPTS, exc)
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
    raise ScoringError(f"scoring failed after {MAX_ATTEMPTS} attempts") from last_error
