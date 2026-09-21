# Touch-Go News — Sprint 2 (Normalisation & déduplication) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every newly collected `NewsItem` a real canonical URL and a content hash, and detect duplicates of already-stored items (by URL, by hash, or by similar title within a 48h window) — without ever deleting, rejecting, or hiding a collected item.

**Architecture:** A new `src/normalization/` package holds three pure/DB-read modules (`url.py` canonicalization, `text.py` normalization + hashing, `dedup.py` duplicate lookup). `src/db/repository.py`'s existing `save_raw_items` is extended to call them for every item before insert, setting `NewsItem.canonical_url`, the new `NewsItem.content_hash` column, and `NewsItem.duplicate_of` (resolved to the root of any duplicate chain). Collectors, the runner, and the scheduler are untouched — this sprint only changes what happens inside the existing insert path.

**Tech Stack:** Same as Sprint 1 (Python 3.12+, SQLAlchemy 2.x, Alembic, pytest). No new dependencies — URL parsing (`urllib.parse`), hashing (`hashlib`), and normalization use the standard library only.

**Spec:** [`docs/superpowers/specs/2026-09-21-touchgo-news-sprint2-normalisation-dedup-design.md`](../specs/2026-09-21-touchgo-news-sprint2-normalisation-dedup-design.md) (implements Sprint 2 of [`SPEC.md`](../../../SPEC.md), sections 28, 29, 30, 34).

## Global Constraints

- Aucune suppression automatique de contenu collecté (SPEC.md section 2) — un item jugé doublon est **toujours inséré**, jamais rejeté ni fusionné ; seul `duplicate_of` est renseigné.
- Un item dupliqué reste pleinement visible et consultable via `GET /items` — aucun changement de `status` ni de visibilité API dans ce sprint.
- Pas de backfill : les items déjà collectés au Sprint 1 gardent `canonical_url = original_url` et `content_hash = NULL` ; seuls les nouveaux items sont normalisés/dédupliqués (design doc section 3).
- Seuils de dédoublonnage (design doc section 5) : recouvrement de tokens ≥ 0.8, fenêtre de date ± 48h — valeurs exactes, ne pas les ajuster sans repasser par une décision de design.
- `duplicate_of` doit toujours pointer vers la racine d'un groupe de doublons (le tout premier item détecté), jamais vers un intermédiaire — un item C similaire à B qui est déjà un doublon de A doit avoir `duplicate_of = A.id`, pas `B.id`.
- Collecte et classification restent séparées (SPEC.md section 30) — ce sprint ne touche à aucune colonne de classification/scoring.

---

### Task 1: `content_hash` column and migration

**Files:**
- Modify: `src/db/models.py:52` (insert the new column right after `original_text`, before `language`)
- Modify: `tests/db/test_models.py`
- Create: `alembic/versions/<generated>.py` (via `alembic revision --autogenerate`)

**Interfaces:**
- Produces: `NewsItem.content_hash: str | None` column.

- [ ] **Step 1: Write the failing test**

Add to `tests/db/test_models.py` (after the existing `test_insert_and_query_news_item` function):

```python
def test_content_hash_column_stores_and_retrieves_value(db_session, make_source):
    make_source(source_id="flightglobal")
    item = NewsItem(
        source_id="flightglobal",
        source_item_id="hash-test",
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Title",
        original_text="Body",
        content_hash="abc123def456",
    )
    db_session.add(item)
    db_session.commit()

    fetched = db_session.query(NewsItem).filter_by(source_item_id="hash-test").one()
    assert fetched.content_hash == "abc123def456"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/db/test_models.py::test_content_hash_column_stores_and_retrieves_value -v`
Expected: FAIL with `TypeError: 'content_hash' is an invalid keyword argument for NewsItem`

- [ ] **Step 3: Add the column to the model**

In `src/db/models.py`, insert this line right after the `original_text` column definition (line 52,
`original_text: Mapped[str] = mapped_column(Text, nullable=False)`) and before the `language`
column:

