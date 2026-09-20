# Touch-Go News — Sprint 1 (Collecte) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `touchgo-news` service — repo scaffolding, Postgres schema, a config-driven collector framework, and a scheduler — so that raw news items from 6 initial sources (RSS + one forum) land untouched in the database and are visible through a minimal read-only API.

**Architecture:** A FastAPI process hosts an APScheduler instance that periodically runs one `Collector` per configured source (`config/sources.yaml`). Each collector fetches raw content and returns `RawItem` objects; a runner persists them via a repository layer that enforces `(source_id, source_item_id)` uniqueness and records per-source run status. No normalization, deduplication, or classification happens in this sprint — items are stored as-is with `status = "NEW"`.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2 / pydantic-settings, httpx, feedparser, BeautifulSoup4, APScheduler, PostgreSQL 16 (Docker Compose), pytest / pytest-asyncio / respx.

**Spec:** [`docs/superpowers/specs/2026-09-20-touchgo-news-sprint1-collecte-design.md`](../specs/2026-09-20-touchgo-news-sprint1-collecte-design.md) (implements Sprint 1 of [`SPEC.md`](../../../SPEC.md), sections 25-27 and 34).

## Global Constraints

- Aucune publication automatique, jamais (SPEC.md section 1) — ce sprint ne touche à aucune API de publication.
- Aucune suppression automatique de contenu collecté (SPEC.md sections 2, 12) — un item inséré n'est jamais supprimé par le pipeline.
- Collecte et classification strictement séparées (SPEC.md section 30) — les collecteurs ne décident jamais si un item est intéressant.
- Python 3.12+, stack imposée par SPEC.md section 26 (FastAPI, SQLAlchemy, Pydantic, httpx, feedparser, BeautifulSoup, YAML).
- Chaque collecteur est isolé : l'échec d'une source ne doit jamais interrompre les autres (design doc section 6).
- Priorité de collecte RSS > API publique > HTML statique > scraping > navigateur automatisé (SPEC.md section 27) — respectée : 5 sources RSS confirmées + 1 source forum en scraping HTML, aucune source en dernier recours (Playwright) dans ce sprint.

---

## Known risk carried into Task 7 (read before implementing)

During planning, live verification (`curl`) confirmed working RSS feeds for FlightGlobal, Airbus,
Opex360, BMPD and TASS, but **pprune.org is behind Cloudflare and returned HTTP 403** to a plain
`curl` from the planning environment — the real thread-listing HTML could not be inspected. The
CSS selectors used in Task 7 (`li.threadbit` / `a.title`) are a best-effort guess based on
PPRuNe's known vBulletin platform, verified only against a hand-built fixture, **not against the
live site**. BEA, EASA, Aeronet, Aviation Herald and a Chinese-language source were also checked
live and found to have **no working RSS feed** (404s, stale feeds, or JS-rendered pages) — they
are explicitly out of scope for this plan (see Task 4).

When executing Task 7, from a normal (non-sandboxed) network: fetch
`https://www.pprune.org/military-aviation/` in a real browser, inspect the actual thread-row
markup, and adjust `THREAD_ROW_SELECTOR` / `TITLE_LINK_SELECTOR` in `src/collectors/forum_pprune.py`
if they don't match. If `httpx` receives a 403 (Cloudflare JS challenge) instead of HTML, this
source needs a Playwright-based fetch instead of `httpx` — this is precisely the "last resort"
case allowed by SPEC.md section 27, and should be filed as a fast-follow task rather than blocking
the rest of Sprint 1.

---

### Task 1: Project scaffolding, dependencies, Postgres via Docker Compose

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `docker-compose.yml`
- Create: `docker/initdb/01-create-test-db.sql`
- Create: `src/__init__.py`
- Modify: rename `TouchGo-News-SPEC.md` → `SPEC.md`
- Modify: `docs/superpowers/specs/2026-09-20-touchgo-news-sprint1-collecte-design.md` (fix relative link after rename)

**Interfaces:**
- Produces: a working `pip install -e .` / venv with all runtime + dev dependencies, and a running Postgres reachable at `postgresql+psycopg://touchgo:touchgo@localhost:5432/touchgo_news` (dev) and `.../touchgo_news_test` (test).

- [ ] **Step 1: Rename the spec file and fix the design doc's link**

```bash
git mv TouchGo-News-SPEC.md SPEC.md
```

In `docs/superpowers/specs/2026-09-20-touchgo-news-sprint1-collecte-design.md`, change:
```
[`TouchGo-News-SPEC.md`](../../../TouchGo-News-SPEC.md)
```
to:
```
[`SPEC.md`](../../../SPEC.md)
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "touchgo-news"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "httpx>=0.27",
    "feedparser>=6.0",
    "beautifulsoup4>=4.12",
    "apscheduler>=3.10",
    "psycopg[binary]>=3.1",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["src*"]
```

- [ ] **Step 3: Create `.env.example`**

```
DATABASE_URL=postgresql+psycopg://touchgo:touchgo@localhost:5432/touchgo_news
SOURCES_CONFIG_PATH=config/sources.yaml
```

- [ ] **Step 4: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.env
.pytest_cache/
*.egg-info/
```

- [ ] **Step 5: Create `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: touchgo
      POSTGRES_PASSWORD: touchgo
      POSTGRES_DB: touchgo_news
    ports:
      - "5432:5432"
    volumes:
      - touchgo_news_pgdata:/var/lib/postgresql/data
      - ./docker/initdb:/docker-entrypoint-initdb.d

volumes:
  touchgo_news_pgdata:
