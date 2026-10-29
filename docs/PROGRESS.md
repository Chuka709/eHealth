# PROGRESS — LabTrack MN

> Тэмдэглэгээ: `[x]` хийгдсэн · `[ ]` хийгдээгүй · `[~]` хэсэгчлэн · `[!]` шийдвэр/саад хүлээж байна.
> Phase бүрийн төгсгөлд DoD-г **нотолгоотой** (команд, тестийн тоо, дэлгэцийн зураг) энд бичнэ. Нээлттэй асуулт → `OPEN_QUESTIONS.md`.

## Одоогийн байдал
**Phase 1 — хийгдэж байна** (2026.10.28). Phase 0 код бүрэн; төхөөрөмж/CI-ийн 3 DoD-г **хэрэглэгчийн шийдвэрээр түр хойшлуулсан** (таны аккаунт/төхөөрөмж шаардана) — Phase 2-ын бета-гаас өмнө заавал хаагдана.

---

## Бэлтгэл (Phase 0-ээс өмнө)
- [x] v7.1 төлөвлөлтийн багцыг үндсэн хавтсанд байршуулах, хуучныг `_archive/`-д
- [x] docs-ын 11 зөрчил засах (`11_TOOLING.md` §1.1)
- [x] Claude Code plugin-ууд (LSP, security-guidance, pr-review-toolkit, commit-commands, claude-md-management, context7, frontend-design, expo)
- [x] `ui-reviewer` agent, `phi-table` skill, cross-platform format hook, allowlist нарийсгах
- [x] `git init`, `.gitignore`, `.gitattributes`, эхний commit
- [x] Хэрэгсэл: Node 22, pnpm, Docker 29, Python 3.13, git, pyright, typescript-language-server
- [x] `just` 1.59, `uv` 0.13.6, `jq` — winget (шинэ терминал нээхэд PATH-д орно)
- [ ] `eas-cli` (`npm i -g eas-cli`) + Expo аккаунт (`eas login`)
- [ ] Android Studio + эмулятор **E: дээр** — заавар `docs/ANDROID_EMULATOR.md` (WHPX бэлэн; iPhone, CI — хойшлуулсан)
- [ ] iOS: Apple Developer Program ($99/жил) + бодит iPhone-ийг `eas device:create`-ээр бүртгэх (Q1 — шийдэгдсэн)
- [ ] Maestro (Android эмулятор; iOS E2E — GitHub Actions macOS)
- [ ] Anthropic API key (Phase 4-өөс заавал; `.env`-д — Claude уншихгүй)
- [ ] GitHub private репо үүсгэж push хийх (Q3 — та хийнэ)
- [ ] Phase 4-д зориулж нэрээ нууцалсан 30+ бөөр/элэгний хариу цуглуулж эхлэх (удаан ажил)
- [ ] Админы хүн таних журам (бичгээр): эргэж залгах + РД HMAC — `04 §1`

---

## Phase 0 — Суурь
- [x] 0.1 Monorepo: pnpm workspace (hoisted, install script opt-in), Biome 2.6 (код файлд), `justfile` (Windows: `pnpm.cmd`), `.editorconfig`, `.env.example` + `just init` (санамсаргүй dev нууц)
- [x] 0.2 Compose: postgres 17 (`labtrack_owner/app/admin/maint` + `labtrack_test` DB), **Valkey 8** (Redis-ийн оронд — лиценз), SeaweedFS S3, migrate, api, worker, web, caddy — бүгд healthcheck; Caddy лог query string нууцална, аюулгүй header
- [x] 0.3 Backend (Python 3.13): FastAPI factory, `/healthz` `/readyz` (алдааны дэлгэрэнгүй гаргахгүй), pydantic-settings, structlog PHI redact, `user_transaction` (`set_config(..., true)`), `bound_text` (`sqlalchemy.text` хориотой), Sentry (бүх data collection off + URL query хасна), Celery ping, Alembic baseline (`REVOKE CREATE/TEMPORARY`), ruff + mypy --strict
- [x] 0.4 `packages/shared`: openapi-fetch client (`just gen-client`, `just check-client`), mn/en (түлхүүр тэнцүү тест), design token (бүх өнгөний хос WCAG AA — тест)
- [x] 0.5 Mobile: **Expo SDK 58** (RN 0.88), Expo Router, TanStack Query, use-intl (mn), `app.config.ts` (fingerprint runtime, env bundle ID, `allowBackup=false`), `eas.json` (development/preview/production), API төлөвийн дэлгэц (өнгө+дүрс+текст, 44pt/48dp), Jest + RNTL v14. Styling: token + StyleSheet + `@expo/ui` (Q14 шийдэгдсэн)
- [x] 0.6 Web: **Next.js 16.4** (cache components, standalone), `lang=mn`, Noto Sans кирилл, security header, `/healthz`, төлөвийн хуудас, Vitest, Docker image. next-intl/shadcn/BFF — Phase 1 (админ самбартай хамт)
- [~] 0.7 CI `.github/workflows/ci.yml` (ruff, mypy, контейнер pytest + alembic up/down/up, biome, tsc, jest, vitest, expo-doctor, stale client) — **GitHub дээр ажиллуулаагүй** (репо байхгүй)
- [x] 0.8 `backend/CLAUDE.md`, `mobile/CLAUDE.md`, `web/CLAUDE.md`

