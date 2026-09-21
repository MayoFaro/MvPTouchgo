# Touch-Go News — Sprint 3 (Classification) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every collected `NewsItem` a `primary_category` (one of the 7 editorial categories),
optional `secondary_categories`, and a `classification_confidence`, assigned by Claude Haiku via a
scheduled job fully decoupled from collection — and make that classification visible through the
existing read-only API.

**Architecture:** A new `src/classification/` package holds the editorial prompt + tool schema
(`prompt.py`), the LLM call with retry/parsing logic behind a swappable interface
(`client.py`), and the batch-selection job (`job.py`). `src/scheduler.py` gains a second,
independent APScheduler job that periodically classifies items where `primary_category IS NULL`.
No collector, runner, or normalization code changes — classification only reads/writes columns
that already exist on `NewsItem` since Sprint 1's schema.

**Tech Stack:** Same as Sprints 1-2, plus the `anthropic` Python SDK (Claude Messages API, tool
use for structured output).

**Spec:** [`docs/superpowers/specs/2026-09-21-touchgo-news-sprint3-classification-design.md`](../specs/2026-09-21-touchgo-news-sprint3-classification-design.md) (implements Sprint 3 of [`SPEC.md`](../../../SPEC.md), sections 4, 5, 6, 18, 30, 34).

## Global Constraints

- Collecte et classification restent séparées (SPEC.md section 30, design doc section 2) —
  classification runs as its own scheduled job, never inline with collection; a slow or failing
  LLM call must never affect a collection cycle.
- Aucune catégorie forcée par défaut en cas d'échec technique (design doc section 6) — a
  classification failure after retries leaves `primary_category = NULL` for a retry next cycle;
  never silently defaults to `DIVERS` or any other value.
- `DIVERS` is the model's own considered choice when no other category clearly fits (SPEC.md
  section 5) — it is a valid LLM output, never a fallback the code injects.
- Per-item error isolation in the classification job (design doc section 6) — one item's failure
  must never stop the rest of the batch.
- No schema migration in this sprint — `primary_category`, `secondary_categories`,
  `classification_confidence`, `model_reason` already exist on `NewsItem` (Sprint 1).
- No real network calls in tests — the LLM client is always injectable/mockable, following the
  same pattern collectors already use for `http_client`.

---

### Task 1: Dependency and configuration

**Files:**
- Modify: `pyproject.toml` (add `anthropic` to `dependencies`)
- Modify: `src/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings.anthropic_api_key: str`, `Settings.classification_batch_size: int` (default
  20), `Settings.classification_interval_minutes: int` (default 3).

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add this line to the `dependencies` list (after `"pyyaml>=6.0",`):

```toml
    "anthropic>=0.40",
```

- [ ] **Step 2: Write the failing test**

Add to `tests/test_config.py` (it already has `test_settings_read_from_env` and
`test_settings_have_defaults` — extend both rather than adding new test functions, since these
fields belong to the same `Settings` object already under test):

```python
def test_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host:5432/db")
    monkeypatch.setenv("SOURCES_CONFIG_PATH", "config/sources.yaml")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("CLASSIFICATION_BATCH_SIZE", "5")
    monkeypatch.setenv("CLASSIFICATION_INTERVAL_MINUTES", "10")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"
    assert settings.sources_config_path == "config/sources.yaml"
    assert settings.anthropic_api_key == "sk-test-key"
    assert settings.classification_batch_size == 5
    assert settings.classification_interval_minutes == 10


def test_settings_have_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SOURCES_CONFIG_PATH", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLASSIFICATION_BATCH_SIZE", raising=False)
    monkeypatch.delenv("CLASSIFICATION_INTERVAL_MINUTES", raising=False)
    settings = Settings(_env_file=None)
    assert "touchgo_news" in settings.database_url
    assert settings.sources_config_path == "config/sources.yaml"
    assert settings.anthropic_api_key == ""
    assert settings.classification_batch_size == 20
    assert settings.classification_interval_minutes == 3
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError` or a pydantic validation error, since `Settings` has no
`anthropic_api_key` field yet.

