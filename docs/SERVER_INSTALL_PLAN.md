# SERVER_INSTALL_PLAN.md — өөрийн серверт backend + мэдээллийн сан суулгах (2026.11.27, ноорог)

> Үндэс: `HOSTING_OPTIONS.md` «Өөрийн сервер» (тоног төхөөрөмж), `OPS_RUNBOOK.md` (нөөц), `04_RBAC_SECURITY.md`
> (KEK, TLS, role), `BETA.md` B1. Энэ баримт **дараалал ба хэн юу хийх**-ийг тогтооно. `[?N]` — доорх
> «Асуултууд»-ын хариу хэрэгтэй газар.

## 0. Одоогийн байдал — сервер бэлэн болохоос өмнө кодод дутуу байгаа зүйлс
| # | Дутуу | Яагаад заавал | Хэн |
|---|---|---|---|
| C1 ✓ | **OpenBao KeyProvider + UserKeyStore** (`openbao.py`, `keys.py`, `user_keys.py`, `openbao_setup.py`) — 2026.11.27 | `OPENBAO_ADDR` тохируулсан үед аль ч орчинд OpenBao; production-д заавал (https) | Claude ✓ (тест + security review) |
| C2 ✓ | **Production compose overlay** `infra/docker-compose.prod.yml` — 2026.11.27 | runtime image, read-only, capability хасалт, санах ой/pid хязгаар, процесс бүр өөрийн env + Docker secret (`/run/secrets`), процесс бүр өөрийн S3 эрх, гарах зам хэрэгтэй нь л тус тусын сүлжээгээр; `keys`/`scan` дотоод сүлжээ; `bao-gateway` | Claude ✓ |
| C3 ✓ | **Production Caddyfile** `infra/caddy/Caddyfile.prod` (+ `labtrack.caddy` хуваалцсан хэсэг) | домэйн, Let's Encrypt, HSTS, 80→443, API-д CSP/CORP, timeout, healthcheck зөвхөн loopback | Claude ✓ |
| C4 ✓ (WAL — дараа) | **Postgres prod тохиргоо** | statement, параметр, DETAIL лог байхгүй (`terse`), `shared_buffers`; WAL архив (PITR) — production (≤ 500) үед | Claude ✓ |
| C5 ✓ | **ClamAV freshclam тусдаа** | clamd гарах замгүй, зөвхөн worker-тэй; freshclam тусдаа; сигнатур бэлэн болохоос өмнө worker эхлэхгүй | Claude ✓ |
| C6 | **Нөөц, мониторингийн systemd timer, скрипт** | `just backup` өдөр бүр 02:00, off-site хуулбар, `/healthz`, диск/RAID/сертификатын дохио | Claude (скрипт) + компани (дохио хүлээн авагч) |
| C7 | `just deploy` / `just prod-*` команд, `.env.production.example` | Давтагдах, баримттай суулгалт | Claude |

**Санал:** C1–C7-г серверийг худалдаж авах/бэлтгэхтэй **зэрэг** хийнэ (код ~4–5 алхам/сесс). Серверийн
тоног төхөөрөмж (§1–3) кодоос хамаарахгүй.

## 1. Тоног төхөөрөмж, байршил (компани)
- Бета (≤ 50): 4 core x86-64 (AVX2), 8 GB, 200 GB NVMe. Production (≤ 500): 8 core, 16 GB ECC, 2×500 GB NVMe RAID 1.
- KEK (OpenBao): бетад ижил серверт тусдаа VM; production-д **тусдаа** машин (2 core, 2 GB, 20 GB).
- Нөөц: өөр машин/байршил, ≥ 500 GB (бета).
- Байршил `[?1]`: колокейшн (Монголын дата төв) эсвэл оффис (түгжээтэй өрөө, UPS ≥ 15 мин).
- Сүлжээ: тогтмол IPv4 `[?2]`, гаднаас зөвхөн 80/443; SSH — VPN эсвэл IP whitelist `[?3]`.
- Домэйн `[?4]`: жишээ нь `api.<домэйн>` (API + web), DNS `A` бичлэг серверийн IP руу.

