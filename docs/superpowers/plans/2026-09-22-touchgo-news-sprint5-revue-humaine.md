# Touch-Go News — Sprint 5 (Revue humaine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a human reviewer see classified-and-scored `NewsItem`s through a minimal web page,
filter them by priority/category/period, and record a feedback decision (🔥/👍/👀/❌/➕) on each —
persisted both as the item's current state and as a full audit history — with the same data also
available as JSON through the existing read-only API.

**Architecture:** A new `src/review/` package (`schemas.py` + `service.py`) mirrors the shape of
`src/classification/` and `src/scoring/` — pure, unit-testable pieces the API layer calls into.
`src/api/main.py` gains one write endpoint (`POST /items/{id}/feedback`), gains query-param
filtering on the existing `GET /items`, and gains a server-rendered HTML page (`GET /`, Jinja2 +
vanilla JS, no build step, no JS framework) that reuses the exact same filtering logic. No new job,
no scheduler changes, no LLM calls — this sprint is pure request/response, backed entirely by
columns and a table (`NewsFeedback`) that have existed unused since the Sprint 1 schema.

**Tech Stack:** Same as Sprints 1-4, plus `jinja2` (server-side HTML templates) — the only new
dependency this sprint adds.

**Spec:** [`docs/superpowers/specs/2026-09-22-touchgo-news-sprint5-revue-humaine-design.md`](../specs/2026-09-22-touchgo-news-sprint5-revue-humaine-design.md)
(implements Sprint 5 per `SPEC.md` sections 12, 13, 16, 17, 20, 21).

## Global Constraints

- Un seul reviewer humain existe pour ce MVP (design §2) — pas d'authentification, pas de saisie de
  nom côté client ; `Settings.default_reviewer_id` fournit la valeur utilisée quand
  `FeedbackIn.reviewer_id` est absent.
- `reason` n'est validé et persisté que lorsque `decision == "REJETER"` ; fourni avec toute autre
  décision, il est ignoré silencieusement, jamais écrit en base (design §3).
- Les trois vues (`a_voir`/`a_surveiller`/`faible_priorite`) sont un pur alias de `priority`
  (A/B/C) — aucune dimension supplémentaire (design §4). Si `view` et `priority` sont fournis
  ensemble, `priority` explicite l'emporte.
- Un item avec `priority IS NULL` n'apparaît dans aucune des trois vues (design §4) — comportement
  voulu, pas un bug : un item non encore scoré n'est pas encore triable.
- `NewsItem.human_decision/human_reason/human_comment/reviewed_at/reviewer_id` représentent le
  **dernier état** (écrasés à chaque nouveau feedback) ; `NewsFeedback` est **l'historique complet**
  (une ligne ajoutée par feedback, jamais écrasée) — design §3, même distinction que
  `touchgo_interest` (état courant) vs `model_metadata["scoring_errors"]` (journal) au Sprint 4.
- Aucun appel réseau réel dans les tests (aucun LLM impliqué dans ce sprint).
- Frontend : HTML servi par FastAPI (Jinja2) + JS vanilla, aucun build step, aucune dépendance JS
  ajoutée au projet (design §6).
- Aucune migration de schéma : toutes les colonnes utilisées (`human_*`, `verification_status`,
  table `news_feedback`) existent depuis la migration initiale du Sprint 1.

---

### Task 1: Settings — `default_reviewer_id`

**Files:**
- Modify: `src/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings.default_reviewer_id: str` (default `"reviewer"`).

- [ ] **Step 1: Write the failing test**

Replace both existing test functions in `tests/test_config.py` in full (they already assert on
`classification_*`/`scoring_*` fields — extend them with `default_reviewer_id` rather than adding
new test functions, same object under test):

```python
import os

from src.config import Settings


def test_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host:5432/db")
    monkeypatch.setenv("SOURCES_CONFIG_PATH", "config/sources.yaml")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("CLASSIFICATION_BATCH_SIZE", "5")
    monkeypatch.setenv("CLASSIFICATION_INTERVAL_MINUTES", "10")
    monkeypatch.setenv("CLASSIFICATION_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("SCORING_BATCH_SIZE", "8")
    monkeypatch.setenv("SCORING_INTERVAL_MINUTES", "15")
    monkeypatch.setenv("SCORING_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("DEFAULT_REVIEWER_ID", "cedric")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"
    assert settings.sources_config_path == "config/sources.yaml"
    assert settings.anthropic_api_key == "sk-test-key"
    assert settings.classification_batch_size == 5
    assert settings.classification_interval_minutes == 10
    assert settings.classification_max_attempts == 3
    assert settings.scoring_batch_size == 8
    assert settings.scoring_interval_minutes == 15
    assert settings.scoring_max_attempts == 4
    assert settings.default_reviewer_id == "cedric"


def test_settings_have_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SOURCES_CONFIG_PATH", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLASSIFICATION_BATCH_SIZE", raising=False)
    monkeypatch.delenv("CLASSIFICATION_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("CLASSIFICATION_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("SCORING_BATCH_SIZE", raising=False)
    monkeypatch.delenv("SCORING_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("SCORING_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("DEFAULT_REVIEWER_ID", raising=False)
    settings = Settings(_env_file=None)
    assert "touchgo_news" in settings.database_url
    assert settings.sources_config_path == "config/sources.yaml"
    assert settings.anthropic_api_key == ""
    assert settings.classification_batch_size == 20
    assert settings.classification_interval_minutes == 3
    assert settings.classification_max_attempts == 5
    assert settings.scoring_batch_size == 20
    assert settings.scoring_interval_minutes == 3
    assert settings.scoring_max_attempts == 5
    assert settings.default_reviewer_id == "reviewer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError`, `Settings` has no `default_reviewer_id` yet.

- [ ] **Step 3: Update `Settings`**