```

- [ ] **Step 6: Create `docker/initdb/01-create-test-db.sql`**

```sql
CREATE DATABASE touchgo_news_test;
```

- [ ] **Step 7: Create `src/__init__.py`** (empty file)

- [ ] **Step 8: Bring up Postgres and install dependencies**

```bash
docker compose up -d
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: `docker compose ps` shows the `db` service healthy; `psql
postgresql://touchgo:touchgo@localhost:5432/touchgo_news_test -c '\q'` connects without error.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "chore: project scaffolding, Docker Postgres, rename SPEC.md"
```

---

### Task 2: Settings

**Files:**
- Create: `src/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings` (pydantic-settings model with `database_url: str`, `sources_config_path: str`), `get_settings() -> Settings` (cached).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import os

from src.config import Settings


def test_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host:5432/db")
    monkeypatch.setenv("SOURCES_CONFIG_PATH", "config/sources.yaml")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db"
    assert settings.sources_config_path == "config/sources.yaml"


def test_settings_have_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SOURCES_CONFIG_PATH", raising=False)
    settings = Settings(_env_file=None)
    assert "touchgo_news" in settings.database_url
    assert settings.sources_config_path == "config/sources.yaml"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/config.py
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://touchgo:touchgo@localhost:5432/touchgo_news"
    sources_config_path: str = "config/sources.yaml"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add Settings for database URL and sources config path"
```

---

### Task 3: Database models and initial migration

**Files:**
- Create: `src/db/__init__.py`
- Create: `src/db/base.py`
- Create: `src/db/models.py`
- Create: `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/` (via `alembic init`)
- Test: `tests/db/test_models.py`
- Test: `tests/conftest.py`

**Interfaces:**
- Produces: `Base` (SQLAlchemy `DeclarativeBase`), ORM classes `NewsSource`, `NewsItem`, `NewsEvent`, `NewsFeedback` (columns per SPEC.md section 16, plus `last_run_at` / `last_run_status` / `last_run_error` on `NewsSource` for Sprint 1 robustness — see design doc section 6).
- Consumes: `get_settings()` from Task 2.

- [ ] **Step 1: Create `src/db/__init__.py`** (empty) and `src/db/base.py`

```python
# src/db/base.py
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 2: Write `src/db/models.py`**

```python
# src/db/models.py
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NewsSource(Base):
    __tablename__ = "news_source"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False)
    confirmation_level: Mapped[str | None] = mapped_column(String, nullable=True)
    detection_value: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_run_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class NewsItem(Base):
    __tablename__ = "news_item"
    __table_args__ = (
        UniqueConstraint("source_id", "source_item_id", name="uq_news_item_source_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("news_source.id"), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String, nullable=False)
    canonical_url: Mapped[str] = mapped_column(String, nullable=False)
    original_url: Mapped[str] = mapped_column(String, nullable=False)
    original_title: Mapped[str] = mapped_column(Text, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    primary_category: Mapped[str | None] = mapped_column(String, nullable=True)
    secondary_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    country: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    entities: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    touchgo_interest: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_importance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    urgency: Mapped[int | None] = mapped_column(Integer, nullable=True)

    priority: Mapped[str | None] = mapped_column(String, nullable=True)
    verification_status: Mapped[str | None] = mapped_column(String, nullable=True)

    duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("news_item.id"), nullable=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("news_event.id"), nullable=True)

    status: Mapped[str] = mapped_column(String, default="NEW", nullable=False)

    model_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    human_decision: Mapped[str | None] = mapped_column(String, nullable=True)
    human_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    human_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(String, nullable=True)


class NewsEvent(Base):
    __tablename__ = "news_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    importance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_status: Mapped[str | None] = mapped_column(String, nullable=True)
    summary_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class NewsFeedback(Base):
    __tablename__ = "news_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    news_item_id: Mapped[int] = mapped_column(ForeignKey("news_item.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_priority: Mapped[str | None] = mapped_column(String, nullable=True)
    previous_category: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    reviewer_id: Mapped[str | None] = mapped_column(String, nullable=True)
```

- [ ] **Step 3: Write `tests/conftest.py`**

```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.base import Base
from src.db.models import NewsSource  # noqa: F401 ensures metadata is populated

TEST_DATABASE_URL = "postgresql+psycopg://touchgo:touchgo@localhost:5432/touchgo_news_test"


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, future=True, expire_on_commit=False)
    session = session_factory()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def make_source(db_session):
    def _make(source_id: str = "test-source", **overrides) -> NewsSource:
        source = NewsSource(
            id=source_id,
            name=overrides.get("name", "Test Source"),
            url=overrides.get("url", "https://example.com/feed"),
            source_type=overrides.get("source_type", "press"),
            language=overrides.get("language", "en"),
            active=overrides.get("active", True),
        )
        db_session.add(source)
        db_session.commit()
        return source

    return _make
```

- [ ] **Step 4: Write the failing test**

```python
# tests/db/test_models.py
from datetime import datetime, timezone

from src.db.models import NewsItem


def test_insert_and_query_news_item(db_session, make_source):
    make_source(source_id="flightglobal")
    item = NewsItem(
        source_id="flightglobal",
        source_item_id="abc123",
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Title",
        original_text="Body",
        language="en",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(item)
    db_session.commit()

    fetched = db_session.query(NewsItem).filter_by(source_item_id="abc123").one()
    assert fetched.status == "NEW"
    assert fetched.primary_category is None
    assert fetched.detected_at is not None


def test_duplicate_source_item_id_rejected(db_session, make_source):
    make_source(source_id="flightglobal")
    db_session.add(
        NewsItem(
            source_id="flightglobal",
            source_item_id="dup",
            canonical_url="https://example.com/a",
            original_url="https://example.com/a",
            original_title="A",
            original_text="A",
        )
    )
    db_session.commit()

    db_session.add(
        NewsItem(
            source_id="flightglobal",
            source_item_id="dup",
            canonical_url="https://example.com/b",
            original_url="https://example.com/b",
            original_title="B",
            original_text="B",
        )
    )
    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db_session.commit()
```

Test file needs an `__init__.py` sibling directory: create empty `tests/__init__.py` and `tests/db/__init__.py` if your pytest config requires package-style test discovery (not required with default rootdir-relative discovery, skip unless imports fail).

- [ ] **Step 5: Run test to verify it fails**

Run: `pytest tests/db/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.db.models'` (or connection error if Postgres isn't up yet — start it with `docker compose up -d` first)

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/db/test_models.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Set up Alembic and generate the initial migration**

```bash
alembic init alembic
```

Edit `alembic/env.py`: after the existing imports, add:

```python
from src.config import get_settings
from src.db.base import Base
from src.db import models  # noqa: F401 populate Base.metadata

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata
```

Replace the file's existing `target_metadata = None` line with the block above (keep it right
after the existing `config = context.config` line, before `target_metadata` is first used); leave
the rest of the generated boilerplate (the `run_migrations_offline` / `run_migrations_online`
functions and their invocation at the bottom of the file) untouched.

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Expected: a new file under `alembic/versions/` creating `news_source`, `news_item`, `news_event`,
`news_feedback`; `alembic upgrade head` runs against the **dev** database
(`touchgo_news`, from `.env` / default) without error.