## 2. OS суулгах, хатууруулах (серверийн газар, ~2 цаг)
1. Ubuntu Server 24.04 LTS, суулгах үед **LUKS бүрэн дискний шифрлэлт** (production-д RAID 1 + LUKS).
   Дахин асахад LUKS нууц үг `[?5]`: гараар оруулах (хамгийн аюулгүй, унтралтын дараа хүн очих) эсвэл
   Tang/Clevis сүлжээний түгжээ.
2. Хэрэглэгч: `deploy` (sudo), root SSH хаах, зөвхөн SSH түлхүүр (нууц үгээр нэвтрэлт хаах), 2 хүний түлхүүр.
3. `ufw`: 80, 443 нээлттэй; 22 — зөвхөн VPN/whitelist-ээс. `fail2ban`.
4. `unattended-upgrades` (security), цаг `chrony` (JWT, TOTP, сануулгын цагт чухал), timezone UTC.
5. Docker Engine + Compose plugin (docker.com-ийн албан ёсны apt repo), `deploy`-г `docker` бүлэгт.
6. `/etc/docker/daemon.json`: `log-driver local`, `max-size`, `live-restore: true`.
7. Swap 4 GB (ClamAV-ийн шинэчлэлтийн оргилд).

## 3. OpenBao (KEK) — тусдаа VM/машин
1. OpenBao (MPL-2.0) суулгах, TLS-тэй, зөвхөн апп серверийн IP-ээс хүрэх (firewall). Хувилбар: тест
   2.7.2 дээр (2026.11.27); суулгахын өмнө хамгийн сүүлийн patch (2.7.3+)-ийн release note-ийг шалгана.
2. Initialize: **Shamir 5 хэсэг, 3-аар нээх** `[?6]` — хэсгүүдийг өөр өөр хүмүүс хадгална (цаас + сейф).
3. Тохиргоог **нэг команд** хийнэ (апп серверээс, root token-оор; дараа нь root token цуцлагдана):
   `BAO_ADDR=https://<bao>:8200 BAO_TOKEN=<root> BAO_CACERT=<ca.pem> python -m labtrack.cli openbao-setup
   --out /etc/labtrack/secrets/openbao --bound-cidr <апп серверийн IP>/32` (аудит асаалтгүй OpenBao-д татгалзана)
   - `transit` engine + `labtrack-kek` (aes256-gcm96, экспортлохгүй, устгах боломжгүй);
   - 3 AppRole (token 1 цаг, хамгийн ихдээ 4 цаг, зөвхөн тухайн IP-ээс): **api** — KEK ба хэрэглэгчийн
     түлхүүрээр шифрлэх/тайлах, шинэ хэрэглэгчид түлхүүр үүсгэх (зөвхөн `type`); **worker** — KEK-ээр
     тайлах л; **maint** — хэрэглэгчийн түлхүүр устгах л. Хэн ч түлхүүр экспорт/backup хийх, тохиргоо
     өөрчлөх эрхгүй (тест: `tests/openbao`);
   - role бүрийн `role_id`/`secret_id` — тусдаа файл (0600); дахин ажиллуулахад хуучин secret_id цуцлагдана.
   - Хэрэглэгчийн түлхүүр `u-<id>` аккаунттай хамт үүснэ; DB-ийн мөрөнд зөвхөн тэмдэг (`openbao:v1`).
4. Апп-ын тохиргоо (S2): `OPENBAO_ADDR`, `OPENBAO_ROLE_ID`, secret `openbao_secret_id` (Docker secret, `/run/secrets`),
   `OPENBAO_CA_CERT` — api, worker, maint-worker тус бүр өөрийн role-оор.
5. Аудит лог — OpenBao 2.x-д зөвхөн тохиргооны файлаар (`infra/openbao/openbao.hcl`), ≥ 35 хоног, өөр газар.
6. Дахин асахад unseal `[?7]`: гараар (3 хүн) эсвэл auto-unseal (HSM/өөр KMS — Монголд байхгүй бол гараар).
   OpenBao унтарсан/sealed үед апп 503 («Үйлчилгээ түр ажиллахгүй»), баримт хүлээгдэнэ (алдагдахгүй).
