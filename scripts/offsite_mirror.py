"""Daily encrypted Railway PostgreSQL backup on the operator's Mac, outside Railway."""
import argparse
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import UTC,datetime,timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROJECT=os.environ.get('RAILWAY_BACKUP_PROJECT_ID', '')
SERVICE=os.environ.get('RAILWAY_BACKUP_SERVICE_ID', '')


def remote(command):
    if not PROJECT or not SERVICE:
        raise RuntimeError("请配置 RAILWAY_BACKUP_PROJECT_ID 和 RAILWAY_BACKUP_SERVICE_ID")
    return [str(Path.home()/'.railway/bin/railway'),'ssh','--project',PROJECT,'--environment','production',
        '--service',SERVICE,'--identity-file',str(Path.home()/'.ssh/campusmate-railway'),
        '--','sh','-c',command]


def report_verified(saved):
    verified_at=datetime.now(UTC).isoformat()
    sql="INSERT INTO worker_heartbeats(name,observed_at,state) VALUES ('offsite-backup',CURRENT_TIMESTAMP,'ok') ON CONFLICT(name) DO UPDATE SET observed_at=EXCLUDED.observed_at,state='ok';"
    feedback=subprocess.run(remote('PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB" psql -X -v ON_ERROR_STOP=1 -c "'+sql+'"'),
        cwd=ROOT,capture_output=True,timeout=30)
    saved['cloud_status_reported']=feedback.returncode==0;saved['verified_at']=verified_at
    local=ROOT/'local-data/preview.db'
    if local.exists():
        with sqlite3.connect(local) as db:
            db.execute("INSERT INTO worker_heartbeats(name,observed_at,state) VALUES ('offsite-backup',?,'ok') ON CONFLICT(name) DO UPDATE SET observed_at=excluded.observed_at,state='ok'",(verified_at,))
    return saved


def run(force=False):
    os.umask(0o077)
    root=ROOT/'local-data/offsite-backups';root.mkdir(parents=True,exist_ok=True);root.chmod(0o700)
    age=shutil.which('age') or '/opt/homebrew/bin/age'
    identity=Path.home()/'.ssh/campusmate-backup.agekey'
    if not identity.exists():
        result=subprocess.run([age+'-keygen' if age.endswith('/age') else 'age-keygen','-o',str(identity)],capture_output=True)
        if result.returncode:raise RuntimeError('Backup key generation failed')
        identity.chmod(0o600)
    recipient=subprocess.run([age+'-keygen','-y',str(identity)],capture_output=True,check=True,text=True).stdout.strip()
    with (root/'mirror.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'state':'already_running'}
        receipt=root/'latest.json';now=datetime.now(UTC)
        if receipt.exists() and not force:
            previous=json.loads(receipt.read_text())
            if now-datetime.fromisoformat(previous['created_at'])<timedelta(hours=20):return {'state':'fresh'}
        stamp=now.strftime('%Y%m%dT%H%M%SZ');target=root/f'campusmate-{stamp}.dump.age';partial=target.with_suffix('.age.partial')
        try:
            dump=subprocess.Popen(remote('PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB" pg_dump --format=custom --no-owner'),
                cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            with partial.open('wb') as output:
                encryption=subprocess.Popen([age,'--encrypt','--recipient',recipient],stdin=dump.stdout,
                    stdout=output,stderr=subprocess.DEVNULL)
            dump.stdout.close()
            try:
                encrypted_code=encryption.wait(timeout=900);dump_code=dump.wait(timeout=30)
            except subprocess.TimeoutExpired:
                encryption.kill();dump.kill();encryption.wait();dump.wait();raise RuntimeError('Backup timed out')
            if encrypted_code or dump_code:raise RuntimeError('Encrypted backup transfer failed')
            with tempfile.TemporaryDirectory(prefix='campusmate-restore-check-',dir=root) as directory:
                plaintext=Path(directory)/'check.dump'
                with plaintext.open('wb') as output:
                    result=subprocess.run([age,'--decrypt','--identity',str(identity),str(partial)],stdout=output,
                        stderr=subprocess.DEVNULL,timeout=120)
                if result.returncode or plaintext.stat().st_size<100:raise RuntimeError('Backup decryption verification failed')
                with plaintext.open('rb') as source:plain_hash=hashlib.file_digest(source,'sha256').hexdigest()
                restore=shutil.which('pg_restore') or '/opt/homebrew/opt/libpq/bin/pg_restore'
                check=subprocess.run([restore,'--list',str(plaintext)],capture_output=True,timeout=120)
                if check.returncode or b'TABLE' not in check.stdout:raise RuntimeError('Backup restore catalogue invalid')
                count=len(check.stdout.splitlines())
            partial.replace(target)
            with target.open('rb') as source:cipher_hash=hashlib.file_digest(source,'sha256').hexdigest()
            saved={'state':'ok','created_at':now.isoformat(),'encrypted_file':target.name,'encrypted_bytes':target.stat().st_size,
                'encrypted_sha256':cipher_hash,'plaintext_sha256':plain_hash,'restore_catalogue_lines':count,
                'destination':'operator_mac','retention_days':30}
            temporary=receipt.with_suffix('.json.partial');temporary.write_text(json.dumps(saved,indent=2)+'\n');temporary.replace(receipt)
            report_verified(saved)
            temporary.write_text(json.dumps(saved,indent=2)+'\n');temporary.replace(receipt)
            for old in root.glob('campusmate-????????T??????Z.dump.age'):
                if old!=target and datetime.fromtimestamp(old.stat().st_mtime,UTC)<now-timedelta(days=30):old.unlink()
            return saved
        finally:partial.unlink(missing_ok=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--force',action='store_true');args=parser.parse_args()
    try:print(json.dumps(run(args.force),ensure_ascii=False))
    except Exception:
        print(json.dumps({'state':'failed','error':'加密异地备份失败；原有副本保留，请检查 SSH 连接和本机备份密钥'}))
        raise SystemExit(1)
