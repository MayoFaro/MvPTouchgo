# src/classification/client.py
import asyncio
import logging

import anthropic
from pydantic import BaseModel

from src.classification.prompt import CATEGORIES, CLASSIFY_TOOL, SYSTEM_PROMPT
from src.config import get_settings

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
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
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "classify_news_item":
            data = block.input
            primary = data.get("primary_category")
            if primary not in CATEGORIES:
                raise ValueError(f"invalid primary_category from model: {primary!r}")
            secondary = [c for c in data.get("secondary_categories", []) if c in CATEGORIES]
            return ClassificationResult(
                primary_category=primary,
                secondary_categories=secondary,
                classification_confidence=float(data.get("classification_confidence", 0.0)),
                reasoning=str(data.get("reasoning", "")),
            )
    raise ValueError("no tool_use block named classify_news_item in Claude response")


async def classify_item(
    title: str,
    text: str,
    examples: str = "",
    client: anthropic.AsyncAnthropic | None = None,
) -> ClassificationResult:
    active_client = client or anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
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
            response = await active_client.messages.create(
                model=MODEL,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                tools=[CLASSIFY_TOOL],
                tool_choice={"type": "tool", "name": "classify_news_item"},
                messages=[{"role": "user", "content": user_message}],
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
