"""System content skips editorial approval; manual input never self-selects this mode."""
from test_data_catalog import sample  # noqa: F401
from app.database import SessionLocal
from app.intake_models import DocumentVersion, DocumentArchive
from app.data_catalog import auto_publish


def test_system_direct_and_admin_delete(sample):
    client, data = sample
    with SessionLocal.begin() as db:
        doc = db.get(DocumentVersion, data['did'])
        assert not auto_publish(db, doc)
        doc.import_mode = 'system'
        assert auto_publish(db, doc)
    catalog = client.get('/v1/data/catalog').json()
    assert any(x['id'] == data['item_id'] for x in catalog['items'])
    path = f"/v1/admin/data/documents/{data['did']}"
    assert client.delete(path, headers={'x-user-id':'student'}).status_code == 403
    assert client.delete(path).status_code == 200
    with SessionLocal.begin() as db:
        assert not auto_publish(db, db.get(DocumentVersion, data['did']))
    assert data['item_id'] not in {x['id'] for x in client.get('/v1/data/catalog').json()['items']}


def test_fixture_only_demo_and_not_in_production(sample, monkeypatch):
    from app.config import settings
    _, data = sample
    with SessionLocal.begin() as db:
        doc = db.get(DocumentVersion, data['did'])
        db.get(DocumentArchive, doc.id).is_fixture = True
        doc.import_mode = 'system'
        assert not auto_publish(db, doc)
        doc.import_mode, doc.test_batch = 'demo', 'unit-demo'
        assert auto_publish(db, doc)
        monkeypatch.setattr(settings, 'demo_mode', False)
        assert not auto_publish(db, doc)