- [ ] **Step 8: Commit**

```bash
git add src/db alembic alembic.ini tests/conftest.py tests/db/test_models.py .env.example
git commit -m "feat: add NewsSource/NewsItem/NewsEvent/NewsFeedback models and initial migration"
```

---

### Task 4: Sources configuration loading

**Files:**
- Create: `src/collectors/__init__.py`
- Create: `src/collectors/sources_config.py`
- Create: `config/sources.yaml`
- Test: `tests/collectors/test_sources_config.py`
- Test fixture: `tests/fixtures/sources_sample.yaml`

**Interfaces:**
- Produces: `SourceConfig` (pydantic model: `id: str, name: str, type: str, url: str, language: str, source_type: str, poll_interval_minutes: int, active: bool = True`), `load_sources_config(path: str | Path) -> list[SourceConfig]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/collectors/test_sources_config.py
from pathlib import Path

from src.collectors.sources_config import SourceConfig, load_sources_config

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sources_sample.yaml"
REAL_CONFIG = Path(__file__).parent.parent.parent / "config" / "sources.yaml"


def test_load_sources_config_parses_fixture():
    sources = load_sources_config(FIXTURE)
    assert sources == [
        SourceConfig(
            id="example",
            name="Example Feed",
            type="rss",
            url="https://example.com/feed",
            language="en",
            source_type="press",
            poll_interval_minutes=30,
            active=True,
        )
    ]


def test_real_sources_config_is_valid_and_has_six_active_sources():
    sources = load_sources_config(REAL_CONFIG)
    active_ids = {s.id for s in sources if s.active}
    assert active_ids == {
        "flightglobal",
        "airbus",
        "opex360",
        "bmpd",
        "tass",
        "pprune_military",
    }
```

- [ ] **Step 2: Create the fixture**

```yaml
# tests/fixtures/sources_sample.yaml
sources:
  - id: example
    name: Example Feed
    type: rss
    url: https://example.com/feed
    language: en
    source_type: press
    poll_interval_minutes: 30
    active: true
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/collectors/test_sources_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collectors.sources_config'`

- [ ] **Step 4: Write `src/collectors/__init__.py`** (empty) and `src/collectors/sources_config.py`

```python
# src/collectors/sources_config.py
from pathlib import Path

import yaml
from pydantic import BaseModel


class SourceConfig(BaseModel):
    id: str
    name: str
    type: str
    url: str
    language: str
    source_type: str
    poll_interval_minutes: int
    active: bool = True


def load_sources_config(path: str | Path) -> list[SourceConfig]:
    data = yaml.safe_load(Path(path).read_text())
    return [SourceConfig(**entry) for entry in data["sources"]]
```

- [ ] **Step 5: Write the real `config/sources.yaml`**

