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
