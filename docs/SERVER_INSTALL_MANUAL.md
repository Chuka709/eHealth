# SERVER_INSTALL_MANUAL.md — серверт гараар суулгах заавар (2026.11.27)

> Төлөвлөгөө, шалтгаан: `SERVER_INSTALL_PLAN.md`. Энэ баримт — **хуулж ажиллуулах команд**. Claude SSH-ээр
> суулгах үед ч яг эдгээрийг ажиллуулна (ижил скрипт) — 🔒 тэмдэгтэй алхмуудаас бусдыг (тэдгээрийг зөвхөн хүн). `<...>` — өөрийн утгаар солино. Команд бүрийг
> `root` эсвэл `sudo`-оор. Нууц үг, түлхүүрийг терминал, чат, тикетэд **хэзээ ч бүү хуул**.

## 0. Эхлэхээс өмнө бэлдэх мэдээлэл
| Юу | Жишээ | Хаана хэрэглэгдэнэ |
|---|---|---|
| Апп серверийн гадаад IP, домэйн | `203.0.113.20`, `app.<компани>.mn` | DNS `A` бичлэг, Caddy |
| Апп серверийн дотоод IP | `10.0.0.4` | OpenBao firewall, `--bound-cidr` |
| OpenBao VM-ийн дотоод IP, нэр | `10.0.0.5`, `bao.labtrack.internal` | TLS сертификат, `OPENBAO_*` |
| Админ хандах сүлжээ (оффис/VPN-ийн **гадаад** IP) | `198.51.100.7/32` | `/admin` allowlist (хувийн 10/172.16/192.168 хүрээ хориотой) |
| ACME имэйл | `ops@<компани>.mn` | Let's Encrypt |
| Нөөцийн диск | `/srv/labtrack-backups` | `BACKUP_DIR` |
| Дохионы суваг | Telegram bot token + chat id, эсвэл webhook | `ALERT_*` |
| age нийтийн түлхүүр | `age1...` (OPS_RUNBOOK §2-оор **офлайн** үүсгэсэн) | `BACKUP_AGE_RECIPIENT` |

## 1. OS суулгах (хоёр машин: апп сервер, OpenBao VM)
1. Ubuntu Server 24.04 LTS. Суулгагчид **«Use LVM with encryption (LUKS)»**, хүчтэй passphrase (Shamir-тэй ижил
   журмаар хадгална). Production-д апп серверт 2 диск — RAID 1 (суулгагчид «Custom storage layout»).
2. Хэрэглэгч `deploy`, OpenSSH server асаана, SSH түлхүүрээ оруулна.

## 2. Хатууруулах (хоёр машинд)
```bash
sudo apt update && sudo apt -y full-upgrade
sudo apt -y install unattended-upgrades fail2ban ufw chrony curl jq git ca-certificates age
sudo dpkg-reconfigure -plow unattended-upgrades          # "Yes"
sudo timedatectl set-timezone UTC
# SSH: зөвхөн түлхүүрээр, root-гүй
sudo sed -i -E 's/^#?PasswordAuthentication .*/PasswordAuthentication no/; s/^#?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart ssh
# swap 4 GB (ClamAV-ийн шинэчлэлтийн оргилд)
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```
Firewall — **апп сервер**:
```bash
sudo ufw default deny incoming && sudo ufw default allow outgoing
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 443/udp
sudo ufw allow from <админы VPN/оффисын IP> to any port 22 proto tcp
sudo ufw enable
```
Firewall — **OpenBao VM** (зөвхөн апп серверээс):
```bash
sudo ufw default deny incoming && sudo ufw default allow outgoing
sudo ufw allow from <апп серверийн дотоод IP> to any port 8200 proto tcp
sudo ufw allow from <админы VPN/оффисын IP> to any port 22 proto tcp
sudo ufw enable
```