These 6 sources were live-verified during planning (RSS URLs return HTTP 200 with RSS/XML
content; PPRuNe's HTML structure could not be verified — see the "Known risk" note above Task 1).

```yaml
sources:
  - id: flightglobal
    name: FlightGlobal
    type: rss
    url: https://www.flightglobal.com/rss
    language: en
    source_type: press
    poll_interval_minutes: 30
    active: true

  - id: airbus
    name: Airbus Newsroom
    type: rss
    url: https://www.airbus.com/en/rss.xml
    language: en
    source_type: official
    poll_interval_minutes: 30
    active: true

  - id: opex360
    name: Opex360
    type: rss
    url: https://www.opex360.com/feed/
    language: fr
    source_type: press
    poll_interval_minutes: 20
    active: true

  - id: bmpd
    name: BMPD
    type: rss
    url: https://bmpd.livejournal.com/data/rss
    language: ru
    source_type: media
    poll_interval_minutes: 30
    active: true

  - id: tass
    name: TASS
    type: rss
    url: https://tass.com/rss/v2.xml
    language: en
    source_type: official
    poll_interval_minutes: 30
    active: true

  - id: pprune_military
    name: "PPRuNe - Military Aviation"
    type: forum_pprune
    url: https://www.pprune.org/military-aviation/
    language: en
    source_type: community
    poll_interval_minutes: 60
    active: true
```

Note: `tass` pulls TASS's general newswire (no aviation-specific section was confirmed working),
and is intentionally broad per the MVP's recall-first philosophy (SPEC.md section 2) — narrowing
it is a classification-time concern (Sprint 3), not a collection-time one.

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/collectors/test_sources_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add src/collectors/__init__.py src/collectors/sources_config.py config/sources.yaml \
  tests/collectors/test_sources_config.py tests/fixtures/sources_sample.yaml
git commit -m "feat: load sources.yaml into SourceConfig, add 6 verified initial sources"
```

---

### Task 5: Collector base types

**Files:**
- Create: `src/collectors/base.py`
- Test: `tests/collectors/test_base.py`

**Interfaces:**
- Produces: `RawItem` (pydantic model), `Collector` (ABC with `source_id: str` and `async def fetch(self) -> list[RawItem]`).

- [ ] **Step 1: Write the failing test**

```python
# tests/collectors/test_base.py
import pytest

from src.collectors.base import Collector, RawItem


def test_raw_item_requires_core_fields():
    item = RawItem(
        source_item_id="1",
        canonical_url="https://example.com/1",
        original_url="https://example.com/1",
        original_title="Title",
        original_text="Text",
        language="en",
    )
    assert item.author is None
    assert item.published_at is None


def test_collector_is_abstract():
    with pytest.raises(TypeError):
        Collector(source_id="x")  # type: ignore[abstract]


@pytest.mark.asyncio
async def test_collector_subclass_must_implement_fetch():
    class Incomplete(Collector):
        pass

    with pytest.raises(TypeError):
        Incomplete(source_id="x")  # type: ignore[abstract]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/collectors/test_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collectors.base'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/collectors/base.py
from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class RawItem(BaseModel):
    source_item_id: str
    canonical_url: str
    original_url: str
    original_title: str
    original_text: str
    language: str
    author: str | None = None
    published_at: datetime | None = None
    raw_metadata: dict = {}


class Collector(ABC):
    def __init__(self, source_id: str):
        self.source_id = source_id

    @abstractmethod
    async def fetch(self) -> list[RawItem]:
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/collectors/test_base.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/collectors/base.py tests/collectors/test_base.py
git commit -m "feat: add RawItem and Collector base types"
```

---

### Task 6: RSS collector

**Files:**
- Create: `src/collectors/rss.py`
- Test: `tests/collectors/test_rss_collector.py`
- Test fixture: `tests/fixtures/sample_feed.xml`

**Interfaces:**
- Consumes: `Collector`, `RawItem` (Task 5).
- Produces: `RSSCollector(source_id: str, feed_url: str, http_client: httpx.AsyncClient | None = None)` with `async fetch() -> list[RawItem]`.

- [ ] **Step 1: Create the fixture**

```xml
<!-- tests/fixtures/sample_feed.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Feed</title>
    <item>
      <title>First article</title>
      <link>https://example.com/articles/1</link>
      <guid>https://example.com/articles/1</guid>
      <description>Summary of the first article.</description>
      <author>jane@example.com</author>
      <pubDate>Mon, 01 Jan 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Second article</title>
      <link>https://example.com/articles/2</link>
      <guid>https://example.com/articles/2</guid>
      <description>Summary of the second article.</description>
      <pubDate>Tue, 02 Jan 2026 08:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>
```

- [ ] **Step 2: Write the failing test**

```python
# tests/collectors/test_rss_collector.py
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx

from src.collectors.rss import RSSCollector

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "sample_feed.xml").read_text()


@pytest.mark.asyncio
@respx.mock
async def test_rss_collector_parses_entries_into_raw_items():
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=FIXTURE, headers={"content-type": "application/rss+xml"})
    )
    collector = RSSCollector(source_id="example", feed_url="https://example.com/feed")

    items = await collector.fetch()

    assert len(items) == 2
    first = items[0]
    assert first.source_item_id == "https://example.com/articles/1"
    assert first.original_title == "First article"
    assert first.original_url == "https://example.com/articles/1"
    assert first.canonical_url == "https://example.com/articles/1"
    assert first.original_text == "Summary of the first article."
    assert first.author == "jane@example.com"
    assert first.published_at == datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
@respx.mock
async def test_rss_collector_raises_on_http_error():
    respx.get("https://example.com/feed").mock(return_value=httpx.Response(500))
    collector = RSSCollector(source_id="example", feed_url="https://example.com/feed")

    with pytest.raises(httpx.HTTPStatusError):
        await collector.fetch()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/collectors/test_rss_collector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collectors.rss'`

- [ ] **Step 4: Write minimal implementation**

```python
# src/collectors/rss.py
from datetime import datetime, timezone

import feedparser
import httpx

from src.collectors.base import Collector, RawItem

_HEADERS = {"User-Agent": "TouchGoNewsBot/0.1 (+https://touch-go.example)"}


class RSSCollector(Collector):
    def __init__(
        self,
        source_id: str,
        feed_url: str,
        http_client: httpx.AsyncClient | None = None,
    ):
        super().__init__(source_id)
        self.feed_url = feed_url
        self._http_client = http_client

    async def fetch(self) -> list[RawItem]:
        body = await self._fetch_body()
        parsed = feedparser.parse(body)
        return [self._to_raw_item(entry) for entry in parsed.entries]

    async def _fetch_body(self) -> str:
        if self._http_client is not None:
            response = await self._http_client.get(self.feed_url, headers=_HEADERS)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self.feed_url, headers=_HEADERS)
        response.raise_for_status()
        return response.text

    @staticmethod
    def _to_raw_item(entry) -> RawItem:
        link = entry.get("link", "")
        return RawItem(
            source_item_id=entry.get("id") or link,
            canonical_url=link,
            original_url=link,
            original_title=entry.get("title", ""),
            original_text=entry.get("summary", ""),
            language="",
            author=entry.get("author"),
            published_at=_parse_published(entry),
        )


def _parse_published(entry) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None)
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/collectors/test_rss_collector.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/collectors/rss.py tests/collectors/test_rss_collector.py tests/fixtures/sample_feed.xml
git commit -m "feat: add RSSCollector"
```

