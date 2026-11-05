# Дараагийн session-д өгөх промпт (Phase 2.7-оос)

> Шинэ Claude Code session нээгээд **Plan mode** (Shift+Tab) асаагаад доорх блокыг бүтнээр нь буулгана.
> Session бүрийн төгсгөлд энэ файлыг (төлөв, сургамж) шинэчилнэ.

```
LabTrack MN төслийн Phase 2.7-г эхлүүлнэ: яаралтай тусламжийн карт.
Надтай монголоор харилц.

## Эхлээд унш (зөвхөн эдгээрийг — токен хэмнэ)
- CLAUDE.md, backend/CLAUDE.md, mobile/CLAUDE.md (автоматаар ачаалагдана)
- docs/PROGRESS.md — Phase 2 хэсэг (2.0–2.6c хийгдсэн, батлагдсан төлөвлөгөө, үлдсэн зүйлс)
- docs/01_PLAN.md — Phase 2 №5 (яаралтай карт)
- docs/08_MOBILE.md — "Яаралтай тусламжийн карт", "Аюулгүй байдал (төхөөрөмж дээр)"
- docs/09_CLINICAL_SAFETY.md — H10, H17, H22, H26, H27
- docs/OPEN_QUESTIONS.md — шийдэгдсэнийг дахин бүү маргалд
- API: packages/shared/openapi.json — /patients/{id}/transplants, /medications,
  /allergies, /contacts (backend/src/labtrack/api/records.py, api/health_records.py)

## Одоогийн төлөв (2026.11.05, салбар phase-2, сүүлийн commit c5db1ba)
- Phase 2 нэг PR-аар: https://github.com/Chuka709/eHealth/pull/1 (draft, base main).
  Алхам бүрийн дараа `git push origin phase-2` (зөвшөөрөгдсөн); main руу шууд push, force push
  хориотой (.claude/settings.json deny + .githooks/pre-push). PR-д Auto-fix асаалттай — CI-г бүү poll хий.
- Хийгдсэн:
  - 2.5 эм, тунгийн түүх, локал сануулга (дараалал, «Уусан»/«10 мин дараа», цагийн бүсийн
    түүх 0017, сарын хураангуй, exact alarm, Maestro урсгал эмулятор дээр давсан);
  - 2.6a migration 0018 (clinical_events, vitals, allergies, emergency_contacts, appointments,
    doctor_questions) + 0019 (үйл явдал/харшил/холбоог зөвхөн эзэн эсвэл бичсэн хүн засна,
    устгана), core/vitals.py (боломжит хязгаар, сахар ммоль/л);
  - 2.6b «Профайл» tab (Нүүр · Эм · Профайл · Тохиргоо), features/health/* дэлгэцүүд;
  - 2.6c товлолын локал сануулга (нэг sync эмийн сануулгатай, 5 слот, нэр/газар — тусдаа
    тохиргоо).
- Тест: backend ~630 (`just test-api`, контейнер), Jest 186, `just lint` цэвэр.

## 2.7-ийн хүрээ (батлагдсан төлөвлөгөө — 01_PLAN Phase 2 №5, 08_MOBILE)
- Яаралтай карт: эрхтэн, шилжүүлэн суулгасан огноо, төв + утас, одоогийн дархлаа
  дарангуйлагч эмүүд (тун нь эмчийн зааврын дагуу — санал болгохгүй), цусны бүлэг, харшил,
  яаралтай холбоо барих хүн. Өгөгдөл одоо байгаа API-аас (шинэ хүснэгт хэрэгтэй эсэхийг шалга).
- Апп-ын эхэнд нэг товшилтоор (Нүүрний дээд буланд 🆘); **түгжээгүй нээх — анхдагч OFF**
  (хэрэглэгчийн шийдвэр 10e; PROGRESS шийдвэр (3): тохиргоо төхөөрөмж дээр, серверт биш),
  onboarding/Тохиргоонд тайлбартайгаар санал болгоно (H17).
- Түрийвчний карт PDF (mn/en) — утсан дээр үүсгэх эсэх, эсвэл backend WeasyPrint (Phase 7-той
  уялдуулах) — төлөвлөгөөнд санал болго.
- Түгжээтэй дэлгэцийн зураг (wallpaper) — галерейд хадгалахгүй байх дүрэм (8) ба
  хэрэглэгч өөрөө хадгалах хоорондын зөрчлийг AskUserQuestion-оор шийдүүл.
- iPhone Medical ID-д апп бичих боломжгүй — гараар нэмэх заавар.
- Офлайнд ажиллана (кэшлэгдсэн өгөгдлөөс), PHI-г лог/URL/мэдэгдэлд оруулахгүй (3).
- Hazard log H17, H22 шинэчлэх; тестээр нотлох (10c).

## Ажлын хэв маяг
- Алхам бүр: төлөвлөгөө → миний зөвшөөрөл → хэрэгжүүлэх → security-reviewer (+UI-д ui-reviewer,
  эмнэлгийн текстэд medical-reviewer) → засах → (шаардлагатай бол) дахин review → commit → push.
- Commit-ийн автомат security review (plugin) олдвор гаргавал заавал засна эсвэл тайлбарлана.
- Эмнэлгийн тодорхойгүй шийдвэр → AskUserQuestion эсвэл OPEN_QUESTIONS.
- `node_modules` уншихыг хориглосон — сангийн API-г баримтаас (WebFetch) эсвэл tsc алдаанаас.

## Windows-ийн урхи ба сургамж
- uv/just: %LOCALAPPDATA%\Microsoft\WinGet\Links; UV_PYTHON_DOWNLOADS=never.
  Backend тест: `just test-api` (контейнер). Шинэ migration-ий дараа dev DB-д `just migrate`.
- **Bash heredoc-д зарим ишлэлтэй агуулга эвдэрдэг:** олон мөрийн засварыг Python скрипт
  болгож scratchpad-д Write хэрэгслээр бичээд `python -I script.py "$(pwd)"`-ээр ажиллуул.
  Formatter (hook) файлыг өөрчилдөг тул скриптийн anchor таарахгүй бол файлыг дахин унш.
- **`backend/src/labtrack/api/health.py` бол /healthz router** — тэр нэрээр файл бүү үүсгэ.
- Аудитын action `^[a-z]+[.][a-z_]+$` (эхний хэсэгт доогуур зураасгүй).
- RNTL v14: `fireEvent.changeText` async — заавал `await`, эс бөгөөс act() давхцаж төлөв алдагдана.
  TextField-ийн алдааны текст тэмдэгттэй эхэлдэг — тестэд regex хэрэглэ.
- Typed routes: шинэ route нэмсний дараа `CI=1 timeout 90 npx expo start --offline --port 8099`.
- expo-notifications: `sound: true` (`"default"` нь Android-д тусгай файл гэж уншигдаж алдаа гаргана).
- Эмулятор: build хийхдээ emulator унтраалттай; prebuild `local.properties`-ийг устгавал
  `sdk.dir`/`cmake.dir` (4.1.2)-ийг дахин бич; дэлгэцийн зураг хар гардаг (screen-capture
  хамгаалалт) — `MSYS_NO_PATHCONV=1 adb shell uiautomator dump`; `just e2e-mobile`-д JAVA_HOME
  (E:/Android/Android Studio/jbr); 8081 дээр хуучин Metro үлдвэл `Stop-Process` + `--clear`;
  API контейнер ENOMEM-ээр унавал `docker restart labtrack-api-1`.
```
