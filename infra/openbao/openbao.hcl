# OpenBao on its own VM (docs/SERVER_INSTALL_PLAN.md §3; SERVER_INSTALL_MANUAL.md §4).
# Integrated (raft) storage on the VM's encrypted disk; TLS only; no UI.
storage "raft" {
  path    = "/openbao/data"
  node_id = "labtrack-bao-1"
}

listener "tcp" {
  address       = "0.0.0.0:8200"
  tls_cert_file = "/openbao/tls/bao.crt"
  tls_key_file  = "/openbao/tls/bao.key"
  tls_min_version = "tls13"
}

api_addr     = "https://OPENBAO_HOSTNAME:8200"
cluster_addr = "https://OPENBAO_HOSTNAME:8201"
ui           = false
# raft keeps its data in a memory-mapped file: OpenBao advises against mlock with it (the
# VM's swap is on the LUKS volume)
disable_mlock = true
log_level    = "warn"

# OpenBao 2.x enables audit devices from the config only (not the API). Every request and
# answer, values HMAC'd; kept 35+ days (logrotate on the VM, SERVER_INSTALL_MANUAL.md §4).
audit "file" "file" {
  description = "every request and answer, values HMAC'd"
  options {
    file_path = "/openbao/audit/audit.log"
  }
}
