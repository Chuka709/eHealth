# CLAUDE.md — LabTrack MN

**Эрхтэн шилжүүлэн суулгуулсан хүмүүст** зориулсан, **гар утас үндсэн**, хаалттай бүлгийн апп: шилжүүлэн суулгалтын мэдээлэл, байнга уудаг эм (тунгийн түүх, сануулга), эмчилгээ/үйл явдал, шинжилгээний хариу (скан/PDF → AI → хүний хяналт) — нэг цагийн хэлхээс, хандлагын графикт. Хэрэглэгчийг **супер админ бүртгэнэ**, нууц үгийг админ шинэчилнэ. **Эрүүл мэндийн эмзэг өгөгдөл (PHI)** — аюулгүй байдал, нарийвчлал хурднаас чухал.

## Phase → унших docs (бүгдийг биш, хэрэгтэйг л — токен хэмнэнэ)
Эхний удаа (Phase 0 төлөвлөхөд) бүх `docs/`-ыг нэг удаа уншина. Түүнээс хойш:
| Ажил | Унших |
|---|---|
| Phase 0–1 (суурь, auth, админ) | 01 (тухайн phase), 02, 03 (users…consents, RLS), 04 |
| Phase 2 (шилжүүлэн суулгалт, эм, сануулга) | 01, 03 (ШИЛЖҮҮЛЭН СУУЛГАЛТ…ЗӨВШӨӨРӨЛ), 08, 09 |
| Phase 3–5 (оруулах, AI задлалт, review) | 01, 05, 06 §3–4, 08 (Хариу оруулах, Хянах), `seed/*` |
| Phase 6–7 (дашбоард, хуваалцах, PDF) | 01, 06, 08, 09 (H15) |
| Phase 8 (дэлгүүр) | 04 §5, 08 (Дэлгүүрт гаргах), 09 (Release) |
`07_CRITIQUE.md`, `10_RESEARCH.md` — зөвхөн шийдвэрийн шалтгаан хэрэгтэй үед. `11_TOOLING.md` — Claude Code тохиргоо. `_archive/` — хэзээ ч бүү унш (хуучин хувилбар).