```python
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
```

- [ ] **Step 4: Generate and apply the migration**

```bash
alembic revision --autogenerate -m "add content_hash to news_item"
alembic upgrade head
```

Expected: a new file under `alembic/versions/` with an `upgrade()` that calls
`op.add_column('news_item', sa.Column('content_hash', sa.String(), nullable=True))` and a matching
`downgrade()` that drops it; `alembic upgrade head` runs against the dev database without error.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/db/test_models.py -v`
Expected: PASS (3 tests — the two pre-existing ones plus this new one). The test database is
rebuilt from the real migration chain by `tests/conftest.py`'s session-scoped `engine` fixture, so
it will pick up this new migration automatically the next time the suite runs.

- [ ] **Step 6: Commit**

```bash
git add src/db/models.py tests/db/test_models.py alembic/versions/
git commit -m "feat: add content_hash column to news_item"
```

---

### Task 2: URL canonicalization

**Files:**
- Create: `src/normalization/__init__.py`
- Create: `src/normalization/url.py`
- Test: `tests/normalization/test_url.py`

**Interfaces:**
- Produces: `canonicalize_url(url: str) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/normalization/test_url.py
from src.normalization.url import canonicalize_url


def test_canonicalize_url_lowercases_host():
    assert canonicalize_url("https://Example.COM/Article") == "https://example.com/Article"


def test_canonicalize_url_forces_https_scheme():
    assert canonicalize_url("http://example.com/a") == "https://example.com/a"


def test_canonicalize_url_strips_tracking_params():
    result = canonicalize_url("https://example.com/a?utm_source=x&utm_medium=y&b=2")
    assert result == "https://example.com/a?b=2"


def test_canonicalize_url_strips_fragment():
    assert canonicalize_url("https://example.com/a#section") == "https://example.com/a"


def test_canonicalize_url_strips_trailing_slash():
    assert canonicalize_url("https://example.com/a/") == "https://example.com/a"


def test_canonicalize_url_preserves_root_path():
    assert canonicalize_url("https://example.com/") == "https://example.com/"


def test_canonicalize_url_preserves_non_tracking_query_params():
    result = canonicalize_url("https://example.com/a?id=42")
    assert result == "https://example.com/a?id=42"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/normalization/test_url.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.normalization'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/normalization/__init__.py
```

(empty file)

```python
# src/normalization/url.py
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url)

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in _TRACKING_PARAMS
    ]

    return urlunsplit(("https", parts.netloc.lower(), path, urlencode(query_pairs), ""))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/normalization/test_url.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/normalization/__init__.py src/normalization/url.py tests/normalization/test_url.py
git commit -m "feat: add URL canonicalization"
```

---

### Task 3: Text normalization and content hashing

**Files:**
- Create: `src/normalization/text.py`
- Test: `tests/normalization/test_text.py`

**Interfaces:**
- Produces: `normalize_text(text: str) -> str`, `compute_content_hash(title: str, text: str) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/normalization/test_text.py
from src.normalization.text import compute_content_hash, normalize_text


def test_normalize_text_lowercases_and_strips_punctuation():
    assert normalize_text("Hello, World!  Foo.") == "hello world foo"


def test_normalize_text_collapses_whitespace():
    assert normalize_text("a   b\tc\nd") == "a b c d"


def test_compute_content_hash_is_deterministic():
    first = compute_content_hash("Title", "Body text")
    second = compute_content_hash("Title", "Body text")
    assert first == second


def test_compute_content_hash_differs_for_different_content():
    first = compute_content_hash("Title A", "Body text")
    second = compute_content_hash("Title B", "Body text")
    assert first != second


def test_compute_content_hash_is_case_and_punctuation_insensitive():
    first = compute_content_hash("Airbus Unveils!", "New variant.")
    second = compute_content_hash("airbus unveils", "new variant")
    assert first == second
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/normalization/test_text.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.normalization.text'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/normalization/text.py
import hashlib
import re