In `src/config.py`, replace the class body:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://touchgo:touchgo@localhost:5432/touchgo_news"
    sources_config_path: str = "config/sources.yaml"
    anthropic_api_key: str = ""
    classification_batch_size: int = 20
    classification_interval_minutes: int = 3
    classification_max_attempts: int = 5
    scoring_batch_size: int = 20
    scoring_interval_minutes: int = 3
    scoring_max_attempts: int = 5
    default_reviewer_id: str = "reviewer"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Update `.env.example`**

Append after the existing `SCORING_MAX_ATTEMPTS=5` line:

```
DEFAULT_REVIEWER_ID=reviewer
```

- [ ] **Step 6: Commit**

```bash
git add src/config.py tests/test_config.py .env.example
git commit -m "feat: add default_reviewer_id setting"
```

---

### Task 2: Review schemas — `FeedbackIn`, `DECISIONS`, `REJECT_REASONS`

**Files:**
- Create: `src/review/__init__.py`
- Create: `src/review/schemas.py`
- Create: `tests/review/__init__.py`
- Test: `tests/review/test_schemas.py`

**Interfaces:**
- Produces: `DECISIONS: list[str]`, `REJECT_REASONS: list[str]`, `FeedbackIn` (pydantic model:
  `decision: str`, `reason: str | None`, `comment: str | None`, `reviewer_id: str | None`).

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_schemas.py
import pytest
from pydantic import ValidationError

from src.review.schemas import DECISIONS, REJECT_REASONS, FeedbackIn


def test_decisions_has_exactly_the_five_spec_values():
    assert DECISIONS == [
        "TRES_INTERESSANT",
        "INTERESSANT",
        "A_SUIVRE",
        "REJETER",
        "NOUVELLE_CATEGORIE",
    ]


def test_reject_reasons_has_exactly_the_nine_spec_values():
    assert REJECT_REASONS == [
        "trop_mineur",
        "pas_pertinent_touchgo",
        "trop_commercial",
        "trop_local",
        "signal_trop_faible",
        "doublon",
        "information_douteuse",
        "hors_perimetre",
        "autre",
    ]


def test_feedback_in_accepts_a_simple_decision_with_no_reason_or_comment():
    feedback = FeedbackIn(decision="TRES_INTERESSANT")
    assert feedback.decision == "TRES_INTERESSANT"
    assert feedback.reason is None
    assert feedback.comment is None
    assert feedback.reviewer_id is None


def test_feedback_in_rejects_an_unknown_decision():
    with pytest.raises(ValidationError):
        FeedbackIn(decision="MAYBE")


def test_feedback_in_requires_a_valid_reason_when_rejecting():
    with pytest.raises(ValidationError):
        FeedbackIn(decision="REJETER")


def test_feedback_in_rejects_an_unknown_reason_when_rejecting():
    with pytest.raises(ValidationError):
        FeedbackIn(decision="REJETER", reason="parce_que")


def test_feedback_in_accepts_a_valid_reason_when_rejecting():
    feedback = FeedbackIn(decision="REJETER", reason="doublon")
    assert feedback.reason == "doublon"


def test_feedback_in_requires_a_comment_when_suggesting_a_new_category():
    with pytest.raises(ValidationError):
        FeedbackIn(decision="NOUVELLE_CATEGORIE")


def test_feedback_in_accepts_a_comment_when_suggesting_a_new_category():
    feedback = FeedbackIn(decision="NOUVELLE_CATEGORIE", comment="Catégorie drones civils")
    assert feedback.comment == "Catégorie drones civils"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/review/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.review'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/review/__init__.py
```

(empty file)

```python
# tests/review/__init__.py
```

(empty file)

```python
# src/review/schemas.py
from pydantic import BaseModel, ValidationInfo, field_validator

DECISIONS = [
    "TRES_INTERESSANT",
    "INTERESSANT",
    "A_SUIVRE",
    "REJETER",
    "NOUVELLE_CATEGORIE",
]

REJECT_REASONS = [
    "trop_mineur",
    "pas_pertinent_touchgo",
    "trop_commercial",
    "trop_local",
    "signal_trop_faible",
    "doublon",
    "information_douteuse",
    "hors_perimetre",
    "autre",
]


class FeedbackIn(BaseModel):
    decision: str
    reason: str | None = None
    comment: str | None = None
    reviewer_id: str | None = None

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str) -> str:
        if value not in DECISIONS:
            raise ValueError(f"invalid decision: {value!r}")
        return value

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None, info: ValidationInfo) -> str | None:
        decision = info.data.get("decision")
        if decision == "REJETER" and value not in REJECT_REASONS:
            raise ValueError(
                f"reason must be one of {REJECT_REASONS} when decision is REJETER"
            )
        return value

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str | None, info: ValidationInfo) -> str | None:
        decision = info.data.get("decision")
        if decision == "NOUVELLE_CATEGORIE" and not value:
            raise ValueError("comment is required when decision is NOUVELLE_CATEGORIE")
        return value
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/review/test_schemas.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/review/__init__.py src/review/schemas.py tests/review/__init__.py tests/review/test_schemas.py
git commit -m "feat: add review feedback schema with decision/reason/comment validation"
```

---

### Task 3: Review service — `submit_feedback`

**Files:**
- Create: `src/review/service.py`
- Test: `tests/review/test_service.py`

**Interfaces:**
- Consumes: `FeedbackIn` (Task 2), `NewsItem`, `NewsFeedback` (existing), `get_settings` (existing,
  `Settings.default_reviewer_id` from Task 1).
- Produces: `ItemNotFoundError` (exception), `submit_feedback(session: Session, item_id: int,
  feedback: FeedbackIn) -> NewsItem`.

- [ ] **Step 1: Write the failing test**

```python
# tests/review/test_service.py
import pytest

from src.config import get_settings
from src.db.models import NewsFeedback, NewsItem
from src.review.schemas import FeedbackIn
from src.review.service import ItemNotFoundError, submit_feedback


