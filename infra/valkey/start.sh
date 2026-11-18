#!/bin/sh
# Valkey with two ACL users (BETA B10, Phase 8.3):
# - default: the API, the workers and beat (as before);
# - ai: the AI worker (4.5) only - the de-identified input it takes (read + delete), the answer
#   it writes (write only: it cannot read others' answers), the "ai" queue, the queue's binding
#   (read only - the producer declares it), and its OWN unacked bookkeeping keys (ai-unacked*,
#   settings.ai_worker_isolation), never the shared ones other queues use. An explicit command
#   list: no SCAN/KEYS/RANDOMKEY (key names carry user ids), no SELECT, no pub/sub, scripts only
#   to run (kombu's unacked lock; keys inside a script are checked too - no SCRIPT FLUSH/KILL),
#   no admin or dangerous commands.
# Passwords are written as SHA-256 hashes to an ACL file on tmpfs, never on the command line;
# the server then runs as the valkey user, not root.
set -eu
: "${VALKEY_PASSWORD:?}" "${VALKEY_AI_PASSWORD:?}"
hash() { printf '%s' "$1" | sha256sum | cut -d' ' -f1; }
acl=/tmp/users.acl
umask 077
{
  echo "user default on #$(hash "$VALKEY_PASSWORD") ~* &* +@all"
  echo "user ai on #$(hash "$VALKEY_AI_PASSWORD") resetkeys resetchannels" \
    "%RW~ai-input:* %W~ai-output:* %RW~ai %R~_kombu.binding.ai" \
    "%RW~ai-unacked %RW~ai-unacked_index %RW~ai-unacked_mutex" \
    "-@all +ping +echo +hello +client|setname +client|getname +client|id +client|setinfo" \
    "+info +get +set +getdel +del +exists +expire +pexpire +ttl +pttl +type" \
    "+lpush +rpush +brpop +lpop +rpop +llen +lrange +smembers +sismember" \
    "+hset +hget +hdel +hgetall +hlen +zadd +zrem +zrangebyscore +zrevrangebyscore +zcard" \
    "+multi +exec +discard +watch +unwatch +eval +evalsha +script|load +script|exists"
} > "$acl"
chown valkey "$acl"
exec setpriv --reuid=valkey --regid=valkey --clear-groups valkey-server --save '' --appendonly no --aclfile "$acl"
