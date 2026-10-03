"""Shared notification model, independent of worker entry points."""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    reminder_id: Mapped[int] = mapped_column(unique=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    opportunity_id: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[str] = mapped_column(String(40))
    read_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
