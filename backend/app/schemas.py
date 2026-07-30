from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AgeGroup = Literal["infant", "child", "adolescent", "adult", "older_adult"]
PregnancyStatus = Literal[
    "not_applicable",
    "none",
    "pregnant",
    "breastfeeding",
    "prefer_not_to_say",
]


class ContextPatch(BaseModel):
    age_group: AgeGroup | None = None
    goals: list[str] | None = None
    conditions: list[str] | None = None
    medications: list[str] | None = None
    allergies: list[str] | None = None
    pregnancy_status: PregnancyStatus | None = None
    budget_max_vnd: int | None = Field(default=None, gt=0)
    preferred_dosage_forms: list[str] | None = None


class SessionCreate(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)
    version_id: str = "version_1"
    provider: Literal["openai", "gemini"] = "openai"


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    context: dict[str, Any] = Field(default_factory=dict)
    version_id: str
    provider: str
    chat_model: str
    embedding_provider: str
    embedding_model: str
    dataset_fingerprint: str
    created_at: datetime
    updated_at: datetime


class RunCreate(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    status: str
    query: str
    answer: dict[str, Any] | None = None
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime


class TraceEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    sequence: int
    type: str
    payload: dict[str, Any]
    created_at: datetime


class ResumeRunRequest(BaseModel):
    context_patch: ContextPatch | None = None
    response: dict[str, Any] = Field(default_factory=dict)