---

### Task 7: PPRuNe forum collector

**Files:**
- Create: `src/collectors/forum_pprune.py`
- Test: `tests/collectors/test_forum_pprune_collector.py`
- Test fixture: `tests/fixtures/pprune_thread_list.html`

**Interfaces:**
- Consumes: `Collector`, `RawItem` (Task 5).
- Produces: `PPRuneForumCollector(source_id: str, listing_url: str, http_client: httpx.AsyncClient | None = None)` with `async fetch() -> list[RawItem]`; `parse_thread_listing(html: str, base_url: str) -> list[RawItem]` (pure function, unit-testable without network).

- [ ] **Step 1: Create the fixture**

This mirrors the general vBulletin thread-listing shape PPRuNe is known to run — see the "Known
risk" note above Task 1 for why it could not be verified against the live site.

```html
<!-- tests/fixtures/pprune_thread_list.html -->
<!DOCTYPE html>
<html>
<body>
  <ol id="threads">
    <li class="threadbit">
      <a class="title" href="/military-aviation/654321-new-fighter-programme.html">
        New fighter programme announced
      </a>
    </li>
    <li class="threadbit">
      <a class="title" href="/military-aviation/654322-drone-exercise-report.html">
        Drone exercise report
      </a>
    </li>
    <li class="threadbit sticky">
      <a class="title" href="/military-aviation/1-forum-rules.html">
        Forum rules (read before posting)
      </a>
    </li>
  </ol>
</body>
</html>
```

- [ ] **Step 2: Write the failing test**

```python
# tests/collectors/test_forum_pprune_collector.py
from pathlib import Path

import httpx
import pytest
import respx

from src.collectors.forum_pprune import PPRuneForumCollector, parse_thread_listing

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "pprune_thread_list.html").read_text()


def test_parse_thread_listing_extracts_all_threads():
    items = parse_thread_listing(FIXTURE, base_url="https://www.pprune.org/military-aviation/")

    assert len(items) == 3
    first = items[0]
    assert first.source_item_id == "654321-new-fighter-programme.html"
    assert first.original_title == "New fighter programme announced"
    assert first.original_url == "https://www.pprune.org/military-aviation/654321-new-fighter-programme.html"
    assert first.language == "en"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_uses_parse_thread_listing():
    respx.get("https://www.pprune.org/military-aviation/").mock(
        return_value=httpx.Response(200, text=FIXTURE)
    )
    collector = PPRuneForumCollector(
        source_id="pprune_military",
        listing_url="https://www.pprune.org/military-aviation/",
    )

    items = await collector.fetch()

    assert len(items) == 3
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/collectors/test_forum_pprune_collector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collectors.forum_pprune'`

- [ ] **Step 4: Write minimal implementation**

```python
# src/collectors/forum_pprune.py
import httpx
from bs4 import BeautifulSoup

from src.collectors.base import Collector, RawItem

# Best-effort selectors for PPRuNe's vBulletin thread listing. pprune.org is
# behind Cloudflare and could not be inspected live while writing this
# collector — verify against the real page before relying on this in
# production (see the plan's "Known risk" note).
THREAD_ROW_SELECTOR = "li.threadbit"
TITLE_LINK_SELECTOR = "a.title"

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TouchGoNewsBot/0.1)"}


class PPRuneForumCollector(Collector):
    def __init__(
        self,
        source_id: str,
        listing_url: str,
        http_client: httpx.AsyncClient | None = None,
    ):
        super().__init__(source_id)
        self.listing_url = listing_url
        self._http_client = http_client

    async def fetch(self) -> list[RawItem]:
        html = await self._fetch_html()
        return parse_thread_listing(html, base_url=self.listing_url)

    async def _fetch_html(self) -> str:
        if self._http_client is not None:
            response = await self._http_client.get(self.listing_url, headers=_HEADERS)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self.listing_url, headers=_HEADERS)
        response.raise_for_status()
        return response.text


def parse_thread_listing(html: str, base_url: str) -> list[RawItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[RawItem] = []
    for row in soup.select(THREAD_ROW_SELECTOR):
        link = row.select_one(TITLE_LINK_SELECTOR)
        if link is None or not link.get("href"):
            continue
        href = link["href"]
        url = href if href.startswith("http") else str(httpx.URL(base_url).join(href))
        thread_id = href.rstrip("/").rsplit("/", 1)[-1]
        title = link.get_text(strip=True)
        items.append(
            RawItem(
                source_item_id=thread_id,
                canonical_url=url,
                original_url=url,
                original_title=title,
                original_text=title,
                language="en",
            )
        )
    return items
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/collectors/test_forum_pprune_collector.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/collectors/forum_pprune.py tests/collectors/test_forum_pprune_collector.py \
  tests/fixtures/pprune_thread_list.html
git commit -m "feat: add PPRuNe forum thread-listing collector (selectors unverified, see plan note)"
```