**Security review (security-reviewer, 2 High + 8 Medium + 8 Low) — засагдсан, ажиллаж буй stack дээр батлагдсан**
- [x] H1 функцийн default EXECUTE: `IN SCHEMA` хэлбэр PostgreSQL-д юу ч хийдэггүй байсан → `for role labtrack_owner` + регресс тест
- [x] H2/M1 сүлжээ: `edge` / `backend` (internal) / `egress`; web → postgres/valkey/seaweedfs **хаалттай**, seaweedfs интернэтгүй (probe-оор шалгасан). SeaweedFS JWT signing — Phase 3 (баримт хадгалахаас өмнө)
- [x] M1 Valkey `requirepass` · M2 Caddy `127.0.0.1` (утсаар турших: `CADDY_BIND=0.0.0.0`) · M6 proxy header зөвхөн Caddy-ийн IP-ээс
- [x] M3 Caddy лог: query, request/response header бүгд хасагдсан (token/cookie/referer 0 олдсон) · `/readyz` гаднаас 404
- [x] M4 stdlib логгер (uvicorn, sqlalchemy, asyncpg, celery) redaction chain-ээр; driver-ийн `DETAIL`/`Key (...)=(...)`, query string scrub; `_token/_secret/_key/_email` · M5 Sentry exception/breadcrumb/logentry scrub — тесттэй
- [x] M7 CI action-ууд commit SHA-аар, `persist-credentials: false`, expo-doctor devDependency · M8 preview/production build `https://` биш бол унана
- [x] Low: prod-д OpenAPI хаалттай, Redis client дахин ашиглана, compose `${VAR:?}`, SeaweedFS 4.50 pin, web файлууд root эзэмшилтэй, downgrade CREATE өгөхгүй, `.dockerignore` `.env.*`
- [x] L8 `tests/rls/` — 39 тест (1.1, 1.2)

**Phase 1 DB security review (1 Critical, 5 High, 5 Medium, 4 Low) — засагдсан**
- [x] C1 админ аккаунт булаах боломжтой байсан → админд хүснэгт бичих эрх 0, бүх үйлдэл `0004` definer функцээр (DB шалгалттай); `activation_consume`
- [x] H1 dev DB-д definer функц PUBLIC-д нээлттэй байсан → migration бүрт тодорхой `revoke … from public` + `pg_proc` тест · H2 админ аудитын actor = `app.user_id` · H3 админ бусад админд хүрэхгүй, support зөвхөн тайлна · H4 сесс сэргээх боломжгүй (`revoke_my_session`) · H5 `notify` төрөл + хүлээн авагчийн хандалт шалгана
- [x] M1 `is_minor` төрсөн огнооноос, засах боломжгүй · M2 зөвшөөрлийн огноо DB-ийнх · M3 `audit_write` харь өвчтөнд татгалзана · M4 хуваалцах lookup 30/цаг, зөвхөн идэвхтэй user/doctor-д · M5 self profile зөвхөн `admin_create_user`-д
- [x] L1 устгасан профайл уншигдахгүй · L2 `granted_by` DB тогтооно
- Нийт backend тест: **157** (RLS 76, API 27, unit 50+)

