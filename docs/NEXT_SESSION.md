# Дараагийн session-д өгөх промпт (Phase 2.8b-ээс)

> Шинэ Claude Code session нээгээд **Plan mode** (Shift+Tab) асаагаад доорх блокыг бүтнээр нь буулгана.
> Session бүрийн төгсгөлд энэ файлыг (төлөв, сургамж) шинэчилнэ.

```
LabTrack MN төслийн Phase 2.8b-г эхлүүлнэ: push суурь (token API + Celery илгээгч).
Надтай монголоор харилц.

## Эхлээд унш (зөвхөн эдгээрийг — токен хэмнэ)
- CLAUDE.md, backend/CLAUDE.md (автоматаар ачаалагдана)
- docs/PROGRESS.md — Phase 2 хэсэг: 2.8 төлөвлөгөө + шийдвэр (a)(b)(c), 2.8a мөр (хийгдсэн, үлдсэн M4/L3)
- docs/08_MOBILE.md — "Мэдэгдэл", "Асран хамгаалагч (opt-in)"
- docs/04_RBAC_SECURITY.md — push payload-д PHI байхгүй (§ checklist)
- docs/09_CLINICAL_SAFETY.md — H12, H16
- docs/OPEN_QUESTIONS.md — шийдэгдсэнийг дахин бүү маргалд; Q8 (push), Q42 (нээлттэй)
- backend/alembic/versions/0020_caregivers_and_push.py, 0021_one_notice_per_entity.py, 0022_unique_notice_per_entity.py —
  `set_session_push_token`, `maint_push_queue`, `maint_mark_pushed`, `maint_forget_push_token`,
  `push_receipts` (зөвхөн labtrack_maint), notify() дүрмүүд
- backend/src/labtrack/worker/celery_app.py, worker/maintenance.py (labtrack_maint холболт, beat)
- backend/src/labtrack/api/me.py (/me router), api/deps.py (claims — JWT-ийн `sid`)
- backend/src/labtrack/admin/users.py — admin_reset урсгал (notifications мөр үүсдэг эсэхийг шалга)

## Одоогийн төлөв (2026.11.10, салбар phase-2, сүүлийн commit — `git log -1`)
- Phase 2 нэг PR-аар: https://github.com/Chuka709/eHealth/pull/1 (draft, base main).
  Алхам бүрийн дараа `git push origin phase-2` (зөвшөөрөгдсөн); main руу шууд push, force push
  хориотой (.claude/settings.json deny + .githooks/pre-push). PR-д Auto-fix асаалттай — CI-г бүү poll хий.
- Хийгдсэн: 2.0–2.7 (эм, сануулга, эрүүл мэндийн бичлэг, Профайл tab, товлол, яаралтай карт +
  түгжээтэй үед нээх + түрийвчний PDF + wallpaper + Medical ID; Maestro activation→эм→карт
  эмулятор дээр давсан). 2.8a: migration 0020 (урилга, caregiver_alert_settings, dose_alerts,
  push_receipts, push token setter, maint push queue) + 0021/0022 (нэг урилга/тунд нэг мэдэгдэл, DB-ийн unique index-ээр).
  Security review (1 High, 6 Medium) засагдсан.
- Тест: backend бүгд давсан (`just test-api`, контейнер; ~690), Jest 215, `just lint` цэвэр.
- Dev DB 0022 хүртэл migrate хийгдсэн. Эмулятор/Metro/Docker stack өмнөх session-д асаалттай байсан.

## Шийдэгдсэн (PROGRESS 2.8, хэрэглэгч 2026.11.10)
- (a) Тун хоцорсныг **сервер** илрүүлнэ (2.8e: Celery beat + core/slots.py), текст «шалгана уу».
- (b) Профайл сонгогч 2.8f-д.
- (c) Expo/FCM/APNs credential одоогоор **байхгүй** — Expo push API-г тестэд mock-лоно; credential
  байхгүй үед илгээгч no-op (мэдэгдлийг "илгээсэн" гэж тэмдэглэхгүй), бодит push бетагийн өмнө.

## 2.8b-ийн хүрээ (төлөвлөгөө → миний зөвшөөрөл → хэрэгжүүлэх)
- **Эхлээд Q42-ыг надаас AskUserQuestion-оор асуу** (зөвшөөрөл татахад одоо байгаа асран
  хамгаалагчийн эрх: хэвээр / автоматаар цуцлах) — шийдвэрийг OPEN_QUESTIONS-д тэмдэглэ.
- `PUT /me/push-token` {token | null} — одоогийн сесс (JWT `sid`) → `set_session_push_token`;
  `DELETE` ижил. Rate limit; token-ыг хэзээ ч логлохгүй; буруу хэлбэр → 422.
- `exponent-server-sdk` нэмэх (`uv add`, лиценз MIT эсэхийг шалга — AGPL/SSPL хориотой, дүрэм 11).
- Celery task (labtrack_maint, beat ~30–60 сек): `maint_push_queue` → Expo руу багцаар (≤100)
  илгээх → `push_receipts`-д ticket → `maint_mark_pushed`. Receipt task (~15 мин дараа):
  `DeviceNotRegistered` → `maint_forget_push_token`; бусад алдааг зөвхөн код (`error` ^[A-Za-z]+$).
  Celery аргументэд зөвхөн ID (дүрэм 3). Давтан ажиллахад давхар push явуулахгүй (idempotent).
- **Payload (security review L3):** харагдах текст ерөнхий, нэргүй, эмгүй, утгагүй (жишээ нь
  «LabTrack: танд шинэ мэдэгдэл байна» / dose_overdue «Эмээ уусан эсэхийг шалгана уу» — эмийн нэр,
  өвчтөний нэр хэзээ ч үгүй); `data`-д зөвхөн `notification_id` + `kind` (patient_id ч хэрэггүй —
  апп нэвтэрсний дараа API-аас авна). Хэрэглэгчийн хэлийг (users.locale) хэрхэн авахыг төлөвлө
  (maint функц өргөтгөх migration 0022 хэрэгтэй эсэх).
- admin_reset (H12): `maint_push_queue` цуцлагдсан төхөөрөмжид ч өгдөг — admin_reset үед
  notifications мөр үүсдэг эсэхийг шалгаж, байхгүй бол нэм (2.8c-тэй нэгтгэж болно — санал болго).
- Тест: Expo client-ийг mock-лох (сүлжээ рүү хэзээ ч гарахгүй), багц, receipt, DeviceNotRegistered,
  credential байхгүй үед no-op, payload-д PHI байхгүй (нэр/эмийн нэр/patient_id орохгүйг шалгах),
  token API (өөрийн сесс, буруу хэлбэр, гарсан сесс).
- Hazard log H12, H16 шинэчлэх; 10c.

## Ажлын хэв маяг
- Алхам бүр: төлөвлөгөө → миний зөвшөөрөл → хэрэгжүүлэх → security-reviewer (+UI-д ui-reviewer,
  эмнэлгийн текстэд medical-reviewer) → засах → (шаардлагатай бол) дахин review → commit → push.
- Commit-ийн автомат security review (plugin) олдвор гаргавал заавал засна эсвэл тайлбарлана.
- Эмнэлгийн тодорхойгүй шийдвэр → AskUserQuestion эсвэл OPEN_QUESTIONS.
- `node_modules` уншихыг хориглосон — сангийн API-г баримтаас (WebFetch) эсвэл tsc алдаанаас.

## Windows-ийн урхи ба сургамж
- uv/just: %LOCALAPPDATA%\Microsoft\WinGet\Links; UV_PYTHON_DOWNLOADS=never.
  Backend тест: `just test-api` (контейнер). Шинэ migration-ий дараа dev DB-д `just migrate`.
  Хэрэгжсэн migration-ийг засвал тестийн DB-д `just reset-test-db`.
- **Bash heredoc-д ишлэл/апостроф эвдэрдэг:** олон мөрийн засварыг Python скрипт болгож
  scratchpad-д Write хэрэгслээр бичээд `python -I script.py "$(pwd)"`-ээр ажиллуул (эсвэл Edit).
  Formatter (hook) файлыг өөрчилдөг тул anchor таарахгүй бол файлыг дахин унш.
- Shell-д `cmd; echo exit=$?` гэвэл бүтэлгүйтэл нуугдана — exit code-оо заавал дамжуул.
- **`backend/src/labtrack/api/health.py` бол /healthz router** — тэр нэрээр файл бүү үүсгэ.
- Аудитын action `^[a-z]+[.][a-z_]+$`. Definer функц нэмбэл `tests/rls/test_function_hardening.py`
  EXECUTE_MATRIX-ийг шинэчил. RLS тестэд алдаа гаргах дуудлагыг тусдаа `as_user` transaction-д
  (abort нь өмнөх бичилтийг rollback хийнэ). caregiver эрхийг `grant()` helper хүлээн авсан урилгаар
  (owner role) үүсгэдэг; шууд оролдлогыг `direct=True`.
- Docker: өөр төслийн контейнерууд (supabase_*) автоматаар асаж RAM эзэлдэг — энэ төслийн
  ажилд `docker stop`-оор зогсоохыг хэрэглэгч зөвшөөрсөн (устгахгүй). Docker engine 500 өгвөл
  `docker desktop restart`. Docker + эмулятор асаалттай Gradle → clang out-of-memory: эмуляторыг
  унтрааж `assembleDebug -PreactNativeArchitectures=x86_64 --max-workers=3`.
- Эмулятор: prebuild `local.properties`-ийг устгавал `sdk.dir`/`cmake.dir` (4.1.2)-ийг дахин бич;
  `just e2e-mobile`-д JAVA_HOME (E:/Android/Android Studio/jbr), Metro-г тусад нь асаана;
  dev build-ийн хөвөгч Tools товч header-ийн баруун буланг таглана; Maestro debug гаралт
  (`E2E_KEEP_DEBUG=1`) түр нууц үгтэй — уншсаны дараа устга.
```
