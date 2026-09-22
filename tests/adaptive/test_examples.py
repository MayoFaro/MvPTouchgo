from src.adaptive.examples import build_classification_examples, build_scoring_examples
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
    )
    defaults.update(overrides)
    item = NewsItem(**defaults)
    db_session.add(item)
    db_session.commit()
    return item


def _feedback(db_session, item: NewsItem, **overrides) -> NewsFeedback:
    defaults = dict(
        news_item_id=item.id,
        decision="REJETER",
        reason=None,
        comment=None,
        previous_priority=None,
        previous_category=None,
        reviewer_id="reviewer",
    )
    defaults.update(overrides)
    feedback = NewsFeedback(**defaults)
    db_session.add(feedback)
    db_session.commit()
    return feedback


def test_build_classification_examples_returns_empty_string_below_threshold(
    db_session, make_source
):
    item = _item(db_session, make_source)
    _feedback(
        db_session,
        item,
        decision="NOUVELLE_CATEGORIE",
        comment="Drones civils",
        previous_category="MEETING",
    )

    result = build_classification_examples(db_session, min_examples=2, max_examples=5)

    assert result == ""


def test_build_classification_examples_formats_new_category_feedback(db_session, make_source):
    item = _item(db_session, make_source)
    _feedback(
        db_session,
        item,
        decision="NOUVELLE_CATEGORIE",
        comment="Drones civils",
        previous_category="MEETING",
    )

    result = build_classification_examples(db_session, min_examples=1, max_examples=5)

    assert result == (
        '- Item classé MEETING par le modèle ; retour humain : proposer une nouvelle '
        'catégorie ("Drones civils").'
    )


def test_build_classification_examples_formats_out_of_scope_rejection(db_session, make_source):
    item = _item(db_session, make_source)
    _feedback(
        db_session,
        item,
        decision="REJETER",
        reason="hors_perimetre",
        previous_category="COMMERCIAL",
    )

    result = build_classification_examples(db_session, min_examples=1, max_examples=5)

    assert result == (
        "- Item classé COMMERCIAL par le modèle ; retour humain : hors périmètre Touch-Go."
    )


def test_build_classification_examples_ignores_rejections_with_other_reasons(
    db_session, make_source
):
    item = _item(db_session, make_source)
    _feedback(
        db_session, item, decision="REJETER", reason="doublon", previous_category="COMMERCIAL"
    )

    result = build_classification_examples(db_session, min_examples=1, max_examples=5)

    assert result == ""


def test_build_classification_examples_ignores_unrelated_decisions(db_session, make_source):
    item = _item(db_session, make_source)
    _feedback(db_session, item, decision="TRES_INTERESSANT", previous_category="MILITAIRE")

    result = build_classification_examples(db_session, min_examples=1, max_examples=5)

    assert result == ""


def test_build_classification_examples_respects_max_examples_and_recency(db_session, make_source):
    item = _item(db_session, make_source)
    for category in ["COMMERCIAL", "EMPLOI", "MILITAIRE"]:
        _feedback(
            db_session,
            item,
            decision="REJETER",
            reason="hors_perimetre",
            previous_category=category,
        )

    result = build_classification_examples(db_session, min_examples=1, max_examples=2)

    lines = result.splitlines()
    assert len(lines) == 2
    assert "MILITAIRE" in lines[0]
    assert "EMPLOI" in lines[1]


def test_build_scoring_examples_returns_empty_string_below_threshold(db_session, make_source):
    item = _item(db_session, make_source)
    _feedback(db_session, item, decision="TRES_INTERESSANT", previous_priority="C")

    result = build_scoring_examples(db_session, min_examples=2, max_examples=5)

    assert result == ""


def test_build_scoring_examples_formats_tres_interessant_as_underestimated(
    db_session, make_source
):
    item = _item(db_session, make_source)
    _feedback(db_session, item, decision="TRES_INTERESSANT", previous_priority="C")

    result = build_scoring_examples(db_session, min_examples=1, max_examples=5)

    assert result == (
        "- Item priorité C donnée par le modèle ; retour humain : "
        "🔥 (probablement sous-évalué)."
    )


def test_build_scoring_examples_formats_interessant_as_underestimated(db_session, make_source):
    item = _item(db_session, make_source)
    _feedback(db_session, item, decision="INTERESSANT", previous_priority="B")

    result = build_scoring_examples(db_session, min_examples=1, max_examples=5)

    assert result == (
        "- Item priorité B donnée par le modèle ; retour humain : "
        "👍 (probablement sous-évalué)."
    )


def test_build_scoring_examples_formats_rejection_as_overestimated(db_session, make_source):
    item = _item(db_session, make_source)
    _feedback(db_session, item, decision="REJETER", reason="doublon", previous_priority="A")

    result = build_scoring_examples(db_session, min_examples=1, max_examples=5)

    assert result == (
        "- Item priorité A donnée par le modèle ; retour humain : "
        "❌ rejeté (probablement surévalué)."
    )


def test_build_scoring_examples_ignores_a_suivre(db_session, make_source):
    item = _item(db_session, make_source)
    _feedback(db_session, item, decision="A_SUIVRE", previous_priority="B")

    result = build_scoring_examples(db_session, min_examples=1, max_examples=5)

    assert result == ""


def test_build_scoring_examples_ignores_new_category_suggestions(db_session, make_source):
    item = _item(db_session, make_source)
    _feedback(
        db_session, item, decision="NOUVELLE_CATEGORIE", comment="x", previous_priority="B"
    )

    result = build_scoring_examples(db_session, min_examples=1, max_examples=5)

    assert result == ""