**Auth security review (1 Critical, 2 High, 4 Medium, 5 Low) — засагдсан**: grace-ээр reset тойрох (C1), argon2 event loop + IP хязгааргүй (H1), зэрэгцээ түгжээ тойрох (H2), итгэмжлэгдсэн төхөөрөмж цуцлагддаггүй (M1), CGNAT-аар утас түгжих (M2), нууц үг солих oracle (M3), `session_create` нууц үг шалгалтгүй (M4), SQL параметр лог, идэвхжүүлэхэд нэрийн шалгалт, `ENVIRONMENT` анхдагч dev, сессийн туйлын хугацаа. Нээлттэй: `04 §6.12`.

**DoD — нотолгоо**
- [x] `just up` — 7 сервис healthy; `curl :8080/api/v1/readyz` → `{"status":"ok","database":true,"queue":true}`; вэб хуудас Caddy-аар "Сервер хэвийн ажиллаж байна"
- [x] Шалгалтууд: `just lint` 0 алдаа; `just test` — backend 23 (DB, migration up/down, эрхийн регресс орсон), shared 6, web 3, mobile 2 — бүгд ногоон; `just check-client` цэвэр; `expo-doctor` 20/20; Android JS bundle (`expo export`) амжилттай; `next build` амжилттай
- [ ] Dev build **Android эмулятор** дээр API дуудна — AVD + `npx expo run:android` (эсвэл `eas build --profile development --platform android`) **таны машин дээр**
- [ ] Dev build **бодит iPhone** — Apple Developer + Expo аккаунт, `eas device:create`, `eas build --profile development --platform ios` (**та**)
- [ ] CI ногоон — GitHub репо үүсгэж push хийсний дараа (**та**)

## Phase 1 — Auth, супер админ, профайл
- [x] 1.1 Migration (`0002`, 35 RLS тест): extensions, enum, `labtrack_owner/app/admin/maint` role, `REVOKE TEMPORARY/CREATE`; users (`account_status`, `token_version`, шифрлэлттэй утас, РД argon2 hash) + column-level эрх, activation_tokens, sessions (`revoked_reason`, `device_trusted`), auth_attempts (+индекс), patients, patient_access, consents (append-only), notifications, audit_logs (`target_user_id`, trigger, `REVOKE TRUNCATE`); definer функцууд (`search_path` хатуу): `can_read/can_write_patient`, `is_owner`, `create_self_profile`, `auth_*`, `audit_write`, `my_admin_actions`, `notify`, `lookup_user_for_share`; хүснэгт бүрт 4 үйлдлийн policy; ENABLE+FORCE RLS
- [x] 1.2 Migration `0003`: test_catalog, test_synonyms (сурсан синоним хувийн), unit_aliases, unit_conversions, medication_catalog; `just seed` (idempotent, Decimal, хязгаар/тун агуулбал татгалзана; 61 тест, 271 синоним, 30 эм); `core/text.normalize_name` (кирилл/латин ижил хэлбэрийн үсэг, hypothesis)
- [x] 1.3 `core/security` (+ `auth/tokens`; hypothesis түгжээний overflow-ыг илрүүлж засуулсан): envelope шифрлэлт (`core/envelope` + `keys.KeyProvider`, AES-256-GCM, толгойтой формат, AAD — **1.6a-д нөхөж хийсэн**: өмнө нь тэмдэглэгдсэн боловч кодод байгаагүй), argon2id (+pepper РД-д), нууц үгийн бодлого (≥ 10, zxcvbn, задарсан жагсаалт), идэвхжүүлэх токен (≥ 128 бит, hash), JWT ES256 (kid, `sid`, `tv`), refresh rotation + reuse detection + 20 сек grace, device-cookie түгжээ, dummy hash — hypothesis тест
- [~] 1.4 Service: auth ✓ (`auth/service.py`, DB-д зөвхөн `0005` definer функцээр); admin, consents — 1.6–1.7-той хамт
- [x] 1.5 `/auth` (15 API тест бодит DB-тэй; slowapi IP хязгаар — дараа, одоо DB-ийн device-cookie түгжээ): activate, login, refresh (`401 admin_reset` код), logout, change-password, sessions, delete-account request; slowapi; нэг төрлийн алдааны мессеж/хугацаа
- [x] 1.6 **хийгдсэн (1.6a–f):** envelope шифрлэлт + `KeyProvider`; migration `0006` (админ сесс, `labtrack_admin_login` role, TOTP алхам нэг удаа, `admin_actor` ↔ тухайн транзакцын сесс, шалтгааны enum, РД-г тохируулсан админ reset олгохгүй, токен өөрөө ашиглахыг илрүүлэх); `/admin/auth` (нууц үг + TOTP, 8ц/15мин, ≤ 3 сесс, IP allowlist — Caddy + API); `just create-admin`, `just unlock-admin`; `/admin/users` (бүртгэх, хайх, дэлгэрэнгүй, төлөв, түгжээ тайлах, таних шалгалт, РД тохируулах, токен QR/SMS, утас нээх), `/admin/security-events`; `SmsSender` (dev: console, токен/дугааргүй лог). CSV импорт (санах ойд, preview → ижил sha256-тай commit, бүгд эсвэл юу ч үгүй, аудитад hash + мөрийн тоо). Хамгаалалт: утас нээх 20/өдөр/админ, түгжээ тайлах 3/өдөр/хэрэглэгч, түгжих/идэвхгүй болгоход амьд токен цуцлагдана, ASCII-ээс өөр цифр/bidi нэр татгалзана, `Cache-Control: no-store`, DB алдааны текст хариу/логт гарахгүй. Security review 3 шат + автомат review (2 High, 12 Medium, 18 Low) — засагдсан. Backend тест: **278** (контейнер) + unit.
  - Одоо байгаа DB-д `labtrack_admin_login` role-ыг гараар үүсгэнэ (`01-roles.sh` зөвхөн шинэ volume-д): `create role labtrack_admin_login login password … nobypassrls; grant connect on database …` — migration 0006-аас өмнө.
  - 1.10-д: BFF админы жинхэнэ IP-г дамжуулна (`X-Forwarded-For`, web-ийг `FORWARDED_ALLOW_IPS`-д) — эс бөгөөс §6.1-ийн сүлжээний шалгалт BFF-ийн IP-г харна.
