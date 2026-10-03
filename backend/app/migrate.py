"""Explicit schema gate. API and worker never mutate database structure."""
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from .database import engine


def check_schema():
    cfg = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    expected = set(ScriptDirectory.from_config(cfg).get_heads())
    with engine.connect() as connection:
        actual = set(MigrationContext.configure(connection).get_current_heads())
    if actual != expected:
        raise RuntimeError('Database migration required: run alembic upgrade head before starting API/worker')
