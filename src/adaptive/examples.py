from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import NewsFeedback

_UNDERESTIMATED_LABELS = {
    "TRES_INTERESSANT": "🔥 (probablement sous-évalué)",
    "INTERESSANT": "👍 (probablement sous-évalué)",
}


def build_classification_examples(session: Session, min_examples: int, max_examples: int) -> str:
    rows = (
        session.execute(
            select(NewsFeedback)
            .where(
                (NewsFeedback.decision == "NOUVELLE_CATEGORIE")
                | (
                    (NewsFeedback.decision == "REJETER")
                    & (NewsFeedback.reason == "hors_perimetre")
                )
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
                f'proposer une nouvelle catégorie ("{feedback.comment}").'
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
            .where(NewsFeedback.decision.in_(["TRES_INTERESSANT", "INTERESSANT", "REJETER"]))
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
        label = _UNDERESTIMATED_LABELS.get(
            feedback.decision, "❌ rejeté (probablement surévalué)"
        )
        lines.append(
            f"- Item priorité {feedback.previous_priority} donnée par le modèle ; retour "
            f"humain : {label}."
        )
    return "\n".join(lines)
