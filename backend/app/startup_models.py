"""Private startup briefs and immutable document versions."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class StartupProject(Base):
    __tablename__ = 'startup_projects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(160))
    brief_json: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StartupArtifact(Base):
    __tablename__ = 'startup_artifacts'
    __table_args__ = (UniqueConstraint('project_id', 'kind', 'version', name='uq_startup_artifact_version'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('startup_projects.id'), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer)
    project_revision: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    markdown: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