_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    lowered = text.lower()
    without_punctuation = _PUNCTUATION_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", without_punctuation).strip()


def compute_content_hash(title: str, text: str) -> str:
    combined = f"{normalize_text(title)} {normalize_text(text)}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:32]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/normalization/test_text.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/normalization/text.py tests/normalization/test_text.py
git commit -m "feat: add text normalization and content hashing"
```

---

### Task 4: Duplicate detection

**Files:**
- Create: `src/normalization/dedup.py`
- Test: `tests/normalization/test_dedup.py`

**Interfaces:**
- Consumes: `NewsItem` (Task 1's `content_hash` column), `normalize_text` (Task 3).
- Produces: `jaccard_similarity(a: str, b: str) -> float`,
  `find_duplicate(session: Session, canonical_url: str, content_hash: str, original_title: str, reference_date: datetime) -> NewsItem | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/normalization/test_dedup.py
from datetime import datetime, timezone

from src.db.models import NewsItem
from src.normalization.dedup import find_duplicate, jaccard_similarity


def _insert_item(db_session, source_id: str = "flightglobal", **overrides) -> NewsItem:
    defaults = dict(
        source_id=source_id,
        source_item_id=overrides.pop("source_item_id", "seed"),
        canonical_url="https://example.com/seed",
        original_url="https://example.com/seed",
        original_title="Airbus unveils new variant",
        original_text="Body text",
        content_hash="seedhash",
        published_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    item = NewsItem(**defaults)
    db_session.add(item)
    db_session.commit()
    return item


def test_jaccard_similarity_identical_strings_is_one():
    assert jaccard_similarity("airbus unveils new variant", "airbus unveils new variant") == 1.0


def test_jaccard_similarity_disjoint_strings_is_zero():
    assert jaccard_similarity("airbus unveils variant", "boeing delivers order") == 0.0


def test_find_duplicate_matches_by_canonical_url(db_session, make_source):
    make_source(source_id="flightglobal")
    seed = _insert_item(db_session)

    match = find_duplicate(
        db_session,
        canonical_url="https://example.com/seed",
        content_hash="different-hash",
        original_title="Unrelated title",
        reference_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert match is not None
    assert match.id == seed.id


def test_find_duplicate_matches_by_content_hash(db_session, make_source):
    make_source(source_id="flightglobal")
    seed = _insert_item(db_session)

    match = find_duplicate(
        db_session,
        canonical_url="https://example.com/different",
        content_hash="seedhash",
        original_title="Unrelated title",
        reference_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert match is not None
    assert match.id == seed.id


def test_find_duplicate_matches_by_similar_title_within_window(db_session, make_source):
    make_source(source_id="flightglobal")
    seed = _insert_item(db_session)

    match = find_duplicate(
        db_session,
        canonical_url="https://example.com/different",
        content_hash="different-hash",
        original_title="Airbus unveils new variant",
        reference_date=datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc),
    )

    assert match is not None
    assert match.id == seed.id


def test_find_duplicate_ignores_match_outside_date_window(db_session, make_source):
    make_source(source_id="flightglobal")
    _insert_item(db_session)

    match = find_duplicate(
        db_session,
        canonical_url="https://example.com/different",
        content_hash="different-hash",
        original_title="Airbus unveils new variant",
        reference_date=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )

    assert match is None


def test_find_duplicate_ignores_dissimilar_title(db_session, make_source):
    make_source(source_id="flightglobal")
    _insert_item(db_session)

    match = find_duplicate(
        db_session,
        canonical_url="https://example.com/different",
        content_hash="different-hash",
        original_title="Boeing delivers first order",
        reference_date=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )

    assert match is None


def test_find_duplicate_returns_none_when_no_items_exist(db_session):
    match = find_duplicate(
        db_session,
        canonical_url="https://example.com/none",
        content_hash="nohash",
        original_title="Anything",
        reference_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert match is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/normalization/test_dedup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.normalization.dedup'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/normalization/dedup.py
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.db.models import NewsItem
from src.normalization.text import normalize_text

SIMILARITY_THRESHOLD = 0.8
DATE_WINDOW = timedelta(hours=48)


def jaccard_similarity(a: str, b: str) -> float:
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def find_duplicate(
    session: Session,
    canonical_url: str,
    content_hash: str,
    original_title: str,
    reference_date: datetime,
) -> NewsItem | None:
    by_url = session.execute(
        select(NewsItem).where(NewsItem.canonical_url == canonical_url)
    ).scalars().first()
    if by_url is not None:
        return by_url

    by_hash = session.execute(
        select(NewsItem).where(NewsItem.content_hash == content_hash)
    ).scalars().first()
    if by_hash is not None:
        return by_hash

    normalized_title = normalize_text(original_title)
    window_start = reference_date - DATE_WINDOW
    window_end = reference_date + DATE_WINDOW
    effective_date = func.coalesce(NewsItem.published_at, NewsItem.detected_at)
    candidates = session.execute(
        select(NewsItem).where(
            effective_date >= window_start,
            effective_date <= window_end,
        )
    ).scalars().all()
    for candidate in candidates:
        candidate_title = normalize_text(candidate.original_title)
        if jaccard_similarity(normalized_title, candidate_title) >= SIMILARITY_THRESHOLD:
            return candidate
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/normalization/test_dedup.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/normalization/dedup.py tests/normalization/test_dedup.py
git commit -m "feat: add duplicate detection by URL, hash, and title similarity"
```

---

### Task 5: Wire canonicalization and content hashing into `save_raw_items`

**Files:**
- Modify: `src/db/repository.py:46-84` (the `save_raw_items` function)
- Modify: `tests/db/test_repository.py`

**Interfaces:**
- Consumes: `canonicalize_url` (Task 2), `compute_content_hash` (Task 3).
- Produces: no change to `save_raw_items`'s signature or `SaveResult` — only what gets written to
  `NewsItem.canonical_url` and `NewsItem.content_hash` changes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/db/test_repository.py` (the file already imports `RawItem`, `NewsItem`, `NewsSource`,
`save_raw_items`, `sync_sources`, `update_source_run_status` — add one more import line and these
two test functions):

```python
from src.normalization.text import compute_content_hash


def test_save_raw_items_canonicalizes_the_url(db_session, make_source):
    make_source(source_id="flightglobal")
    item = RawItem(
        source_item_id="1",
        canonical_url="https://example.com/a",
        original_url="https://Example.com/a?utm_source=newsletter",
        original_title="Title",
        original_text="Body",
        language="en",
    )

    save_raw_items(db_session, "flightglobal", [item])

    stored = db_session.query(NewsItem).filter_by(source_item_id="1").one()
    assert stored.canonical_url == "https://example.com/a"


def test_save_raw_items_computes_content_hash(db_session, make_source):
    make_source(source_id="flightglobal")
    item = RawItem(
        source_item_id="1",
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Some Title",
        original_text="Some body text",
        language="en",
    )

    save_raw_items(db_session, "flightglobal", [item])

    stored = db_session.query(NewsItem).filter_by(source_item_id="1").one()
    assert stored.content_hash == compute_content_hash("Some Title", "Some body text")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/db/test_repository.py::test_save_raw_items_canonicalizes_the_url tests/db/test_repository.py::test_save_raw_items_computes_content_hash -v`
Expected: FAIL — `test_save_raw_items_canonicalizes_the_url` fails because `stored.canonical_url`
is still `"https://Example.com/a?utm_source=newsletter"` (today `save_raw_items` just copies
`item.canonical_url` verbatim); `test_save_raw_items_computes_content_hash` fails because
`stored.content_hash` is `None`.

- [ ] **Step 3: Update `save_raw_items`**

In `src/db/repository.py`, add these two imports near the top (with the existing imports):

```python
from src.normalization.text import compute_content_hash
from src.normalization.url import canonicalize_url
```

Replace the body of the `for item in items:` loop's insert block. The current code (lines 67-81)
reads:

```python
        seen_in_batch.add(key)
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
```

Replace it with:

```python
        seen_in_batch.add(key)
        canonical_url = canonicalize_url(item.original_url)
        content_hash = compute_content_hash(item.original_title, item.original_text)
        session.add(
            NewsItem(
                source_id=source_id,
                source_item_id=item.source_item_id,
                canonical_url=canonical_url,
                original_url=item.original_url,
                original_title=item.original_title,
                original_text=item.original_text,
                language=item.language or None,
                author=item.author,
                published_at=item.published_at,
                status="NEW",
                content_hash=content_hash,
            )
        )
        inserted += 1
```

(`item.canonical_url` — the field collectors set, currently just a copy of the raw link — is no
longer used; `original_url` remains the untouched raw value collectors produced.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/db/test_repository.py -v`
Expected: PASS (all tests in the file, including the two new ones and the pre-existing ones — none
of the pre-existing tests' URLs contain tracking params or trailing slashes beyond the root, so
their stored `canonical_url` values are unchanged by this task).

- [ ] **Step 5: Commit**

```bash
git add src/db/repository.py tests/db/test_repository.py
git commit -m "feat: canonicalize URLs and compute content hash on insert"
```

---

### Task 6: Wire duplicate detection into `save_raw_items`

**Files:**
- Modify: `src/db/repository.py` (the `save_raw_items` function, as left by Task 5)
- Modify: `tests/db/test_repository.py`

**Interfaces:**
- Consumes: `find_duplicate` (Task 4).
- Produces: no change to `save_raw_items`'s signature — only `NewsItem.duplicate_of` gets set when
  a match is found.

- [ ] **Step 1: Write the failing tests**

Add to `tests/db/test_repository.py` (add `from datetime import datetime, timezone` to the imports
if not already present as a top-level import — check the file first, it currently imports from
`dataclasses`-adjacent modules only at the top; add the datetime import alongside the existing
ones):

```python
def test_save_raw_items_marks_duplicate_by_matching_canonical_url(db_session, make_source):
    make_source(source_id="flightglobal")
    make_source(source_id="reuters")
    original = RawItem(
        source_item_id="1",
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Original title",
        original_text="Original body",
        language="en",
    )
    save_raw_items(db_session, "flightglobal", [original])
    original_id = db_session.query(NewsItem).filter_by(source_item_id="1").one().id

    duplicate = RawItem(
        source_item_id="99",
        canonical_url="https://example.com/a",
        original_url="https://example.com/a?utm_source=newsletter",
        original_title="A different title entirely",
        original_text="Completely different body",
        language="en",
    )
    save_raw_items(db_session, "reuters", [duplicate])

    stored = db_session.query(NewsItem).filter_by(source_item_id="99").one()
    assert stored.duplicate_of == original_id


def test_save_raw_items_marks_duplicate_by_similar_title_within_window(db_session, make_source):
    make_source(source_id="flightglobal")
    make_source(source_id="reuters")
    original = RawItem(
        source_item_id="1",
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Airbus unveils new variant",
        original_text="Original body",
        language="en",
        published_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    )
    save_raw_items(db_session, "flightglobal", [original])
    original_id = db_session.query(NewsItem).filter_by(source_item_id="1").one().id

    similar = RawItem(
        source_item_id="99",
        canonical_url="https://example.com/b",
        original_url="https://example.com/b",
        original_title="Airbus unveils new variant",
        original_text="A differently worded confirmation of the same news",
        language="en",
        published_at=datetime(2026, 1, 1, 18, 0, tzinfo=timezone.utc),
    )
    save_raw_items(db_session, "reuters", [similar])

    stored = db_session.query(NewsItem).filter_by(source_item_id="99").one()
    assert stored.duplicate_of == original_id


def test_save_raw_items_does_not_mark_unrelated_items_as_duplicates(db_session, make_source):
    make_source(source_id="flightglobal")
    items = [
        RawItem(
            source_item_id="1",
            canonical_url="https://example.com/a",
            original_url="https://example.com/a",
            original_title="Airbus unveils new variant",
            original_text="Body A",
            language="en",
        ),
        RawItem(
            source_item_id="2",
            canonical_url="https://example.com/b",
            original_url="https://example.com/b",
            original_title="Boeing delivers first order",
            original_text="Body B",
            language="en",
        ),
    ]

    save_raw_items(db_session, "flightglobal", items)

    stored = db_session.query(NewsItem).filter_by(source_id="flightglobal").all()
    assert all(item.duplicate_of is None for item in stored)


def test_save_raw_items_resolves_duplicate_chain_to_the_root(db_session, make_source):
    make_source(source_id="flightglobal")
    make_source(source_id="reuters")
    make_source(source_id="air-cosmos")

    root = RawItem(
        source_item_id="1",
        canonical_url="https://example.com/a",
        original_url="https://example.com/a",
        original_title="Airbus unveils new variant",
        original_text="Root body",
        language="en",
        published_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    )
    save_raw_items(db_session, "flightglobal", [root])
    root_id = db_session.query(NewsItem).filter_by(source_item_id="1").one().id

    # Duplicate of root by exact content hash (identical title + text).
    second = RawItem(
        source_item_id="1",
        canonical_url="https://example.com/b",
        original_url="https://example.com/b",
        original_title="Airbus unveils new variant",
        original_text="Root body",
        language="en",
        published_at=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
    )
    save_raw_items(db_session, "reuters", [second])
    second_id = db_session.query(NewsItem).filter_by(source_id="reuters").one().id
    assert db_session.get(NewsItem, second_id).duplicate_of == root_id

    # Similar title to `second`, within the date window of `second` (not `root`),
    # but must still resolve to `root_id`, not `second_id`.
    third = RawItem(
        source_item_id="1",
        canonical_url="https://example.com/c",
        original_url="https://example.com/c",
        original_title="Airbus unveils new variant",
        original_text="A third, differently worded write-up",
        language="en",
        published_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )
    save_raw_items(db_session, "air-cosmos", [third])

    third_stored = db_session.query(NewsItem).filter_by(source_id="air-cosmos").one()
    assert third_stored.duplicate_of == root_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/db/test_repository.py -k duplicate -v`
Expected: FAIL — all four new tests fail because `duplicate_of` is never set (`stored.duplicate_of`
is `None` in each assertion that expects a real id).

- [ ] **Step 3: Wire `find_duplicate` into `save_raw_items`**

Add this import to `src/db/repository.py` alongside the two added in Task 5:

```python
from src.normalization.dedup import find_duplicate
```

Update the loop body again — insert the duplicate lookup between the `content_hash = ...` line
Task 5 added and the `session.add(...)` call, and add `duplicate_of` to the `NewsItem(...)` kwargs:

```python
        seen_in_batch.add(key)
        canonical_url = canonicalize_url(item.original_url)
        content_hash = compute_content_hash(item.original_title, item.original_text)
        reference_date = item.published_at or datetime.now(timezone.utc)
        duplicate = find_duplicate(
            session,
            canonical_url=canonical_url,
            content_hash=content_hash,
            original_title=item.original_title,
            reference_date=reference_date,
        )
        duplicate_of_id = (duplicate.duplicate_of or duplicate.id) if duplicate is not None else None
        session.add(
            NewsItem(
                source_id=source_id,
                source_item_id=item.source_item_id,
                canonical_url=canonical_url,
                original_url=item.original_url,
                original_title=item.original_title,
                original_text=item.original_text,
                language=item.language or None,
                author=item.author,
                published_at=item.published_at,
                status="NEW",
                content_hash=content_hash,
                duplicate_of=duplicate_of_id,
            )
        )
        inserted += 1
```

`datetime` and `timezone` are already imported at the top of `src/db/repository.py` (used by
`update_source_run_status`), so no new import is needed for those two names.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/db/test_repository.py -v`
Expected: PASS (every test in the file — Task 5's tests, Task 6's four new tests, and every
pre-existing test).

- [ ] **Step 5: Commit**

```bash
git add src/db/repository.py tests/db/test_repository.py
git commit -m "feat: detect and link duplicates on insert, resolved to the group root"
```

---

### Task 7: Integration test — cross-source duplicate detected end to end

**Files:**
- Modify: `tests/test_integration_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 1-6, plus the existing `build_collector`/`run_collection`
  pipeline from Sprint 1.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_integration_pipeline.py` (the file already has `FEED` loaded from
`tests/fixtures/sample_feed.xml`, and imports `httpx`, `pytest`, `respx`, `TestClient`, `app`,
`get_session`, `run_collection`, `SourceConfig`, `build_collector`, `NewsItem` — add this constant
near `FEED` and this test function):

```python
SECOND_SOURCE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Reuters Feed</title>
    <item>
      <title>First article</title>
      <link>https://reuters.example.com/articles/99</link>
      <guid>https://reuters.example.com/articles/99</guid>
      <description>A different summary confirming the first article.</description>
      <pubDate>Mon, 01 Jan 2026 18:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


@pytest.mark.asyncio
@respx.mock
async def test_cross_source_duplicate_is_linked_but_still_visible(db_session, make_source):
    make_source(source_id="flightglobal", url="https://example.com/feed")
    make_source(source_id="reuters", url="https://reuters.example.com/feed")

    flightglobal_config = SourceConfig(
        id="flightglobal",
        name="FlightGlobal",
        type="rss",
        url="https://example.com/feed",
        language="en",
        source_type="press",
        poll_interval_minutes=30,
    )
    reuters_config = SourceConfig(
        id="reuters",
        name="Reuters",
        type="rss",
        url="https://reuters.example.com/feed",
        language="en",
        source_type="press",
        poll_interval_minutes=30,
    )
    respx.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=FEED, headers={"content-type": "application/rss+xml"})
    )
    respx.get("https://reuters.example.com/feed").mock(
        return_value=httpx.Response(
            200, text=SECOND_SOURCE_FEED, headers={"content-type": "application/rss+xml"}
        )
    )

    first_result = await run_collection(
        db_session, flightglobal_config, build_collector(flightglobal_config)
    )
    assert first_result.ok is True
    assert first_result.inserted == 2

    second_result = await run_collection(
        db_session, reuters_config, build_collector(reuters_config)
    )
    assert second_result.ok is True
    assert second_result.inserted == 1

    flightglobal_first_article = (
        db_session.query(NewsItem)
        .filter_by(source_id="flightglobal", original_title="First article")
        .one()
    )
    reuters_item = db_session.query(NewsItem).filter_by(source_id="reuters").one()
    assert reuters_item.duplicate_of == flightglobal_first_article.id
    assert db_session.query(NewsItem).count() == 3

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        response = TestClient(app).get("/items")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    titles = [item["original_title"] for item in response.json()]
    assert titles.count("First article") == 2
    assert "Second article" in titles
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration_pipeline.py::test_cross_source_duplicate_is_linked_but_still_visible -v`
Expected: this should already PASS once Tasks 1-6 are done, since it only exercises code paths
those tasks already built and tested individually — this task adds no new production code, only a
test proving the whole chain agrees. If it fails, the failure traces back to a mismatch between
this test's expectations and what Tasks 1-6 actually produced; re-check against those tasks rather
than assuming this test is wrong.

- [ ] **Step 3: Run the full test suite**

Run: `pytest -v`
Expected: every test across Sprint 1 and Sprint 2 passes, output as clean as the pre-existing run
(only the two known pre-existing FastAPI/Starlette deprecation warnings).

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_pipeline.py
git commit -m "test: add end-to-end cross-source duplicate detection test"
```