- [x] 1.6 (анхны төлөвлөгөө) `/admin/users` (`labtrack_admin` role): бүртгэх + идэвхжүүлэх QR, CSV (санах ойд) → `pending_activation`, хайх, идэвхгүй (`token_version`+1), түгжээ тайлах, таних шалгалт (тийм/үгүй, 5/өдөр, 10 мин state) → сэргээх токен (QR/SMS, шалтгаан, сесс цуцлах, хохирогчид SMS), утас нээх (аудит); `SmsSender` (dev: console); TOTP; `just create-admin`; `/admin` IP allowlist, сесс 8ц/15 мин
- [x] 1.7 **хийгдсэн:** `/me` (профайл GET/PATCH — нэрэнд control/bidi хориотой; `/auth/me` → `/me`), `/me/consents` (append-only, зөвхөн одоогийн хувилбарт, заавал: terms/privacy/sensitive_data, сонголт: ai_processing+cross_border; хүүхдийн профайлд зөвхөн эзэн — RLS; `draft-2026-10` текстээр production эхлэхгүй — Q12; `consents.require()` gate Phase 2-оос), `/me/admin-actions` (хэзээ/юу/role — хэн нь биш), `/me/notifications`, `/me/report-unwanted-admin-action` ("Би хүсээгүй" — 30 хоногийн дотор, аккаунт locked, бүх сесс/токен цуцлагдана, `security.user_report`; сэжигтэй түгжээг (админы `suspected_compromise` ба "Би хүсээгүй") төлөв солих замаар хэн ч тайлахгүй — зөвхөн таних шалгалт + reset токен, шинэ нууц үг — migration `0007`). Зөвшөөрөл татахад хувилбар шаардахгүй; нэр солиход аудит (утгагүй). Security review (1 Medium, 6 Low) — засагдсан. Hazard H21. Backend тест: 289.
- [ ] 1.7 (анхны төлөвлөгөө) `/me`: профайл, 5 зөвшөөрөл (хувилбартай; хүүхдийн профайлд асран хамгаалагчийн зөвшөөрөл API-д шалгах), админы үйлдлийн түүх
- [x] 1.8 **хийгдсэн:** `POST /me/delete` (нууц үг дахин шалгана, нууц үг солихтой ижил түгжээ; бүх сесс/токен шууд цуцлагдана; 202 + `scheduled_for`) — 1.5-д "хийгдсэн" гэж бичсэн ч кодод байгаагүй; migration `0008`: `request_account_deletion`, `admin_cancel_deletion` (30 хоногт, super_admin; аккаунт `locked` + `reset_required` — таних шалгалт + шинэ нууц үгээр л сэргэнэ), `maint_purge_deleted_users` (`labtrack_maint`: эзэмшдэг профайл + бүх PHI, аккаунт, түлхүүр; аудитад зөвхөн id), `user_keys` — хэрэглэгч бүрийн түлхүүр (утасны дугаар үүгээр шифрлэгдэнэ; purge-д устгаснаар бүх хуулбар уншигдахгүй — crypto-shredding; dev-д DB-д, production-д OpenBao named key); Celery beat (`beat` сервис, өдөр бүр 03:00 УБ): purge + `auth_attempts` 90 хоног; админ: `deletion_pending` шүүлтүүр, `cancel-deletion` (шалтгааны enum). Security review (4 Medium, 7 Low) — засагдсан: устгал хүлээгдэж буй үед бусад (асран хамгаалагч/эмч) профайлд хандахгүй; purge нэг аккаунтын алдаагаар зогсохгүй (`security.purge_failed`), retention тусдаа; maint credential зөвхөн `maint-worker`-т (queue `maintenance`); хуучин утсыг `just rewrap-user-keys`, KEK fallback хаагдсан; `user_key_get` зөвхөн аудитлагдсан reveal-ийн дараа, `user_key_put` зөвхөн шинэ аккаунтад; устгасан аккаунтыг токен сэргээхгүй; purge-д username-ийн `auth_attempts`; FK-ийн schema тест; downgrade хамгаалалт. Устгах хүсэлтийн SMS мэдэгдэл — Q13-тай хамт. Backend тест: 306.
- [ ] 1.8 (анхны төлөвлөгөө) Аккаунт устгах: soft delete + 30 хоногийн дараа Celery beat-ээр бүрэн устгах
- [x] 1.9 `just gen-client`: OpenAPI + `schema.d.ts` шинэчлэгдсэн (`/admin/*`, `/me/*`); `error-codes.json` (45 алдааны код + 12 CSV асуудал) — mn/en текст бүгдэд, shared тест шаардана
- [x] 1.10 **хийгдсэн:** Next.js BFF — session токен зөвхөн `__Host-` httpOnly/Secure/SameSite=Strict cookie-д, server action-аар API руу bearer + админы жинхэнэ IP (Caddy `X-LabTrack-Client-IP {client_ip}`, API web-ийн IP-д итгэнэ); хатуу nonce CSP (`proxy.ts`; `cacheComponents`/PPR унтраасан); Caddy allowlist `/admin` хуудсанд ч; dev лог server action-ий аргумент/URL бичихгүй. Хуудсууд: нэвтрэх (TOTP), хэрэглэгчид (хайлт, шүүлтүүр, устгал хүлээгдэж буй), бүртгэх, дэлгэрэнгүй (төлөв+шалтгаан+баталгаажуулалт, түгжээ тайлах, утас нээх — баталгаажуулалт + 60 сек, РД бүртгэх, таних шалгалт → сэргээх QR/SMS + баталгаажуулалт, идэвхжүүлэх QR — нэг удаа, тоолуур, нуух, нэвтрэх карт хэвлэх, устгалт цуцлах), CSV импорт (яг тэр байтаар, preview → баталгаажуулж commit), аюулгүй байдлын дохио. Playwright e2e (`just e2e-web`, түр админ, teardown-оор идэвхгүй болгоно). **API засвар:** DB dependency бүр `scope="function"` — транзакц хариу илгээхээс ӨМНӨ commit (өмнө нь шинэ сесс/токен commit болохоос өмнө клиентэд очиж race үүсгэдэг байсан; e2e илрүүлсэн). security-reviewer (1 Medium, 7 Low) + ui-reviewer (5 High, 10 Medium, 7 Low) — засагдсан. Үлдсэн: production-д админыг тусдаа host (`admin.`) дээр гаргах; e2e-ийн `e2eu*` хэрэглэгчид dev DB-д үлдэнэ.
- [ ] 1.10 (анхны төлөвлөгөө) Web админ: нэвтрэх + TOTP, хэрэглэгчид, бүртгэх, CSV, идэвхжүүлэх QR харуулах, нэвтрэх карт (нууц үггүй) хэвлэх, таних шалгалт → сэргээх, тайлах, идэвхгүй болгох
- [ ] 1.11 Апп: welcome, идэвхжүүлэх (QR/линк → нууц үг + хүчтэй байдлын заагч), login, `admin_reset` мэдэгдлийн дэлгэц, зөвшөөрлүүд, биометр, "нууц үгээ мартсан", профайл, тохиргоо (сесс, нууц үг, админы түүх + "Би хүсээгүй", аккаунт устгах), lock, secure-store (`WHEN_UNLOCKED_THIS_DEVICE_ONLY`), refresh single-flight, privacy overlay
  - [x] 1.11a **Суурь:** native модулиуд (`expo-secure-store`, `-local-authentication`, `-camera` — зөвхөн QR, микрофон/RECORD_AUDIO хаалттай, `-screen-capture`, `-file-system`, `-dev-client` — production-д plugin-гүй) → **шинэ dev build хэрэгтэй** (`eas build --profile development`, төхөөрөмжийн DoD-той хамт хойшлогдсон). Access token зөвхөн санах ойд; refresh + device token secure-store `WHEN_UNLOCKED_THIS_DEVICE_ONLY`; auth fetch (bearer зөвхөн API origin-д, redirect-гүй, зөвхөн `auth.required`/`auth.session_invalid` 401-д нэг refresh + retry); single-flight refresh + epoch (гарах/нэвтрэх үед хуучин refresh бичигдэхгүй); `wipeLocal` (кэш, refresh; device token энгийн гаралтад үлдэнэ, admin_reset/устгалтад устна); iOS дахин суулгахад Keychain-ийн үлдэгдлийг устгана (Documents marker); `auth.admin_reset` код literal болсон (error-codes + mn/en). Jest 26 тест. security-reviewer (1 High, 4 Medium, 6 Low) — засагдсан; L6 (`usePreventScreenCapture`) 1.11d-д.
  - [x] 1.11b **Нэвтрэлтийн дэлгэцүүд:** welcome, activate (апп доторх QR уншигч — зөвхөн `labtrack://activate#…`; линк → `+native-intent` токеныг санах ойд, route/params/түүхэнд орохгүй, 2 мин TTL; бусад бүх гадны линк `/` руу), нууц үг + давталт + zxcvbn-ts заагч (зөвхөн зөвлөмж), login (`device_token`, `device_name` = загвар), forgot, admin-reset (мэдэгдэл secure-store-ийн тэмдгээр апп дахин эхэлсэн ч хадгалагдана, screen reader зарлана, тусламжийн утас `EXPO_PUBLIC_SUPPORT_PHONE` — preview/production-д заавал). `Stack.Protected` + `/` anchor redirect; splash төлөв уншигдтал. login/activate: `usePreventScreenCapture` + iOS app-switcher blur; credential mutation `gcTime: 0`. Jest 53 тест (RNTL + `expo-router/testing-library`). security-reviewer (2 Medium, 7 Low) + ui-reviewer (3 High, 7 Medium, 6 Low) — засагдсан, M2 (custom scheme-ийн SMS линкийг өөр Android апп барьж авах) — хэрэглэгчийн шийдвэрээр идэвхжүүлэхэд **хэрэглэгчийн нэр** шаардана (migration `0009`: мэдэгдэхгүй токен ба буруу нэр нэг замаар — ижил SQL, ижил хариу; буруу нэр 3 удаа → токен цуцлагдана + аюулгүй байдлын дохио; definer функц бүрийн `search_path` ба PUBLIC эрхийн ерөнхий тест; backend 316 тест; security review 2 Medium, 4 Low — засагдсан; үлдсэн: таахад амархан нэр, цуцлагдсаныг SMS-ээр мэдэгдэх — Q13); App Links/Universal Links — домэйн шийдэгдсэний дараа. Төхөөрөмж дээр шалгах: `+native-intent`-ийн `path` fragment-тэй ирэх эсэх (fallback бий). 5(в) "Би хүсээгүй" — 1.11e.
