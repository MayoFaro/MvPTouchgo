# src/classification/client.py
import asyncio
import logging

import ollama
from pydantic import BaseModel

from src.classification.prompt import CATEGORIES, CLASSIFY_TOOL, SYSTEM_PROMPT
from src.config import get_settings

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 1


class ClassificationResult(BaseModel):
    primary_category: str
    secondary_categories: list[str]
    classification_confidence: float
    reasoning: str


class ClassificationError(Exception):
    """Raised when classification fails after all retry attempts."""


def parse_classification_response(response) -> ClassificationResult:
    tool_calls = response.message.tool_calls
    if tool_calls:
        for tool_call in tool_calls:
            if tool_call.function.name == "classify_news_item":
                data = tool_call.function.arguments
                primary = data.get("primary_category")
                if primary not in CATEGORIES:
                    raise ValueError(f"invalid primary_category from model: {primary!r}")
                if "classification_confidence" not in data:
                    raise ValueError(
                        "missing required field 'classification_confidence' in model response"
                    )
                confidence = float(data["classification_confidence"])
                if not 0.0 <= confidence <= 1.0:
                    raise ValueError(
                        f"classification_confidence out of range (must be 0.0-1.0): {confidence!r}"
                    )
                secondary = [c for c in data.get("secondary_categories", []) if c in CATEGORIES]
                return ClassificationResult(
                    primary_category=primary,
                    secondary_categories=secondary,
                    classification_confidence=confidence,
                    reasoning=str(data.get("reasoning", "")),
                )
    raise ValueError("no tool call named classify_news_item in Ollama response")


async def classify_item(
    title: str,
    text: str,
    examples: str = "",
    client: ollama.AsyncClient | None = None,
) -> ClassificationResult:
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
        f"{examples_block}Titre : {title}\n\nTexte :\n<article>\n{truncated_text}\n</article>"
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
                tools=[CLASSIFY_TOOL],
            )
            return parse_classification_response(response)
        except Exception as exc:  # noqa: BLE001 - any failure takes the same retry/backoff path
            last_error = exc
            logger.warning("Classification attempt %d/%d failed: %s", attempt, MAX_ATTEMPTS, exc)
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
    raise ClassificationError(
        f"classification failed after {MAX_ATTEMPTS} attempts"
    ) from last_error
