#!/bin/sh
# Production S3 (docs/SERVER_INSTALL_PLAN.md §4; docs/04 §3): one identity per service, each
# held to the documents bucket and to what that service does - checked on SeaweedFS 4.50:
#   api     Read + Write (put, get, delete)     worker  Read (get)
#   maint   List + Write (sweep, delete)        backup  Read + List
# Nobody may create a bucket (s3-init makes it through the master) or touch another one.
# Secret keys come from Docker secrets (letters and digits only: they go into JSON as they are);
# the identity file lives on tmpfs, readable by this process alone.
set -eu
b="${S3_BUCKET:?}"
secret() {
	v=$(cat "/run/secrets/$1")
	case "$v" in *[!A-Za-z0-9]*|'') echo "s3 secret $1: letters and digits only" >&2; exit 1 ;; esac
	printf '%s' "$v"
}
umask 077
cat > /tmp/s3.json <<JSON
{"identities":[
 {"name":"api","credentials":[{"accessKey":"${S3_API_ACCESS_KEY:?}","secretKey":"$(secret s3_api)"}],"actions":["Read:$b","Write:$b"]},
 {"name":"worker","credentials":[{"accessKey":"${S3_WORKER_ACCESS_KEY:?}","secretKey":"$(secret s3_worker)"}],"actions":["Read:$b"]},
 {"name":"maint","credentials":[{"accessKey":"${S3_MAINT_ACCESS_KEY:?}","secretKey":"$(secret s3_maint)"}],"actions":["List:$b","Write:$b"]},
 {"name":"backup","credentials":[{"accessKey":"${S3_BACKUP_ACCESS_KEY:?}","secretKey":"$(secret s3_backup)"}],"actions":["Read:$b","List:$b"]}
]}
JSON
exec weed server -dir=/data -s3 -s3.port=8333 -s3.config=/tmp/s3.json -master.volumeSizeLimitMB=1024 -volume.max=0
