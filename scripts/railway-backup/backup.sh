#!/bin/sh
set -eu
umask 077
mkdir -p /backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
archive="/backups/campusmate-${stamp}.dump"
temporary="${archive}.partial"
trap 'rm -f "$temporary"' EXIT INT TERM
pg_dump --format=custom --no-owner --file="$temporary"
pg_restore --list "$temporary" >/dev/null
mv "$temporary" "$archive"
# Delete only our verified, dated dumps, after a successful new backup.
find /backups -name 'campusmate-????????T??????Z.dump' -type f -mtime +14 -delete
printf 'Verified PostgreSQL backup: %s (%s bytes)\n' "$archive" "$(wc -c < "$archive")"
if [ "${BACKUP_VALIDATE_RESTORE:-false}" = true ]; then
    restore_db="campusmate_restore_${stamp}_$$"
    createdb "$restore_db"
    # This database is newly created here; never restore into PGDATABASE.
    trap 'dropdb --if-exists "$restore_db"; rm -f "$temporary"' EXIT INT TERM
    pg_restore --exit-on-error --single-transaction --no-owner --dbname="$restore_db" "$archive"
    psql -X -v ON_ERROR_STOP=1 --dbname="$restore_db" -c 'SELECT version_num FROM alembic_version; SELECT count(*) AS documents FROM document_versions; SELECT count(*) AS public_items FROM data_publications WHERE status='"'"'published'"'"'; SELECT count(*) AS queue_resources FROM notice_resources;'
    mismatches=$(psql -X -At -v ON_ERROR_STOP=1 --dbname="$restore_db" -c "SELECT count(*) FROM document_archives a JOIN document_versions d ON d.id=a.document_id WHERE encode(sha256(a.content),'hex')<>d.content_hash")
    [ "$mismatches" = 0 ]
    printf 'Isolated restore verified: every archived byte hash matches; live database unchanged.\n'
    dropdb "$restore_db"
    trap 'rm -f "$temporary"' EXIT INT TERM
fi
psql -X -v ON_ERROR_STOP=1 -c "INSERT INTO worker_heartbeats(name,observed_at,state) VALUES ('collection-backup',CURRENT_TIMESTAMP,'ok') ON CONFLICT(name) DO UPDATE SET observed_at=EXCLUDED.observed_at,state='ok';" >/dev/null
sha256sum "$archive" > "${archive}.sha256"
if [ -n "${BACKUP_AGE_RECIPIENT:-}" ]; then
    age --encrypt --recipient "$BACKUP_AGE_RECIPIENT" --output "${archive}.age.partial" "$archive"
    mv "${archive}.age.partial" "${archive}.age"
    sha256sum "${archive}.age" > "${archive}.age.sha256"
    printf 'Encrypted backup prepared for an offsite copy.\n'
    python3 /usr/local/bin/collection-offsite.py "${archive}.age"
elif [ "${BACKUP_OFFSITE_REQUIRED:-false}" = true ]; then
    printf 'Offsite backup required: configure the age recipient and storage variables.\n' >&2
    exit 1
else
    printf 'Offsite backup not configured; verified Railway volume copy only.\n'
fi
find /backups -name 'campusmate-????????T??????Z.dump.*' -type f -mtime +14 -delete
