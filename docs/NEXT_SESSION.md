# Дараагийн session-д өгөх промпт (Phase 2.5-аас)

> Шинэ Claude Code session нээгээд **Plan mode** (Shift+Tab) асаагаад доорх блокыг бүтнээр нь буулгана.
> Session бүрийн төгсгөлд энэ файлыг (төлөв, сургамж) шинэчилнэ.

```
LabTrack MN төслийн Phase 2.5-ыг эхлүүлнэ: эм, тунгийн түүх, локал сануулга (апп тал).
Надтай монголоор харилц.

## Эхлээд унш (зөвхөн эдгээрийг — токен хэмнэ)
- CLAUDE.md, backend/CLAUDE.md, mobile/CLAUDE.md (автоматаар ачаалагдана)
- docs/PROGRESS.md — Phase 2 хэсэг (2.0–2.4 хийгдсэн, батлагдсан төлөвлөгөө, үлдсэн зүйлс)
- docs/08_MOBILE.md — "Эм", "Сануулгын найдвартай байдал", "Мэдэгдэл"
- docs/09_CLINICAL_SAFETY.md — H6, H7, H8, H10, H14, H18, H20, H23
- docs/OPEN_QUESTIONS.md — Q16–Q25 (Q22 "local" цагийн бүс энэ алхамд шийдэгдэнэ);
  шийдэгдсэнийг дахин бүү маргалд
- API: packages/shared/openapi.json дахь /patients/{patient_id}/medications, /regimens,
  /regimens/{id}/void, /intakes, /medication-catalog (backend/src/labtrack/api/records.py)

## Одоогийн төлөв (2026.11.04, салбар phase-2, сүүлийн commit 5e231ef)
- Phase 2 нэг PR-аар явна: https://github.com/Chuka709/eHealth/pull/1 (draft, base main).
  Алхам бүрийн дараа `git push origin phase-2` (зөвшөөрөгдсөн); main руу шууд push, force push
  хориотой (.claude/settings.json deny + .githooks/pre-push — core.hooksPath идэвхтэй).
  PR-д Auto-fix асаалттай: CI унавал app сэрээнэ — CI-г бүү poll хий.
- Хийгдсэн: 2.0 /patients + consents gate; 2.1 migration 0014 (transplants, medications,
  regimens append-only, intakes); 2.2 core (medications, timeline) + API, migration 0015
  (цаг тус бүрийн тун `times[].amount`, ирээдүйн буруу тунг void, planned_end_on, нэгжийн
  код, минутын слот), 0016 (taken_by); 2.3 шифрлэлттэй MMKV (account-тай холбоотой),
  query persist (`meta.persist`, mutation хэзээ ч үгүй), offline queue (`client_id`,
  epoch-оор тусгаарласан), wipeLocal (store + түлхүүр + мэдэгдэл), expo-notifications plugin,
  USE_EXACT_ALARM хаагдсан; 2.4 шилжүүлэн суулгалтын wizard/жагсаалт/засах.
- Тест: backend 459 (контейнер, `just test-api`), Jest 127, shared 11, `just lint` цэвэр.
- Tabs хараахан алга (2.5-д Нүүр · Эм · Профайл/Тохиргоо).
- Шинэ native модуль (MMKV, notifications, netinfo, crypto) нэмэгдсэн — төхөөрөмж дээр
  шалгахын тулд шинэ dev build хэрэгтэй (Android: docs/ANDROID_EMULATOR.md).

## 2.5-ын хүрээ (батлагдсан төлөвлөгөө — PROGRESS)
- Эмийн жагсаалт (одоо уудаг / өмнөх; дархлаа дарангуйлагч эхэнд — сервер эрэмбэлнэ),
  нэмэх (каталог хайлт эсвэл гараар → хэлбэр, хүч → цаг бүрийн тун + нэгжийн код → заавар →
  эхэлсэн огноо), тун өөрчлөх (шинэ regimen, огноо заавал, ирээдүйн өөрчлөлт `next_regimen`),
  ирээдүйн буруу өөрчлөлтийг цуцлах, түүх, курсын `planned_end_on`, зогсоох.
- Локал сануулга: цэвэр TS функц — хуваарьлах хоног `min(7, floor(56 / өдрийн_мэдэгдэл))`
  (8 слот товлол/"10 мин дараа"-д), эргэлдүүлэх (апп нээгдэх бүрт), сүүлчийн слотод "апп-аа
  нээнэ үү"; property тест (fast-check хэрэгтэй бол `npx expo install`-оор биш dev dependency).
  Тун хүчин төгөлдөр болох өдрөөс шинэ тунгаар (`next_regimen`), зогссон/дууссан эмд сануулгагүй.
- Нууцлал (H10, 2.3-ын L6): түгжээтэй дэлгэцэнд анхдагчаар эмийн нэргүй ("Эм уух цаг боллоо"),
  `data`-д зөвхөн ID, Android channel `lockscreenVisibility` private, iOS preview placeholder;
  хэрэглэгч нэрийг харуулахаар сонгож болно.
- Цагийн бүс (H7, Q22): `home` — Улаанбаатарын цагаар; төхөөрөмжийн бүс солигдоход асуух;
  `local` горимд хоёр төхөөрөмжийн `scheduled_at` ижил байх аргыг шийдэж Q22-ыг хаах.
- Мэдэгдлийн товч "Уусан" / "10 мин дараа" → intake offline queue-ээр (`client_id`, минутын
  `scheduled_at`); H20-ийн нэгтгэл серверт.
- Android exact alarm (H18): `SCHEDULE_EXACT_ALARM` + тайлбар дэлгэц + inexact fallback +
  Нүүрэнд анхааруулга; мэдэгдлийн зөвшөөрөл унтарсан бол улаан анхааруулга (H6).
  Expo SDK 58-ийн API-г versioned docs-оос шалгах (context7 нэвтрэлтгүй — WebFetch).
- Уусан/алгассан тэмдэглэл, сарын хураангуй (adherence — core/-д, цагийн бүсийн шийдэлтэй хамт);
  тун санал болгохгүй, дүгнэлтгүй (дүрэм 10).
- Tabs навигаци; Maestro урсгал (эм нэмэх → сануулга) — эмулятор дээр.

## Ажлын хэв маяг
- Алхам бүр: төлөвлөгөө → миний зөвшөөрөл → хэрэгжүүлэх → security-reviewer (+UI-д ui-reviewer,
  эмнэлгийн логик/хуваарь/текстэд medical-reviewer) → засах → дахин review → commit → push.
- Эмнэлгийн тодорхойгүй шийдвэр → AskUserQuestion (санал болгох сонголттой) эсвэл OPEN_QUESTIONS.
- Commit-ийн автомат security review (plugin) олдвор гаргавал заавал засна эсвэл тайлбарлана.
- `node_modules` уншихыг хориглосон — сангийн API-г баримтаас (WebFetch) эсвэл tsc алдаанаас.

## Windows-ийн урхи ба сургамж
- uv/just: %LOCALAPPDATA%\Microsoft\WinGet\Links; UV_PYTHON_DOWNLOADS=never; gh:
  "/c/Program Files/GitHub CLI". Backend тест: `just test-api` (контейнер); migration-ийг
  засаад дахин ажиллуулахад тест DB-д хуучин хувилбар үлдвэл `just reset-test-db`.
- Typed routes: шинэ route нэмсний дараа `CI=1 timeout 90 npx expo start --offline --port 8099`
  (`.expo/types/router.d.ts` шинэчлэгдэнэ), дараа нь `pnpm typecheck`.
- Jest: RNTL-д deep link (`initialUrl` "/"-ээс өөр) "/" anchor-оор буцдаг — UI-аар навигац хий;
  query-д 5 мин GC timer үлдвэл Jest гарахгүй — afterEach-д `queryClient.clear()`; MMKV-ийн
  mock jest.setup.ts-д (id тус бүр тусдаа Map); `expo-crypto`, `expo-notifications`, netinfo
  mock jest.setup.ts-д. Бүтэн suite ачаалалтай үед хааяа нэг тест унадаг — дахин ажиллуулж шалга.
- Hypothesis deadline контейнерт унтраалттай (tests/conftest.py).
- Android build: LongPaths, `mobile/android/local.properties`-д `cmake.dir` 4.1.2, Gradle үед
  эмулятор унтраалттай; Maestro: `just e2e-mobile`.
```