def _item(db_session, make_source, **overrides) -> NewsItem:
    make_source(source_id=overrides.pop("source_id", "flightglobal"))
    defaults = dict(
        source_id="flightglobal",
        source_item_id=overrides.pop("source_item_id", "1"),
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Title",
        original_text="Body",
        primary_category="COMMERCIAL",
        priority="A",
    )
    defaults.update(overrides)
    item = NewsItem(**defaults)
    db_session.add(item)
    db_session.commit()
    return item


def test_submit_feedback_raises_when_item_does_not_exist(db_session):
    with pytest.raises(ItemNotFoundError):
        submit_feedback(db_session, 999999, FeedbackIn(decision="INTERESSANT"))


def test_submit_feedback_updates_the_item_for_a_simple_decision(db_session, make_source):
    item = _item(db_session, make_source)

    updated = submit_feedback(
        db_session, item.id, FeedbackIn(decision="INTERESSANT", reviewer_id="cedric")
    )

    assert updated.human_decision == "INTERESSANT"
    assert updated.human_reason is None
    assert updated.human_comment is None
    assert updated.reviewer_id == "cedric"
    assert updated.reviewed_at is not None


def test_submit_feedback_uses_the_default_reviewer_id_when_none_given(
    db_session, make_source, monkeypatch
):
    monkeypatch.setenv("DEFAULT_REVIEWER_ID", "cedric-default")
    get_settings.cache_clear()
    try:
        item = _item(db_session, make_source)

        updated = submit_feedback(db_session, item.id, FeedbackIn(decision="A_SUIVRE"))

        assert updated.reviewer_id == "cedric-default"
    finally:
        get_settings.cache_clear()


def test_submit_feedback_stores_the_reason_only_when_rejecting(db_session, make_source):
    item = _item(db_session, make_source)

    updated = submit_feedback(
        db_session, item.id, FeedbackIn(decision="REJETER", reason="doublon")
    )

    assert updated.human_reason == "doublon"


def test_submit_feedback_stores_the_comment_when_suggesting_a_new_category(
    db_session, make_source
):
    item = _item(db_session, make_source)

    updated = submit_feedback(
        db_session,
        item.id,
        FeedbackIn(decision="NOUVELLE_CATEGORIE", comment="Catégorie drones civils"),
    )

    assert updated.human_comment == "Catégorie drones civils"


def test_submit_feedback_inserts_a_feedback_history_row(db_session, make_source):
    item = _item(db_session, make_source, primary_category="MILITAIRE", priority="B")

    submit_feedback(db_session, item.id, FeedbackIn(decision="TRES_INTERESSANT", reviewer_id="c"))

    rows = db_session.query(NewsFeedback).filter_by(news_item_id=item.id).all()
    assert len(rows) == 1
    assert rows[0].decision == "TRES_INTERESSANT"
    assert rows[0].previous_priority == "B"
    assert rows[0].previous_category == "MILITAIRE"
    assert rows[0].reviewer_id == "c"


def test_submit_feedback_appends_a_new_history_row_without_deleting_previous_ones(
    db_session, make_source
):
    item = _item(db_session, make_source)

    submit_feedback(db_session, item.id, FeedbackIn(decision="INTERESSANT", reviewer_id="c"))
    submit_feedback(
        db_session,
        item.id,
        FeedbackIn(decision="REJETER", reason="doublon", reviewer_id="c"),
    )

    rows = (
        db_session.query(NewsFeedback)
        .filter_by(news_item_id=item.id)
        .order_by(NewsFeedback.id)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].decision == "INTERESSANT"
    assert rows[1].decision == "REJETER"
    assert item.human_decision == "REJETER"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/review/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.review.service'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/review/service.py
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.config import get_settings
from src.db.models import NewsFeedback, NewsItem
from src.review.schemas import FeedbackIn


class ItemNotFoundError(Exception):
    """Raised when submit_feedback targets a NewsItem id that doesn't exist."""


def submit_feedback(session: Session, item_id: int, feedback: FeedbackIn) -> NewsItem:
    item = session.get(NewsItem, item_id)
    if item is None:
        raise ItemNotFoundError(f"news item {item_id} not found")

    reviewer_id = feedback.reviewer_id or get_settings().default_reviewer_id
    # reason only carries meaning for REJETER; any value supplied alongside
    # another decision is not persisted (see design doc §3).
    reason = feedback.reason if feedback.decision == "REJETER" else None

    session.add(
        NewsFeedback(
            news_item_id=item.id,
            decision=feedback.decision,
            reason=reason,
            comment=feedback.comment,
            previous_priority=item.priority,
            previous_category=item.primary_category,
            reviewer_id=reviewer_id,
        )
    )

    item.human_decision = feedback.decision
    item.human_reason = reason
    item.human_comment = feedback.comment
    item.reviewed_at = datetime.now(timezone.utc)
    item.reviewer_id = reviewer_id

    session.commit()
    return item
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/review/test_service.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/review/service.py tests/review/test_service.py
git commit -m "feat: add submit_feedback recording current state and full history"
```

---

### Task 4: Feedback endpoint and expose review fields via the API

**Files:**
- Modify: `src/api/schemas.py`
- Modify: `src/api/main.py`
- Modify: `tests/api/test_items.py`
- Create: `tests/api/test_feedback.py`

**Interfaces:**
- Consumes: `FeedbackIn` (Task 2), `submit_feedback`, `ItemNotFoundError` (Task 3).
- Produces: `NewsItemOut` gains `verification_status`, `human_decision`, `human_reason`,
  `human_comment`, `reviewed_at`, `reviewer_id`. `POST /items/{item_id}/feedback` endpoint.

- [ ] **Step 1: Write the failing tests**

Modify `tests/api/test_items.py`'s existing `test_items_returns_persisted_items` test — extend it
with the new fields (same pattern as Sprint 3/4: extend the existing test rather than adding a new
one for "more fields to check"):

```python
from fastapi.testclient import TestClient