## Стек
- **backend/** — Python 3.13, uv, FastAPI, Pydantic v2, SQLAlchemy 2 async + Alembic, Celery + Valkey, pwdlib[argon2], PyJWT (ES256), pdfplumber, pypdfium2, Pillow + pillow-heif, OpenCV, anthropic, rapidfuzz, structlog, exponent-server-sdk, WeasyPrint; pytest + hypothesis + schemathesis (DB тест — compose-ийн `labtrack_test`); Ruff, mypy --strict
- **mobile/** (үндсэн) — Expo SDK 58 + Expo Router, styling: shared token (сан — Q14), TanStack Query, react-hook-form + zod, document-scanner, expo-share-intent, secure-store, local-authentication, notifications, MMKV, @wuba/react-native-echarts, react-native-pdf, use-intl; Jest + RNTL, Maestro
- **web/** (хоёрдогч) — Next.js App Router (BFF auth), shadcn/ui, ECharts, next-intl; Vitest, Playwright
- **packages/shared/** — OpenAPI client, zod, `messages/{mn,en}.json`, design token
- **infra/** — PostgreSQL 17, Valkey (Redis-ийн BSD fork — Redis 7.4+/8 нь RSAL/SSPL/AGPL), S3 нийцтэй storage (SeaweedFS dev), Caddy, Docker Compose

## Харилцах хэл
Хэрэглэгчтэй **монгол хэлээр**. Код, identifier, commit — англиар. UI текст — `packages/shared/messages/mn.json` (үндсэн), `en.json`.

## Командууд (`justfile`, Phase 0-д үүсгэнэ)
```bash
just up              # docker compose up
just dev             # api + worker + web
just mobile          # expo start (dev build)
just test            # pytest + jest + vitest
just test-rls        # RLS тест
just e2e-mobile      # maestro
just lint            # ruff + mypy + biome + tsc
just migrate / seed / create-admin   # seed: lab_tests + medications
just gen-client      # OpenAPI → packages/shared/api
just eval            # задлалтын eval
```

## Хатуу дүрэм
1. **RLS:** PHI хүснэгт бүрт `ENABLE` + `FORCE` + policy + харь хэрэглэгчийн тест. Апп `labtrack_app` role, хүсэлт/task бүрт `set_config('app.user_id', :uid, true)` (bind параметр). DB role, хүснэгт бүрийн policy, definer функцийн `search_path` — `03_DATA_MODEL.md`.
2. **Auth:** өөрөө бүртгүүлэх endpoint БАЙХГҮЙ — хэрэглэгчийг зөвхөн `super_admin` үүсгэнэ. Нууц үг — argon2id, **хэрэглэгч өөрөө тохируулна** (түр нууц үг байхгүй — нэг удаагийн идэвхжүүлэх QR/SMS токен; админ нууц үг хэзээ ч мэдэхгүй); JWT-д `sid` + `token_version` (цуцлалт шууд); refresh/share token — зөвхөн hash; refresh rotation + reuse detection; админ нууц үг шинэчлэхэд бүх сесс цуцлах + шалтгаан + аудит + хэрэглэгчид мэдэгдэх; алдааны мессеж нэр илчлэхгүй.
2a. **Админ PHI харахгүй:** `super_admin`/`support` токеноор шинжилгээ, эм, шилжүүлэн суулгалт, үйл явдлын endpoint 403, RLS-ээр ч хаалттай (тест заавал). Break-glass — 2 админ батлах, аудит.
3. **PHI логлохгүй:** лог, Sentry, Celery аргумент, push payload, алдааны мессежинд нэр/утга/огноо байхгүй. Зөвхөн ID.
4. **AI гаралт = draft.** `confirmed` болоогүй утга дашбоардад орохгүй (критик баннер үл хамаарна).
5. **Лавлах ба критик хязгаар зөвхөн баримтаас** (эсвэл хэрэглэгч гараар, эсвэл эмчийн patient_target). Байхгүй бол `no_reference` — хэзээ ч нөхөхгүй.
6. **Эмнэлгийн логик** зөвхөн `backend/src/labtrack/core/`-д, pytest + hypothesis. Апп, web тооцоолол хийхгүй.
7. **Тоо:** Python `Decimal`, DB `numeric`, JSON string; утга ба хязгаар ижил коэффициентоор.
8. **Төхөөрөмж дээр:** токен → secure-store; кэш/дараалал → шифрлэлттэй MMKV; гарахад бүгдийг устгах; скан зургийг галерейд хадгалахгүй.
9. API type гараар бичихгүй — `just gen-client`.
10. Оношилгоо, эмчилгээний зөвлөмж, **эмийн тун санал болгохгүй**, эмийн харилцан үйлчлэл шалгахгүй (MVP). Эмийн тун өөрчлөхөд хуучин regimen-г засахгүй, шинэ мөр нэмнэ.
10a. Эмийн сануулга — төхөөрөмж дээр локал хуваарь; түгжээтэй дэлгэцэнд анхдагчаар эмийн нэргүй; цагийн бүсийн горим (`home`/`local`).
10b. **Зориулалтын хил** (`09_CLINICAL_SAFETY.md`): цэгцлэх, хадгалах, хянах, хэрэглэгчийн тохируулсан сануулга, хуваалцах. AI чат, AI тайлбар, тун/эмчилгээний санал, харилцан үйлчлэлийн дүгнэлт — хориотой. Такролимус CV% — эмч болон өвчтөнд, босго/өнгө/"сайн-муу" үнэлгээгүй, эмчээр хянуулсан тайлбартай.
10c. Шинэ функц бүрт `09_CLINICAL_SAFETY.md`-ийн hazard log-ийг шинэчилж, хяналт бүрийг тестээр нотолно.
10d. `product_events`-д PHI орохгүй (HMAC user, зөвхөн enum/тоо).
10e. Анхдагч утгууд (хэрэглэгчийн шийдвэр): яаралтай карт түгжээгүй нээх OFF; асран хамгаалагчийн мэдэгдэл 30 мин; бета ба eval — бөөр, элэг. Өгөгдлийн хариуцагч — компани.
11. Загварын нэр, key — env. AGPL/SSPL сан хэрэглэхгүй (PyMuPDF гэх мэт).

## Хэв маяг
- Python: router → service → repository; Pydantic (API) ба SQLAlchemy (DB) model тусдаа; домэйн exception → `{code, message_key}`.
- TS: `any` хориотой, named export; апп-д дэлгэц = route, логик = hooks (`useXxx`), API = shared client.
- Огноо: DB UTC, харуулах `Asia/Ulaanbaatar`. Commit: Conventional Commits.

## Ажлын урсгал
1. Phase эхлэхэд төлөвлөгөө бичиж хэрэглэгчээр батлуулна.
2. Дараалал: migration → repository → core + тест → API + тест → gen-client → апп дэлгэц → Maestro → (шаардлагатай бол) web.
3. Алхам бүрийн дараа `just lint && just test`.
4. Phase дуусахад DoD-г нотолгоотой `docs/PROGRESS.md`-д бичнэ.
5. Эмнэлгийн тодорхойгүй асуудлыг `docs/OPEN_QUESTIONS.md`-д бичиж асууна.
6. Auth/RLS/storage → `security-reviewer`; эмнэлгийн логик/prompt → `medical-reviewer`.

## Claude Code хэрэгсэл ба токен хэмнэлт (дэлгэрэнгүй: `docs/11_TOOLING.md`)
- Agents: `security-reviewer`, `medical-reviewer` (opus), `ui-reviewer` (sonnet). Skill: `phi-table`. Commands: `/phase N`, `/security-check`.
- Код навигаци — LSP (pyright, typescript) эхэлж, дараа нь Grep; том файлыг бүтнээр биш `offset/limit`-ээр унш.
- Олон файлын хайлт/судалгаа → `Explore` subagent (үр дүнг л буцаана). Сан/Expo SDK-ийн API → context7 (таамаглахгүй).
- Phase хооронд `/clear`; урт сессэд `/compact`. Тестийн гаралтыг бүтнээр биш `-q`/`--reporter=dot`, алдааг л харуул.
- Хянагч agent-уудыг зөвхөн `git diff`-ээр ажиллуул — бүх репог бүү уншуул.

## Мэдэгдэж буй урхи
- Хөгжүүлэлтийн машин **Windows**: hook-ууд `node`-оор; `justfile`-д `set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]`; backend тест/worker **контейнер дотор** (WeasyPrint, libmagic); iOS — EAS cloud build + бодит iPhone (симулятор байхгүй); мөрийн төгсгөл LF.
- Android: `USE_EXACT_ALARM` зарлахгүй (Play татгалзана) — `SCHEDULE_EXACT_ALARM` + тайлбар + inexact fallback (`08_MOBILE.md`).
- Шийдэгдсэн асуултууд, шалтгаан: `docs/OPEN_QUESTIONS.md` — дахин бүү маргалд.
- `seed/extraction.schema.json`-ийн `value_numeric` нь float — хадгалах утгыг `core` нь `raw_value`-аас `Decimal`-аар дахин задлана.
- Кирилл/латин ижил хэлбэрийн үсэг; аравтын таслал `12,4`; `03.05.2025` огноо.
- Лавлах хязгаарын олон хэлбэр: "3.5–5.1", "< 5", "Эр: 62–115 / Эм: 44–97".
- HEIC, EXIF эргэлт; SQLAlchemy async-д `set_config(..., true)` transaction дотор, pool-д буцаахад `DISCARD ALL`.
- Шилжүүлэн суулгалтын огноо зөвхөн он/сартай байж болно (`date_precision`) — тооцоолол, харуулалтад анхаар.
- Android 12+ exact alarm зөвшөөрөл, iOS 64 локал мэдэгдлийн хязгаар — сануулгын хуваарийг ойрын хугацаагаар (жишээ нь 7 хоног) эргэлдүүлэн дахин хуваарьлах.
- Expo: native модуль нэмбэл dev build дахин хийх; OTA зөвхөн JS өөрчлөлтөд (`runtimeVersion: fingerprint`).
- iOS share extension, Android intent filter-ийг хоёуланд нь бодит төхөөрөмж дээр турших.