- [ ] 1.12 Тест: RLS (2+ хэрэглэгч, хугацаа дууссан/цуцлагдсан, worker context, `app.user_id`-гүй, pg_temp shadowing, `users` жагсаалт задрахгүй, role өөрчлөх боломжгүй, нууц багана SELECT хориотой, хуурамч аудит, caregiver насанд хүрэгчийн өмнөөс зөвшөөрөхгүй), админ токен PHI → 403, админ өөрийн олгосон токеноор нэвтрэх → татгалзах, auth (reuse, grace, device-cookie түгжээ, идэвхгүй хэрэглэгчийн JWT шууд 401, pending/disabled ялгагдахгүй, AAD), schemathesis, Maestro идэвхжүүлэх урсгал
- [ ] 1.13 `security-reviewer`, `ui-reviewer` хяналт; PROGRESS/OPEN_QUESTIONS шинэчлэх

**DoD**
- [ ] Админ бүртгэсэн хэрэглэгч ≤ 2 мин-д QR-аар идэвхжүүлж өөрийн нууц үгээр нэвтэрнэ (админ нууц үг мэдэхгүй)
- [ ] Сэргээх токен олгоход хуучин бүх сесс шууд цуцлагдаж, хуучин төхөөрөмж `admin_reset` мэдэгдэл харуулна
- [ ] Админ токеноор PHI endpoint → 403 (RLS-ээр ч 0 мөр)