## 3. Docker (хоёр машинд)
```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt update && sudo apt -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
echo '{"log-driver":"local","log-opts":{"max-size":"20m","max-file":"10"},"live-restore":true}' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker
# Docker-ийн published port нь ufw-г тойрдог: апп серверт зөвхөн 80/443 published (compose); OpenBao нь host network (ufw үйлчилнэ)
docker compose version     # v2.24+ (`!override` хэрэгтэй)
```
Репо (хоёр машинд, зөвхөн уншдаг deploy key-ээр):
```bash
sudo git clone <repo URL> /opt/labtrack && cd /opt/labtrack && sudo git checkout <release tag/sha>
```

## 4. OpenBao VM
> 🔒 **Зөвхөн хүн** (Claude ч, ямар ч автоматжуулалт ч биш): `operator init`, `operator unseal`, root token-той
> бүх алхам (энэ хэсгийн 🔒 тэмдэгтэй блокууд), §6-ийн `create-admin`. Эдгээрийн гаралт (Shamir хэсэг, root
> token, TOTP QR) Claude-ын транскрипт, SSH-ийн лог, `tmux`/`screen`/`script`-ийн бичлэгт **орох ёсгүй** — логгүй
> энгийн терминалд хийнэ. Claude SSH-ээр суулгаж байгаа бол энэ үед зогсоод танд шилжүүлнэ.

Firewall (§2) **эхлээд** асаалттай байх ёстой: init хийгдээгүй OpenBao-г хүрч чадсан хэн ч өөрөө init хийж
эзэмшинэ. Compose нь host network ашигладаг (Docker-ийн published port ufw-г тойрдог тул).

CA ба сертификат. **Санал:** CA-г офлайн машин дээр үүсгэж (`make-tls.sh`-ийг тэнд ажиллуулаад `bao.crt`,
`bao.key`, `ca.crt`-г VM руу хуулна) — SSD/LUKS дээр `shred` баталгаатай устгадаггүй. VM дээр хийвэл:
```bash
cd /opt/labtrack
sudo infra/openbao/make-tls.sh <OPENBAO_HOSTNAME> <OpenBao дотоод IP>
sudo cp /root/openbao-ca.key <офлайн зөөвөрлөгч> && sudo shred -u /root/openbao-ca.key
```
Тохиргоо `/etc/openbao`-д (репогийн файлыг засахгүй — дараагийн `git pull` эвдэрнэ):
```bash
sudo mkdir -p /var/lib/openbao/data /var/log/openbao /etc/openbao/pgp
sudo chown -R 100:1000 /var/lib/openbao/data /var/log/openbao     # OpenBao image-ийн хэрэглэгч
sudo cp infra/openbao/openbao.hcl infra/openbao/docker-compose.yml /etc/openbao/
sudo sed -i "s/OPENBAO_HOSTNAME/<OPENBAO_HOSTNAME>/" /etc/openbao/openbao.hcl
echo "127.0.0.1 <OPENBAO_HOSTNAME>" | sudo tee -a /etc/hosts
sudo docker compose -f /etc/openbao/docker-compose.yml up -d
export BAO_ADDR=https://<OPENBAO_HOSTNAME>:8200 BAO_CACERT=/etc/openbao/tls/ca.crt
B="sudo --preserve-env=BAO_ADDR,BAO_TOKEN docker compose -f /etc/openbao/docker-compose.yml exec -T -e BAO_CACERT=/openbao/tls/ca.crt -e BAO_ADDR -e BAO_TOKEN openbao"
# interactive (a hidden prompt needs a terminal): unseal
U="sudo --preserve-env=BAO_ADDR docker compose -f /etc/openbao/docker-compose.yml exec -e BAO_CACERT=/openbao/tls/ca.crt -e BAO_ADDR openbao"
```
🔒 **Initialize — 5 хэсэг, 3-аар нээнэ.** Хамгийн аюулгүй нь хадгалагч бүрийн PGP нийтийн түлхүүрээр
шифрлэх — дэлгэцэнд зөвхөн шифр гарна (`.asc` файлуудыг VM-ийн `/etc/openbao/pgp/`-д хуулна; контейнерт
`/openbao/pgp` болж харагдана):
```bash
$B bao operator init -key-shares=5 -key-threshold=3 \
  -pgp-keys=/openbao/pgp/k1.asc,/openbao/pgp/k2.asc,/openbao/pgp/k3.asc,/openbao/pgp/k4.asc,/openbao/pgp/k5.asc \
  -root-token-pgp-key=/openbao/pgp/ops.asc
```
(PGP-гүй бол `-pgp-keys`-гүй ажиллуулж, хэсэг бүрийг дэлгэцээс шууд хадгалагчид цаасаар өгнө; файлд бүү хадгал.)
🔒 Unseal — 3 хүн тус бүр өөрийн хэсгийг оруулна (дэлгэцэнд харагдахгүй):
```bash
$U bao operator unseal
```
🔒 Root token-оор (апп-ын тохиргооны өмнө — тэр нь төгсгөлдөө root token-ыг цуцална) snapshot-ын token:
```bash
read -rs -p "Initial root token: " BAO_TOKEN && export BAO_TOKEN && echo      # дэлгэц, history-д үлдэхгүй
echo 'path "sys/storage/raft/snapshot" { capabilities = ["read"] }' | $B bao policy write snapshot -
$B bao token create -policy=snapshot -orphan -period=768h -field=token | sudo tee /root/.bao-snapshot >/dev/null
sudo chmod 600 /root/.bao-snapshot
```
(periodic token: `snapshot.sh` өдөр бүр сунгадаг тул дуусахгүй.)

