from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: str
    title: str
    organization: str
    summary: str
    location: str
    deadline: datetime
    source_url: str
    source_label: str
    trust_score: float
    tags: list[str]
    fetched_at: datetime


class OpportunityList(BaseModel):
    items: list[OpportunityOut]
    total: int


class StatsOut(BaseModel):
    total: int
    by_type: dict[str, int]
    closing_soon: int


class ProfileIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    display_name: str = Field(default="同学", min_length=1, max_length=40)
    discoverable: bool = False
    school: str = Field(default="示范大学", min_length=1, max_length=120)
    college: str = Field(max_length=120)
    grade: str = Field(max_length=40)
    major: str = Field(max_length=120)
    interests: list[str] = Field(default_factory=list, max_length=20)
    skills: list[str] = Field(default_factory=list, max_length=20)
    weekly_hours: int = Field(default=8, ge=0, le=80)
    degree: str = Field(default="本科", max_length=40)
    target_year: int | None = Field(default=None, ge=2020, le=2100)
    target_path: str = Field(default="", max_length=40)
    target_region: str = Field(default="", max_length=80)
    language_score: str = Field(default="", max_length=80)
    research_exp: str = Field(default="", max_length=2000)
    internship_exp: str = Field(default="", max_length=2000)
    competition_exp: str = Field(default="", max_length=2000)
    startup_exp: str = Field(default="", max_length=2000)

    @field_validator("interests", "skills")
    @classmethod
    def validate_labels(cls, values):
        if any(not v.strip() or len(v) > 40 or "," in v for v in values):
            raise ValueError("标签必须为 1–40 字且不能包含逗号")
        values = list(dict.fromkeys(v.strip() for v in values))
        if len(",".join(values)) > 300:
            raise ValueError("标签总长度不能超过 300 字")
        return values


class ProfileOut(ProfileIn):
    user_id: str
    updated_at: datetime


class PathOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str | None = None
    parent_id: int | None = None
    name: str
    description: str
    target_group: str
    duration: str
    status: str


class TimelineNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    path_id: int
    title: str
    month: str
    grade: str
    description: str
    importance: str


class PlanIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    path_id: int | None = None
    due_date: datetime | None = None
    status: Literal["todo", "doing", "done"] = "todo"
    note: str = Field(default="", max_length=2000)


class PlanOut(PlanIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: str
    created_at: datetime
    updated_at: datetime


class TrackerWriteIn(BaseModel):
    opportunity_id: str
    stage: Literal["saved", "preparing", "applied", "interview", "completed"] = "saved"
    note: str = Field(default="", max_length=500)


class TrackerItemOut(BaseModel):
    id: int
    opportunity: OpportunityOut
    stage: str
    note: str
    created_at: datetime
    updated_at: datetime


class ReminderIn(BaseModel):
    opportunity_id: str
    hours_before: int = Field(default=24, ge=1, le=720)


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    opportunity_id: str
    due_at: datetime
    channel: str
    sent: bool


class EligibilityCheckIn(BaseModel):
    opportunity_id: str


class RuleResult(BaseModel):
    evidence: str = ""
    label: str
    passed: bool | None
    actual: str
    expected: str
    source_url: str


class EligibilityOut(BaseModel):
    eligible: bool | None
    opportunity_id: str
    results: list[RuleResult]


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    source_url: str
    risk_level: str
    confidence: float
    status: str
    extracted_payload: str
    created_at: datetime
