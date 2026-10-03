"""Build clean Railway upload directories containing only code and public archives."""
import argparse,json,shutil,subprocess
from pathlib import Path

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',required=True,help='New directory for api and worker upload packages')
parser.add_argument('--include-public-data',action='store_true',help='Only for first bootstrap into a fresh collection database')
args=parser.parse_args()
target=Path(args.output).resolve()
if target.exists():raise SystemExit('Output already exists; choose a new directory')
target.mkdir(parents=True)
backend=root/'backend'
for role in ['api','worker']:
    directory=target/role;directory.mkdir()
    for name in ['app','migrations']:
        shutil.copytree(backend/name,directory/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ['pyproject.toml','requirements-tested.txt','alembic.ini']:
        shutil.copy2(backend/name,directory/name)
    docker=(backend/'Dockerfile').read_text()
    if role=='api' and args.include_public_data:docker+='\nCOPY collection-data.json.gz /app/collection-data.json.gz\n'
    docker+='\nCMD ["python", "-m", "app.collection_entrypoint"]\n'
    (directory/'Dockerfile').write_text(docker)
if args.include_public_data:
    subprocess.run([str(backend/'.venv/bin/python'),'-m','app.collection_bundle','--export',
        str(target/'api/collection-data.json.gz')],cwd=backend,check=True)
print(json.dumps({'api':str(target/'api'),'worker_and_monitor':str(target/'worker')},ensure_ascii=False))