---

### Task 8: Collector factory

**Files:**
- Create: `src/collectors/factory.py`
- Test: `tests/collectors/test_factory.py`

**Interfaces:**
- Consumes: `SourceConfig` (Task 4), `RSSCollector` (Task 6), `PPRuneForumCollector` (Task 7).
- Produces: `build_collector(source_config: SourceConfig) -> Collector`.

- [ ] **Step 1: Write the failing test**

```python
# tests/collectors/test_factory.py
import pytest

from src.collectors.factory import build_collector
from src.collectors.forum_pprune import PPRuneForumCollector
from src.collectors.rss import RSSCollector
from src.collectors.sources_config import SourceConfig


def _config(**overrides) -> SourceConfig:
    base = dict(
        id="s1",
        name="Source 1",
        type="rss",
        url="https://example.com/feed",
        language="en",
        source_type="press",
        poll_interval_minutes=30,
    )
    base.update(overrides)
    return SourceConfig(**base)


def test_build_collector_rss():
    collector = build_collector(_config(type="rss"))
    assert isinstance(collector, RSSCollector)
    assert collector.source_id == "s1"
    assert collector.feed_url == "https://example.com/feed"


def test_build_collector_forum_pprune():
    collector = build_collector(_config(type="forum_pprune"))
    assert isinstance(collector, PPRuneForumCollector)
    assert collector.listing_url == "https://example.com/feed"


def test_build_collector_unknown_type_raises():
    with pytest.raises(ValueError, match="Unknown collector type"):
        build_collector(_config(type="carrier_pigeon"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/collectors/test_factory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collectors.factory'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/collectors/factory.py
from src.collectors.base import Collector
from src.collectors.forum_pprune import PPRuneForumCollector
from src.collectors.rss import RSSCollector
from src.collectors.sources_config import SourceConfig


def build_collector(source_config: SourceConfig) -> Collector:
    if source_config.type == "rss":
        return RSSCollector(source_id=source_config.id, feed_url=source_config.url)
    if source_config.type == "forum_pprune":
        return PPRuneForumCollector(source_id=source_config.id, listing_url=source_config.url)
    raise ValueError(f"Unknown collector type: {source_config.type}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/collectors/test_factory.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/collectors/factory.py tests/collectors/test_factory.py
git commit -m "feat: add collector factory mapping SourceConfig.type to a Collector"
```

---

### Task 9: Repository (persistence)

**Files:**
- Create: `src/db/repository.py`
- Test: `tests/db/test_repository.py`

**Interfaces:**
- Consumes: `NewsItem`, `NewsSource` (Task 3), `RawItem` (Task 5).
- Produces: `SaveResult` (dataclass: `inserted: int, skipped_duplicates: int`), `save_raw_items(session: Session, source_id: str, items: list[RawItem]) -> SaveResult`, `update_source_run_status(session: Session, source_id: str, status: str, error: str | None = None) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/db/test_repository.py
from src.collectors.base import RawItem
from src.db.models import NewsItem, NewsSource
from src.db.repository import save_raw_items, update_source_run_status


def _raw_item(source_item_id: str) -> RawItem:
    return RawItem(
        source_item_id=source_item_id,
        canonical_url=f"https://example.com/{source_item_id}",
        original_url=f"https://example.com/{source_item_id}",
        original_title=f"Title {source_item_id}",
        original_text="Body",
        language="en",
    )


def test_save_raw_items_inserts_new_items(db_session, make_source):
    make_source(source_id="flightglobal")

    result = save_raw_items(db_session, "flightglobal", [_raw_item("1"), _raw_item("2")])

    assert result.inserted == 2
    assert result.skipped_duplicates == 0
    assert db_session.query(NewsItem).count() == 2


def test_save_raw_items_skips_existing_duplicates(db_session, make_source):
    make_source(source_id="flightglobal")
    save_raw_items(db_session, "flightglobal", [_raw_item("1")])

    result = save_raw_items(db_session, "flightglobal", [_raw_item("1"), _raw_item("2")])

    assert result.inserted == 1
    assert result.skipped_duplicates == 1
    assert db_session.query(NewsItem).count() == 2


def test_update_source_run_status_records_success(db_session, make_source):
    make_source(source_id="flightglobal")

    update_source_run_status(db_session, "flightglobal", status="OK")

    source = db_session.get(NewsSource, "flightglobal")
    assert source.last_run_status == "OK"
    assert source.last_run_at is not None
    assert source.last_run_error is None


def test_update_source_run_status_records_failure(db_session, make_source):
    make_source(source_id="flightglobal")

    update_source_run_status(db_session, "flightglobal", status="FAILED", error="timeout")

    source = db_session.get(NewsSource, "flightglobal")
    assert source.last_run_status == "FAILED"
    assert source.last_run_error == "timeout"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/db/test_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.db.repository'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/db/repository.py
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.collectors.base import RawItem
from src.db.models import NewsItem, NewsSource


@dataclass
class SaveResult:
    inserted: int
    skipped_duplicates: int


def save_raw_items(session: Session, source_id: str, items: list[RawItem]) -> SaveResult:
    inserted = 0
    skipped = 0
    for item in items:
        already_exists = session.execute(
            select(NewsItem.id).where(
                NewsItem.source_id == source_id,
                NewsItem.source_item_id == item.source_item_id,
            )
        ).first()
        if already_exists:
            skipped += 1
            continue
        session.add(
            NewsItem(
                source_id=source_id,
                source_item_id=item.source_item_id,
                canonical_url=item.canonical_url,
                original_url=item.original_url,
                original_title=item.original_title,
                original_text=item.original_text,
                language=item.language or None,
                author=item.author,
                published_at=item.published_at,
                status="NEW",
            )
        )
        inserted += 1
    session.commit()
    return SaveResult(inserted=inserted, skipped_duplicates=skipped)


def update_source_run_status(
    session: Session, source_id: str, status: str, error: str | None = None
) -> None:
    source = session.get(NewsSource, source_id)
    if source is None:
        return
    source.last_run_at = datetime.now(timezone.utc)
    source.last_run_status = status
    source.last_run_error = error
    session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/db/test_repository.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/db/repository.py tests/db/test_repository.py
git commit -m "feat: add repository for persisting RawItems and source run status"
```

