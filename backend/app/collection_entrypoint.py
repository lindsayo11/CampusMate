"""Railway entrypoint: one API migrates; private workers wait for the schema."""
import os,subprocess,sys,time
from pathlib import Path


def main():
    role=sys.argv[1] if len(sys.argv)>1 else os.environ.get('COLLECTION_ROLE','api')
    if role=='api':
        subprocess.run(['alembic','upgrade','head'],check=True)
        from .database import SessionLocal
        from .collection_bundle import import_bundle
        from .notice_watch import install
        bundle=Path('/app/collection-data.json.gz')
        with SessionLocal.begin() as db:
            if bundle.exists():import_bundle(db,bundle.read_bytes())
        with SessionLocal() as db:install(db,os.environ['NOTICE_WATCH_OPERATOR'])
        os.execvp('uvicorn',['uvicorn','app.main:app','--host','0.0.0.0','--port',os.environ.get('PORT','8000')])
    elif role in {'worker','monitor'}:
        from .migrate import check_schema
        for attempt in range(120):
            try:check_schema();break
            except Exception:time.sleep(2)
        else:raise RuntimeError('Collection database not ready')
        from .database import SessionLocal
        from .intake_models import SourceEndpoint
        from sqlalchemy import select
        for attempt in range(120):
            with SessionLocal() as db:
                if db.scalar(select(SourceEndpoint.id).where(SourceEndpoint.scheduled.is_(True))):break
            time.sleep(2)
        else:raise RuntimeError('Collection sources not installed')
        os.execv(sys.executable,[sys.executable,'-m','app.worker' if role=='worker' else 'app.collection_monitor'])
    else:raise ValueError('Unknown collection role')


if __name__=='__main__':main()
