FROM postgres:18-alpine
RUN apk add --no-cache age python3 py3-boto3
COPY backup.sh /usr/local/bin/collection-backup
COPY offsite.py /usr/local/bin/collection-offsite.py
RUN chmod 755 /usr/local/bin/collection-backup
ENTRYPOINT ["/usr/local/bin/collection-backup"]
