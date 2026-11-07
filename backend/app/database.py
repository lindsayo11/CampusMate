from sqlalchemy import create_engine,event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False,"timeout":30} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
if settings.database_url.startswith('sqlite'):
    @event.listens_for(engine,'connect')
    def sqlite_concurrency(connection,_):
        # Coverage reads and large archive writes run concurrently. WAL prevents
        # a long read from holding the rollback-journal lock against the collector.
        cursor=connection.cursor()
        try:
            cursor.execute('PRAGMA busy_timeout=30000')
            if cursor.execute('PRAGMA journal_mode').fetchone()[0]!='wal':cursor.execute('PRAGMA journal_mode=WAL')
        finally:cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
