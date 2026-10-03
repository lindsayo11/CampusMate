"""Build a clean handover archive, API contract and SHA-256 file manifest."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.test-runtime', 'node_modules', '.next', '.deps', '.venv', '__pycache__',
            '.pytest_cache', '.ruff_cache', '.git', 'test-results', 'playwright-report',
            'pytest-of-root', 'local-data', 'ingested-data', 'logs', 'releases'}
PUBLIC_DATABASES = {'demo-data/release-preview.db', 'demo-data/retained-demo.db'}
MANIFEST = 'handover/file-manifest.json'
DIFF = 'handover/changes-from-original.json'


def selected_files():
    selected = []
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in EXCLUDED or part.startswith('pip-') or part.endswith('.egg-info') for part in rel.parts):
            continue
        if rel.parts[0] == 'artifacts' and rel.parts[1:2] != ('stage34',):
            continue
        if rel.as_posix() in PUBLIC_DATABASES:
            selected.append(path)
            continue
        if path.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.log', '.pyc', '.tsbuildinfo', '.zip', '.pem', '.key'}:
            continue
        if path.name.startswith('.env') and path.name != '.env.example':
            continue
        if path.name == '.DS_Store' or path.name.startswith('tmp') or path.name.endswith(('.db-wal', '.db-shm')):
            continue
        selected.append(path)
    return selected


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--baseline', type=Path, help='Original prototype ZIP; read only')
    args = parser.parse_args()
    if not (ROOT / 'demo-data/release-preview.db').is_file():
        parser.error('先使用 export_handover_data.py 导出公开快照')
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.main import app
    (ROOT / 'specs/openapi.json').write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    handover = ROOT / 'handover'
    handover.mkdir(exist_ok=True)
    if args.baseline:
        with ZipFile(args.baseline) as original:
            prefix = 'CampusMate/'
            baseline = {name[len(prefix):]: sha(original.read(name)) for name in original.namelist()
                        if name.startswith(prefix) and not name.endswith('/')}
        current = {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in selected_files()
                   if p.relative_to(ROOT).as_posix() not in {MANIFEST, DIFF}}
        diff = {'baseline': 'User-provided CampusMate(1).zip', 'version': app.version,
                'note': 'Changes in shipped files only; excluded runtime/private files are not deletions.',
                'added': sorted(set(current) - set(baseline)),
                'modified': [{'path': p, 'original_sha256': baseline[p], 'current_sha256': current[p]}
                             for p in sorted(current.keys() & baseline.keys()) if baseline[p] != current[p]],
                'unchanged_shipped_files': sum(baseline.get(p) == v for p, v in current.items())}
        (ROOT / DIFF).write_text(json.dumps(diff, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    files = [p for p in selected_files() if p.relative_to(ROOT).as_posix() != MANIFEST]
    manifest = {'version': app.version, 'created_at': datetime.now(timezone.utc).isoformat(),
                'note': 'SHA-256 for every shipped file except this self-referential manifest.',
                'files': [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size,
                           'sha256': sha(p.read_bytes())} for p in files]}
    (ROOT / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    files = selected_files()
    output = args.output or ROOT.parent / 'releases' / f'CampusMate_v{app.version}_handover_20261001.zip'
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.zip.tmp')
    try:
        with ZipFile(temporary, 'w', ZIP_DEFLATED, compresslevel=6) as archive:
            for path in files:
                archive.write(path, 'CampusMate/' + path.relative_to(ROOT).as_posix())
        with temporary.open('rb') as saved:
            os.fsync(saved.fileno())
        with ZipFile(temporary) as saved:
            if saved.testzip() is not None or len(set(saved.namelist())) != len(saved.namelist()):
                raise RuntimeError('Archive integrity validation failed')
            for entry in manifest['files']:
                if sha(saved.read('CampusMate/' + entry['path'])) != entry['sha256']:
                    raise RuntimeError('Archive hash mismatch: ' + entry['path'])
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    digest = sha(output.read_bytes())
    output.with_suffix('.zip.sha256').write_text(digest + '  ' + output.name + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'files': len(files), 'bytes': output.stat().st_size,
                      'sha256': digest, 'version': app.version}, ensure_ascii=False))


if __name__ == '__main__':
    main()
