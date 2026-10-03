"""Database-backed fixed-window quotas shared by all API processes."""
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import String, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class SocialQuota(Base):
    __tablename__ = "social_quotas"
    key: Mapped[str] = mapped_column(String(180), primary_key=True)
    window: Mapped[int]
    count: Mapped[int]


def consume(db, user: str, action: str, limit: int, seconds: int):
    now = int(datetime.now(UTC).timestamp())
    window = now // seconds
    key = f"{action}:{user}"
    if not db.get(SocialQuota, key):
        try:
            with db.begin_nested():
                db.add(SocialQuota(key=key, window=window, count=0))
                db.flush()
        except IntegrityError:
            pass
    # Serialize the reset and increment on one account/action row.
    db.execute(update(SocialQuota).where(SocialQuota.key == key).values(count=SocialQuota.count))
    db.execute(update(SocialQuota).where(SocialQuota.key == key, SocialQuota.window != window)
               .values(window=window, count=0))
    result = db.execute(update(SocialQuota).where(SocialQuota.key == key, SocialQuota.count < limit)
                        .values(count=SocialQuota.count + 1))
    if not result.rowcount:
        raise HTTPException(429, "已达到账号操作次数限制，请稍后重试",
                            headers={"Retry-After": str(seconds - now % seconds)})
