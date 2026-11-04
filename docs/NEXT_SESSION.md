# Дараагийн session-д өгөх промпт (Phase 2-оос)

> Шинэ Claude Code session нээгээд **Plan mode** (Shift+Tab) асаагаад доорх блокыг бүтнээр нь буулгана.
> Session бүрийн төгсгөлд энэ файлыг (төлөв, сургамж) шинэчилнэ.

```
LabTrack MN төслийн Phase 2-ыг эхлүүлнэ (шилжүүлэн суулгалт, эм, сануулга, амин үзүүлэлт, товлол).
Надтай монголоор харилц.

## Эхлээд унш (зөвхөн эдгээрийг — токен хэмнэ)
- CLAUDE.md, backend/CLAUDE.md, mobile/CLAUDE.md (автоматаар ачаалагдана)
- docs/PROGRESS.md — Phase 1 хэсгийн 1.13 (carry-over жагсаалт), Phase 2
- docs/01_PLAN.md — Phase 2
- docs/03_DATA_MODEL.md — ШИЛЖҮҮЛЭН СУУЛГАЛТ … ЗӨВШӨӨРӨЛ
- docs/08_MOBILE.md, docs/09_CLINICAL_SAFETY.md (H6–H10, hazard log)
- docs/OPEN_QUESTIONS.md — шийдэгдсэнийг дахин бүү маргалд

## Одоогийн төлөв (2026.11.04, сүүлийн commit 7628083)
- Phase 1 дууссан: migration 0001–0012; backend 330 тест (контейнер), RLS 141, Jest 104,
  web 7, shared 11; `just lint` цэвэр; Maestro `activation.yaml` Android эмулятор дээр давсан.
- Push хийгдээгүй (GitHub репо — та). Бодит iPhone, GitHub CI хойшлогдсон.
- Ерөнхий хамгаалалтын тестүүд (`tests/rls/test_function_hardening.py`): шинэ хүснэгт заавал
  ENABLE+FORCE RLS, definer функц бүр нэг signature, role бүрийн EXECUTE matrix snapshot —
  Phase 2-ын migration бүрт snapshot-ийг санаатай шинэчилнэ. Админ токен хэрэглэгчийн бүх замд
  401 (OpenAPI-аас ерөнхий тест — шинэ PHI route автоматаар хамрагдана).

## Phase 2-т заавал (Phase 1-ээс шилжсэн)
- `consents.require()` gate — PHI route бүр (DoD).
- `wipeLocal` — MMKV болон локал сануулгыг гарахад устгах (MMKV нэмэх commit-ийн DoD).
- Нууц үг солигдсоныг бусад төхөөрөмжид push-ээр мэдэгдэх.
- Бусад carry-over — PROGRESS 1.13.

## Ажлын хэв маяг
- Алхам бүр: төлөвлөгөө → миний зөвшөөрөл → хэрэгжүүлэх → security-reviewer (+UI-д ui-reviewer,
  эмнэлгийн логикт medical-reviewer) → засах → commit.
- Шинэ PHI хүснэгт → `phi-table` skill.

## Windows-ийн урхи
- uv/just: %LOCALAPPDATA%\Microsoft\WinGet\Links; UV_PYTHON_DOWNLOADS=never. Backend тест: `just test-api`
  (контейнер). Тест DB бохирдвол `just reset-test-db`.
- Android build: LongPaths асаалттай, `mobile/android/local.properties`-д `cmake.dir` 4.1.2
  (`expo prebuild --clean` устгадаг — дахин бич), Gradle ажиллах үед эмулятор унтраалттай
  (paging file C: дээр). Эмулятор: `emulator -avd Pixel_API36 -no-snapshot`. Дэлгэрэнгүй:
  docs/ANDROID_EMULATOR.md. Maestro: `just e2e-mobile` (Metro `npx expo start --dev-client`).
- Jest suite-үүд module state хуваалцана (queryClient, session store) — beforeEach-д reset.
  RNTL тестэд Date.now-г бүү freeze хий — clock inject (lockClock).
```
