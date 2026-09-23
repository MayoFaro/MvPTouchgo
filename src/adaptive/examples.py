from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import NewsFeedback

_SCORING_DECISION_LABELS = {
    "TRES_INTERESSANT": "🔥 (probablement sous-évalué)",
    "INTERESSANT": "👍 (probablement sous-évalué)",
    "REJETER": "❌ rejeté (probablement surévalué)",
}

# Only reject reasons that actually speak to the priority level count as an
# "overestimated" signal — "doublon"/"information_douteuse"/"autre" say nothing
# about whether the score itself was too high (see SPEC.md §17 for the full list).
_OVERESTIMATED_REJECT_REASONS = [
    "trop_mineur",
    "pas_pertinent_touchgo",
    "trop_commercial",
    "trop_local",
    "signal_trop_faible",
]


def _sanitize_comment(comment: str) -> str:
    return comment.replace("<", "").replace(">", "").replace("\n", " ").replace("\r", " ")


def build_classification_examples(session: Session, min_examples: int, max_examples: int) -> str:
    rows = (
        session.execute(
            select(NewsFeedback)
            .where(
                (
                    (NewsFeedback.decision == "NOUVELLE_CATEGORIE")
                    | (
                        (NewsFeedback.decision == "REJETER")
                        & (NewsFeedback.reason == "hors_perimetre")
                    )
                )
                & NewsFeedback.previous_category.is_not(None)
            )
            .order_by(NewsFeedback.created_at.desc())
            .limit(max_examples)
        )
        .scalars()
        .all()
    )

    if len(rows) < min_examples:
        return ""

    lines = []
    for feedback in rows:
        if feedback.decision == "NOUVELLE_CATEGORIE":
            lines.append(
                f"- Item classé {feedback.previous_category} par le modèle ; retour humain : "
                f'proposer une nouvelle catégorie ("{_sanitize_comment(feedback.comment)}").'
            )
        else:
            lines.append(
                f"- Item classé {feedback.previous_category} par le modèle ; retour humain : "
                "hors périmètre Touch-Go."
            )
    return "\n".join(lines)


def build_scoring_examples(session: Session, min_examples: int, max_examples: int) -> str:
    rows = (
        session.execute(
            select(NewsFeedback)
            .where(
                (
                    NewsFeedback.decision.in_(["TRES_INTERESSANT", "INTERESSANT"])
                    | (
                        (NewsFeedback.decision == "REJETER")
                        & NewsFeedback.reason.in_(_OVERESTIMATED_REJECT_REASONS)
                    )
                )
                & NewsFeedback.previous_priority.is_not(None)
            )
            .order_by(NewsFeedback.created_at.desc())
            .limit(max_examples)
        )
        .scalars()
        .all()
    )

    if len(rows) < min_examples:
        return ""

    lines = []
    for feedback in rows:
        label = _SCORING_DECISION_LABELS[feedback.decision]
        lines.append(
            f"- Item priorité {feedback.previous_priority} donnée par le modèle ; retour "
            f"humain : {label}."
        )
    return "\n".join(lines)
