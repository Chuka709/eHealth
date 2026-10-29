# Дараагийн session-д өгөх промпт (Phase 1.11-ээс)

> Шинэ Claude Code session нээгээд **Plan mode** (Shift+Tab) асаагаад доорх блокыг бүтнээр нь буулгана.
> Session бүрийн төгсгөлд энэ файлыг (төлөв, сургамж) шинэчилнэ.

```
LabTrack MN төслийн Phase 1-ийг үргэлжлүүлнэ (1.11 — апп дэлгэцүүд). Надтай монголоор харилц.

## Эхлээд унш (зөвхөн эдгээрийг — токен хэмнэ)
- CLAUDE.md, mobile/CLAUDE.md (автоматаар ачаалагдана)
- docs/PROGRESS.md — Phase 1 хэсэг (1.1–1.10 хийгдсэн, review-ийн тэмдэглэлүүд), 1.11–1.13
- docs/OPEN_QUESTIONS.md — шийдэгдсэн (дахин маргалдахгүй; Q14 styling), нээлттэй Q10–Q13, Q15
- docs/08_MOBILE.md (onboarding, secure-store, MMKV, privacy overlay, биометр)
- docs/04_RBAC_SECURITY.md §1 (Нэвтрэх, Биометр, Нууц үг мартсан 5-р алхам, Хэрэглэгчийн
  тохиргоо), §6.8 (төхөөрөмж)
- packages/shared/src/api/schema.d.ts — зөвхөн /api/v1/auth/* ба /api/v1/me/* хэсэг (grep-ээр)
- packages/shared/messages/mn.json — `error.*`, `admin.*` бүтэц (апп-ын текстийг `app.*`-д нэм)
- mobile/src/ (одоогийн бүтэц: lib/api.ts, төлөвийн дэлгэц, тест)
- web/src/app/admin/** — BFF-ийн хэв маяг, алдааны кодын орчуулга (`error.<code>`) жишээ

## Одоогийн төлөв (2026.10.29, сүүлийн commit ac641eb)
- Phase 0 код бүрэн; төхөөрөмж/CI-ийн 3 DoD (Android эмулятор, бодит iPhone, GitHub CI)
  хэрэглэгчийн шийдвэрээр хойшлогдсон.
- Phase 1: 1.1–1.10 хийгдсэн. Migration 0001–0008. Backend 312 тест (контейнер) ногоон,
  web e2e (Playwright, `just e2e-web`) 2/2. Үе шат бүрт security-reviewer (+UI-д ui-reviewer)
  — бүх олдвор засагдсан. Push хийгдээгүй.
- Апп ашиглах API (бүгд бэлэн, OpenAPI-д): `POST /auth/activate {token, new_password}`,
  `/auth/login {username,password,platform,device_name?,device_token?}` → access(15 мин)
  + refresh(60 хоног, rotation) + device_token (итгэмжлэгдсэн төхөөрөмж), `/auth/refresh`
  (401 `auth.admin_reset` → "админ сэргээсэн" дэлгэц), `/auth/logout`, `/auth/password`,
  `/auth/sessions` (+DELETE), `GET/PATCH /me`, `GET/POST /me/consents` (заавал: terms,
  privacy, sensitive_data; сонголт: ai_processing+cross_border; хувилбар `draft-2026-10`),
  `/me/admin-actions`, `/me/notifications` (+`/{id}/read`), `/me/report-unwanted-admin-action`
  ("Би хүсээгүй"), `POST /me/delete {password}` → 202.
- Идэвхжүүлэх линк: `labtrack://activate#<token>` (fragment — логт орохгүй); QR ч мөн энэ.
- Алдаа: `{code, message_key}`; бүх код `packages/shared/error-codes.json`-д, mn/en текст бэлэн
  (`error.<code>`; нууц үгийн бодлого `error.password.*`). Нэвтрэх алдаа нэг л янз.

## Дараагийн ажил — 1.11 → 1.13
1.11 Апп (Expo SDK 58; styling = shared token + StyleSheet + @expo/ui, Q14; Tailwind-гүй):
  welcome, идэвхжүүлэх (QR уншуулах / deep link `labtrack://activate#…` → нууц үг + хүчтэй
  байдлын заагч; серверийн дүрэм: ≥ 10, zxcvbn ≥ 3, нэр агуулахгүй), login (device_token-ийг
  secure-store-д), `admin_reset` мэдэгдлийн дэлгэц, зөвшөөрлүүд (onboarding, хувилбар),
  биометр санал + түгжээ (5 мин background), "нууц үгээ мартсан" (админтай холбогдох
  мэдээлэл), профайл, тохиргоо (төхөөрөмжүүд, нууц үг солих, админы түүх + "Би хүсээгүй",
  аккаунт устгах), secure-store (`WHEN_UNLOCKED_THIS_DEVICE_ONLY`), refresh single-flight
  (+ сервер талын 20 сек grace), гарахад бүх кэш/токен устгах, privacy overlay
  (app switcher), дэлгэцийн зураг хамгаалалт шаардлагатай эсэх.