Snapshot өдөр бүр — **35 хоногоос ихгүй** (энд ч, off-site-д ч; SERVER_INSTALL_PLAN §3.7). Snapshot бүх
түлхүүрийг агуулдаг: VM-ийн диск ба бүх snapshot алга болбол бүх баримт уншигдахгүй болно — off-site заавал:
```bash
sudo mkdir -p /srv/bao-snapshots && sudo chmod 700 /srv/bao-snapshots
sudo tee /etc/openbao/snapshot.env >/dev/null <<'EOF'
BAO_ADDR=https://<OPENBAO_HOSTNAME>:8200
BAO_CACERT=/etc/openbao/tls/ca.crt
BAO_TOKEN_FILE=/root/.bao-snapshot
BACKUP_AGE_RECIPIENT=<age1...>
SNAPSHOT_DIR=/srv/bao-snapshots
OFFSITE_SYNC=/etc/openbao/offsite-sync
ALERT_TELEGRAM_TOKEN=<...>
ALERT_TELEGRAM_CHAT=<...>
EOF
sudo chmod 600 /etc/openbao/snapshot.env
# off-site: DB нөөцөөс ТУСДАА газар, 35 хоногийн дараа устгана (жишээ — rclone, өөрийн remote-оор)
sudo tee /etc/openbao/offsite-sync >/dev/null <<'EOF'
#!/bin/sh
set -eu
rclone --config /etc/openbao/rclone.conf copy "$1" bao-offsite:labtrack-bao/
rclone --config /etc/openbao/rclone.conf delete --min-age 35d bao-offsite:labtrack-bao/
EOF
sudo chmod 700 /etc/openbao/offsite-sync
sudo tee /etc/cron.d/labtrack-bao-snapshot >/dev/null <<'EOF'
30 18 * * * root /opt/labtrack/infra/openbao/snapshot.sh >>/var/log/bao-snapshot.log 2>&1
0 4 * * * root /opt/labtrack/infra/openbao/snapshot.sh --check >>/var/log/bao-snapshot.log 2>&1
EOF
echo '/var/log/openbao/audit.log { daily rotate 40 compress missingok notifempty copytruncate }' | sudo tee /etc/logrotate.d/openbao-audit
sudo /opt/labtrack/infra/openbao/snapshot.sh      # нэг удаа шалгах: "snapshot ok"
```
(18:30 UTC = 02:30 Улаанбаатар. Амжилтгүй бол дохио ирнэ; 04:00 UTC-д `--check` хамгийн сүүлийн snapshot 26
цагаас хуучин бол — cron огт ажиллаагүй ч — дохио өгнө.)

