import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def run(db, *args):
    env={**os.environ, 'DATABASE_URL': 'sqlite:///'+str(db)}
    return subprocess.run([sys.executable, '-m', 'alembic', '-c', str(ROOT/'alembic.ini'), *args], env=env, check=True, capture_output=True)


def test_baseline_upgrade_preserves_rows(tmp_path):
    db=tmp_path/'migration.db'
    run(db, 'upgrade', '0001')
    with sqlite3.connect(db) as con:
        con.execute("INSERT INTO notifications (id,reminder_id,user_id,opportunity_id,created_at) VALUES (1,1,'existing','job','2026-01-01')")
    run(db, 'upgrade', 'head')
    run(db, 'check')
    with sqlite3.connect(db) as con:
        assert con.execute('SELECT user_id,read_at FROM notifications').fetchone()==('existing',None)
    run(db, 'downgrade', '0001')
    run(db, 'upgrade', 'head')
    with sqlite3.connect(db) as con:
        assert con.execute('SELECT COUNT(*) FROM notifications').fetchone()[0]==1


def test_knowledge_backfill_does_not_publish_private_archives(tmp_path):
    db=tmp_path/'knowledge-upgrade.db'
    run(db,'upgrade','0010')
    with sqlite3.connect(db) as con:
        con.execute("INSERT INTO source_extractions (id,document_id,review_id) VALUES ('extraction','source-document',42)")
        con.execute("""INSERT INTO opportunities
            (id,type,title,organization,summary,location,deadline,source_url,source_label,trust_score,tags,status,fetched_at)
            VALUES ('old-opportunity','contest','测试','测试单位','摘要','线上','2030-01-01','https://example.edu/','测试',0.8,'','published','2026-01-01')""")
        con.execute("""INSERT INTO audit_events (actor,action,resource,detail,created_at)
            VALUES ('admin','approve','review:42','{"opportunity_id":"old-opportunity"}','2026-01-01')""")
    run(db,'upgrade','head');run(db,'check')
    with sqlite3.connect(db) as con:
        assert con.execute('SELECT opportunity_id,document_id,review_id FROM knowledge_publications').fetchall()==[('old-opportunity','source-document',42)]
        assert con.execute('SELECT COUNT(*) FROM knowledge_access').fetchone()[0]==0