7. Snapshot нөөц: OpenBao-ийн raft snapshot → age-ээр шифрлэж **өгөгдлийн нөөцөөс тусдаа** газар.
   **Хадгалах хугацаа ≤ 35 хоног** (DB нөөцтэй адил): устгасан хэрэглэгчийн түлхүүр snapshot-д үлддэг тул
   урт хадгалбал crypto-shredding хүчингүй болно. Snapshot-оос сэргээсний дараа `just redelete` (OPS_RUNBOOK §5.6).

## 4. Апп суулгах (Claude-ийн скриптээр, ~1 цаг)
1. Репо: `git clone` (зөвхөн уншдаг deploy key) эсвэл image-ийг registry-ээс татах `[?8]`.
2. Нууц үүсгэх (`just prod-init`, серверт): Postgres role бүрийн нууц үг, Valkey, S3 key (bucket тус бүр
   эрхээр), JWT ES256 private key, `IDENTITY_PEPPER`, OpenBao AppRole — бүгд `/etc/labtrack/secrets/`
   (root:root 0600, Docker secret файл). `.env.production` — зөвхөн нууц биш тохиргоо.
3. `BACKUP_AGE_RECIPIENT` — нийтийн түлхүүр (OPS_RUNBOOK §2-оор **офлайн** үүсгэсэн), хувийн түлхүүр
   серверт хэзээ ч үгүй.
4. Гадны үйлчилгээ: `EXPO_ACCESS_TOKEN` (push — B2/B3), `SENTRY_DSN` (заавал биш), `ANTHROPIC_API_KEY`
   (`AI_EXTRACTION_ENABLED` — анх `false` `[?9]`).
5. `docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file /etc/labtrack/labtrack.env up -d`
   (хувьсагч, нууц файлын жагсаалт — `.env.production.example`; нууц файл: фолдер root 0700, файл 0444):
   postgres → valkey → seaweedfs → `migrate` (alembic head) → api, worker-ууд, beat, web, caddy.
6. `just seed` (lab_tests + medications лавлах) — **demo хэрэглэгчгүй**.
7. `just create-admin` — эхний `super_admin`, MFA тохируулах (ADMIN_IDENTITY_PROCEDURE).
8. Caddy автоматаар Let's Encrypt сертификат авна (80/443 гаднаас хүрэх ёстой).

## 5. Шалгалт (суулгасны дараа, Claude + та)
- `https://<домэйн>/api/v1/healthz` → 200; `readyz` гаднаас 404; `/admin` whitelist-ээс гадна 404.
- `just test-rls` production DB-ийн хуулбар дээр биш — **staging**-д; production дээр smoke: нэвтрэх,
  эм нэмэх, PDF оруулах (ClamAV шалгасан), яаралтай карт, гарах.
- TLS: SSL Labs A, HSTS; `docker ps` — бүх healthcheck healthy; логт PHI байхгүй (санамсаргүй 100 мөр).
- Нөөц: `just backup` гараар нэг удаа → off-site-д очсон → **`just restore-drill`** өөр машин дээр ✅.
- Ачаалал: `just load-test` 200 хэрэглэгч (8.3-ын үлдэгдэл).
- Апп: `eas.json` `beta` profile-д `EXPO_PUBLIC_API_URL=https://<домэйн>` → Play Internal build (B2).

## 6. Өдөр тутмын ажиллагаа
- Нөөц: өдөр бүр 02:00 UB (systemd timer) → off-site (зөвхөн нэмэх эрх, immutability, 35 хоног);
  сард нэг restore-drill (OPS_RUNBOOK §4).
- Шинэчлэл: `git pull` + `just deploy` (migration → rolling restart), өмнө нь нөөц; rollback — өмнөх image tag.
- Мониторинг `[?10]`: `/healthz`, диск < 80%, RAID, сертификат < 14 хоног, нөөц амжилттай эсэх,
  OpenBao sealed эсэх → утсанд дохио (Uptime Kuma / healthchecks.io / Telegram бот гэх мэт).