from src.api.main import app, get_session
from src.db.repository import save_raw_items
from src.collectors.base import RawItem
from src.db.models import NewsItem


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
    stored.classification_attempts = 2
    stored.touchgo_interest = 8
    stored.event_importance = 7
    stored.source_confidence = 6
    stored.urgency = 5
    stored.priority = "A"
    stored.verification_status = "UNVERIFIED"
    stored.human_decision = "TRES_INTERESSANT"
    stored.human_reason = None
    stored.human_comment = "Bon signal"
    stored.reviewer_id = "cedric"
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
    assert body[0]["classification_attempts"] == 2
    assert body[0]["touchgo_interest"] == 8
    assert body[0]["event_importance"] == 7
    assert body[0]["source_confidence"] == 6
    assert body[0]["urgency"] == 5
    assert body[0]["priority"] == "A"
    assert body[0]["verification_status"] == "UNVERIFIED"
    assert body[0]["human_decision"] == "TRES_INTERESSANT"
    assert body[0]["human_reason"] is None
    assert body[0]["human_comment"] == "Bon signal"
    assert body[0]["reviewer_id"] == "cedric"
    assert body[0]["reviewed_at"] is None
    assert body[0]["duplicate_of"] is None
```

Create `tests/api/test_feedback.py`:

```python
from fastapi.testclient import TestClient

from src.api.main import app, get_session
from src.db.models import NewsFeedback, NewsItem


def _item(db_session, make_source, **overrides) -> NewsItem:
    make_source(source_id=overrides.pop("source_id", "flightglobal"))
    defaults = dict(
        source_id="flightglobal",
        source_item_id=overrides.pop("source_item_id", "1"),
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Title",
        original_text="Body",
        primary_category="COMMERCIAL",
        priority="A",
    )
    defaults.update(overrides)
    item = NewsItem(**defaults)
    db_session.add(item)
    db_session.commit()
    return item


