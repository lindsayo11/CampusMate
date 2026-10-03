"""Database backup/restore. Restore refuses any existing SQLite file; PostgreSQL must be empty."""
import argparse
import os
import sqlite3
import subprocess
from pathlib import Path

from sqlalchemy.engine import make_url


def sqlite_check(path):
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup integrity check failed")
        if not db.execute("SELECT name FROM sqlite_master WHERE name='alembic_version'").fetchone():
            raise RuntimeError("Missing migration version in database")


def run(action, database_url, archive):
    url = make_url(database_url)
    archive = Path(archive).resolve()
    if url.drivername.startswith("sqlite"):
        db_path = Path(url.database).resolve()
        source, target = (db_path, archive) if action == "backup" else (archive, db_path)
        if target.exists():
            raise RuntimeError("Destination already exists; choose a new path")
        sqlite_check(source)
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src, sqlite3.connect(target) as dest:
            src.backup(dest)
        sqlite_check(target)
        target.chmod(0o600)
    elif url.drivername.startswith("postgresql"):
        env = {**os.environ, "PGHOST": url.host or "localhost", "PGPORT": str(url.port or 5432),
               "PGUSER": url.username or "", "PGPASSWORD": url.password or "", "PGDATABASE": url.database or ""}
        for key, value in url.query.items():
            if key in {"sslmode", "sslcert", "sslkey", "sslrootcert"}:
                env["PG" + key.upper()] = str(value)
            else:
                raise RuntimeError("Unsupported PostgreSQL URL option: " + key)
        if action == "backup":
            if archive.exists():
                raise RuntimeError("Archive already exists")
            subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--file", str(archive)], env=env, check=True)
            archive.chmod(0o600)
            subprocess.run(["pg_restore", "--list", str(archive)], env=env, check=True, stdout=subprocess.DEVNULL)
        else:
            result = subprocess.run(["psql", "-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", "SELECT count(*) FROM pg_tables WHERE schemaname='public'"], env=env, check=True, capture_output=True, text=True)
            if result.stdout.strip() != '0':
                raise RuntimeError("Restore target public schema must be empty")
            subprocess.run(["pg_restore", "--exit-on-error", "--single-transaction", "--no-owner", "--dbname", url.database, str(archive)], env=env, check=True)
    else:
        raise RuntimeError("Unsupported database")
    print(f"{action}: verified command completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("archive")
    args = parser.parse_args()
    run(args.action, os.environ["DATABASE_URL"], args.archive)
