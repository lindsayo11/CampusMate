"""Export a public-only SQLite preview; never modify the source database."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_TABLES = (
    'agent_actions', 'agent_turns', 'agent_conversations', 'data_corrections',
    'data_subscriptions', 'plan_reminders', 'plan_steps', 'user_plans', 'profiles',
    'tracker_items', 'reminders', 'notifications', 'room_messages', 'room_reads',
    'rooms', 'team_invitations', 'team_tasks', 'teams', 'social_blocks',
    'social_quotas', 'message_reports', 'task_alerts', 'audit_events', 'worker_heartbeats',
)


def export(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or not source.is_file():
        raise ValueError('必须指定存在的源数据库，并使用不同的输出路径')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        target = Path(directory) / 'public.db'
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
            with sqlite3.connect(target) as dst:
                src.backup(dst)
        with sqlite3.connect(target) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            # Fail closed: do not accidentally distribute user-imported/private documents.
            private = db.execute("SELECT count(*) FROM document_versions WHERE import_mode != 'system' OR deleted_at IS NOT NULL").fetchone()[0]
            if private or db.execute('SELECT count(*) FROM knowledge_access WHERE public != 1').fetchone()[0]:
                raise ValueError('数据库含非公开文档，需要先单独审查并导出公开内容')
            db.execute('PRAGMA secure_delete=ON')
            removed = {}
            for table in PRIVATE_TABLES:
                if table in tables:
                    removed[table] = db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                    db.execute(f'DELETE FROM "{table}"')
            db.execute("UPDATE source_endpoints SET secret_ref = ''")
            for table in ('notice_resources', 'source_endpoint_runs'):
                db.execute(f'UPDATE {table} SET lease_until = NULL, lease_token = NULL')
            db.commit()
            db.execute('VACUUM')
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('公开快照完整性检查失败')
            counts = {t: db.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in sorted(tables)}
            if any(counts.get(t, 0) for t in PRIVATE_TABLES):
                raise RuntimeError('个人数据清理检查失败')
            report = {'exported_at': datetime.now(timezone.utc).isoformat(),
                      'schema': db.execute('SELECT version_num FROM alembic_version').fetchone()[0],
                      'scope': 'public system-imported documents and source configuration; private tables emptied',
                      'removed_private_rows': removed, 'table_counts': counts}
        target.replace(output)
    report_path = ROOT / 'handover/data-package-report.json'
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'demo-data/release-preview.db')
    args = parser.parse_args()
    result = export(args.source, args.output)
    print(json.dumps({'schema': result['schema'], 'public_items': result['table_counts']['development_items'],
                      'archived_versions': result['table_counts']['document_versions'],
                      'removed_private_rows': sum(result['removed_private_rows'].values())}, ensure_ascii=False))
