import importlib.util
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.operations import heartbeat


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[2] / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_worker_status_permissions_and_trace():
    heartbeat('ok')
    with TestClient(app) as c:
        assert c.get('/v1/admin/operations', headers={'X-User-Id': 'other'}).status_code == 403
        r = c.get('/v1/admin/operations')
        assert r.json()['worker']['healthy']
        assert len(r.headers['x-request-id']) == 36
        heartbeat('error')
        assert not c.get('/v1/admin/operations').json()['worker']['healthy']


def test_backup_restore_preserves_rows_and_refuses_overwrite(tmp_path):
    backup = load_script('backup')
    original = tmp_path / 'source.db'
    with sqlite3.connect(original) as db:
        db.execute('CREATE TABLE alembic_version(version_num TEXT)')
        db.execute("INSERT INTO alembic_version VALUES ('0007')")
        db.execute('CREATE TABLE evidence(id INTEGER PRIMARY KEY, body TEXT)')
        db.execute("INSERT INTO evidence VALUES (1, 'restore-proof')")
    archive = tmp_path / 'backup.sqlite'
    restored = tmp_path / 'restored.db'
    backup.run('backup', 'sqlite:///' + str(original), archive)
    backup.run('restore', 'sqlite:///' + str(restored), archive)
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT body FROM evidence').fetchone()[0] == 'restore-proof'
    import pytest
    with pytest.raises(RuntimeError, match='already exists'):
        backup.run('restore', 'sqlite:///' + str(restored), archive)


def test_preflight_rejects_demo_and_missing_services():
    preflight = load_script('preflight')
    errors = preflight.check({'DEMO_MODE': 'true'})
    assert any('DEMO_MODE' in e for e in errors)
    assert not any('Dify' in e for e in errors)
    assert not any('Dify' in e for e in preflight.check({'ENABLE_AGENT_UI':'true'}))
    assert any('Dify' in e for e in preflight.check({'DEVELOPMENT_DIFY_API_BASE':'https://dify.test/v1'}))


def test_identity_outage_and_invalid_provider_response(monkeypatch):
    import httpx

    from app import auth
    from app.config import settings
    monkeypatch.setattr(settings, 'demo_mode', False)
    monkeypatch.setattr(settings, 'supabase_url', 'https://auth.test')
    monkeypatch.setattr(settings, 'supabase_anon_key', 'test')
    with TestClient(app) as c:
        monkeypatch.setattr(auth.httpx, 'get', lambda *a, **k: httpx.Response(503))
        assert c.get('/v1/profile', headers={'Authorization': 'Bearer test'}).status_code == 503
        monkeypatch.setattr(auth.httpx, 'get', lambda *a, **k: httpx.Response(200, text='bad json'))
        assert c.get('/v1/profile', headers={'Authorization': 'Bearer test'}).status_code == 503


def test_preflight_refuses_local_security_overrides_and_sqlite():
    preflight=load_script('preflight')
    errors=preflight.check({'DEMO_MODE':'false','SINGLE_ADMIN_OVERRIDES':'true','COLLECTOR_SKIP_ROBOTS':'true','DATABASE_URL':'sqlite:///preview.db'})
    assert any('SINGLE_ADMIN_OVERRIDES' in e for e in errors)
    assert any('COLLECTOR_SKIP_ROBOTS' in e for e in errors)
    assert any('PostgreSQL' in e for e in errors)