## Phase 2 — Шилжүүлэн суулгалт, эм, амин үзүүлэлт, товлол
- [ ] PHI хүснэгтүүд + RLS (`phi-table`), idempotency түлхүүр (`11_TOOLING` B)
- [ ] Wizard ≤ 3 мин; эм, тунгийн түүх (шинэ regimen)
- [ ] Локал сануулга: iOS 64 хязгаарын тооцоо (`11_TOOLING` A), цагийн бүсийн горим, түгжээтэй дэлгэцэнд нэргүй
- [ ] Амин үзүүлэлт, харшил, яаралтай карт, товлол, эмчээс асуух асуулт, асран хамгаалагчийн мэдэгдэл
- [ ] Сануулгын тест матриц (iOS 2, Samsung, Xiaomi, хямд Android; хаалттай, нислэгийн горим, цагийн бүс, reboot)
- [ ] H6–H10 тестээр нотлох; `medical-reviewer`
- [ ] TestFlight / Play Internal — 10–20 бета (бөөр, элэг)

## Phase 3 — Оруулах
- [ ] Presigned upload, python-magic, давхардал, ClamAV, Celery
- [ ] Scanner, зургийн сан, PDF, share intent (iOS + Android бодит төхөөрөмж), offline дараалал
- [ ] DoD: нислэгийн горимд скан → давхардалгүй илгээгдэнэ; Messenger-ээс PDF share