- [ ] **Step 4: Update `Settings`**

In `src/config.py`, replace the class body:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://touchgo:touchgo@localhost:5432/touchgo_news"
    sources_config_path: str = "config/sources.yaml"
    anthropic_api_key: str = ""
    classification_batch_size: int = 20
    classification_interval_minutes: int = 3
```

- [ ] **Step 5: Install the new dependency and run the test**

```bash
.venv/bin/pip install -e ".[dev]"
```

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Update `.env.example`**

```
DATABASE_URL=postgresql+psycopg://touchgo:touchgo@localhost:5432/touchgo_news
SOURCES_CONFIG_PATH=config/sources.yaml
ANTHROPIC_API_KEY=
CLASSIFICATION_BATCH_SIZE=20
CLASSIFICATION_INTERVAL_MINUTES=3
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/config.py tests/test_config.py .env.example
git commit -m "feat: add anthropic dependency and classification settings"
```

---

### Task 2: Editorial prompt and tool schema

**Files:**
- Create: `src/classification/__init__.py`
- Create: `src/classification/prompt.py`
- Test: `tests/classification/test_prompt.py`

**Interfaces:**
- Produces: `CATEGORIES: list[str]` (the 7 category names), `SYSTEM_PROMPT: str`,
  `CLASSIFY_TOOL: dict` (Claude tool-use schema).

- [ ] **Step 1: Write the failing test**

```python
# tests/classification/test_prompt.py
from src.classification.prompt import CATEGORIES, CLASSIFY_TOOL, SYSTEM_PROMPT


def test_categories_has_exactly_the_seven_spec_values():
    assert CATEGORIES == [
        "COMMERCIAL",
        "EMPLOI",
        "MILITAIRE",
        "REGLEMENTATION",
        "MEETING",
        "ACCIDENT_INCIDENT",
        "DIVERS",
    ]


def test_system_prompt_mentions_every_category():
    for category in CATEGORIES:
        assert category in SYSTEM_PROMPT


def test_system_prompt_states_the_divers_never_reject_rule():
    assert "DIVERS" in SYSTEM_PROMPT
    assert "JAMAIS" in SYSTEM_PROMPT.upper() or "JAMAIS" in SYSTEM_PROMPT


