"""Guarded static-only overlay, run inside its extracted VPS release directory."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request


STAGE = Path(__file__).resolve().parent
MANIFEST = json.loads((STAGE / 'manifest.json').read_text())
RELEASE = MANIFEST['release']
APP = Path(MANIFEST['expectedAppRelease'])
PUBLIC = Path('/opt/campusmate/homepage.new')
TARGETS = [PUBLIC, APP / 'frontend/public/landing', APP / 'frontend/.next/standalone/frontend/public/landing']
UNITS = ['campusmate-web.service', 'campusmate-api.service', 'campusmate-worker.service', 'nginx.service']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def services():
    return {unit: subprocess.check_output(['systemctl', 'show', unit, '-p', 'MainPID', '-p', 'ActiveState'], text=True).strip() for unit in UNITS}


def protected():
    paths = [
        APP / 'frontend/.next/BUILD_ID', APP / 'frontend/proxy.ts', APP / 'scripts/start-web.cjs',
        APP / 'backend/app/main.py', APP / 'backend/app/auth.py',
        APP / 'frontend/app/api/session/route.ts', APP / 'frontend/app/auth/callback/route.ts',
        Path('/etc/nginx/sites-enabled/campusmate'), Path('/etc/nginx/sites-enabled/campusmate-homepage'),
        Path('/etc/cloudflared/config.yml'),
    ]
    return {str(p): digest(p.read_bytes()) for p in paths if p.is_file()}


def atomic(path, data, ownership=None):
    fd, temp = tempfile.mkstemp(prefix='.cm-static-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o644)
        if ownership:
            os.chown(temp, *ownership)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_url(url):
    with urllib.request.urlopen(url, timeout=15) as response:
        assert response.status == 200, (url, response.status)
        return response.read()


def preflight():
    assert STAGE == Path('/opt/campusmate/static-deployments') / RELEASE, 'Unexpected stage'
    assert Path('/opt/campusmate/current').resolve() == APP, 'Running application release changed'
    assert (APP / 'frontend/.next/BUILD_ID').read_text().strip() == MANIFEST['expectedBuildId'], 'Build changed'
    for target in TARGETS:
        assert target.is_dir() and target.resolve() == target, 'Unexpected static target'
        assert digest((target / 'auth.js').read_bytes()) == MANIFEST['expectedAuthHash'], 'Live auth changed'
        assert digest((target / 'index.html').read_bytes()) == MANIFEST['expectedIndexHash'], 'Landing changed since inspection'
        for page in MANIFEST['pages']:
            assert (target / page).is_file() and not (target / page).is_symlink()
    for relative, info in MANIFEST['files'].items():
        path = (STAGE / relative).resolve()
        assert path.is_relative_to(STAGE), 'Unsafe package path'
        assert digest(path.read_bytes()) == info['sha256'], relative
    for state in services().values():
        assert 'ActiveState=active' in state, state
    assert MANIFEST['authLogicIdentical'] is True
    return {'status':'preflight-ok', 'release':RELEASE, 'appRelease':str(APP), 'targets':[str(p) for p in TARGETS], 'files':len(MANIFEST['files'])}


def publish():
    print(json.dumps(preflight()), flush=True)
    assert not (STAGE / 'deployment.json').exists(), 'Already deployed'
    assert not (STAGE / 'before-pages.tar.gz').exists(), 'Existing backup: inspect before retry'
    original_services, original_protected = services(), protected()
    originals = {}
    with tarfile.open(STAGE / 'before-pages.tar.gz', 'w:gz') as archive:
        for index, target in enumerate(TARGETS):
            for page in MANIFEST['pages']:
                file = target / page
                stat = file.stat()
                originals[file] = (file.read_bytes(), (stat.st_uid, stat.st_gid))
                archive.add(file, arcname=f'{index}/{page}', recursive=False)
    before = {'release':RELEASE, 'appRelease':str(APP), 'targets':[str(p) for p in TARGETS], 'hashes':{str(p):digest(v[0]) for p,v in originals.items()}, 'services':original_services, 'protected':original_protected}
    (STAGE / 'before.json').write_text(json.dumps(before, indent=2))
    # Publish immutable resources first, through the already-routed /assets/ prefix.
    destination = PUBLIC / 'assets' / RELEASE
    assert not destination.exists(), 'Asset version already present'
    temp = Path(tempfile.mkdtemp(prefix='.cm-static-', dir=PUBLIC / 'assets'))
    try:
        shutil.copytree(STAGE / 'assets' / RELEASE, temp, dirs_exist_ok=True)
        for path in [temp, *temp.rglob('*')]:
            os.chmod(path, 0o755 if path.is_dir() else 0o644)
        os.rename(temp, destination)
    finally:
        if temp.exists():
            assert temp.parent == PUBLIC / 'assets' and temp.name.startswith('.cm-static-')
            shutil.rmtree(temp)
    changed = []
    try:
        for relative, info in MANIFEST['files'].items():
            if relative.startswith('assets/'):
                assert digest(read_url('http://127.0.0.1:8080/' + relative)) == info['sha256'], relative
        for file, (_, owner) in originals.items():
            atomic(file, (STAGE / 'pages' / file.name).read_bytes(), owner)
            changed.append(file)
        for prefix in ['http://127.0.0.1:8080/', 'http://127.0.0.1:3000/landing/']:
            for page in MANIFEST['pages']:
                assert digest(read_url(prefix + page)) == MANIFEST['files']['pages/' + page]['sha256'], prefix + page
        assert services() == original_services, 'Service process changed'
        assert protected() == original_protected, 'Protected configuration changed'
        record = {**before, 'status':'published', 'staticAssetRoot':str(destination), 'backup':str(STAGE / 'before-pages.tar.gz'), 'buildId':MANIFEST['expectedBuildId'], 'newHashes':{str(p):digest(p.read_bytes()) for p in originals}}
        atomic(STAGE / 'deployment.json', json.dumps(record, indent=2).encode())
        atomic(STAGE.parent / 'current.json', json.dumps({'release':RELEASE, 'appRelease':str(APP), 'record':str(STAGE / 'deployment.json')}, indent=2).encode())
        print(json.dumps({'status':'published', 'release':RELEASE, 'updatedHtmlFiles':len(changed), 'servicesUnchanged':True, 'businessCodeUnchanged':True, 'backup':record['backup']}), flush=True)
    except BaseException:
        for file in changed:
            data, owner = originals[file]
            atomic(file, data, owner)
        print('Publication failed; original HTML pages restored.', flush=True)
        raise


def rollback():
    assert Path('/opt/campusmate/current').resolve() == APP
    record = json.loads((STAGE / 'deployment.json').read_text())
    for name, expected in record['newHashes'].items():
        assert digest(Path(name).read_bytes()) == expected, 'Subsequent publication detected'
    with tarfile.open(STAGE / 'before-pages.tar.gz') as archive:
        for index, target in enumerate(TARGETS):
            for page in MANIFEST['pages']:
                member = archive.getmember(f'{index}/{page}')
                atomic(target / page, archive.extractfile(member).read(), (member.uid, member.gid))
    record['status'] = 'rolled-back'
    atomic(STAGE / 'deployment.json', json.dumps(record, indent=2).encode())
    atomic(STAGE.parent / 'current.json', json.dumps({'release':RELEASE, 'status':'rolled-back', 'appRelease':str(APP)}).encode())
    print('Original static pages restored. Immutable assets retained for open browser tabs.')


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else '--check'
    if mode == '--publish':
        publish()
    elif mode == '--rollback':
        rollback()
    else:
        assert mode == '--check'
        print(json.dumps(preflight()))
