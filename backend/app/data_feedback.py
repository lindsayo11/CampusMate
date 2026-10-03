"""Version-specific corrections are private to their author and administrators."""
from datetime import UTC, datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column
from .auth import actor_id, require_admin
from .database import Base, get_db
from .data_catalog import publication
from .governance import audit


class DataCorrection(Base):
    __tablename__ = 'data_corrections'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    publication_id: Mapped[str] = mapped_column(String(36), index=True)
    category: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    review_note: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CorrectionIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    publication_id: str = Field(min_length=36, max_length=36)
    category: Literal['date','content','source','other']
    message: str = Field(min_length=5, max_length=2000)


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    status: Literal['resolved','dismissed']
    note: str = Field(min_length=3, max_length=2000)


router = APIRouter(prefix='/v1/data/corrections')
admin = APIRouter(prefix='/v1/admin/data/corrections', dependencies=[Depends(require_admin)])


@router.post('', status_code=201)
def submit(body: CorrectionIn, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    publication(body.publication_id, db)
    row = DataCorrection(user_id=user, **body.model_dump(), created_at=datetime.now(UTC))
    db.add(row); db.commit(); db.refresh(row)
    return {'id':row.id,'status':row.status}


@router.get('')
def mine(user: str = Depends(actor_id), db: Session = Depends(get_db)):
    return db.scalars(select(DataCorrection).where(DataCorrection.user_id == user)
        .order_by(DataCorrection.id.desc()).limit(100)).all()


@admin.get('')
def queue(db: Session = Depends(get_db)):
    return db.scalars(select(DataCorrection).order_by(DataCorrection.id.desc()).limit(100)).all()


@admin.patch('/{correction_id}')
def review(correction_id: int, body: ReviewIn, user: str = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(DataCorrection, correction_id)
    if not row: raise HTTPException(404,'反馈不存在')
    row.status, row.review_note = body.status, body.note
    audit(db,user,'data_correction_review',f'data_correction:{row.id}',{'status':body.status,'note':body.note})
    db.commit(); return {'id':row.id,'status':row.status}
