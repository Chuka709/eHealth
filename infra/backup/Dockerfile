# Backups and restore drills (Phase 8.2; docs/OPS_RUNBOOK.md).
# pg_dump/pg_restore of the same major version as the server; age (BSD-3) encrypts to a public
# key only - this container never holds the private key except during a restore drill;
# rclone (MIT) reads the document store over the S3 API (SeaweedFS in dev, any S3 in production).
FROM postgres:17-alpine
RUN apk add --no-cache age rclone coreutils jq
COPY backup.sh restore-drill.sh /usr/local/bin/
RUN chmod 0755 /usr/local/bin/backup.sh /usr/local/bin/restore-drill.sh
USER postgres
WORKDIR /backups
ENTRYPOINT []
CMD ["backup.sh"]
