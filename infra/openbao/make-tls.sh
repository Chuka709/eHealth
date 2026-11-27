#!/usr/bin/env bash
# A private CA and OpenBao's certificate (SERVER_INSTALL_MANUAL.md §4). Run on the OpenBao VM
# as root: infra/openbao/make-tls.sh <OPENBAO_HOSTNAME> <OpenBao private IP>
# Writes /etc/openbao/tls/{ca.crt,bao.crt,bao.key}; the CA's private key goes to
# /root/openbao-ca.key - copy it offline and delete it from the VM (it signs nothing else).
# ca.crt goes to the app server as /etc/labtrack/secrets/openbao/ca.pem.
set -euo pipefail
umask 077
host="${1:?OpenBao hostname}" ip="${2:?OpenBao private IP}"
dir=/etc/openbao/tls
mkdir -p "$dir"
[ -e "$dir/bao.crt" ] && { echo "make-tls: $dir/bao.crt exists - remove it to make a new one" >&2; exit 1; }
# Python 3.13 verifies strictly (VERIFY_X509_STRICT): the CA needs basicConstraints and
# keyUsage, the leaf its key identifiers - found by the app's own round trip (2026.11.27)
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 3650 \
	-subj "/CN=LabTrack OpenBao CA" -keyout /root/openbao-ca.key -out "$dir/ca.crt" \
	-addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
	-addext "keyUsage=critical,keyCertSign,cRLSign" \
	-addext "subjectKeyIdentifier=hash" \
	-addext "nameConstraints=critical,permitted;DNS:$host,permitted;IP:$ip/255.255.255.255"
# (the CA may sign for this one host and address only)
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj "/CN=$host" \
	-keyout "$dir/bao.key" -out "$work/bao.csr"
printf '%s\n' "subjectAltName=DNS:$host,IP:$ip" "basicConstraints=critical,CA:FALSE" \
	"keyUsage=critical,digitalSignature" "extendedKeyUsage=serverAuth" \
	"subjectKeyIdentifier=hash" "authorityKeyIdentifier=keyid:always" >"$work/bao.ext"
openssl x509 -req -in "$work/bao.csr" -CA "$dir/ca.crt" -CAkey /root/openbao-ca.key \
	-CAserial "$work/ca.srl" -CAcreateserial -days 825 -extfile "$work/bao.ext" -out "$dir/bao.crt"
# OpenBao runs as uid 100 (openbao) in its image
chown -R 100:1000 "$dir"
chmod 600 "$dir/bao.key"
chmod 644 "$dir/bao.crt" "$dir/ca.crt"
echo "make-tls: $dir ready (certificate for $host / $ip, 825 days)"
