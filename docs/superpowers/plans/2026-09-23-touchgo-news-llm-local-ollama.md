# Touch-Go News — LLM local via Ollama Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the paid Anthropic API with a local LLM served by Ollama for both classification
and scoring, with zero change to the stable `classify_item`/`score_item` facade that the rest of
the codebase (jobs, adaptive examples, API, tests) already depends on.

**Architecture:** `src/classification/` and `src/scoring/` each get their tool schema reshaped
from Anthropic's `input_schema` format to Ollama's `{"type": "function", "function": {...,
"parameters": {...}}}` format, their client rewritten to call `ollama.AsyncClient.chat(...)`
instead of `anthropic.AsyncAnthropic.messages.create(...)`, and their `job.py` construct an
`ollama.AsyncClient` instead of an `anthropic.AsyncAnthropic` client — same one-client-per-batch
pattern as today. No other file changes: `src/adaptive/`, `src/api/`, `src/review/`,
`src/scheduler.py`, and every existing integration test already interact with `classify_item`/
`score_item` through the facade, never through the underlying SDK.

**Tech Stack:** `ollama` (official Python client, verified installed as version 0.6.2 during
planning) replaces `anthropic`. No other new dependency.

**Spec:** [`docs/superpowers/specs/2026-09-23-touchgo-news-llm-local-ollama-design.md`](../specs/2026-09-23-touchgo-news-llm-local-ollama-design.md)

## Global Constraints

- Remplacement complet d'Anthropic par Ollama, aucune couche multi-provider (design §1).
- Runtime : Ollama. Modèle par défaut : `qwen2.5:7b-instruct` (design §2).
- Ollama ne garantit pas d'appel d'outil forcé — toute réponse du modèle sans appel d'outil
  valide (ou avec des données invalides) est traitée comme un échec de parsing, absorbé par le
  retry/isolation déjà en place depuis les Sprints 3/4 (`MAX_ATTEMPTS = 2`, inchangé) (design §3).