- Лог ≥ 35 хоног, өөр газар (OPS_RUNBOOK §3).
- Түлхүүр солих: JWT жил бүр (2 kid зэрэг), KEK rotate (OpenBao, хуучин хувилбарыг устгахгүй), age жил бүр.

## 7. Дараалал ба хугацаа (санал)
| Алхам | Агуулга | Хамаарал |
|---|---|---|
| S1 | C1 OpenBao KeyProvider + UserKeyStore + тест (dev-д OpenBao контейнер) | — |
| S2 | C2+C3+C4+C5 prod compose, Caddy TLS, Postgres, freshclam | — |
| S3 | C6+C7 prod-init, deploy, backup timer, мониторинг скрипт | S2 |
| S4 | Сервер дээр §2–4 (та SSH өгнө, эсвэл таны гараар — Claude заавар өгнө) | сервер, домэйн |
| S5 | §5 шалгалт, restore-drill, PROGRESS/BETA B1 ✅ | S4 |

## Шийдвэр (хэрэглэгч, 2026.11.27)
- Байршил: **колокейшн** — өөрийн сервер Монголын дата төвд (асуулт 1 — тоног төхөөрөмжийн үзүүлэлт үлдсэн).
- Удирдлага: **хоёр горимоор бэлдэнэ** — эхлээд Claude SSH-ээр (танай PC-ээс, түлхүүрээр; алхам бүрийг
  шалгаж ажиллуулна), болохгүй бол гараар: алхам бүр хуулж ажиллуулах командын блок + хүлээгдэх гаралт
  (`docs/SERVER_INSTALL_MANUAL.md`, S3-т). Скриптүүд (`just prod-init`, `just deploy`) хоёр горимд ижил.
- Домэйн: **байгаа** (нэрийг S2-т тодруулна).
- **Зөвхөн хүн** (Claude SSH-ээр суулгаж байсан ч): OpenBao `init`/`unseal`, root token-той алхмууд, эхний
  админ (`create-admin`, TOTP QR) — Shamir хэсэг, token, QR Claude-ын транскрипт, лог руу орохгүй (MANUAL §4–6 🔒).
- Эхний алхам: **S1 OpenBao KeyProvider**.

## Асуултууд (хариулт хэрэгтэй)
1. **Байршил:** колокейшн (дата төв) уу, оффис уу? Сервер аль хэдийн байгаа юу (CPU/RAM/диск)?
2. **IP:** тогтмол гадаад IPv4 байгаа юу? Провайдер 80/443-ыг нээх үү?
3. **Удирдлага:** Claude SSH-ээр шууд суулгах уу (танай PC-ээс), эсвэл та командыг гараар ажиллуулах уу?
4. **Домэйн:** бүртгэлтэй домэйн байгаа юу (жишээ нь `labtrack.mn`)? API, web ижил домэйн дээр үү?
5. **LUKS нээх:** асах бүрт гараар нууц үг оруулах уу, сүлжээний түгжээ (Tang) уу?
6. **OpenBao түлхүүрийн хэсгүүдийг** хэдэн хүн хадгалах вэ (5/3 санал)? Хэн бэ (нэр биш — үүрэг)?
7. **OpenBao тусдаа машин:** бетад ижил серверт VM хангалттай юу (KVM/Proxmox байгаа юу)?
8. **Image:** серверт build хийх үү (энгийн), эсвэл GitHub Container Registry-ээс татах уу?
9. **AI унших:** эхний бетад унтраалттай эхлэх үү (санал — тийм; Q12 хуульчийн хариутай холбоотой)?
10. **Дохио:** алдааны мэдэгдэл хаашаа — Telegram, имэйл, SMS?
11. **Off-site нөөц:** хаана (өөр оффис дахь NAS, Монголын S3 үйлчилгээ, …)?
12. **Staging:** бетаас өмнө ижил серверт тусдаа staging stack хэрэгтэй юу (санал — тийм, жижиг)?