1.12 Тест: RNTL (дэлгэц бүр), Maestro идэвхжүүлэх урсгал (эмулятор хойшлогдсон — flow-г
  бичээд ажиллуулахыг тэмдэглэ), docs/04 §6-ийн жагсаалтаас үлдсэн RLS/auth тестүүд.
1.13 security-reviewer + ui-reviewer; PROGRESS/OPEN_QUESTIONS; Phase 1 DoD нотолгоо.

## Ажиллах журам
- Алхам бүрийн өмнө товч төлөвлөгөө → миний зөвшөөрөл → хэрэгжүүлэх → тест → commit.
- Алхам бүрийн дараа `security-reviewer` (токен/кэш/auth), UI дээр `ui-reviewer`.
- Expo/сангийн API-г таамаглахгүй — expo skill-үүд (expo-overview → expo-router, expo-ui
  г.м.) эсвэл баримт. Native модуль нэмбэл dev build дахин хийх шаардлагатайг тэмдэглэ.
- API type гараар бичихгүй — `just gen-client` (backend өөрчлөгдвөл).

## Орчны онцлог (Windows) — заавал
- uv/just PATH: `export PATH="/c/Users/PC/AppData/Local/Microsoft/WinGet/Links:$PATH"`,
  `UV_PYTHON_DOWNLOADS=never` (систем Python 3.13). pnpm-ийг `pnpm.cmd`-ээр.
- **C: диск бараг дүүрэн (~234 MB)** — том татан авалтыг F:-д хий. Playwright браузер
  repo-ийн `.playwright-browsers`-д (`just e2e-web` тохируулсан). Docker C: дээр — build удаан.
- Backend тест контейнерт: `just test-api`; шинэ Python dependency бол `docker compose ... build api`.
  Web өөрчлөлтийг e2e-д харахын тулд `docker compose ... build web && up -d web`.
- Dev stack: `just up`; админ: `just create-admin <нэр>` (TOTP), `just unlock-admin <нэр>`.
- Хэрэглэсэн migration-ыг засвал (deploy хийгдээгүй тул зөвшөөрөгдөнө) dev/test DB-г дахин
  үүсгэ: postgres-д `drop database labtrack with (force)` → `create database labtrack owner
  labtrack_owner` → `revoke all … from public` → `grant connect … to labtrack_app,
  labtrack_admin, labtrack_admin_login, labtrack_maint` → `run --rm migrate` → `… cli seed`.
- `.env`-г уншиж болохгүй; шинэ нууц бол `.env.example` + `just init` (дутуу түлхүүрийг нэмнэ).
- bash heredoc дотор урт Python заримдаа "unexpected EOF" өгдөг — скриптийг scratchpad-д
  бичиж ажиллуул.

## Өмнө нь гарсан урхи (давтахгүй)
- FastAPI-ийн DB dependency `Depends(..., scope="function")` байх ёстой — эс бөгөөс commit
  хариуны ДАРАА хийгдэж шинэ сесс/токен клиентэд эрт очдог (e2e илрүүлсэн; тесттэй).
- Migration-ы f-string-д SQL quantifier `{{1,40}}`; `revoke execute on all functions in schema
  public from public` migration бүрт; RLS FORCE → owner-д ч policy; definer функц
  `search_path = pg_catalog, public, pg_temp`. Өмнөх функцийг өөрчлөхдөө анхны текстийг
  ачаалж `_patched(...)`-аар (0007/0008-ийн хэв маяг).
- Аудитын "хамгийн сүүлийн мөр"-өөс аюулгүй байдлын төлөв гаргахгүй — байнгын багана
  (`users.reset_required` жишээ).
- Next 16: `cacheComponents`/PPR унтраалттай (nonce CSP); server action-д `redirect()` хийвэл
  дараагийн хуудас тэр хариунд рендерлэгдэж шинэ cookie-г харахгүй — клиент талаас шилжих;
  `__Host-` cookie-г ижил attribute-тайгаар л устгана; хуудас render хийх үед cookie өөрчлөхгүй.
- RNTL v14: `await render(...)`, `await fireEvent...`; openapi-fetch-ийн fetch-ийг late-bind.
- Hypothesis бодит алдаа олдог — core функц бүрт property тест.

## Нээлттэй (хийхээр төлөвлөсөн)
HIBP top-N нууц үгийн жагсаалт · timing статистик тест · SeaweedFS JWT signing (Phase 3-аас
өмнө) · production Postgres параметр лог унтраах · OpenBao KeyProvider ба хэрэглэгчийн
түлхүүр (production-аас өмнө) · админыг тусдаа host (`admin.`) · SMS (Q13: SmsSender бэлэн)
· Q10 bundle ID, Q11 hosting, Q12 хуульч/эмч (зөвшөөрлийн текст draft), Q15 устгасан
аккаунтын зөвшөөрлийн бичлэг.

Эхлэх: дээрх файлуудыг уншаад 1.11-ийн алхамчилсан төлөвлөгөөг (дэлгэцүүд, навигаци,
token/кэш хадгалалт, шинэ native модуль ба dev build хэрэгтэй эсэх, тест) гарга, миний
зөвшөөрлийг хүлээ.
```
