# Industrial software evaluation — 2026-09-29

## Environment

- Python 3.12.14 virtual environment at `backend/.venv`.
- All pins from `backend/requirements-tested.txt` installed.
- Node v24.19.0 / npm 11.9.0; `frontend/package-lock.json` installed with `npm ci`.
- SQLite isolated migration/test database; no Docker, PostgreSQL, Supabase, SMTP or external identity provider.

## Verification

| Gate | Result |
|---|---|
| Alembic upgrade + `alembic check` | Pass; no new upgrade operations |
| Backend pytest | 52 passed, 1 Starlette/httpx deprecation warning |
| Frontend unit tests | 19 passed |
| TypeScript | Pass |
| Next production build | Pass with repository RSS compatibility preload |
| Full `scripts/check.sh` | Pass |

## Defect fixed during evaluation

The isolated collector parser launched `python -m app.parsers` without an import root. When the service was started from the repository root, HTML/text/XLSX/PDF collection subprocesses failed with `ModuleNotFoundError`, causing retry/failure states. `extract_isolated` now supplies the backend working directory and `PYTHONPATH`, and the regression suite passes.

The release check now automatically loads the existing RSS compatibility preload in environments where Node cannot read `uv_resident_set_memory`; this keeps the build deterministic in restricted Linux runners without changing application behavior.

## Industrial readiness assessment

The package is suitable for a controlled staging release: migrations are consistent, the automated backend/frontend gates are green, and the collector failure is covered by tests. Production release still requires a real PostgreSQL migration rehearsal, external identity/provider integration tests, TLS/reverse-proxy validation, backup/restore drill, load testing, dependency vulnerability scanning in CI, and browser E2E execution with the managed Chromium binary.

The main remaining operational risk is environment coverage rather than a known application test failure. Demo mode must remain disabled outside isolated environments, and collector source permissions/rate limits require production configuration review.