- `classify_item(title, text, examples="", client=None)` et `score_item(title, text, source_type,
  examples="", client=None)` gardent exactement leur signature actuelle — aucun appelant
  (`job.py`, `src/adaptive/`, les tests d'intégration) ne doit être modifié au-delà du swap interne
  (design §4).
- Le texte du `SYSTEM_PROMPT` de chaque pipeline ne change pas — seule sa méthode de transmission
  change (paramètre séparé chez Anthropic → premier message de la liste `messages` chez Ollama)
  (design §4).
- Aucun appel réseau réel dans les tests automatisés — jamais de serveur Ollama réel sollicité par
  la suite de tests (design §6).
- Aucun changement de schéma DB, aucun changement aux réglages de batch/intervalle/retry existants
  (design §5).
- Le client Ollama JSON-schema n'a pas de mots-clés `minimum`/`maximum` sur ses propriétés
  (vérifié en explorant le paquet `ollama` 0.6.2 pendant la planification — silencieusement
  éliminés par `Tool.model_validate()` s'ils étaient présents) : les bornes numériques (0-10, 0.0-1.0)
  vivent uniquement dans le texte `description` de chaque propriété, jamais comme mot-clé JSON
  Schema qui laisserait croire à tort qu'elles sont appliquées côté serveur.

---

### Task 1: Configuration — réglages Ollama et dépendance

**Files:**
- Modify: `src/config.py`
- Modify: `.env.example`
- Modify: `pyproject.toml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings.ollama_host: str` (défaut `"http://localhost:11434"`),
  `Settings.ollama_model: str` (défaut `"qwen2.5:7b-instruct"`). `Settings.anthropic_api_key` est
  supprimé.

- [ ] **Step 1: Write the failing test**

Remplacer les deux fonctions de test existantes dans `tests/test_config.py` en entier (même objet
`Settings` déjà sous test, on étend plutôt que d'ajouter de nouvelles fonctions) :

```python
import os

from src.config import Settings


def test_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host:5432/db")
    monkeypatch.setenv("SOURCES_CONFIG_PATH", "config/sources.yaml")
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama-test:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("CLASSIFICATION_BATCH_SIZE", "5")
    monkeypatch.setenv("CLASSIFICATION_INTERVAL_MINUTES", "10")
    monkeypatch.setenv("CLASSIFICATION_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("SCORING_BATCH_SIZE", "8")
    monkeypatch.setenv("SCORING_INTERVAL_MINUTES", "15")
    monkeypatch.setenv("SCORING_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("DEFAULT_REVIEWER_ID", "cedric")
    monkeypatch.setenv("ADAPTIVE_MIN_EXAMPLES", "2")
    monkeypatch.setenv("ADAPTIVE_MAX_EXAMPLES", "10")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"
    assert settings.sources_config_path == "config/sources.yaml"
    assert settings.ollama_host == "http://ollama-test:11434"
    assert settings.ollama_model == "test-model"
    assert settings.classification_batch_size == 5
    assert settings.classification_interval_minutes == 10
    assert settings.classification_max_attempts == 3
    assert settings.scoring_batch_size == 8
    assert settings.scoring_interval_minutes == 15
    assert settings.scoring_max_attempts == 4
    assert settings.default_reviewer_id == "cedric"
    assert settings.adaptive_min_examples == 2
    assert settings.adaptive_max_examples == 10


def test_settings_have_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SOURCES_CONFIG_PATH", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("CLASSIFICATION_BATCH_SIZE", raising=False)
    monkeypatch.delenv("CLASSIFICATION_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("CLASSIFICATION_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("SCORING_BATCH_SIZE", raising=False)
    monkeypatch.delenv("SCORING_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("SCORING_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("DEFAULT_REVIEWER_ID", raising=False)
    monkeypatch.delenv("ADAPTIVE_MIN_EXAMPLES", raising=False)
    monkeypatch.delenv("ADAPTIVE_MAX_EXAMPLES", raising=False)
    settings = Settings(_env_file=None)
    assert "touchgo_news" in settings.database_url
    assert settings.sources_config_path == "config/sources.yaml"
    assert settings.ollama_host == "http://localhost:11434"
    assert settings.ollama_model == "qwen2.5:7b-instruct"
    assert settings.classification_batch_size == 20
    assert settings.classification_interval_minutes == 3
    assert settings.classification_max_attempts == 5
    assert settings.scoring_batch_size == 20
    assert settings.scoring_interval_minutes == 3
    assert settings.scoring_max_attempts == 5
    assert settings.default_reviewer_id == "reviewer"
    assert settings.adaptive_min_examples == 5
    assert settings.adaptive_max_examples == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError`, `Settings` has no `ollama_host`/`ollama_model` yet (and still
has `anthropic_api_key`, which the new test no longer references — not itself a failure, but the
new assertions on `ollama_host`/`ollama_model` will raise `AttributeError`).

- [ ] **Step 3: Update `Settings`**

In `src/config.py`, replace the class body:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://touchgo:touchgo@localhost:5432/touchgo_news"
    sources_config_path: str = "config/sources.yaml"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    classification_batch_size: int = 20
    classification_interval_minutes: int = 3
    classification_max_attempts: int = 5
    scoring_batch_size: int = 20
    scoring_interval_minutes: int = 3
    scoring_max_attempts: int = 5
    default_reviewer_id: str = "reviewer"
    adaptive_min_examples: int = 5
    adaptive_max_examples: int = 5
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Update `.env.example`**

Replace the `ANTHROPIC_API_KEY=` line with:

```
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
```

(Keep its original position in the file — right after `SOURCES_CONFIG_PATH=config/sources.yaml`.)

- [ ] **Step 6: Update `pyproject.toml`**

In the `dependencies` list, replace `"anthropic>=0.40",` with `"ollama>=0.6",` (keep its original
position in the list).

Then reinstall:

```bash
.venv/bin/pip install -e .
```

- [ ] **Step 7: Commit**

```bash
git add src/config.py tests/test_config.py .env.example pyproject.toml
git commit -m "feat: replace Anthropic settings with Ollama host/model"
```

---

### Task 2: Classification — schéma d'outil, client, et job Ollama

**Files:**
- Modify: `src/classification/prompt.py`
- Modify: `src/classification/client.py`
- Modify: `src/classification/job.py`
- Test: `tests/classification/test_prompt.py`
- Test: `tests/classification/test_client.py`

**Interfaces:**
- Consumes: `Settings.ollama_host`/`ollama_model` (Task 1).
- Produces: `CLASSIFY_TOOL` reshaped to Ollama's function-calling format.
  `classify_item(title: str, text: str, examples: str = "", client: ollama.AsyncClient | None =
  None) -> ClassificationResult` — same signature as before, `client` type changes from
  `anthropic.AsyncAnthropic | None` to `ollama.AsyncClient | None`.
  `parse_classification_response(response) -> ClassificationResult` — same signature, now reads
  Ollama's response shape.

- [ ] **Step 1: Write the failing prompt test**

In `tests/classification/test_prompt.py`, replace the last test function
(`test_classify_tool_schema_has_required_fields`) — everything above it in the file is unchanged:

```python
def test_classify_tool_schema_has_required_fields():
    assert CLASSIFY_TOOL["function"]["name"] == "classify_news_item"
    properties = CLASSIFY_TOOL["function"]["parameters"]["properties"]
    assert set(properties) == {
        "primary_category",
        "secondary_categories",
        "classification_confidence",
        "reasoning",
    }
    assert properties["primary_category"]["enum"] == CATEGORIES
    assert properties["secondary_categories"]["items"]["enum"] == CATEGORIES
    required = CLASSIFY_TOOL["function"]["parameters"]["required"]
    assert set(required) == {
        "primary_category",
        "secondary_categories",
        "classification_confidence",
        "reasoning",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/classification/test_prompt.py -v`
Expected: FAIL with `KeyError: 'function'` (the current `CLASSIFY_TOOL` still has a top-level
`"name"` key, not a nested `"function"` key).

- [ ] **Step 3: Update `CLASSIFY_TOOL`**

In `src/classification/prompt.py`, `SYSTEM_PROMPT` is unchanged — only `CLASSIFY_TOOL` (the last
block in the file) changes. Replace it:

```python
CLASSIFY_TOOL = {
    "type": "function",
    "function": {
        "name": "classify_news_item",
        "description": (
            "Classify an aviation news item into Touch-Go's editorial categories, per the system "
            "prompt's rules."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "primary_category": {
                    "type": "string",
                    "enum": CATEGORIES,
                    "description": "The single best-fitting category.",
                },
                "secondary_categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": CATEGORIES},
                    "description": "Zero or more additional categories that also clearly apply.",
                },
                "classification_confidence": {
                    "type": "number",
                    "description": "Confidence in the primary_category choice, from 0.0 to 1.0.",
                },
                "reasoning": {
                    "type": "string",
                    "description": "One or two sentences explaining the choice, for human audit.",
                },
            },
            "required": [
                "primary_category",
                "secondary_categories",
                "classification_confidence",
                "reasoning",
            ],
        },
    },
}
```

(Note: no `minimum`/`maximum` keywords — Ollama's client silently strips them, per the Global
Constraints. The `0.0 to 1.0` guidance lives in `description` instead, same information, honestly
represented.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/classification/test_prompt.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Write the failing client tests**

Replace `tests/classification/test_client.py` in full:

```python
# tests/classification/test_client.py
import ollama
import pytest

from src.classification.client import (
    ClassificationError,
    ClassificationResult,
    classify_item,
    parse_classification_response,
)


class _FakeOllamaClient:
    def __init__(self, response=None, exception=None, fail_times=0):
        self._response = response
        self._exception = exception
        self._fail_times = fail_times
        self.calls = 0
        self.last_kwargs: dict | None = None

    async def chat(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self.calls <= self._fail_times:
            raise RuntimeError("simulated transient failure")
        if self._exception is not None:
            raise self._exception
        return self._response


def _valid_response() -> ollama.ChatResponse:
    return ollama.ChatResponse(
        model="test-model",
        message=ollama.Message(
            role="assistant",
            tool_calls=[
                ollama.Message.ToolCall(
                    function=ollama.Message.ToolCall.Function(
                        name="classify_news_item",
                        arguments={
                            "primary_category": "MILITAIRE",
                            "secondary_categories": ["ACCIDENT_INCIDENT"],
                            "classification_confidence": 0.85,
                            "reasoning": "Accident impliquant un appareil militaire.",
                        },
                    )
                )
            ],
        ),
        done=True,
    )


def test_parse_classification_response_extracts_the_tool_call():
    result = parse_classification_response(_valid_response())

    assert result == ClassificationResult(
        primary_category="MILITAIRE",
        secondary_categories=["ACCIDENT_INCIDENT"],
        classification_confidence=0.85,
        reasoning="Accident impliquant un appareil militaire.",
    )


def test_parse_classification_response_rejects_invalid_category():
    response = ollama.ChatResponse(
        model="test-model",
        message=ollama.Message(
            role="assistant",
            tool_calls=[
                ollama.Message.ToolCall(
                    function=ollama.Message.ToolCall.Function(
                        name="classify_news_item",
                        arguments={
                            "primary_category": "NOT_A_REAL_CATEGORY",
                            "secondary_categories": [],
                            "classification_confidence": 0.5,
                            "reasoning": "test",
                        },
                    )
                )
            ],
        ),
        done=True,
    )

    with pytest.raises(ValueError):
        parse_classification_response(response)


def test_parse_classification_response_raises_when_no_tool_call():
    response = ollama.ChatResponse(
        model="test-model",
        message=ollama.Message(role="assistant", content="I won't call a tool."),
        done=True,
    )

    with pytest.raises(ValueError):
        parse_classification_response(response)


@pytest.mark.asyncio
async def test_classify_item_returns_result_on_first_success():
    client = _FakeOllamaClient(response=_valid_response())

    result = await classify_item("Some title", "Some text", client=client)

    assert result.primary_category == "MILITAIRE"
    assert client.calls == 1


@pytest.mark.asyncio
async def test_classify_item_retries_once_then_succeeds():
    client = _FakeOllamaClient(response=_valid_response(), fail_times=1)

    result = await classify_item("Some title", "Some text", client=client)

    assert result.primary_category == "MILITAIRE"
    assert client.calls == 2


@pytest.mark.asyncio
async def test_classify_item_raises_classification_error_after_max_attempts():
    client = _FakeOllamaClient(fail_times=2)

    with pytest.raises(ClassificationError):
        await classify_item("Some title", "Some text", client=client)

    assert client.calls == 2


@pytest.mark.asyncio
async def test_classify_item_truncates_long_article_text():
    client = _FakeOllamaClient(response=_valid_response())
    long_text = "x" * 10_000

    await classify_item("Some title", long_text, client=client)

    sent_message = client.last_kwargs["messages"][-1]["content"]
    assert "x" * 4000 in sent_message
    assert "x" * 4001 not in sent_message


@pytest.mark.asyncio
async def test_classify_item_includes_examples_block_when_provided():
    client = _FakeOllamaClient(response=_valid_response())

    await classify_item(
        "Some title",
        "Some text",
        examples="- Item classé COMMERCIAL par le modèle ; retour humain : hors périmètre Touch-Go.",
        client=client,
    )

    sent_message = client.last_kwargs["messages"][-1]["content"]
    assert "<exemples_feedback>" in sent_message
    assert "hors périmètre Touch-Go" in sent_message


@pytest.mark.asyncio
async def test_classify_item_omits_examples_block_when_not_provided():
    client = _FakeOllamaClient(response=_valid_response())

    await classify_item("Some title", "Some text", client=client)

    sent_message = client.last_kwargs["messages"][-1]["content"]
    assert "<exemples_feedback>" not in sent_message


@pytest.mark.asyncio
async def test_classify_item_sends_system_prompt_as_first_message():
    client = _FakeOllamaClient(response=_valid_response())

    await classify_item("Some title", "Some text", client=client)

    messages = client.last_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `.venv/bin/pytest tests/classification/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError` or `ImportError`-adjacent failures, since `client.py` still
imports `anthropic` and exposes an `anthropic.AsyncAnthropic`-shaped `classify_item`; more
precisely, `_FakeOllamaClient.chat` is never called because `classify_item` still calls
`active_client.messages.create(...)`, so every test fails with `AttributeError: 'NoneType' object
has no attribute 'messages'`-style errors from `_FakeOllamaClient` not having a `.messages`
attribute.

- [ ] **Step 7: Update `classify_item` and `parse_classification_response`**

Replace `src/classification/client.py` in full:

```python
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
                secondary = [c for c in data.get("secondary_categories", []) if c in CATEGORIES]
                return ClassificationResult(
                    primary_category=primary,
                    secondary_categories=secondary,
                    classification_confidence=float(data.get("classification_confidence", 0.0)),
                    reasoning=str(data.get("reasoning", "")),
                )
    raise ValueError("no tool call named classify_news_item in Ollama response")


async def classify_item(
    title: str,
    text: str,
    examples: str = "",
    client: ollama.AsyncClient | None = None,
) -> ClassificationResult:
    active_client = client or ollama.AsyncClient(host=get_settings().ollama_host)
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
```

- [ ] **Step 8: Run test to verify it passes**

Run: `.venv/bin/pytest tests/classification/test_client.py -v`
Expected: PASS (9 tests)

- [ ] **Step 9: Update `src/classification/job.py`**

The current top of the file reads:

```python
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session
```

and further down:

```python
    async with anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key) as client:
```

Replace `import anthropic` with `import ollama`, and replace the `async with` line with:

```python
    async with ollama.AsyncClient(host=settings.ollama_host) as client:
```

Nothing else in the file changes — the per-item try/except isolation, the bookkeeping, the
success path are all untouched.

- [ ] **Step 10: Run the classification test suite and the full suite**

Run: `.venv/bin/pytest tests/classification/ -v`
Expected: PASS (every test in `tests/classification/` — the job tests never construct a real
client, since every test monkeypatches `job_module.classify_item`, so they need no code changes
themselves, but must still pass now that `job.py` imports `ollama` instead of `anthropic`).

Run: `.venv/bin/pytest -v`
Expected: PASS (every test in the whole suite, no regressions elsewhere).

- [ ] **Step 11: Commit**

```bash
git add src/classification/prompt.py src/classification/client.py src/classification/job.py tests/classification/test_prompt.py tests/classification/test_client.py
git commit -m "feat: switch classification from Anthropic to a local Ollama model"
```

---

### Task 3: Scoring — schéma d'outil, client, et job Ollama

**Files:**
- Modify: `src/scoring/prompt.py`
- Modify: `src/scoring/client.py`
- Modify: `src/scoring/job.py`
- Test: `tests/scoring/test_prompt.py`
- Test: `tests/scoring/test_client.py`

**Interfaces:**
- Consumes: `Settings.ollama_host`/`ollama_model` (Task 1).
- Produces: `SCORE_TOOL` reshaped to Ollama's function-calling format.
  `score_item(title: str, text: str, source_type: str, examples: str = "", client:
  ollama.AsyncClient | None = None) -> ScoringResult` — same signature as before, `client` type
  changes from `anthropic.AsyncAnthropic | None` to `ollama.AsyncClient | None`.
  `parse_scoring_response(response) -> ScoringResult` — same signature, now reads Ollama's
  response shape.

This task mirrors Task 2 exactly, adapted for scoring's extra `source_type` parameter and its own
tool/response shape — read `src/classification/client.py` and `src/classification/prompt.py` on
this worktree's current HEAD (after Task 2) for the pattern this task reproduces.

- [ ] **Step 1: Write the failing prompt test**

In `tests/scoring/test_prompt.py`, replace the last test function
(`test_score_tool_schema_has_required_fields`) — everything above it in the file is unchanged:

```python
def test_score_tool_schema_has_required_fields():
    assert SCORE_TOOL["function"]["name"] == "score_news_item"
    properties = SCORE_TOOL["function"]["parameters"]["properties"]
    assert set(properties) == {
        "touchgo_interest",
        "event_importance",
        "source_confidence",
        "urgency",
        "priority",
        "reasoning",
    }
    assert properties["priority"]["enum"] == PRIORITIES
    for dimension in ["touchgo_interest", "event_importance", "source_confidence", "urgency"]:
        assert "0 to 10" in properties[dimension]["description"]
    required = SCORE_TOOL["function"]["parameters"]["required"]
    assert set(required) == {
        "touchgo_interest",
        "event_importance",
        "source_confidence",
        "urgency",
        "priority",
        "reasoning",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/scoring/test_prompt.py -v`
Expected: FAIL with `KeyError: 'function'` (the current `SCORE_TOOL` still has a top-level
`"name"` key).

- [ ] **Step 3: Update `SCORE_TOOL`**

In `src/scoring/prompt.py`, `SYSTEM_PROMPT` is unchanged — only `SCORE_TOOL` (the last block in
the file) changes. Replace it:

```python
SCORE_TOOL = {
    "type": "function",
    "function": {
        "name": "score_news_item",
        "description": (
            "Score an aviation news item on four independent 0-10 dimensions and assign a treatment "
            "priority, per the system prompt's rules."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "touchgo_interest": {
                    "type": "integer",
                    "description": (
                        "How much this interests the Touch-Go community specifically, "
                        "from 0 to 10."
                    ),
                },
                "event_importance": {
                    "type": "integer",
                    "description": "The objective importance of the event itself, from 0 to 10.",
                },
                "source_confidence": {
                    "type": "integer",
                    "description": (
                        "How reliable this information is, given the source type and content, "
                        "from 0 to 10."
                    ),
                },
                "urgency": {
                    "type": "integer",
                    "description": "How time-sensitive this news is, from 0 to 10.",
                },
                "priority": {
                    "type": "string",
                    "enum": PRIORITIES,
                    "description": "Overall treatment priority: A (high), B (review), or C (low but kept).",
                },
                "reasoning": {
                    "type": "string",
                    "description": "One or two sentences explaining the scores, for human audit.",
                },
            },
            "required": [
                "touchgo_interest",
                "event_importance",
                "source_confidence",
                "urgency",
                "priority",
                "reasoning",
            ],
        },
    },
}
```

(Same reasoning as Task 2: no `minimum`/`maximum` keywords, the `0 to 10` guidance lives in
`description`. The client-side range validation in `parse_scoring_response`, added after Sprint
4's final review, is unaffected and still enforces this at the app level regardless of what the
model actually returns.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/scoring/test_prompt.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Write the failing client tests**

Replace `tests/scoring/test_client.py` in full:

```python
import ollama
import pytest

from src.scoring.client import (
    ScoringError,
    ScoringResult,
    parse_scoring_response,
    score_item,
)


class _FakeOllamaClient:
    def __init__(self, response=None, exception=None, fail_times=0):
        self._response = response
        self._exception = exception
        self._fail_times = fail_times
        self.calls = 0
        self.last_kwargs: dict | None = None

    async def chat(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self.calls <= self._fail_times:
            raise RuntimeError("simulated transient failure")
        if self._exception is not None:
            raise self._exception
        return self._response


def _valid_response() -> ollama.ChatResponse:
    return ollama.ChatResponse(
        model="test-model",
        message=ollama.Message(
            role="assistant",
            tool_calls=[
                ollama.Message.ToolCall(
                    function=ollama.Message.ToolCall.Function(
                        name="score_news_item",
                        arguments={
                            "touchgo_interest": 10,
                            "event_importance": 9,
                            "source_confidence": 3,
                            "urgency": 6,
                            "priority": "A",
                            "reasoning": "Sujet militaire majeur signalé par une source communautaire.",
                        },
                    )
                )
            ],
        ),
        done=True,
    )


def test_parse_scoring_response_extracts_the_tool_call():
    result = parse_scoring_response(_valid_response())

    assert result == ScoringResult(
        touchgo_interest=10,
        event_importance=9,
        source_confidence=3,
        urgency=6,
        priority="A",
        reasoning="Sujet militaire majeur signalé par une source communautaire.",
    )


def test_parse_scoring_response_rejects_invalid_priority():
    response = ollama.ChatResponse(
        model="test-model",
        message=ollama.Message(
            role="assistant",
            tool_calls=[
                ollama.Message.ToolCall(
                    function=ollama.Message.ToolCall.Function(
                        name="score_news_item",
                        arguments={
                            "touchgo_interest": 5,
                            "event_importance": 5,
                            "source_confidence": 5,
                            "urgency": 5,
                            "priority": "Z",
                            "reasoning": "test",
                        },
                    )
                )
            ],
        ),
        done=True,
    )

    with pytest.raises(ValueError):
        parse_scoring_response(response)


def test_parse_scoring_response_rejects_missing_numeric_field():
    response = ollama.ChatResponse(
        model="test-model",
        message=ollama.Message(
            role="assistant",
            tool_calls=[
                ollama.Message.ToolCall(
                    function=ollama.Message.ToolCall.Function(
                        name="score_news_item",
                        arguments={
                            "event_importance": 5,
                            "source_confidence": 5,
                            "urgency": 5,
                            "priority": "A",
                            "reasoning": "test",
                        },
                    )
                )
            ],
        ),
        done=True,
    )

    with pytest.raises(ValueError):
        parse_scoring_response(response)


def test_parse_scoring_response_rejects_out_of_range_score():
    response = ollama.ChatResponse(
        model="test-model",
        message=ollama.Message(
            role="assistant",
            tool_calls=[
                ollama.Message.ToolCall(
                    function=ollama.Message.ToolCall.Function(
                        name="score_news_item",
                        arguments={
                            "touchgo_interest": 99,
                            "event_importance": 5,
                            "source_confidence": 5,
                            "urgency": 5,
                            "priority": "A",
                            "reasoning": "test",
                        },
                    )
                )
            ],
        ),
        done=True,
    )

    with pytest.raises(ValueError):
        parse_scoring_response(response)


def test_parse_scoring_response_raises_when_no_tool_call():
    response = ollama.ChatResponse(
        model="test-model",
        message=ollama.Message(role="assistant", content="I won't call a tool."),
        done=True,
    )

    with pytest.raises(ValueError):
        parse_scoring_response(response)


@pytest.mark.asyncio
async def test_score_item_returns_result_on_first_success():
    client = _FakeOllamaClient(response=_valid_response())

    result = await score_item("Some title", "Some text", "community", client=client)

    assert result.priority == "A"
    assert client.calls == 1


@pytest.mark.asyncio
async def test_score_item_retries_once_then_succeeds():
    client = _FakeOllamaClient(response=_valid_response(), fail_times=1)

    result = await score_item("Some title", "Some text", "community", client=client)

    assert result.priority == "A"
    assert client.calls == 2


@pytest.mark.asyncio
async def test_score_item_raises_scoring_error_after_max_attempts():
    client = _FakeOllamaClient(fail_times=2)

    with pytest.raises(ScoringError):
        await score_item("Some title", "Some text", "community", client=client)

    assert client.calls == 2


@pytest.mark.asyncio
async def test_score_item_truncates_long_article_text():
    client = _FakeOllamaClient(response=_valid_response())
    long_text = "x" * 10_000

    await score_item("Some title", long_text, "community", client=client)

    sent_message = client.last_kwargs["messages"][-1]["content"]
    assert "x" * 4000 in sent_message
    assert "x" * 4001 not in sent_message


@pytest.mark.asyncio
async def test_score_item_includes_source_type_in_the_prompt():
    client = _FakeOllamaClient(response=_valid_response())

    await score_item("Some title", "Some text", "community", client=client)

    sent_message = client.last_kwargs["messages"][-1]["content"]
    assert "community" in sent_message


@pytest.mark.asyncio
async def test_score_item_includes_examples_block_when_provided():
    client = _FakeOllamaClient(response=_valid_response())

    await score_item(
        "Some title",
        "Some text",
        "community",
        examples="- Item priorité C donnée par le modèle ; retour humain : 🔥 (probablement sous-évalué).",
        client=client,
    )

    sent_message = client.last_kwargs["messages"][-1]["content"]
    assert "<exemples_feedback>" in sent_message
    assert "probablement sous-évalué" in sent_message


@pytest.mark.asyncio
async def test_score_item_omits_examples_block_when_not_provided():
    client = _FakeOllamaClient(response=_valid_response())

    await score_item("Some title", "Some text", "community", client=client)

    sent_message = client.last_kwargs["messages"][-1]["content"]
    assert "<exemples_feedback>" not in sent_message


@pytest.mark.asyncio
async def test_score_item_sends_system_prompt_as_first_message():
    client = _FakeOllamaClient(response=_valid_response())

    await score_item("Some title", "Some text", "community", client=client)

    messages = client.last_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `.venv/bin/pytest tests/scoring/test_client.py -v`
Expected: FAIL — `_FakeOllamaClient` has no `.messages` attribute, but the current `score_item`
still calls `active_client.messages.create(...)`.

- [ ] **Step 7: Update `score_item` and `parse_scoring_response`**

Replace `src/scoring/client.py` in full:

```python
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
    active_client = client or ollama.AsyncClient(host=get_settings().ollama_host)
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
```

- [ ] **Step 8: Run test to verify it passes**

Run: `.venv/bin/pytest tests/scoring/test_client.py -v`
Expected: PASS (12 tests)

- [ ] **Step 9: Update `src/scoring/job.py`**

The current top of the file reads:

```python
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session
```

and further down:

```python
    async with anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key) as client:
```

Replace `import anthropic` with `import ollama`, and replace the `async with` line with:

```python
    async with ollama.AsyncClient(host=settings.ollama_host) as client:
```

Nothing else in the file changes.

- [ ] **Step 10: Run the scoring test suite and the full suite**

Run: `.venv/bin/pytest tests/scoring/ -v`
Expected: PASS (every test in `tests/scoring/` — same reasoning as Task 2 Step 10: the job tests
monkeypatch `job_module.score_item`, so they need no changes themselves).

Run: `.venv/bin/pytest -v`
Expected: PASS (every test in the whole suite, no regressions elsewhere).

- [ ] **Step 11: Commit**

```bash
git add src/scoring/prompt.py src/scoring/client.py src/scoring/job.py tests/scoring/test_prompt.py tests/scoring/test_client.py
git commit -m "feat: switch scoring from Anthropic to a local Ollama model"
```

---

## Manual verification (not automated)

After Task 3, with Ollama installed and running, and the model pulled:

```bash
ollama pull qwen2.5:7b-instruct
docker compose up -d
.venv/bin/alembic upgrade head
.venv/bin/uvicorn src.api.main:app --reload
```

- Confirm `grep -rn "anthropic" src/ pyproject.toml` returns nothing — the dependency and every
  reference are fully gone, not just unused.
- Wait for at least one classification and one scoring cycle (or temporarily lower
  `CLASSIFICATION_INTERVAL_MINUTES`/`SCORING_INTERVAL_MINUTES` in `.env` for a quick manual
  check), then `curl http://localhost:8000/items` and confirm items now show real
  `primary_category`/`touchgo_interest`/`event_importance`/`source_confidence`/`urgency`/
  `priority` values (not `null`) — produced by the local model, not Claude.
- Per the design doc's §6 "vérification manuelle renforcée": read a handful of real classified
  and scored items (via `/items` or the review page at `/`) and judge by eye whether
  `qwen2.5:7b-instruct`'s category choices and scores look like reasonable editorial judgment
  given the article title/text — not a pass/fail automated check, but the step that tells you
  whether this replacement is actually usable day-to-day, versus merely "runs without crashing."
  If the quality reads as poor, the design doc names `llama3.1:8b` as the next model to try before
  reconsidering the approach (design §2) — that's a config-only change (`OLLAMA_MODEL` in `.env`),
  not a code change.
- Confirm a genuinely malformed/missing tool call is handled gracefully: temporarily point
  `OLLAMA_MODEL` at a model that doesn't support tool-calling (or stop the Ollama service
  entirely) and confirm the classification/scoring jobs log warnings and leave items
  un-classified/un-scored rather than crashing the scheduler — this exercises the "no tool_choice
  forcing" risk named in the design (§3) against the real failure mode, not just the fake-client
  unit tests.
