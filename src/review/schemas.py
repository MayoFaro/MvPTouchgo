from pydantic import BaseModel, field_validator, model_validator

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

    @model_validator(mode="after")
    def validate_reason_and_comment(self) -> "FeedbackIn":
        if self.decision == "REJETER":
            if self.reason is None or self.reason not in REJECT_REASONS:
                raise ValueError(
                    f"reason must be one of {REJECT_REASONS} when decision is REJETER"
                )
        if self.decision == "NOUVELLE_CATEGORIE":
            if not self.comment:
                raise ValueError("comment is required when decision is NOUVELLE_CATEGORIE")
        return self
