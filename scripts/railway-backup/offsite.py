"""Upload only age-encrypted backups, then read back and verify every byte."""
import hashlib
import ipaddress
import os
import re
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def upload(path,client,bucket,key):
    expected=digest(path)
    client.upload_file(str(path),bucket,key,ExtraArgs={'Metadata':{'sha256':expected},'ContentType':'application/octet-stream'})
    response=client.get_object(Bucket=bucket,Key=key)
    observed=hashlib.sha256();size=0
    try:
        for chunk in iter(lambda:response['Body'].read(1024*1024),b''):
            size+=len(chunk)
            if size>path.stat().st_size:raise ValueError('offsite size mismatch')
            observed.update(chunk)
    finally:response['Body'].close()
    if size!=path.stat().st_size or observed.hexdigest()!=expected:raise ValueError('offsite hash mismatch')
    return {'bytes':size,'sha256':expected}


def main():
    path=Path(sys.argv[1])
    if not re.fullmatch(r'campusmate-\d{8}T\d{6}Z\.dump\.age',path.name) or not path.is_file():
        raise ValueError('encrypted backup required')
    with path.open('rb') as source:
        if source.read(22)!=b'age-encryption.org/v1\n':raise ValueError('age envelope missing')
    bucket=os.environ.get('BACKUP_S3_BUCKET','')
    if not bucket:
        if os.environ.get('BACKUP_OFFSITE_REQUIRED')=='true':raise ValueError('offsite destination missing')
        print('Encrypted backup ready; no S3 destination configured.');return
    import boto3
    from botocore.config import Config
    endpoint=os.environ.get('BACKUP_S3_ENDPOINT')
    if endpoint:
        parts=urlsplit(endpoint)
        if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError('invalid offsite endpoint')
        addresses={r[4][0] for r in socket.getaddrinfo(parts.hostname,parts.port or 443,type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):raise ValueError('offsite endpoint must be public')
    prefix=os.environ.get('BACKUP_S3_PREFIX','campusmate/')
    if not re.fullmatch(r'[a-zA-Z0-9/_-]{1,120}',prefix):raise ValueError('invalid backup prefix')
    client=boto3.client('s3',endpoint_url=endpoint,region_name=os.environ.get('AWS_DEFAULT_REGION','auto'),
        config=Config(connect_timeout=10,read_timeout=60,retries={'max_attempts':3},s3={'addressing_style':'path'}))
    verified=upload(path,client,bucket,prefix.rstrip('/')+'/'+path.name)
    print(f"Offsite encrypted backup read-back verified: {verified['bytes']} bytes; SHA256 matches.")


if __name__=='__main__':
    try:main()
    except Exception:
        print('Offsite backup failed; check private storage configuration. Verified local backup retained.',file=sys.stderr)
        sys.exit(1)
