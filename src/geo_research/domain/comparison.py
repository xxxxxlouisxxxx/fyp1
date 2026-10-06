"""Explicit human-reviewed query/prompt comparison decisions, never inferred."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from geo_research.domain.identifiers import RegistryIdentifier
from geo_research.domain.serp import RegistryModel


class ComparisonMapping(RegistryModel):
    """Review metadata stays in the CSV snapshot, not the legacy Bronze schema."""

    comparison_id: RegistryIdentifier
    query_id: RegistryIdentifier
    prompt_id: RegistryIdentifier
    intent_id: RegistryIdentifier
    review_status: str = Field(min_length=1)
    reviewer: str
    reviewed_at: datetime | None
    active: bool

    @field_validator("review_status", "reviewer")
    @classmethod
    def strip_review_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("reviewed_at", mode="before")
    @classmethod
    def parse_review_timestamp(cls, value: object) -> object:
        if value == "":
            return None
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if isinstance(value, datetime) and value.utcoffset() is None:
            raise ValueError("reviewed_at must be a timezone-aware timestamp")
        return value

    @model_validator(mode="after")
    def require_human_approval(self) -> ComparisonMapping:
        if self.active:
            if self.review_status != "approved":
                raise ValueError("active comparison requires approved review_status")
            if not self.reviewer:
                raise ValueError("active comparison requires a named reviewer")
            if self.reviewed_at is None:
                raise ValueError("active comparison requires reviewed_at timestamp")
        return self