---

### Task 10: Collection runner (error isolation)

**Files:**
- Create: `src/collectors/runner.py`
- Test: `tests/collectors/test_runner.py`

**Interfaces:**
- Consumes: `Collector` (Task 5), `SourceConfig` (Task 4), `save_raw_items` / `update_source_run_status` (Task 9).
- Produces: `CollectionResult` (dataclass: `source_id: str, ok: bool, inserted: int = 0, skipped_duplicates: int = 0, error: str | None = None`), `async def run_collection(session: Session, source_config: SourceConfig, collector: Collector) -> CollectionResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/collectors/test_runner.py
import pytest

from src.collectors.base import Collector, RawItem
from src.collectors.runner import run_collection
from src.collectors.sources_config import SourceConfig
from src.db.models import NewsItem, NewsSource


def _config(source_id: str = "s1") -> SourceConfig:
    return SourceConfig(
        id=source_id,
        name="Source",
        type="rss",
        url="https://example.com/feed",
        language="en",
        source_type="press",
        poll_interval_minutes=30,
    )


class _WorkingCollector(Collector):
    async def fetch(self) -> list[RawItem]:
        return [
            RawItem(
                source_item_id="1",
                canonical_url="https://example.com/1",
                original_url="https://example.com/1",
                original_title="Title",
                original_text="Body",
                language="en",
            )
        ]


class _FailingCollector(Collector):
    async def fetch(self) -> list[RawItem]:
        raise httpx_timeout_error()


def httpx_timeout_error() -> Exception:
    import httpx

    return httpx.TimeoutException("timed out")


@pytest.mark.asyncio
async def test_run_collection_persists_items_and_marks_source_ok(db_session, make_source):
    make_source(source_id="s1")
    config = _config()

    result = await run_collection(db_session, config, _WorkingCollector(source_id="s1"))

    assert result.ok is True
    assert result.inserted == 1
    assert db_session.query(NewsItem).count() == 1
    source = db_session.get(NewsSource, "s1")
    assert source.last_run_status == "OK"


@pytest.mark.asyncio
async def test_run_collection_isolates_collector_failure(db_session, make_source):
    make_source(source_id="s1")
    config = _config()

    result = await run_collection(db_session, config, _FailingCollector(source_id="s1"))

    assert result.ok is False
    assert "timed out" in result.error
    assert db_session.query(NewsItem).count() == 0
    source = db_session.get(NewsSource, "s1")
    assert source.last_run_status == "FAILED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/collectors/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collectors.runner'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/collectors/runner.py
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.collectors.base import Collector
from src.collectors.sources_config import SourceConfig
from src.db.repository import save_raw_items, update_source_run_status

logger = logging.getLogger(__name__)


@dataclass
class CollectionResult:
    source_id: str
    ok: bool
    inserted: int = 0
    skipped_duplicates: int = 0
    error: str | None = None


async def run_collection(
    session: Session, source_config: SourceConfig, collector: Collector
) -> CollectionResult:
    try:
        items = await collector.fetch()
        result = save_raw_items(session, source_config.id, items)
        update_source_run_status(session, source_config.id, status="OK")
        return CollectionResult(
            source_id=source_config.id,
            ok=True,
            inserted=result.inserted,
            skipped_duplicates=result.skipped_duplicates,
        )
    except Exception as exc:  # noqa: BLE001 - a single source must never break the others
        logger.exception("Collection failed for source %s", source_config.id)
        update_source_run_status(session, source_config.id, status="FAILED", error=str(exc))
        return CollectionResult(source_id=source_config.id, ok=False, error=str(exc))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/collectors/test_runner.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/collectors/runner.py tests/collectors/test_runner.py
git commit -m "feat: add run_collection with per-source error isolation"
```

---

### Task 11: Scheduler

**Files:**
- Create: `src/scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `SourceConfig` (Task 4), `build_collector` (Task 8), `run_collection` (Task 10).
- Produces: `build_scheduler(sources: list[SourceConfig], session_factory: sessionmaker) -> AsyncIOScheduler`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scheduler.py
from src.collectors.sources_config import SourceConfig
from src.scheduler import build_scheduler


def _config(source_id: str, active: bool = True, interval: int = 30) -> SourceConfig:
    return SourceConfig(
        id=source_id,
        name=source_id,
        type="rss",
        url="https://example.com/feed",
        language="en",
        source_type="press",
        poll_interval_minutes=interval,
        active=active,
    )


def test_build_scheduler_registers_one_job_per_active_source():
    sources = [_config("a"), _config("b", active=False), _config("c")]

    scheduler = build_scheduler(sources, session_factory=lambda: None)

    job_ids = {job.id for job in scheduler.get_jobs()}
    assert job_ids == {"a", "c"}


def test_build_scheduler_uses_configured_interval():
    sources = [_config("a", interval=45)]

    scheduler = build_scheduler(sources, session_factory=lambda: None)

    job = scheduler.get_job("a")
    assert job.trigger.interval.total_seconds() == 45 * 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.scheduler'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.collectors.factory import build_collector
from src.collectors.runner import run_collection
from src.collectors.sources_config import SourceConfig


def build_scheduler(sources: list[SourceConfig], session_factory) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    for source in sources:
        if not source.active:
            continue
        scheduler.add_job(
            _run_source_job,
            "interval",
            minutes=source.poll_interval_minutes,
            id=source.id,
            args=[source, session_factory],
        )
    return scheduler


async def _run_source_job(source: SourceConfig, session_factory) -> None:
    collector = build_collector(source)
    session = session_factory()
    try:
        await run_collection(session, source, collector)
    finally:
        session.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scheduler.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/scheduler.py tests/test_scheduler.py
git commit -m "feat: add APScheduler wiring, one interval job per active source"
```