**Дахин асахад:** OpenBao sealed болно → апп 503 («Үйлчилгээ түр ажиллахгүй»), баримт хүлээгдэнэ. 3 хүн
🔒 `$U bao operator unseal` хийнэ. Мониторинг «API ready … keys» дохио өгнө.
**Дараа нь root хэрэгтэй бол** (жишээ нь бодлого өөрчлөх): `bao operator generate-root` — 3 хадгалагчийн
хамтын ажиллагаагаар, ажил дуусмагц `bao token revoke -self`.

## 5. Апп сервер — тохиргоо
```bash
cd /opt/labtrack
echo "<OpenBao дотоод IP> <OPENBAO_HOSTNAME>" | sudo tee -a /etc/hosts     # openbao-setup-д
sudo infra/prod/prod-init.sh --domain <домэйн> --acme-email <имэйл> --admin-cidr <админы гадаад IP>/32 \
  --openbao-hostname <OPENBAO_HOSTNAME> --openbao-upstream <OpenBao дотоод IP>:8200 \
  --backup-dir /srv/labtrack-backups
sudo mkdir -p /srv/labtrack-backups && sudo chmod 700 /srv/labtrack-backups
```
OpenBao-ийн CA (`/etc/openbao/tls/ca.crt`, OpenBao VM-ээс) → `/etc/labtrack/secrets/openbao/ca.pem`.

🔒 OpenBao-ийн тохиргоо (transit, KEK, 3 AppRole; аудитгүй OpenBao-д татгалзана; root token-ыг төгсгөлд нь —
амжилтгүй болсон ч — цуцална). Апп-ын image-ээс:
```bash
sudo install -d -m 700 -o 10001 /root/bao-out
sudo docker build -q -t labtrack-backend:setup --target runtime backend
read -rs -p "OpenBao root token: " BAO_TOKEN && export BAO_TOKEN && echo
sudo --preserve-env=BAO_TOKEN docker run --rm --add-host <OPENBAO_HOSTNAME>:<OpenBao дотоод IP> \
  -v /etc/labtrack/secrets/openbao/ca.pem:/ca.pem:ro -v /root/bao-out:/out \
  -e BAO_ADDR=https://<OPENBAO_HOSTNAME>:8200 -e BAO_CACERT=/ca.pem -e BAO_TOKEN \
  labtrack-backend:setup python -m labtrack.cli openbao-setup --out /out --bound-cidr <апп серверийн дотоод IP>/32
# token цуцлагдсаныг шалгах (403 "permission denied" байх ёстой), дараа нь мартах
curl -s -o /dev/null -w '%{http_code}\n' --cacert /etc/labtrack/secrets/openbao/ca.pem \
  -H @<(printf 'X-Vault-Token: %s' "$BAO_TOKEN") https://<OPENBAO_HOSTNAME>:8200/v1/auth/token/lookup-self
unset BAO_TOKEN
sudo cp /root/bao-out/* /etc/labtrack/secrets/openbao/ && sudo shred -u /root/bao-out/* && sudo rmdir /root/bao-out
sudo infra/prod/prod-init.sh        # role id-уудыг env файлд хуулж, эрхийг засна
```
Үлдсэнийг гараар (`sudo nano /etc/labtrack/labtrack.env`): `APP_DOWNLOAD_URL`, `ORG_SUPPORT_PHONE`,
`BACKUP_AGE_RECIPIENT`, дохионы `ALERT_*`. Дахин `sudo infra/prod/prod-init.sh` — «prod-init: complete».

Off-site нөөц (DB + баримт) — OpenBao snapshot-оос **өөр** газар, 35 хоногийн дараа устгана:
```bash
sudo tee /etc/labtrack/offsite-sync >/dev/null <<'EOF'
#!/bin/sh
set -eu
rclone --config /etc/labtrack/rclone.conf copy "$1" offsite:labtrack-backups/"$(basename "$1")"
rclone --config /etc/labtrack/rclone.conf delete --min-age 35d offsite:labtrack-backups/
rclone --config /etc/labtrack/rclone.conf rmdirs --leave-root offsite:labtrack-backups/
EOF
sudo chmod 700 /etc/labtrack/offsite-sync
```
(Remote нь «зөвхөн нэмэх» эрхтэй түлхүүр бол `delete`-ийн оронд bucket-ийн 35 хоногийн lifecycle дүрэм.)

