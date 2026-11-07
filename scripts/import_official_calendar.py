"""Bounded, evidence-checked live import into the LOCAL preview only.

Default: fetch/validate and report, no DB writes. --apply uses only
local-data/demo.db, backs it up once, and never modifies personal plans.
Known dated facts come from a reviewed manifest, not guessed/LLM-extracted dates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
DB = ROOT / "local-data/demo.db"
MANIFEST = ROOT / "backend/app/calendar_source_manifest.json"
UA = "CampusMateSourcePreview/1.0"
LIMIT = 3 * 1024 * 1024


def compact(text):
    return re.sub(r"\s+", "", text)


def fetch_verified(client, entry):
    url = entry["url"]
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(url))
    robots = client.get(origin + "/robots.txt")
    if robots.status_code == 200:
        rules = RobotFileParser()
        rules.parse(robots.text.splitlines())
        if not rules.can_fetch(UA, url):
            raise ValueError("robots.txt 禁止抓取")
    elif robots.status_code not in {404, 410}:
        raise ValueError(f"robots.txt 无法确认：HTTP {robots.status_code}")
    time.sleep(1)
    with client.stream("GET", url) as response:
        response.raise_for_status()
        if response.is_redirect:
            raise ValueError("页面发生跳转，需要重新核验官方地址")
        if "text/html" not in response.headers.get("content-type", ""):
            raise ValueError("不是预期的 HTML 公告")
        payload = bytearray()
        for chunk in response.iter_bytes():
            payload.extend(chunk)
            if len(payload) > LIMIT:
                raise ValueError("正文超过 3 MB 限制")
    raw = bytes(payload)
    # Official pages occasionally mislabel UTF-8 as Latin-1 in HTTP headers.
    html = raw.decode("utf-8", errors="strict")
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript"]):
        node.decompose()
    text = soup.get_text("\n", strip=True)
    normalized = compact(text)
    for expected in entry["checks"]:
        if compact(expected) not in normalized:
            raise ValueError("日期证据未匹配：" + expected)
    return {**entry, "raw_text": text, "archive_bytes": raw,
            "content_type": "text/html; charset=utf-8", "trust": 0.98,
            "summary": entry["summary"] + " " + entry["date_precision"]}


def import_entry(db, item):
    from sqlalchemy import select
    from app.intake_models import Source, SourceEndpoint, DocumentVersion, DevelopmentItem, DevelopmentItemPath
    from app.models import Path as DevelopmentPath
    from app.real_content import _id, _parse, seed_real_content
    from app.data_catalog import auto_publish

    document_id = _id("document:" + item["key"])
    digest = hashlib.sha256(item["archive_bytes"]).hexdigest()
    old = db.get(DocumentVersion, document_id)
    if old:
        if old.content_hash != digest and compact(old.raw_text) != compact(item["raw_text"]):
            raise ValueError("已归档正文有变化；保留现有版本，需重新核验后发布")
        return {"result": "unchanged", "document_id": document_id, "milestones": len(item["milestones"])}
    code, now = item["source_code"], datetime.now(UTC)
    source_id = _id("source:" + code)
    if not db.get(Source, source_id):
        db.add(Source(id=source_id, source_code=code, name=item["source_label"],
            publisher=item["source_label"], authority_level="A", official=True,
            source_class=item["source_class"], jurisdiction_level="national",
            supported_paths=json.dumps([item["path_code"]] if item["path_code"] else []),
            supported_item_types=json.dumps([item["item_type"]]),
            base_url=item["url"].split("/", 3)[0] + "//" + urlsplit(item["url"]).netloc,
            active=True, verified_at=now))
        db.flush()
        db.add(SourceEndpoint(id=_id("endpoint:" + code), source_id=source_id,
            name=item["key"], endpoint_type="html", url=item["url"],
            access_tags='["DIRECT"]', auth_type="none", format="html",
            parser_type="VerifiedCalendarImport", automation_level="AUTO-2",
            agent_mode="REVIEW", active=True, scheduled=False))
        db.flush()
    seed_real_content(db, [item])
    for step in item["milestones"]:
        key = _id("milestone:" + item["key"] + ":" + step["key"])
        db.add(DevelopmentItem(id=key, title=step["title"], item_type="calendar_stage",
            cycle_type="event", description=step["note"], start_time=_parse(step["start"]),
            deadline=_parse(step["end"]), location=item["location"],
            materials='["核对原文与适用对象", "按主办方最新通知安排"]',
            status="published", source_document_id=document_id))
        db.flush()
        if item["path_code"]:
            path = db.scalar(select(DevelopmentPath).where(DevelopmentPath.code == item["path_code"]))
            if path:
                db.add(DevelopmentItemPath(development_item_id=key, path_id=path.id))
    db.flush()
    if not auto_publish(db, db.get(DocumentVersion, document_id)):
        raise ValueError("日历发布校验未通过")
    return {"result": "imported", "document_id": document_id, "milestones": len(item["milestones"])}


def repair_archived_dates(entries):
    """Correct UTC storage using only already verified/archived manifest facts."""
    if not DB.is_file() or DB.resolve().parent != (ROOT / "local-data").resolve():
        raise RuntimeError("仅允许修复本地预览数据库")
    os.environ.update(DATABASE_URL="sqlite:///" + DB.as_posix(), DEMO_MODE="true",
                      COLLECTOR_ENABLED="false")
    from app.main import app
    from app.database import SessionLocal
    from app.intake_models import DocumentVersion, DocumentArchive, DevelopmentItem
    from app.models import Opportunity
    from app.real_content import _id, _parse
    from app.data_catalog import auto_publish
    repaired = []
    with SessionLocal.begin() as db:
        for item in entries:
            doc = db.get(DocumentVersion, _id("document:" + item["key"]))
            if not doc:
                continue
            archive = db.get(DocumentArchive, doc.id)
            if not archive or hashlib.sha256(archive.content).hexdigest() != doc.content_hash:
                raise ValueError("原文归档完整性验证失败")
            if any(compact(check) not in compact(doc.raw_text) for check in item["checks"]):
                raise ValueError("原文日期证据不匹配")
            opportunity = db.get(Opportunity, "real-" + item["key"][:35])
            opportunity.deadline = _parse(item["deadline"])
            opportunity.summary = item["summary"] + " " + item["date_precision"]
            main = db.get(DevelopmentItem, _id("development-item:" + item["key"]))
            main.start_time, main.deadline = _parse(item["start"]), _parse(item["deadline"])
            main.description = opportunity.summary
            for step in item["milestones"]:
                row = db.get(DevelopmentItem, _id("milestone:" + item["key"] + ":" + step["key"]))
                row.start_time, row.deadline = _parse(step["start"]), _parse(step["end"])
            db.flush()
            if not auto_publish(db, doc):
                raise ValueError("日期修复后发布验证失败")
            repaired.append(item["key"])
    print(json.dumps({"date_storage": "UTC", "repaired": repaired, "personal_plans_changed": 0}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--only", help="只抓取某个已登记条目；未列入白名单的 URL 不允许传入")
    parser.add_argument("--repair-dates", action="store_true", help="仅按已归档证据纠正本地日期时区，不联网")
    args = parser.parse_args()
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.only:
        entries = [entry for entry in entries if entry["key"] == args.only]
        if not entries:
            parser.error("条目不在已核验来源清单内")
    if args.repair_dates:
        repair_archived_dates(entries)
        return
    verified, report = [], []
    # No inherited proxy/auth cookies; only four allowlisted public URLs.
    with httpx.Client(timeout=25, headers={"User-Agent": UA}, follow_redirects=False) as client:
        for entry in entries:
            row = {"key": entry["key"], "url": entry["url"], "fetched_at": datetime.now(UTC).isoformat()}
            try:
                item = fetch_verified(client, entry)
                verified.append(item)
                row.update(status="verified", sha256=hashlib.sha256(item["archive_bytes"]).hexdigest(),
                           bytes=len(item["archive_bytes"]))
            except Exception as exc:
                row.update(status="failed", error=str(exc))
            report.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            time.sleep(1)
    if args.apply and verified:
        if not DB.is_file() or DB.resolve().parent != (ROOT / "local-data").resolve():
            raise RuntimeError("拒绝写入：仅允许现有的本地预览数据库")
        backup = DB.with_name("before-official-calendar-20261107.db")
        if not backup.exists():
            with sqlite3.connect(DB) as src, sqlite3.connect(backup) as dest:
                src.backup(dest)
        os.environ.update(DATABASE_URL="sqlite:///" + DB.as_posix(), DEMO_MODE="true",
                          COLLECTOR_ENABLED="false")
        from app.main import app  # register mapped tables; does not start the ASGI app
        from app.database import SessionLocal
        from app.models import Opportunity
        from app.real_content import REAL_CONTENT
        with SessionLocal() as db:
            for item in verified:
                row = next(r for r in report if r["key"] == item["key"])
                try:
                    with db.begin_nested():
                        row.update(import_entry(db, item))
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    row.update(status="failed", error=str(exc))
            # Targeted repair only: preserve record IDs, originals and user links.
            for item in REAL_CONTENT:
                if item["opportunity_type"] == "policy":
                    existing = db.get(Opportunity, "real-" + item["key"][:35])
                    if existing:
                        existing.type = "policy"
            for fixture_id in ("contest-001",):
                fixture = db.get(Opportunity, fixture_id)
                if fixture and fixture.source_url.startswith("https://example.edu/"):
                    fixture.status = "archived"
            db.commit()
    output = ROOT / "docs/local-calendar-settings-review/import-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.only and output.exists():
        previous = json.loads(output.read_text(encoding="utf-8"))
        active_keys = {entry["key"] for entry in json.loads(MANIFEST.read_text(encoding="utf-8"))}
        report = [row for row in previous if row["key"] in active_keys and row["key"] != args.only] + report
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REPORT " + str(output), flush=True)
    if any(row["status"] == "failed" for row in report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