def test_classify_tool_schema_has_required_fields():
    assert CLASSIFY_TOOL["name"] == "classify_news_item"
    properties = CLASSIFY_TOOL["input_schema"]["properties"]
    assert set(properties) == {
        "primary_category",
        "secondary_categories",
        "classification_confidence",
        "reasoning",
    }
    assert properties["primary_category"]["enum"] == CATEGORIES
    assert properties["secondary_categories"]["items"]["enum"] == CATEGORIES
    required = CLASSIFY_TOOL["input_schema"]["required"]
    assert set(required) == {
        "primary_category",
        "secondary_categories",
        "classification_confidence",
        "reasoning",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/classification/test_prompt.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.classification'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/classification/__init__.py
```

(empty file)

```python
# src/classification/prompt.py
CATEGORIES = [
    "COMMERCIAL",
    "EMPLOI",
    "MILITAIRE",
    "REGLEMENTATION",
    "MEETING",
    "ACCIDENT_INCIDENT",
    "DIVERS",
]

SYSTEM_PROMPT = """Tu es l'assistant éditorial de Touch-Go, une communauté aéronautique \
professionnelle très avertie (pas un média grand public). Ta tâche : classer une actualité \
aéronautique dans exactement une catégorie principale, et éventuellement une ou plusieurs \
catégories secondaires, parmi ces sept catégories :

COMMERCIAL — Aviation commerciale. Filtrage strict. À conserver : disparition ou faillite d'une \
compagnie significative, fusion ou acquisition importante, restructuration majeure, changement \
important de flotte, nouvel avion, nouvelle variante majeure, certification importante, problème \
industriel sérieux, changement stratégique important chez un grand constructeur (Airbus, Boeing, \
ATR, Embraer...), rupture majeure de chaîne d'approvisionnement. À rejeter généralement : simple \
ouverture de ligne, livraison individuelle d'un avion, petite commande routinière, communication \
corporate sans enjeu réel — sauf si l'ampleur de l'événement modifie réellement le marché.

EMPLOI — Marché de l'emploi aéronautique. Doit être surveillé assez largement. À conserver : \
campagnes de recrutement (pilotes, PNC, maintenance), gels d'embauche, licenciements, réduction \
d'effectifs, pénurie de personnel, changement significatif des conditions de recrutement, \
tendances du marché de l'emploi aéronautique. Priorité géographique : France et Europe élevée, \
reste du monde moyenne — sauf si ça concerne une grande compagnie ou une tendance structurante.

MILITAIRE — Aviation militaire. C'est l'une des catégories les plus importantes pour Touch-Go. \
Couverture mondiale, y compris les sources russes et chinoises. À conserver largement : nouveaux \
appareils, programmes, prototypes, évolutions de flotte, modernisations, armements, drones, \
essais, exercices, opérations, doctrine, organisation des forces, commandes, exportations, \
production, difficultés industrielles, accidents militaires, nouveaux capteurs, guerre \
électronique, systèmes de mission, programmes futurs.

REGLEMENTATION — Filtrage strict. Ne conserver que les changements réglementaires ayant un impact \
réel : licences, médical, âge des pilotes, temps de vol et de service (FTL), formation, règles \
d'exploitation, espace aérien, certification, navigation, obligations opérationnelles. À rejeter \
généralement : mise à jour administrative mineure, modification technique sans conséquence \
pratique réelle, consultation routinière.

MEETING — Grands meetings et salons aéronautiques, manifestations aériennes importantes, grands \
événements militaires, grands événements français ou européens proches, événements internationaux \
exceptionnels.

ACCIDENT_INCIDENT — Le seuil dépend fortement de la zone géographique. Le système doit être plus \
permissif pour la France : en France, un incident moyen doit déjà remonter, un incident important \
ou majeur est toujours prioritaire. À l'étranger : un incident moyen est seulement à examiner, \
important et majeur restent prioritaires. Un accident militaire reçoit aussi la catégorie \
secondaire MILITAIRE.

DIVERS — Catégorie de sécurité. Elle ne doit JAMAIS être considérée comme une catégorie de faible \
valeur. Elle sert à récupérer les sujets qui ne correspondent clairement à aucune des six autres \
catégories, les sujets dont la classification est incertaine, ou les thèmes émergents non prévus \
par les six autres catégories. Règle fondamentale : une actualité ne doit JAMAIS être laissée sans \
catégorie principale faute de correspondance évidente — DIVERS existe précisément pour ce cas, et \
c'est un choix légitime, pas un échec de classification.

Le public de Touch-Go est une communauté professionnelle ou très avertie, pas un lectorat grand \
public : privilégie l'impact professionnel, l'impact opérationnel, l'évolution du secteur, \
l'emploi, la défense, la réglementation importante, les incidents et accidents significatifs.

Si une actualité relève clairement de deux catégories à la fois (par exemple un accident \
militaire), choisis la plus spécifique comme catégorie principale et ajoute l'autre en catégorie \
secondaire plutôt que de forcer un choix arbitraire."""

CLASSIFY_TOOL = {
    "name": "classify_news_item",
    "description": (
        "Classify an aviation news item into Touch-Go's editorial categories, per the system "
        "prompt's rules."
    ),
    "input_schema": {
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
                "minimum": 0.0,
                "maximum": 1.0,
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
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/classification/test_prompt.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/classification/__init__.py src/classification/prompt.py tests/classification/test_prompt.py
git commit -m "feat: add editorial classification prompt and tool schema"
```

---

### Task 3: Classification client

**Files:**
- Create: `src/classification/client.py`
- Test: `tests/classification/test_client.py`

**Interfaces:**
- Consumes: `CATEGORIES`, `SYSTEM_PROMPT`, `CLASSIFY_TOOL` (Task 2), `get_settings` (existing).
- Produces: `ClassificationResult` (pydantic model: `primary_category: str,
  secondary_categories: list[str], classification_confidence: float, reasoning: str`),
  `ClassificationError` (exception), `parse_classification_response(response) ->
  ClassificationResult` (pure function, unit-testable without network),
  `async def classify_item(title: str, text: str, client: anthropic.AsyncAnthropic | None = None)
  -> ClassificationResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/classification/test_client.py
import pytest

from src.classification.client import (
    ClassificationError,
    ClassificationResult,
    classify_item,
    parse_classification_response,
)


class _FakeToolUseBlock:
    def __init__(self, name: str, input_data: dict):
        self.type = "tool_use"
        self.name = name
        self.input = input_data


class _FakeResponse:
    def __init__(self, content: list):
        self.content = content


class _FakeMessages:
    def __init__(self, response=None, exception=None, fail_times=0):
        self._response = response
        self._exception = exception
        self._fail_times = fail_times
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls <= self._fail_times:
            raise RuntimeError("simulated transient failure")
        if self._exception is not None:
            raise self._exception
        return self._response


class _FakeAnthropicClient:
    def __init__(self, response=None, exception=None, fail_times=0):
        self.messages = _FakeMessages(response=response, exception=exception, fail_times=fail_times)


def _valid_response() -> _FakeResponse:
    return _FakeResponse(
        [
            _FakeToolUseBlock(
                "classify_news_item",
                {
                    "primary_category": "MILITAIRE",
                    "secondary_categories": ["ACCIDENT_INCIDENT"],
                    "classification_confidence": 0.85,
                    "reasoning": "Accident impliquant un appareil militaire.",
                },
            )
        ]
    )


def test_parse_classification_response_extracts_the_tool_use_block():
    result = parse_classification_response(_valid_response())

    assert result == ClassificationResult(
        primary_category="MILITAIRE",
        secondary_categories=["ACCIDENT_INCIDENT"],
        classification_confidence=0.85,
        reasoning="Accident impliquant un appareil militaire.",
    )


def test_parse_classification_response_rejects_invalid_category():
    response = _FakeResponse(
        [
            _FakeToolUseBlock(
                "classify_news_item",
                {
                    "primary_category": "NOT_A_REAL_CATEGORY",
                    "secondary_categories": [],
                    "classification_confidence": 0.5,
                    "reasoning": "test",
                },
            )
        ]
    )

    with pytest.raises(ValueError):
        parse_classification_response(response)


def test_parse_classification_response_raises_when_no_tool_use_block():
    with pytest.raises(ValueError):
        parse_classification_response(_FakeResponse([]))


@pytest.mark.asyncio
async def test_classify_item_returns_result_on_first_success():
    client = _FakeAnthropicClient(response=_valid_response())

    result = await classify_item("Some title", "Some text", client=client)

    assert result.primary_category == "MILITAIRE"
    assert client.messages.calls == 1


@pytest.mark.asyncio
async def test_classify_item_retries_once_then_succeeds():
    client = _FakeAnthropicClient(response=_valid_response(), fail_times=1)

    result = await classify_item("Some title", "Some text", client=client)

    assert result.primary_category == "MILITAIRE"
    assert client.messages.calls == 2


@pytest.mark.asyncio
async def test_classify_item_raises_classification_error_after_max_attempts():
    client = _FakeAnthropicClient(fail_times=2)

    with pytest.raises(ClassificationError):
        await classify_item("Some title", "Some text", client=client)

    assert client.messages.calls == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/classification/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.classification.client'`

- [ ] **Step 3: Write minimal implementation**

```python
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
    client: anthropic.AsyncAnthropic | None = None,
) -> ClassificationResult:
    active_client = client or anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    user_message = f"Titre : {title}\n\nTexte : {text}"

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/classification/test_client.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/classification/client.py tests/classification/test_client.py
git commit -m "feat: add classification client with tool-use parsing and retries"
```

---

### Task 4: Classification job

**Files:**
- Create: `src/classification/job.py`
- Test: `tests/classification/test_job.py`

**Interfaces:**
- Consumes: `NewsItem` (existing), `classify_item`, `ClassificationError`,
  `ClassificationResult` (Task 3).
- Produces: `ClassificationJobResult` (dataclass: `classified: int, failed: int`),
  `async def classify_pending_items(session: Session, batch_size: int) -> ClassificationJobResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/classification/test_job.py
import pytest

import src.classification.job as job_module
from src.classification.client import ClassificationError, ClassificationResult
from src.classification.job import classify_pending_items
from src.db.models import NewsItem


def _pending_item(db_session, make_source, source_id: str, **overrides) -> NewsItem:
    make_source(source_id=source_id)
    defaults = dict(
        source_id=source_id,
        source_item_id=overrides.pop("source_item_id", "1"),
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Airbus unveils new variant",
        original_text="Body text",
    )
    defaults.update(overrides)
    item = NewsItem(**defaults)
    db_session.add(item)
    db_session.commit()
    return item


@pytest.mark.asyncio
async def test_classify_pending_items_returns_zero_when_nothing_pending(db_session):
    result = await classify_pending_items(db_session, batch_size=10)

    assert result.classified == 0
    assert result.failed == 0


@pytest.mark.asyncio
async def test_classify_pending_items_updates_matched_items(db_session, make_source, monkeypatch):
    item = _pending_item(db_session, make_source, source_id="flightglobal")

    async def fake_classify_item(title, text):
        return ClassificationResult(
            primary_category="MILITAIRE",
            secondary_categories=["ACCIDENT_INCIDENT"],
            classification_confidence=0.9,
            reasoning="test reasoning",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=10)

    assert result.classified == 1
    assert result.failed == 0
    stored = db_session.get(NewsItem, item.id)
    assert stored.primary_category == "MILITAIRE"
    assert stored.secondary_categories == ["ACCIDENT_INCIDENT"]
    assert stored.classification_confidence == 0.9
    assert stored.model_reason == "test reasoning"


@pytest.mark.asyncio
async def test_classify_pending_items_skips_already_classified_items(
    db_session, make_source, monkeypatch
):
    _pending_item(db_session, make_source, source_id="flightglobal", primary_category="COMMERCIAL")

    async def fake_classify_item(title, text):
        raise AssertionError("should not be called for an already-classified item")

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=10)

    assert result.classified == 0
    assert result.failed == 0


@pytest.mark.asyncio
async def test_classify_pending_items_isolates_a_single_item_failure(
    db_session, make_source, monkeypatch
):
    failing_item = _pending_item(
        db_session,
        make_source,
        source_id="flightglobal",
        original_title="Failing item title",
        original_text="Failing item body",
    )
    ok_item = _pending_item(
        db_session,
        make_source,
        source_id="reuters",
        original_title="OK item title",
        original_text="OK item body",
    )

    async def fake_classify_item(title, text):
        if title == "Failing item title":
            raise ClassificationError("boom")
        return ClassificationResult(
            primary_category="DIVERS",
            secondary_categories=[],
            classification_confidence=0.4,
            reasoning="ok",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=10)

    assert result.classified == 1
    assert result.failed == 1
    assert db_session.get(NewsItem, failing_item.id).primary_category is None
    assert db_session.get(NewsItem, ok_item.id).primary_category == "DIVERS"


@pytest.mark.asyncio
async def test_classify_pending_items_respects_batch_size(db_session, make_source, monkeypatch):
    _pending_item(db_session, make_source, source_id="flightglobal", source_item_id="1")
    _pending_item(db_session, make_source, source_id="flightglobal", source_item_id="2")
    _pending_item(db_session, make_source, source_id="flightglobal", source_item_id="3")

    async def fake_classify_item(title, text):
        return ClassificationResult(
            primary_category="DIVERS",
            secondary_categories=[],
            classification_confidence=0.5,
            reasoning="ok",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    result = await classify_pending_items(db_session, batch_size=2)

    assert result.classified == 2
    assert result.failed == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/classification/test_job.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.classification.job'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/classification/job.py
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.classification.client import ClassificationError, classify_item
from src.db.models import NewsItem

logger = logging.getLogger(__name__)


@dataclass
class ClassificationJobResult:
    classified: int
    failed: int


async def classify_pending_items(session: Session, batch_size: int) -> ClassificationJobResult:
    pending = (
        session.execute(
            select(NewsItem)
            .where(NewsItem.primary_category.is_(None))
            .order_by(NewsItem.detected_at.asc())
            .limit(batch_size)
        )
        .scalars()
        .all()
    )

    classified = 0
    failed = 0
    for item in pending:
        try:
            result = await classify_item(item.original_title, item.original_text)
        except ClassificationError:
            logger.exception("Classification failed for item %s", item.id)
            failed += 1
            continue
        item.primary_category = result.primary_category
        item.secondary_categories = result.secondary_categories
        item.classification_confidence = result.classification_confidence
        item.model_reason = result.reasoning
        session.commit()
        classified += 1
    return ClassificationJobResult(classified=classified, failed=failed)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/classification/test_job.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/classification/job.py tests/classification/test_job.py
git commit -m "feat: add classification job selecting and updating pending items"
```

---

### Task 5: Wire the classification job into the scheduler and app startup

**Files:**
- Modify: `src/scheduler.py`
- Modify: `src/api/main.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `classify_pending_items` (Task 4), `get_settings` (existing).
- Produces: `add_classification_job(scheduler: AsyncIOScheduler, session_factory, batch_size: int,
  interval_minutes: int) -> None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_scheduler.py` (it already imports `datetime`, `timedelta`, `timezone`, `Path`,
`httpx`, `pytest`, `respx`, `SourceConfig`, `NewsItem`, `NewsSource`, and has a line
`from src.scheduler import _run_source_job, build_scheduler` — change that existing line to add the
two new names, and add three more import lines above/below it):

```python
import src.classification.job as job_module
import src.scheduler as scheduler_module
from src.classification.client import ClassificationResult
from src.scheduler import _classify_job, _run_source_job, add_classification_job, build_scheduler
```

(this last line replaces the file's existing `from src.scheduler import _run_source_job,
build_scheduler` line entirely — same statement, two more names.)

```python
def test_add_classification_job_registers_a_job_with_the_configured_interval():
    scheduler = build_scheduler([], session_factory=lambda: None)

    add_classification_job(
        scheduler, session_factory=lambda: None, batch_size=20, interval_minutes=3
    )

    job = scheduler.get_job("classification")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 3 * 60
    assert job.next_run_time is not None
    assert job.next_run_time <= datetime.now(timezone.utc) + timedelta(seconds=5)


@pytest.mark.asyncio
async def test_classify_job_runs_a_full_classification_cycle(db_session, make_source, monkeypatch):
    make_source(source_id="flightglobal")
    item = NewsItem(
        source_id="flightglobal",
        source_item_id="1",
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Airbus unveils new variant",
        original_text="Body",
    )
    db_session.add(item)
    db_session.commit()

    async def fake_classify_item(title, text):
        return ClassificationResult(
            primary_category="COMMERCIAL",
            secondary_categories=[],
            classification_confidence=0.7,
            reasoning="ok",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    await _classify_job(session_factory=lambda: db_session, batch_size=10)

    stored = db_session.get(NewsItem, item.id)
    assert stored.primary_category == "COMMERCIAL"


@pytest.mark.asyncio
async def test_classify_job_does_not_raise_on_unexpected_error(db_session, monkeypatch):
    async def broken_classify_pending_items(session, batch_size):
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler_module, "classify_pending_items", broken_classify_pending_items)

    # Must not raise out of the scheduled job.
    await _classify_job(session_factory=lambda: db_session, batch_size=10)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_scheduler.py -v`
Expected: FAIL with `ImportError: cannot import name '_classify_job' from 'src.scheduler'`

- [ ] **Step 3: Update `src/scheduler.py`**

Add this import near the top, alongside the existing ones:

```python
from src.classification.job import classify_pending_items
```

Add these two functions at the end of the file (after `_run_source_job`):

```python
def add_classification_job(
    scheduler: AsyncIOScheduler,
    session_factory,
    batch_size: int,
    interval_minutes: int,
) -> None:
    scheduler.add_job(
        _classify_job,
        "interval",
        minutes=interval_minutes,
        id="classification",
        args=[session_factory, batch_size],
        # Fire once right away instead of waiting a full poll interval.
        next_run_time=datetime.now(timezone.utc),
    )


async def _classify_job(session_factory, batch_size: int) -> None:
    session = session_factory()
    try:
        await classify_pending_items(session, batch_size)
    except Exception:  # noqa: BLE001 - the classification job must never crash the scheduler
        logger.exception("Classification job failed")
    finally:
        session.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_scheduler.py -v`
Expected: PASS (every test in the file — the 4 pre-existing plus the 3 new ones)

- [ ] **Step 5: Wire it into `lifespan`**

In `src/api/main.py`, add this import alongside the existing ones:

```python
from src.scheduler import add_classification_job, build_scheduler
```

(this replaces the current `from src.scheduler import build_scheduler` line — same import
statement, one more name).

Update the `lifespan` function's body: insert the new call right after `scheduler =
build_scheduler(sources, SessionLocal)` and before `scheduler.start()`:

```python
    scheduler = build_scheduler(sources, SessionLocal)
    add_classification_job(
        scheduler,
        SessionLocal,
        batch_size=settings.classification_batch_size,
        interval_minutes=settings.classification_interval_minutes,
    )
    scheduler.start()
```

- [ ] **Step 6: Run the full test suite**

Run: `.venv/bin/pytest -v`
Expected: every test passes, including `tests/api/test_lifespan.py` (unaffected by this change,
but confirms `lifespan` still starts up cleanly with the extra job registered).

- [ ] **Step 7: Commit**

```bash
git add src/scheduler.py src/api/main.py tests/test_scheduler.py
git commit -m "feat: schedule the classification job alongside collection on startup"
```

---

### Task 6: Expose classification (and Sprint 2's duplicate_of) through the API

**Files:**
- Modify: `src/api/schemas.py`
- Modify: `tests/api/test_items.py`

**Interfaces:**
- Produces: no new function — `NewsItemOut` gains fields.

This task closes two related gaps at once: Sprint 3's classification would otherwise be invisible
through the only read path the system has (`GET /items`), and Sprint 2's final review already
flagged the same problem for `duplicate_of` and parked it as a recommendation for "whenever the API
surface is next touched." That's now.

- [ ] **Step 1: Write the failing test**

Modify `tests/api/test_items.py`'s existing `test_items_returns_persisted_items` test — it currently
seeds one item via `save_raw_items` and asserts on `original_title`/`status` only. Add assertions
for the new fields to the same test (don't add a second test — this is the same behavior, more
fields to check):

```python
def test_items_returns_persisted_items(db_session, make_source):
    make_source(source_id="flightglobal")
    save_raw_items(
        db_session,
        "flightglobal",
        [
            RawItem(
                source_item_id="1",
                canonical_url="https://example.com/1",
                original_url="https://example.com/1",
                original_title="Title",
                original_text="Body",
                language="en",
            )
        ],
    )
    stored = db_session.query(NewsItem).filter_by(source_item_id="1").one()
    stored.primary_category = "COMMERCIAL"
    stored.secondary_categories = ["EMPLOI"]
    stored.classification_confidence = 0.75
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        client = TestClient(app)
        response = client.get("/items")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["original_title"] == "Title"
    assert body[0]["status"] == "NEW"
    assert body[0]["primary_category"] == "COMMERCIAL"
    assert body[0]["secondary_categories"] == ["EMPLOI"]
    assert body[0]["classification_confidence"] == 0.75
    assert body[0]["duplicate_of"] is None
```

You'll need `NewsItem` imported in this test file if it isn't already — check the top of
`tests/api/test_items.py` and add `from src.db.models import NewsItem` if missing.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/api/test_items.py -v`
Expected: FAIL — `KeyError: 'primary_category'` (the response JSON doesn't have that key yet).

- [ ] **Step 3: Update `NewsItemOut`**

In `src/api/schemas.py`, replace the class body:

```python
class NewsItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: str
    original_title: str
    original_url: str
    language: str | None
    published_at: datetime | None
    detected_at: datetime
    status: str
    primary_category: str | None
    secondary_categories: list[str] | None
    classification_confidence: float | None
    duplicate_of: int | None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/api/test_items.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/api/schemas.py tests/api/test_items.py
git commit -m "feat: expose classification and duplicate_of fields through GET /items"
```

---

### Task 7: End-to-end integration test — collect, classify, and see it through the API

**Files:**
- Modify: `tests/test_integration_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 1-6, plus the existing collection pipeline from Sprint 1.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_integration_pipeline.py` (it already has `FEED`, imports `httpx`, `pytest`,
`respx`, `TestClient`, `app`, `get_session`, `run_collection`, `SourceConfig`, `build_collector`,
`NewsItem` — add these two more imports and the test function):

```python
import src.classification.job as job_module
from src.classification.client import ClassificationResult
from src.classification.job import classify_pending_items
```

```python
@pytest.mark.asyncio
@respx.mock
async def test_collected_items_get_classified_and_are_visible_via_api(
    db_session, make_source, monkeypatch
):
    make_source(source_id="flightglobal", url="https://example.com/feed")
    config = SourceConfig(
        id="flightglobal",
        name="FlightGlobal",
        type="rss",
        url="https://example.com/feed",
        language="en",
        source_type="press",
        poll_interval_minutes=30,
    )
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=FEED, headers={"content-type": "application/rss+xml"})
    )
    collector = build_collector(config)
    collection_result = await run_collection(db_session, config, collector)
    assert collection_result.inserted == 2

    async def fake_classify_item(title, text):
        return ClassificationResult(
            primary_category="COMMERCIAL",
            secondary_categories=[],
            classification_confidence=0.6,
            reasoning="Test classification.",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)

    classification_result = await classify_pending_items(db_session, batch_size=10)
    assert classification_result.classified == 2
    assert classification_result.failed == 0

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(item["primary_category"] == "COMMERCIAL" for item in body)
    assert all(item["classification_confidence"] == 0.6 for item in body)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_integration_pipeline.py::test_collected_items_get_classified_and_are_visible_via_api -v`
Expected: this should already PASS once Tasks 1-6 are done, since it only exercises code paths
those tasks already built and tested individually — that's expected, not a TDD violation. If it
fails, diagnose against what Tasks 1-6 actually produced rather than assuming the test itself is
wrong.

- [ ] **Step 3: Run the full test suite**

Run: `.venv/bin/pytest -v`
Expected: every test across Sprints 1-3 passes, output as clean as the pre-existing run (only the
two known pre-existing FastAPI/Starlette deprecation warnings).

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_pipeline.py
git commit -m "test: add end-to-end collect-then-classify integration test"
```

---

## Manual verification (not automated)

After Task 7, with a real `ANTHROPIC_API_KEY` set in `.env`:

```bash
docker compose up -d
alembic upgrade head
uvicorn src.api.main:app --reload
```

- Wait for at least one collection cycle and one classification cycle (or temporarily lower
  `CLASSIFICATION_INTERVAL_MINUTES` for a quick manual check), then `curl http://localhost:8000/items`
  and confirm real collected items now show a real `primary_category` (not `null`) — including at
  least one `DIVERS` if the sample includes something that doesn't clearly fit elsewhere, which
  would confirm the model is using it as intended rather than avoiding it.
- Spot-check `model_reason` in the database for a few items — the reasoning should read as a
  genuine editorial judgment referencing the item's actual content, not a generic or repeated
  string.