## 6. Суулгах, шинэчлэх, буцаах
Хувилбар бүр — гарын үсэгтэй git tag (`git tag -s v0.1.0`); серверт тэр түлхүүрийн нийтийн хэсгийг
`gpg --import` хийнэ. Гарын үсэггүй бетад л `--allow-unsigned` (анхааруулга хэвлэнэ).
```bash
sudo infra/prod/deploy.sh v0.1.0                    # tag-ийн гарын үсгийг шалгаад суулгана
sudo infra/prod/deploy.sh --allow-unsigned main     # (бета) origin/main
sudo infra/prod/deploy.sh --rollback                # өмнөх image руу (migration буцахгүй)
```
Deploy амжилтгүй болбол env файл өмнөх хувилбарыг заасан хэвээр; аль нь ажиллаж байгааг
`sudo infra/prod/lt.sh ps` харуулна, буцаах бол `--rollback` эсвэл өмнөх tag-ийг дахин deploy.

Анхны удаа (deploy-ийн дараа):
```bash
sudo infra/prod/lt.sh run --rm -v /opt/labtrack/seed:/seed:ro migrate python -m labtrack.cli seed
```
🔒 Эхний админ (TOTP QR гарна — зөвхөн хүн, логгүй терминалд):
```bash
sudo infra/prod/lt.sh run --rm migrate python -m labtrack.cli create-admin <нэр> --role super_admin
```
Бусад: `sudo infra/prod/lt.sh ps`, `... logs -f api`, `... restart worker`.

## 7. Нөөц, мониторинг (systemd)
```bash
sudo cp infra/prod/systemd/labtrack-* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now labtrack-backup.timer labtrack-monitor.timer labtrack-restore-drill.timer
sudo infra/prod/monitor.sh --test           # дохио ирж байгааг шалгах
sudo systemctl start labtrack-backup.service && journalctl -u labtrack-backup -n 20   # "backup ok"
```
Сар бүр: `just restore-drill` **өөр машин дээр** (age хувийн түлхүүр серверт хэзээ ч үгүй — OPS_RUNBOOK §4).
Сэргээхэд: сонгосон DB нөөц + **хамгийн сүүлийн** OpenBao snapshot (түлхүүр нь нөөцөөс шинэ байж болно, хуучин
нь — болохгүй: тэр үед үүссэн хэрэглэгчийн түлхүүр алга).

## 8. Шалгах (SERVER_INSTALL_PLAN §5)
- `curl -I https://<домэйн>/api/v1/healthz` → 200, `Strict-Transport-Security` header;
  `https://<домэйн>/api/v1/readyz` → 404; гаднаас `/admin` → 404.
- `sudo infra/prod/lt.sh ps` — бүгд `running`/`healthy`; `sudo infra/prod/monitor.sh; echo $?` → 0.
- SSL Labs — A; апп-аар нэвтэрч, эм нэмж, PDF оруулж, гарах.

## Асуудал гарвал
| Шинж | Шалтгаан | Шийдэл |
|---|---|---|
| Апп «Үйлчилгээ түр ажиллахгүй», readyz `keys: false` | OpenBao sealed / VM унтарсан / firewall | §4 unseal; `nc -zv <OpenBao IP> 8200` апп серверээс |
| `CERTIFICATE_VERIFY_FAILED` | `ca.pem` буруу эсвэл хуучин `make-tls.sh`-ээр хийсэн сертификат (Python 3.13 хатуу шалгадаг) | §4-ийн make-tls-ийг дахин, ca.pem-ийг солих |
| Caddy сертификат авахгүй | DNS, 80/443 гаднаас хаалттай | `dig <домэйн>`, провайдерийн firewall |
| worker асахгүй (clamav хүлээж) | freshclam сигнатур татаж байна (эхний удаа 10 мин хүртэл) | `sudo infra/prod/lt.sh logs freshclam` |
| `prod-init: still to fill in` | дутуу утга | жагсаасан түлхүүрүүдийг §5-аар бөглөх |
