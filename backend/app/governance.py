"""Validated editorial import, atomic publishing and owner-only notification actions."""
import hashlib
import json
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .auth import actor_id, require_admin
from .database import get_db
from .models import AuditEvent, EligibilityRule, Opportunity, Reminder, ReviewItem
from .schemas import ReviewOut
from .notification_models import Notification

router = APIRouter(prefix='/v1')


class RuleImport(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    field: Literal['school', 'college', 'grade', 'major']
    operator: Literal['in', 'contains_any']
    expected: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl
    evidence: str = Field(min_length=1, max_length=2000)

    @field_validator('expected')
    @classmethod
    def valid_expected(cls, value):
        if any(not x.strip() for x in value.split(',')):
            raise ValueError('资格条件不可包含空项')
        return value

    @field_validator('source_url')
    @classmethod
    def source_length(cls, value):
        if len(str(value)) > 500:
            raise ValueError('规则来源链接过长')
        return value


class EditorialImport(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    type: Literal['job', 'contest', 'civil_service', 'volunteer', 'club', 'graduate']
    title: str = Field(min_length=1, max_length=160)
    organization: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=10000)
    location: str = Field(min_length=1, max_length=80)
    deadline: datetime
    source_url: HttpUrl
    source_label: str = Field(min_length=1, max_length=100)
    fetched_at: datetime
    tags: list[str] = Field(default_factory=list, max_length=20)
    rules: list[RuleImport] = Field(default_factory=list, max_length=30)

    @field_validator('deadline', 'fetched_at')
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError('时间必须包含时区')
        return value.astimezone(UTC)

    @field_validator('source_url')
    @classmethod
    def url_length(cls, value):
        if len(str(value)) > 500:
            raise ValueError('来源链接过长')
        return value

    @field_validator('tags')
    @classmethod
    def valid_tags(cls, values):
        if any(not t.strip() or ',' in t or len(t) > 40 for t in values) or len(','.join(values)) > 300:
            raise ValueError('标签为空、过长或包含逗号')
        return list(dict.fromkeys(t.strip() for t in values))


def audit(db, actor, action, resource, detail=None):
    db.add(AuditEvent(actor=actor, action=action, resource=resource,
                      detail=json.dumps(detail or {}, ensure_ascii=False), created_at=datetime.now(UTC)))


@router.post('/admin/imports', response_model=ReviewOut, status_code=201)
def import_content(body: EditorialImport, user: str = Depends(require_admin), db: Session = Depends(get_db)):
    if body.fetched_at > datetime.now(UTC):
        raise HTTPException(422, '采集时间不能在未来')
    row = ReviewItem(title=body.title, source_url=str(body.source_url), risk_level='high',
                     confidence=0, status='pending', extracted_payload=body.model_dump_json(), created_at=datetime.now(UTC))
    db.add(row)
    db.flush()
    audit(db, user, 'import', f'review:{row.id}', {'sha256': hashlib.sha256(row.extracted_payload.encode()).hexdigest()})
    db.commit()
    return row


@router.post('/admin/reviews/{review_id}/{action}', response_model=ReviewOut)
def review(review_id: int, action: Literal['approve', 'reject'], user: str = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(ReviewItem, review_id)
    if not row:
        raise HTTPException(404, '审核记录不存在')
    target = 'approved' if action == 'approve' else 'rejected'
    if row.status == target:
        return row
    if row.status != 'pending':
        raise HTTPException(409, '审核已处理，不能覆盖原决定')
    payload = None
    if action == 'approve':
        try:
            payload = EditorialImport.model_validate_json(row.extracted_payload)
        except ValidationError:
            raise HTTPException(422, '待审数据不完整，无法发布；请重新导入完整内容')
        if payload.deadline <= datetime.now(UTC) or payload.fetched_at > datetime.now(UTC):
            raise HTTPException(422, '截止时间已过或采集时间无效')
        if str(payload.source_url) != row.source_url:
            raise HTTPException(422, '来源与审核记录不一致')
    changed = db.execute(update(ReviewItem).where(ReviewItem.id == review_id, ReviewItem.status == 'pending').values(status=target))
    if not changed.rowcount:
        db.rollback()
        raise HTTPException(409, '审核已由其他管理员处理')
    details = {}
    if payload:
        oid = 'pub-' + str(uuid4())
        data = payload.model_dump(exclude={'tags', 'source_url', 'rules'})
        db.add(Opportunity(id=oid, **data, source_url=str(payload.source_url), tags=','.join(payload.tags), status='published', trust_score=0.8))
        for rule in payload.rules:
            db.add(EligibilityRule(opportunity_id=oid, **rule.model_dump(exclude={'source_url'}), source_url=str(rule.source_url)))
        details['opportunity_id'] = oid
        from .knowledge import record_publication
        record_publication(db, review_id, oid)
    audit(db, user, action, f'review:{review_id}', details)
    db.commit()
    return db.get(ReviewItem, review_id)


@router.post('/admin/opportunities/{opportunity_id}/unpublish')
def unpublish(opportunity_id: str, user: str = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(Opportunity, opportunity_id)
    if not row:
        raise HTTPException(404, '机会不存在')
    if row.status != 'unpublished':
        row.status = 'unpublished'
        audit(db, user, 'unpublish', f'opportunity:{row.id}')
        db.commit()
    return {'status': 'unpublished'}


@router.get('/admin/audit')
def audit_events(user: str = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(100)).all()


@router.post('/notifications/{notification_id}/read')
def read_notification(notification_id: int, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    row = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == user))
    if not row:
        raise HTTPException(404, '通知不存在')
    if row.read_at is None:
        row.read_at = datetime.now(UTC).isoformat()
        db.commit()
    return row


@router.delete('/reminders/{reminder_id}')
def cancel_reminder(reminder_id: int, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    # Same row lock as delivery: cancellation cannot race a sent notification.
    claimed = db.execute(update(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user).values(sent=Reminder.sent))
    if not claimed.rowcount:
        raise HTTPException(404, '提醒不存在')
    row = db.get(Reminder, reminder_id, populate_existing=True)
    if row.sent:
        raise HTTPException(409, '提醒已经投递')
    db.delete(row)
    db.commit()
    return {'cancelled': True}
