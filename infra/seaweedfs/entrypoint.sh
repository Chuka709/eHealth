#!/bin/sh
# Dev-only S3: writes the identity file from env (keys never live in git), then starts SeaweedFS.
# "Admin" lets the API create its bucket on first use (dev/test only; production provisions it).
set -eu
cat > /tmp/s3.json <<JSON
{"identities":[{"name":"labtrack","credentials":[{"accessKey":"${S3_ACCESS_KEY}","secretKey":"${S3_SECRET_KEY}"}],"actions":["Admin","Read","Write","List","Tagging"]}]}
JSON
exec weed server -dir=/data -s3 -s3.port=8333 -s3.config=/tmp/s3.json -master.volumeSizeLimitMB=1024 -volume.max=0
