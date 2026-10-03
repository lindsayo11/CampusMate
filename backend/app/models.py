from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    type: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(160), index=True)
    organization: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(80))
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_url: Mapped[str] = mapped_column(String(500))
    source_label: Mapped[str] = mapped_column(String(100))
    trust_score: Mapped[float] = mapped_column(Float, default=0.8)
    tags: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default="published", index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(40), default="同学", server_default="同学")
    discoverable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    school: Mapped[str] = mapped_column(String(120), default="示范大学")
    college: Mapped[str] = mapped_column(String(120), default="")
    grade: Mapped[str] = mapped_column(String(40), default="")
    major: Mapped[str] = mapped_column(String(120), default="")
    interests: Mapped[str] = mapped_column(String(300), default="")
    skills: Mapped[str] = mapped_column(String(300), default="")
    weekly_hours: Mapped[int] = mapped_column(Integer, default=8)
    degree: Mapped[str] = mapped_column(String(40), default="本科")
    target_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_path: Mapped[str] = mapped_column(String(80), default="")
    target_region: Mapped[str] = mapped_column(String(80), default="")
    language_score: Mapped[str] = mapped_column(String(80), default="")
    research_exp: Mapped[str] = mapped_column(Text, default="")
    internship_exp: Mapped[str] = mapped_column(Text, default="")
    competition_exp: Mapped[str] = mapped_column(Text, default="")
    startup_exp: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Path(Base):
    __tablename__ = "development_paths"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    description: Mapped[str] = mapped_column(Text)
    target_group: Mapped[str] = mapped_column(String(120), default="本科生")
    duration: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(20), default="published", index=True)


class TimelineNode(Base):
    __tablename__ = "timeline_nodes"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    path_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(120))
    month: Mapped[str] = mapped_column(String(30), default="")
    grade: Mapped[str] = mapped_column(String(30), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    importance: Mapped[str] = mapped_column(String(20), default="normal")


class UserPlan(Base):
    __tablename__ = "user_plans"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    path_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="todo")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlanStep(Base):
    __tablename__ = 'plan_steps'
    __table_args__ = (UniqueConstraint('plan_id', 'title'),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('user_plans.id'), index=True)
    title: Mapped[str] = mapped_column(String(300))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TrackerItem(Base):
    __tablename__ = "tracker_items"
    __table_args__ = (UniqueConstraint("user_id", "opportunity_id"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    opportunity_id: Mapped[str] = mapped_column(String(40), index=True)
    stage: Mapped[str] = mapped_column(String(30), default="saved")
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (UniqueConstraint("user_id", "opportunity_id", "due_at"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    opportunity_id: Mapped[str] = mapped_column(String(40), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="in_app")
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EligibilityRule(Base):
    __tablename__ = "eligibility_rules"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    target_type: Mapped[str] = mapped_column(String(30), default="opportunity", server_default="opportunity")
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    field: Mapped[str] = mapped_column(String(40))
    operator: Mapped[str] = mapped_column(String(20))
    expected: Mapped[str] = mapped_column(String(200))
    label: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(500))
    evidence: Mapped[str] = mapped_column(Text, default="", server_default="")
    evidence_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    logic_group: Mapped[str] = mapped_column(String(40), default="all", server_default="all")
    confidence: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    review_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", index=True)
    extractor: Mapped[str] = mapped_column(String(20), default="parser", server_default="parser")


class ReviewItem(Base):
    __tablename__ = "review_items"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(160))
    source_url: Mapped[str] = mapped_column(String(500))
    risk_level: Mapped[str] = mapped_column(String(20), default="medium")
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    extracted_payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(40))
    resource: Mapped[str] = mapped_column(String(100), index=True)
    detail: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentAction(Base):
    __tablename__ = "agent_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    tool: Mapped[str] = mapped_column(String(40))
    arguments: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