---

### Task 12: FastAPI app (`/health`, `/items`)

**Files:**
- Create: `src/db/session.py`
- Create: `src/api/__init__.py`
- Create: `src/api/schemas.py`
- Create: `src/api/main.py`
- Test: `tests/api/test_health.py`
- Test: `tests/api/test_items.py`

**Interfaces:**
- Consumes: `get_settings` (Task 2), `NewsItem` (Task 3), `load_sources_config` (Task 4), `build_scheduler` (Task 11).
- Produces: `app` (FastAPI instance), `get_session` (FastAPI dependency yielding a `Session`), `NewsItemOut` (response schema).

- [ ] **Step 1: Write `src/db/session.py`**

```python
# src/db/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import get_settings

engine = create_engine(get_settings().database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 2: Write `src/api/schemas.py`**

```python
# src/api/schemas.py
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
```

- [ ] **Step 3: Write the failing tests**

```python
# tests/api/test_health.py
from fastapi.testclient import TestClient

from src.api.main import app


def test_health_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

```python
# tests/api/test_items.py
from fastapi.testclient import TestClient

from src.api.main import app, get_session
from src.db.repository import save_raw_items
from src.collectors.base import RawItem


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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/api -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.api.main'`

- [ ] **Step 5: Write `src/api/__init__.py`** (empty) and `src/api/main.py`

```python
# src/api/main.py
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.schemas import NewsItemOut
from src.collectors.sources_config import load_sources_config
from src.config import get_settings
from src.db.models import NewsItem
from src.db.session import SessionLocal, get_session
from src.scheduler import build_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    sources = load_sources_config(settings.sources_config_path)
    scheduler = build_scheduler(sources, SessionLocal)
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown()


app = FastAPI(title="Touch-Go News", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/items", response_model=list[NewsItemOut])
def list_items(session: Session = Depends(get_session)) -> list[NewsItem]:
    return list(
        session.execute(select(NewsItem).order_by(NewsItem.detected_at.desc())).scalars()
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/api -v`
Expected: PASS (2 tests) — note `test_items_returns_persisted_items` overrides the `get_session`
dependency so the API reads through the same transactional `db_session` fixture used to seed data.
`test_health_returns_ok` never opens a DB connection: `create_engine` in `src/db/session.py` is
lazy, so importing `src.api.main` succeeds even with Postgres stopped.

- [ ] **Step 7: Commit**

```bash
git add src/db/session.py src/api tests/api
git commit -m "feat: add FastAPI app with /health and /items, start scheduler on startup"
```

---

### Task 13: End-to-end integration test

**Files:**
- Test: `tests/test_integration_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 3-12.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_integration_pipeline.py
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from src.api.main import app, get_session
from src.collectors.runner import run_collection
from src.collectors.sources_config import SourceConfig
from src.collectors.factory import build_collector
from src.db.models import NewsItem

FEED = (Path(__file__).parent / "fixtures" / "sample_feed.xml").read_text()


@pytest.mark.asyncio
@respx.mock
async def test_full_pipeline_from_collection_to_api(db_session, make_source):
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

    result = await run_collection(db_session, config, collector)

    assert result.ok is True
    assert result.inserted == 2
    assert db_session.query(NewsItem).count() == 2

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    titles = {item["original_title"] for item in response.json()}
    assert titles == {"First article", "Second article"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration_pipeline.py -v`
Expected: FAIL only if a prior task is incomplete — since Tasks 3-12 are already implemented at
this point, the more likely outcome is an immediate PASS; if so skip to Step 3. If it fails,
re-check the imports/signatures above against what Tasks 3-12 actually produced.

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_integration_pipeline.py -v`
Expected: PASS (1 test)

- [ ] **Step 4: Run the full test suite**

Run: `pytest -v`
Expected: all tests across every task PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration_pipeline.py
git commit -m "test: add end-to-end integration test for collect -> store -> API pipeline"
```

---

## Manual verification (not automated)

After Task 13, run the service for real and confirm the sprint's goal end to end:

```bash
docker compose up -d
alembic upgrade head
uvicorn src.api.main:app --reload
```

- `curl http://localhost:8000/health` → `{"status":"ok"}`
- Wait for at least one scheduler cycle (or temporarily lower `poll_interval_minutes` in
  `config/sources.yaml` for a quick manual check), then `curl http://localhost:8000/items` and
  confirm real items from FlightGlobal / Airbus / Opex360 / BMPD / TASS appear.
- Check `SELECT id, last_run_status, last_run_error FROM news_source;` — every active source should
  show `last_run_status = 'OK'` except possibly `pprune_military`, which may show `FAILED` with a
  403-related error if the selectors in Task 7 need adjusting against the live site (see the
  "Known risk" note above Task 1).
