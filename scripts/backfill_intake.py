"""Repair documents collected before the knowledge bridge and date extraction existed.

Two historical gaps are fixed here, both of which made collected data invisible in
the student UI even though it was sitting in the database:

1. **Knowledge chain.** `source_scheduler` writes `document_versions`, while the
   public search reads `source_documents` + `source_heads` + `knowledge_publications`.
   Documents collected before that bridge existed have no archive row, so they can
   never be searched. This mirrors them under their own id (evidence, chunks and
   citations then line up) and publishes them on the system path.

2. **Time fields.** The student timeline (`/v1/data/timeline`) only renders items
   carrying `start_time` or `deadline`, and the policy ingest never set either. The
   document's own text has the 成文日期 and often the 报名窗口, so this re-parses the
   archived HTML and fills them in.

Because `data_catalog.visible()` compares the live snapshot against the stored
publication, any change to the underlying rows invalidates the publication. Both
repairs therefore finish by re-publishing, or the item stays hidden.

Idempotent: safe to run repeatedly.

Usage
-----
    DATABASE_URL=... python scripts/backfill_intake.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.adapters.base import RawArtifact  # noqa: E402
from app.adapters.education import MoEPolicyAdapter  # noqa: E402
from app.data_catalog import auto_publish  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.intake import _parse_date  # noqa: E402
from app.models import Path  # noqa: E402
from app.intake_models import (  # noqa: E402
    DevelopmentItem,
    DevelopmentItemPath,
    DocumentArchive,
    DocumentVersion,
    PolicyRecord,
)
from app.source_scheduler import publish_collected_document  # noqa: E402


def repair_policy_dates(db, document):
    """Re-derive 成文日期 / 报名窗口 from the archived HTML onto the policy rows."""
    archive = db.get(DocumentArchive, document.id)
    if not archive or not archive.content:
        return False
    parsed = MoEPolicyAdapter().parse(RawArtifact(
        content=archive.content, canonical_url=document.canonical_url,
        source_item_id=document.source_item_id, content_type=archive.content_type))
    if not parsed.records:
        return False
    values = parsed.records[0]
    issued = _parse_date(values.get("issued_at"))
    start = _parse_date(values.get("registration_start")) or issued
    deadline = _parse_date(values.get("registration_deadline"))
    if not (start or deadline or issued):
        return False
    changed = False
    policy = db.scalar(select(PolicyRecord).where(
        PolicyRecord.source_document_id == document.id))
    if policy and policy.effective_at != issued:
        policy.effective_at, changed = issued, True
    item = db.scalar(select(DevelopmentItem).where(
        DevelopmentItem.source_document_id == document.id))
    if item and (item.start_time != start or item.deadline != deadline):
        item.start_time, item.deadline, changed = start, deadline, True
    return changed


def retag_paths(db):
    """Re-map every development item onto a channel path.

    The development channels (保研推免/国内考研/境外留学/考公考编/实习就业/创新创业)
    each filter by their own path code, and `path_codes()` only walks *down* from a
    code. Items parked on the parent `domestic_study` therefore appear in 信息中心
    but make all six channels look empty. This re-derives the leaf path from the
    item's own text.
    """
    from app.adapters.education import classify_path

    changed = 0
    for item in db.scalars(select(DevelopmentItem)).all():
        code = classify_path(item.title, item.description or "")
        wanted = db.scalar(select(Path).where(Path.code == code)) if code else None
        current = db.scalars(select(DevelopmentItemPath).where(
            DevelopmentItemPath.development_item_id == item.id)).all()
        if wanted and len(current) == 1 and current[0].path_id == wanted.id:
            continue
        for link in current:
            db.delete(link)
        if wanted:
            db.add(DevelopmentItemPath(development_item_id=item.id, path_id=wanted.id))
        changed += 1
    return changed


def main():
    if not os.environ.get("DATABASE_URL"):
        print("请先设置 DATABASE_URL 环境变量")
        return 1
    with SessionLocal.begin() as db:
        docs = db.scalars(select(DocumentVersion).where(
            DocumentVersion.deleted_at.is_(None),
            DocumentVersion.import_mode == "system",
        ).order_by(DocumentVersion.first_seen_at)).all()
        if docs:
            for document in docs:
                linked = publish_collected_document(db, document)
                dated = repair_policy_dates(db, document)
                # 快照与底层行不一致会隐藏条目，所以两项修复后都要重新发布。
                published = auto_publish(db, document)
                print(f"  {document.canonical_url[:66]}")
                print(f"      建链={'是' if linked else '否'}  补日期={'是' if dated else '否'}"
                      f"  重新发布={'是' if published else '否'}")
        else:
            print("没有需要修复的系统导入文档")
        moved = retag_paths(db)
        print(f"\n路径重挂: {moved} 条")
        # 路径变了，快照也要刷新，否则条目会被 visible() 隐藏。
        refreshed = sum(1 for d in db.scalars(select(DocumentVersion)).all() if auto_publish(db, d))
        print(f"重新发布: {refreshed} 份")
    return 0


if __name__ == "__main__":
    sys.exit(main())
