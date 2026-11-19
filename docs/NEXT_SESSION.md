# Дараагийн session-д өгөх промпт (бодит утасны шалгалтын үргэлжлэл)

> Шинэ Claude Code session нээгээд (`/clear`) доорх блокыг бүтнээр нь буулгана.
> Session бүрийн төгсгөлд энэ файлыг (төлөв, сургамж) шинэчилнэ.

```
LabTrack MN: бодит утасны (B6) шалгалтыг үргэлжлүүл. Надтай монголоор харилц.
Эхлээд 4–6 мөр төлөвлөгөө өгч батлуул.

## Эхлээд унш (зөвхөн эдгээрийг)
- docs/DEVICE_TEST.md — бүхэлд нь (жагсаалт, 2026.11.19-ний үр дүн, олдвор)
- docs/09_CLINICAL_SAFETY.md — зөвхөн H6, H18, H40 мөр
- docs/ANDROID_EMULATOR.md «Б. Локал build» хэсэг

## Хийх
1. Үлдсэн сануулгын тохиолдлууд POCO X3 NFC (MIUI 14) дээр: R5 Doze
   (`dumpsys deviceidle force-idle`), R6 батарей хэмнэлт, R7 exact alarm зөвшөөрөлгүй
   (давталт гарахгүй, «хоцорч болно» анхааруулга), R8 нислэгийн горим (офлайн «Уусан» дараалал),
   R9 цагийн бүс (home/local), R10 мэдэгдлийн «Уусан»/«10 мин дараа» (апп хаалттай үед — давталт
   ба tray-ийн бүх хуулбар арилах), R12 дахин товлолтын дараа давхар alarm байхгүй, чимээгүй
   горим (0) дахь чанга суваг.
2. Урсгалууд F2 скан (камер), F4 Viber/Messenger-ээс share, F5 офлайн, F6 яаралтай карт,
   F7 гарахад cache цэвэрлэгдэх.
3. Олдсон алдааг засах (тест + хянагч), DEVICE_TEST.md-д бүртгэх, commit + push.
4. Боломжтой бол: cold start-ийн эхний синк бүгдийг дахин товлодог тул шинэ эм ~2 мин хоцорч
   орно — нэмэгдсэн/өөрчлөгдсөн өгөгдлийг renew-ээс түрүүлж товлох (H6 үлдэгдэл).

## Одоогийн төлөв (2026.11.19, салбар phase-2, сүүлийн commit 9385382)
- Phase 0–8 код талаас дууссан; бодит утсан дээр R1–R4 ✅, 3 бодит алдаа засагдсан
  (синкийн хурд, өөр газраас нэмсэн эм, MIUI autostart), чанга суваг + 15 минутын давталт
  (хэрэглэгчийн шийдвэр) — энгийн горимд дуугарсан, MIUI чичиргээний горимд зөвхөн чичирдэг.
- eGFR/MELD: Q68–Q77 шийдсэн (одоо тооцохгүй; лабын eGFR «eGFR (лабын хариу)», хариун дээрх
  нэр хандлагын графикт).
- Тест: backend 1384, mobile Jest 342, web 21, shared 13.
- Нээлттэй: Q78 (давталтын текст — эмч), Q65, Q66, Q67, Q12, BETA B1–B8, B10 (компани),
  iPhone огт туршаагүй (iOS 64-ийн хязгаар, дуу).

## Бодит утасны тохиргоо (POCO X3 NFC, Android 12, MIUI 14)
- adb serial `8f2c0cf9`; USB debugging + «USB debugging (Security settings)» асаалттай;
  Background autostart LabTrack-д асаалттай, Battery saver → No restrictions.
- `adb install` MIUI-д хаагддаг → APK-г хэрэглэгч өөрөө хуулж суулгана:
  `F:\My Projects\eHealth\dist\labtrack-dev-arm64.apk` (одоо суусан хувилбар чанга сувагтай).
- Холболт: `adb reverse tcp:8081 tcp:8081` ба `tcp:8080 tcp:8080` (утас дахин асахад алга
  болно); Metro — `.claude/launch.json` `metro-emulator` (preview_start); апп нээх:
  `adb shell am start -a android.intent.action.VIEW -d "exp+labtrack://expo-development-client/?url=http%3A%2F%2Flocalhost%3A8081"`.
- Туршилтын сануулга: `cd backend && uv run python scripts/test_reminder.py 4 8` (одооноос
  +4, +8 мин), дараа нь апп-ыг урд гаргах/дахин эхлүүлэх; шалгах:
  `adb shell dumpsys alarm | grep labtrack`, `dumpsys notification --noredact`.
- MIUI-д `uiautomator dump` ажиллахгүй — `exec-out screencap -p` + `input tap x y`.
- Нэвтрэх: demo_kidney, нууц үг `.env.demo`-оос (хэвлэхгүй, `input text`-ээр).

## Сургамж
- Утас дэлгэц унтарсан/түгжээтэй үед апп синк хийхгүй — хэмжилтийн өмнө хэрэглэгчээр дэлгэцийг
  нээлгэнэ (Settings → Display → Sleep 10 мин).
- Native build-ийн өмнө Docker-оо зогсоо (`docker compose ... stop`), эс бөгөөс clang
  «out of memory»; `expo prebuild` нь `mobile/android/local.properties`-ийг устгадаг —
  `dist/mobile-release/android/local.properties`-оос (CMake 4.1.2) хуулж, `app/.cxx` устгана.
- Metro CI горимд кодын өөрчлөлтийг харахгүй — засварын дараа preview_stop/preview_start.
- `adb` гацвал `taskkill //F //IM adb.exe`; foreground `sleep` хориотой — `timeout N tail -f /dev/null`.
- Expo SDK 58 `File.copy/move/write` async — заавал await.
- Python heredoc доторх `\n` бодит мөр таслалт болдог — код засварыг Write/Edit-ээр.
- Jest-ийг Metro/эмулятор эсвэл бүтэн `just test-api` ажиллаж байхад бүү ажиллуул.
```