## Phase 4 — AI задлалт
- [ ] Eval runner + baseline (30+ кейс, бөөр/элэг ≥ 50/50)
- [ ] Pipeline (`05_EXTRACTION.md`), prompt caching, escalation
- [ ] DoD: тоон утга ≥ 98%, лавлах ≥ 95%, тест таних ≥ 95%, p95 ≤ 30 сек

## Phase 5 — Нормчлол, Review
- [ ] `core/units.py`, `flags.py`, `ranges.py`, `matching.py` + hypothesis
- [ ] Review дэлгэц, критик баннер, `critical_pending` push, гараар оруулах
- [ ] DoD: 5 хүнтэй usability — 1 хуудас ≤ 60 сек (iPhone SE, том фонт)

## Phase 6 — Дашбоард, цагийн хэлхээс
- [ ] Эрхтнээс хамаарах картууд, хандлага (step band + тун + үйл явдал), цагийн хэлхээс
- [ ] DoD: 3000 утга + 5 жил эм — Нүүр p95 < 1.5 сек (дунд Android)

## Phase 7 — Хуваалцах, PDF, web viewer
- [ ] Нэрээр/линк+QR (PIN түгжээ — `11_TOOLING` C), web read-only, "хэн хэзээ үзсэн"
- [ ] Такролимус CV% + зорилтот хүрээнд байсан хувь (эмч болон өвчтөнд, босгогүй)
- [ ] "Эмчид үзүүлэх" PDF, экспорт PDF/JSON/FHIR R4 (шалгагчаар)

## Phase 8 — Дэлгүүрт гаргах
- [ ] `08_MOBILE.md` жагсаалт, `09` release шалгалт, staged rollout
- [ ] Хууль: нууцлалын бодлого, DPA (Anthropic, hosting), зөрчлийн журам, хуульчийн хяналт
- [ ] Pentest, ачааллын тест, нөөц сэргээх сургуулилт