def test_feedback_endpoint_updates_the_item_and_returns_it(db_session, make_source):
    item = _item(db_session, make_source)

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        client = TestClient(app)
        response = client.post(
            f"/items/{item.id}/feedback",
            json={"decision": "TRES_INTERESSANT", "reviewer_id": "cedric"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["human_decision"] == "TRES_INTERESSANT"
    assert body["reviewer_id"] == "cedric"

    db_session.expire_all()
    stored = db_session.get(NewsItem, item.id)
    assert stored.human_decision == "TRES_INTERESSANT"
    assert db_session.query(NewsFeedback).filter_by(news_item_id=item.id).count() == 1


def test_feedback_endpoint_returns_404_for_an_unknown_item(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        client = TestClient(app)
        response = client.post("/items/999999/feedback", json={"decision": "TRES_INTERESSANT"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_feedback_endpoint_returns_422_for_an_invalid_decision(db_session, make_source):
    item = _item(db_session, make_source)

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        client = TestClient(app)
        response = client.post(f"/items/{item.id}/feedback", json={"decision": "MAYBE"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_feedback_endpoint_returns_422_when_rejecting_without_a_valid_reason(
    db_session, make_source
):
    item = _item(db_session, make_source)

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        client = TestClient(app)
        response = client.post(f"/items/{item.id}/feedback", json={"decision": "REJETER"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/api/test_items.py tests/api/test_feedback.py -v`
Expected: FAIL — `test_items.py` fails on `KeyError`/missing keys for the new fields;
`test_feedback.py` fails with `404` on a route FastAPI doesn't know (`POST /items/{id}/feedback`
not yet registered — TestClient returns 404 for unmatched routes, so watch for that vs. the
`ItemNotFoundError` 404 once the route exists).

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
    classification_attempts: int
    touchgo_interest: int | None
    event_importance: int | None
    source_confidence: int | None
    urgency: int | None
    priority: str | None
    verification_status: str | None
    duplicate_of: int | None
    human_decision: str | None
    human_reason: str | None
    human_comment: str | None
    reviewed_at: datetime | None
    reviewer_id: str | None
```

- [ ] **Step 4: Add the feedback endpoint to `src/api/main.py`**

The current imports and route section:

```python
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.schemas import NewsItemOut
from src.collectors.sources_config import load_sources_config
from src.config import get_settings
from src.db.models import NewsItem
from src.db.repository import sync_sources
from src.db.session import SessionLocal, get_session
from src.scheduler import add_classification_job, add_scoring_job, build_scheduler
```

becomes:

```python
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.schemas import NewsItemOut
from src.collectors.sources_config import load_sources_config
from src.config import get_settings
from src.db.models import NewsItem
from src.db.repository import sync_sources
from src.db.session import SessionLocal, get_session
from src.review.schemas import FeedbackIn
from src.review.service import ItemNotFoundError, submit_feedback
from src.scheduler import add_classification_job, add_scoring_job, build_scheduler
```

Add this route after the existing `list_items` function at the end of the file:

```python
@app.post("/items/{item_id}/feedback", response_model=NewsItemOut)
def submit_item_feedback(
    item_id: int, feedback: FeedbackIn, session: Session = Depends(get_session)
) -> NewsItem:
    try:
        return submit_feedback(session, item_id, feedback)
    except ItemNotFoundError:
        raise HTTPException(status_code=404, detail="item not found") from None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/api/test_items.py tests/api/test_feedback.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add src/api/schemas.py src/api/main.py tests/api/test_items.py tests/api/test_feedback.py
git commit -m "feat: add feedback endpoint and expose review fields through GET /items"
```

---

### Task 5: `GET /items` filters — priority, category, since, view

**Files:**
- Modify: `src/api/main.py`
- Modify: `tests/api/test_items.py`

**Interfaces:**
- Consumes: `PRIORITIES` (`src.scoring.prompt`, existing), `CATEGORIES` (`src.classification.prompt`,
  existing).
- Produces: `_filtered_items(session, priority, category, since, view) -> list[NewsItem]` (private
  helper, reused by Task 6's HTML route).

- [ ] **Step 1: Write the failing tests**

Add to `tests/api/test_items.py` (it already imports `TestClient`, `app`, `get_session`, `NewsItem`
— add these functions):

```python
from datetime import datetime, timedelta, timezone


def test_items_filters_by_priority(db_session, make_source):
    make_source(source_id="flightglobal")
    for i, priority in enumerate(["A", "B", "C"]):
        db_session.add(
            NewsItem(
                source_id="flightglobal",
                source_item_id=str(i),
                canonical_url=f"https://example.com/{i}",
                original_url=f"https://example.com/{i}",
                original_title=f"Title {i}",
                original_text="Body",
                priority=priority,
            )
        )
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"priority": "B"})
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert len(body) == 1
    assert body[0]["priority"] == "B"


def test_items_filters_by_category(db_session, make_source):
    make_source(source_id="flightglobal")
    for i, category in enumerate(["COMMERCIAL", "MILITAIRE"]):
        db_session.add(
            NewsItem(
                source_id="flightglobal",
                source_item_id=str(i),
                canonical_url=f"https://example.com/{i}",
                original_url=f"https://example.com/{i}",
                original_title=f"Title {i}",
                original_text="Body",
                primary_category=category,
            )
        )
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"category": "MILITAIRE"})
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert len(body) == 1
    assert body[0]["primary_category"] == "MILITAIRE"


def test_items_filters_by_since(db_session, make_source):
    make_source(source_id="flightglobal")
    db_session.add(
        NewsItem(
            source_id="flightglobal",
            source_item_id="old",
            canonical_url="https://example.com/old",
            original_url="https://example.com/old",
            original_title="Old",
            original_text="Body",
            detected_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
    )
    db_session.add(
        NewsItem(
            source_id="flightglobal",
            source_item_id="recent",
            canonical_url="https://example.com/recent",
            original_url="https://example.com/recent",
            original_title="Recent",
            original_text="Body",
            detected_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"since": "24h"})
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert len(body) == 1
    assert body[0]["original_title"] == "Recent"


def test_items_view_maps_to_the_corresponding_priority(db_session, make_source):
    make_source(source_id="flightglobal")
    for i, priority in enumerate(["A", "B", "C"]):
        db_session.add(
            NewsItem(
                source_id="flightglobal",
                source_item_id=str(i),
                canonical_url=f"https://example.com/{i}",
                original_url=f"https://example.com/{i}",
                original_title=f"Title {i}",
                original_text="Body",
                priority=priority,
            )
        )
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"view": "faible_priorite"})
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert len(body) == 1
    assert body[0]["priority"] == "C"


def test_items_explicit_priority_overrides_the_view(db_session, make_source):
    make_source(source_id="flightglobal")
    for i, priority in enumerate(["A", "B"]):
        db_session.add(
            NewsItem(
                source_id="flightglobal",
                source_item_id=str(i),
                canonical_url=f"https://example.com/{i}",
                original_url=f"https://example.com/{i}",
                original_title=f"Title {i}",
                original_text="Body",
                priority=priority,
            )
        )
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        # view says "a_voir" (priority A); explicit priority=B must win.
        response = TestClient(app).get("/items", params={"view": "a_voir", "priority": "B"})
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert len(body) == 1
    assert body[0]["priority"] == "B"


def test_items_rejects_an_invalid_priority(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"priority": "Z"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_items_rejects_an_invalid_category(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"category": "NOT_A_CATEGORY"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_items_with_null_priority_are_excluded_from_every_view(db_session, make_source):
    make_source(source_id="flightglobal")
    db_session.add(
        NewsItem(
            source_id="flightglobal",
            source_item_id="1",
            canonical_url="https://example.com/1",
            original_url="https://example.com/1",
            original_title="Not scored yet",
            original_text="Body",
        )
    )
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items", params={"view": "a_voir"})
    finally:
        app.dependency_overrides.clear()

    assert response.json() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/api/test_items.py -v`
Expected: FAIL — `GET /items` doesn't accept these query params yet (they're silently ignored by
FastAPI today since `list_items` takes none, so every filter test gets back the unfiltered list —
watch for tests failing on count/content mismatch rather than a hard error).

- [ ] **Step 3: Add filtering to `src/api/main.py`**

Add these imports alongside the existing ones:

```python
from datetime import datetime, timedelta, timezone

from src.classification.prompt import CATEGORIES
from src.scoring.prompt import PRIORITIES
```

Add this module-level state right after the `app = FastAPI(...)` line:

```python
_VIEW_TO_PRIORITY = {
    "a_voir": "A",
    "a_surveiller": "B",
    "faible_priorite": "C",
}

_SINCE_TO_DELTA = {
    "24h": timedelta(hours=24),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
}


def _filtered_items(
    session: Session,
    priority: str | None,
    category: str | None,
    since: str | None,
    view: str | None,
) -> list[NewsItem]:
    if priority is not None and priority not in PRIORITIES:
        raise HTTPException(status_code=422, detail=f"invalid priority: {priority!r}")
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"invalid category: {category!r}")

    effective_priority = priority or _VIEW_TO_PRIORITY.get(view)

    query = select(NewsItem).order_by(NewsItem.detected_at.desc())
    if effective_priority is not None:
        query = query.where(NewsItem.priority == effective_priority)
    if category is not None:
        query = query.where(NewsItem.primary_category == category)
    if since is not None:
        cutoff = datetime.now(timezone.utc) - _SINCE_TO_DELTA[since]
        query = query.where(NewsItem.detected_at >= cutoff)

    return list(session.execute(query).scalars())
```

Replace the existing `list_items` function:

```python
@app.get("/items", response_model=list[NewsItemOut])
def list_items(session: Session = Depends(get_session)) -> list[NewsItem]:
    return list(
        session.execute(select(NewsItem).order_by(NewsItem.detected_at.desc())).scalars()
    )
```

with:

```python
@app.get("/items", response_model=list[NewsItemOut])
def list_items(
    priority: str | None = None,
    category: str | None = None,
    since: str | None = None,
    view: str | None = None,
    session: Session = Depends(get_session),
) -> list[NewsItem]:
    return _filtered_items(session, priority, category, since, view)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/api/test_items.py -v`
Expected: PASS (every test in the file — 1 pre-existing plus the 8 new ones)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: PASS (every test, no regressions elsewhere).

- [ ] **Step 6: Commit**

```bash
git add src/api/main.py tests/api/test_items.py
git commit -m "feat: filter GET /items by priority, category, since, and view"
```

---

### Task 6: Review page — Jinja2 template, static JS/CSS, `GET /`

**Files:**
- Create: `src/api/view_helpers.py`
- Create: `templates/review.html`
- Create: `static/review.css`
- Create: `static/review.js`
- Modify: `src/api/main.py`
- Modify: `pyproject.toml`
- Test: `tests/api/test_view_helpers.py`
- Test: `tests/api/test_review_page.py`

**Interfaces:**
- Consumes: `_filtered_items` (Task 5), `REJECT_REASONS` (Task 2), `CATEGORIES`, `PRIORITIES`
  (existing).
- Produces: `format_relative_time(dt: datetime) -> str`. `GET /` (HTML page). `/static/*` (mounted
  static files).

**Note on frontend behavior:** the design doc describes an inline `<select>` for the ❌ reason
picker; this task uses a plain `window.prompt()` instead — same functional requirement (a reason is
chosen from the closed list before the request is sent), far less code, no extra DOM state to
manage, consistent with "je serai à tout jamais l'unique reviewer, inutile de faire tout un
patacaisse." If this reads as insufficient once you see it running, that's a one-file follow-up
(`static/review.js` only), not a re-plan.

- [ ] **Step 1: Write the failing test for the relative-time helper**

```python
# tests/api/test_view_helpers.py
from datetime import datetime, timedelta, timezone

from src.api.view_helpers import format_relative_time


def test_format_relative_time_under_a_minute():
    dt = datetime.now(timezone.utc) - timedelta(seconds=30)
    assert format_relative_time(dt) == "à l'instant"


def test_format_relative_time_in_minutes():
    dt = datetime.now(timezone.utc) - timedelta(minutes=37)
    assert format_relative_time(dt) == "il y a 37 min"


def test_format_relative_time_in_hours():
    dt = datetime.now(timezone.utc) - timedelta(hours=5)
    assert format_relative_time(dt) == "il y a 5 h"


def test_format_relative_time_in_days():
    dt = datetime.now(timezone.utc) - timedelta(days=2)
    assert format_relative_time(dt) == "il y a 2 j"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/api/test_view_helpers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.api.view_helpers'`

- [ ] **Step 3: Write the helper**

```python
# src/api/view_helpers.py
from datetime import datetime, timezone


def format_relative_time(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    seconds = int((now - dt).total_seconds())
    if seconds < 60:
        return "à l'instant"
    minutes = seconds // 60
    if minutes < 60:
        return f"il y a {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"il y a {hours} h"
    days = hours // 24
    return f"il y a {days} j"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/api/test_view_helpers.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Add the `jinja2` dependency**

In `pyproject.toml`, add `"jinja2>=3.1",` to the `dependencies` list (after `"anthropic>=0.40",`).
Then install it:

```bash
.venv/bin/pip install -e .
```

- [ ] **Step 6: Write the failing page test**

```python
# tests/api/test_review_page.py
from fastapi.testclient import TestClient

from src.api.main import app, get_session
from src.db.models import NewsItem


def test_review_page_renders_items(db_session, make_source):
    make_source(source_id="flightglobal")
    db_session.add(
        NewsItem(
            source_id="flightglobal",
            source_item_id="1",
            canonical_url="https://example.com/1",
            original_url="https://example.com/1",
            original_title="Airbus unveils new variant",
            original_text="Body",
            primary_category="COMMERCIAL",
            priority="A",
        )
    )
    db_session.commit()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Airbus unveils new variant" in response.text


def test_review_page_shows_no_results_message_when_empty(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/", params={"priority": "A"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Aucun résultat" in response.text


def test_review_page_rejects_an_invalid_priority(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/", params={"priority": "Z"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
```

- [ ] **Step 7: Run test to verify it fails**

Run: `.venv/bin/pytest tests/api/test_review_page.py -v`
Expected: FAIL — `404` (no `GET /` route registered yet).

- [ ] **Step 8: Write the template**

```html
<!-- templates/review.html -->
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Touch-Go News — Revue</title>
  <link rel="stylesheet" href="/static/review.css">
</head>
<body>
  <h1>Touch-Go News</h1>

  <nav class="views">
    <a href="/?view=a_voir">À voir</a>
    <a href="/?view=a_surveiller">À surveiller</a>
    <a href="/?view=faible_priorite">Faible priorité</a>
    <a href="/">Toutes</a>
  </nav>

  <form method="get" action="/" class="filters">
    <select name="priority" onchange="this.form.submit()">
      <option value="">Toutes priorités</option>
      {% for p in priorities %}
      <option value="{{ p }}" {% if current_priority == p %}selected{% endif %}>{{ p }}</option>
      {% endfor %}
    </select>
    <select name="category" onchange="this.form.submit()">
      <option value="">Toutes catégories</option>
      {% for c in categories %}
      <option value="{{ c }}" {% if current_category == c %}selected{% endif %}>{{ c }}</option>
      {% endfor %}
    </select>
    <select name="since" onchange="this.form.submit()">
      <option value="">Toute période</option>
      <option value="24h" {% if current_since == "24h" %}selected{% endif %}>24 h</option>
      <option value="3d" {% if current_since == "3d" %}selected{% endif %}>3 jours</option>
      <option value="7d" {% if current_since == "7d" %}selected{% endif %}>7 jours</option>
    </select>
  </form>

  <div class="items">
    {% for item in items %}
    <article class="card" data-item-id="{{ item.id }}">
      <div class="badges">
        <span class="badge priority-{{ item.priority }}">{{ item.priority or "—" }}</span>
        <span class="badge category">{{ item.primary_category or "—" }}</span>
        <span class="time">{{ item.detected_at | relative_time }}</span>
      </div>
      <h2><a href="{{ item.original_url }}" target="_blank" rel="noopener">{{ item.original_title }}</a></h2>
      <p class="source">Source : {{ item.source_id }} — Langue : {{ item.language or "?" }}</p>
      <dl class="scores">
        <dt>Intérêt Touch-Go</dt><dd>{{ item.touchgo_interest if item.touchgo_interest is not none else "—" }}</dd>
        <dt>Importance</dt><dd>{{ item.event_importance if item.event_importance is not none else "—" }}</dd>
        <dt>Fiabilité</dt><dd>{{ item.source_confidence if item.source_confidence is not none else "—" }}</dd>
        <dt>Urgence</dt><dd>{{ item.urgency if item.urgency is not none else "—" }}</dd>
      </dl>
      <p class="status">Statut : {{ item.verification_status or "—" }}{% if item.human_decision %} — traité : {{ item.human_decision }}{% endif %}</p>
      <div class="actions">
        <button data-decision="TRES_INTERESSANT" title="Très intéressant">🔥</button>
        <button data-decision="INTERESSANT" title="Intéressant">👍</button>
        <button data-decision="A_SUIVRE" title="À suivre">👀</button>
        <button data-decision="REJETER" data-needs-reason="true" title="Rejeter">❌</button>
        <button data-decision="NOUVELLE_CATEGORIE" data-needs-comment="true" title="Nouvelle catégorie">➕</button>
      </div>
      <div class="feedback-error" hidden></div>
    </article>
    {% else %}
    <p>Aucun résultat.</p>
    {% endfor %}
  </div>

  <script>
    window.REJECT_REASONS = {{ reject_reasons | tojson }};
  </script>
  <script src="/static/review.js"></script>
</body>
</html>
```

- [ ] **Step 9: Write the stylesheet**

```css
/* static/review.css */
body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
nav.views a, form.filters select { margin-right: 0.5rem; }
.card { border: 1px solid #ccc; border-radius: 6px; padding: 1rem; margin-bottom: 1rem; }
.badges { display: flex; gap: 0.5rem; align-items: center; font-size: 0.85rem; }
.badge { padding: 0.1rem 0.5rem; border-radius: 4px; background: #eee; }
.badge.priority-A { background: #c8e6c9; }
.badge.priority-B { background: #fff9c4; }
.badge.priority-C { background: #eeeeee; }
.time { color: #777; margin-left: auto; }
.scores { display: flex; gap: 1rem; font-size: 0.85rem; }
.scores dt { font-weight: bold; }
.scores dd { margin: 0; }
.actions button { font-size: 1.2rem; margin-right: 0.3rem; cursor: pointer; }
.feedback-error { color: #b00020; font-size: 0.85rem; margin-top: 0.5rem; }
```

- [ ] **Step 10: Write the JS**

```javascript
// static/review.js
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-decision]");
  if (!button) return;

  const card = button.closest(".card");
  const itemId = card.dataset.itemId;
  const decision = button.dataset.decision;

  let reason = null;
  let comment = null;

  if (button.dataset.needsReason) {
    reason = window.prompt("Raison du rejet :\n" + window.REJECT_REASONS.join(", "));
    if (!reason || !window.REJECT_REASONS.includes(reason)) {
      showError(card, "Raison invalide ou annulée.");
      return;
    }
  }

  if (button.dataset.needsComment) {
    comment = window.prompt("Décrivez la catégorie suggérée :");
    if (!comment) {
      showError(card, "Commentaire requis pour cette action.");
      return;
    }
  }

  try {
    const response = await fetch(`/items/${itemId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, reason, comment }),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      showError(card, body.detail ? JSON.stringify(body.detail) : `Erreur ${response.status}`);
      return;
    }

    const updated = await response.json();
    updateCard(card, updated);
  } catch (err) {
    showError(card, "Erreur réseau.");
  }
});

function showError(card, message) {
  const errorBox = card.querySelector(".feedback-error");
  errorBox.textContent = message;
  errorBox.hidden = false;
}

function updateCard(card, item) {
  const errorBox = card.querySelector(".feedback-error");
  errorBox.hidden = true;
  const statusEl = card.querySelector(".status");
  statusEl.textContent = `Statut : ${item.verification_status || "—"} — traité : ${item.human_decision}`;
}
```

- [ ] **Step 11: Wire it into `src/api/main.py`**

The import block at the top of the file (after Task 4 and Task 5) reads:

```python
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.schemas import NewsItemOut
from src.classification.prompt import CATEGORIES
from src.collectors.sources_config import load_sources_config
from src.config import get_settings
from src.db.models import NewsItem
from src.db.repository import sync_sources
from src.db.session import SessionLocal, get_session
from src.review.schemas import FeedbackIn
from src.review.service import ItemNotFoundError, submit_feedback
from src.scheduler import add_classification_job, add_scoring_job, build_scheduler
from src.scoring.prompt import PRIORITIES
```

Replace it with:

```python
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.schemas import NewsItemOut
from src.api.view_helpers import format_relative_time
from src.classification.prompt import CATEGORIES
from src.collectors.sources_config import load_sources_config
from src.config import get_settings
from src.db.models import NewsItem
from src.db.repository import sync_sources
from src.db.session import SessionLocal, get_session
from src.review.schemas import FeedbackIn, REJECT_REASONS
from src.review.service import ItemNotFoundError, submit_feedback
from src.scheduler import add_classification_job, add_scoring_job, build_scheduler
from src.scoring.prompt import PRIORITIES
```

Right after `app = FastAPI(title="Touch-Go News", lifespan=lifespan)`, add (order relative to
Task 5's `_VIEW_TO_PRIORITY`/`_SINCE_TO_DELTA`/`_filtered_items` block, which sits in the same
spot, doesn't matter — both are independent top-level definitions):

```python
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.filters["relative_time"] = format_relative_time
```

Add this route (anywhere after that setup, e.g. right before `list_items`):

```python
@app.get("/", response_class=HTMLResponse)
def review_page(
    request: Request,
    priority: str | None = None,
    category: str | None = None,
    since: str | None = None,
    view: str | None = None,
    session: Session = Depends(get_session),
):
    items = _filtered_items(session, priority, category, since, view)
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "items": items,
            "priorities": PRIORITIES,
            "categories": CATEGORIES,
            "reject_reasons": REJECT_REASONS,
            "current_priority": priority,
            "current_category": category,
            "current_since": since,
            "current_view": view,
        },
    )
```

(`HTMLResponse` was already added to the import block above.)

The five decisions are hardcoded as buttons in `review.html` (matching design §6), so `DECISIONS`
itself has no consumer in this task — only `REJECT_REASONS` is needed, to populate
`window.REJECT_REASONS` for the ❌ prompt.

- [ ] **Step 12: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/api/test_review_page.py -v`
Expected: PASS (3 tests)

- [ ] **Step 13: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: PASS (every test, no regressions).

- [ ] **Step 14: Manual verification**

```bash
docker compose up -d
.venv/bin/alembic upgrade head
.venv/bin/uvicorn src.api.main:app --reload
```

With at least one classified-and-scored item in the database (from a prior sprint's manual
verification, or insert one directly): open `http://localhost:8000/` in a browser and confirm:

- The page renders cards with badges, scores, and the five action buttons.
- Clicking each of 🔥/👍/👀 immediately updates the card's "Statut" line without a page reload.
- Clicking ❌ prompts for a reason from the closed list, rejects a made-up reason (card shows an
  error), and accepts one from the list (card updates).
- Clicking ➕ prompts for a comment, rejects an empty one, accepts a filled one.
- Changing the priority/category/period selects reloads the page with the item list filtered
  accordingly. Clicking each of the three view links (À voir / À surveiller / Faible priorité)
  shows only A / B / C items respectively.
- `curl -X POST http://localhost:8000/items/<some-id>/feedback -H 'Content-Type: application/json' -d '{"decision":"INTERESSANT"}'`
  returns 200 with `reviewer_id` defaulted from `.env`'s `DEFAULT_REVIEWER_ID` (or the built-in
  default `"reviewer"` if unset).

- [ ] **Step 15: Commit**

```bash
git add src/api/view_helpers.py src/api/main.py templates/review.html static/review.css static/review.js pyproject.toml tests/api/test_view_helpers.py tests/api/test_review_page.py
git commit -m "feat: add server-rendered review page with filters and feedback actions"
```

---

### Task 7: End-to-end integration test — score, filter, and give feedback through the real API

**Files:**
- Modify: `tests/test_integration_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 1-6, plus the existing collection/classification/scoring
  pipelines already on `main`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_integration_pipeline.py` (it already has `FEED`, and imports everything this
test needs: `httpx`, `pytest`, `respx`, `TestClient`, `app`, `get_session`, `run_collection`,
`SourceConfig`, `build_collector`, `NewsItem`, `job_module`, `ClassificationResult`,
`classify_pending_items`, `scoring_job_module`, `ScoringResult`, `score_pending_items` — no new
imports needed):

```python
@pytest.mark.asyncio
@respx.mock
async def test_scored_items_can_receive_feedback_and_be_filtered_via_the_review_endpoints(
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

    async def fake_classify_item(title, text, client=None):
        return ClassificationResult(
            primary_category="COMMERCIAL",
            secondary_categories=[],
            classification_confidence=0.6,
            reasoning="Test classification.",
        )

    monkeypatch.setattr(job_module, "classify_item", fake_classify_item)
    classification_result = await classify_pending_items(db_session, batch_size=10, max_attempts=5)
    assert classification_result.classified == 2

    async def fake_score_item(title, text, source_type, client=None):
        return ScoringResult(
            touchgo_interest=8,
            event_importance=7,
            source_confidence=6,
            urgency=5,
            priority="A",
            reasoning="Test scoring.",
        )

    monkeypatch.setattr(scoring_job_module, "score_item", fake_score_item)
    scoring_result = await score_pending_items(db_session, batch_size=10, max_attempts=5)
    assert scoring_result.scored == 2

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        client = TestClient(app)

        view_response = client.get("/items", params={"view": "a_voir"})
        assert view_response.status_code == 200
        items = view_response.json()
        assert len(items) == 2

        target_id = items[0]["id"]
        feedback_response = client.post(
            f"/items/{target_id}/feedback", json={"decision": "TRES_INTERESSANT"}
        )
        assert feedback_response.status_code == 200
        assert feedback_response.json()["human_decision"] == "TRES_INTERESSANT"
        assert feedback_response.json()["reviewer_id"]

        after_feedback = client.get("/items", params={"view": "a_voir"}).json()
        treated = next(item for item in after_feedback if item["id"] == target_id)
        assert treated["human_decision"] == "TRES_INTERESSANT"

        page_response = client.get("/", params={"view": "a_voir"})
        assert page_response.status_code == 200
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_integration_pipeline.py::test_scored_items_can_receive_feedback_and_be_filtered_via_the_review_endpoints -v`
Expected: this should already PASS once Tasks 1-6 are done, since it only exercises code paths
those tasks already built and tested individually — expected, not a TDD violation. If it fails,
diagnose against what Tasks 1-6 actually produced rather than assuming the test is wrong.

- [ ] **Step 3: Run the full test suite**

Run: `.venv/bin/pytest -v`
Expected: every test across Sprints 1-5 passes, output as clean as the pre-existing run (only the
one known pre-existing FastAPI/Starlette deprecation warning).

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_pipeline.py
git commit -m "test: add end-to-end score-filter-feedback integration test"
```
