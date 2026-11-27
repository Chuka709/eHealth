# Дараагийн session-д өгөх промпт (бодит утасны шалгалтын үргэлжлэл)

> Шинэ Claude Code session нээгээд (`/clear`) доорх блокыг бүтнээр нь буулгана.
> Session бүрийн төгсгөлд энэ файлыг (төлөв, сургамж) шинэчилнэ.

```
LabTrack MN: бодит утасны (B6) шалгалтыг үргэлжлүүл. Надтай монголоор харилц.
Эхлээд 4–6 мөр төлөвлөгөө өгч батлуул.

## Эхлээд унш (зөвхөн эдгээрийг)
- docs/DEVICE_TEST.md — «Урсгалууд» хүснэгт, 2026.11.25-ны «Олдвор» (1–11)
- docs/09_CLINICAL_SAFETY.md — зөвхөн H6, H40 мөр

## Хийх
(2026.11.27 хийгдсэн: сэрүүлэг — нэг тунгийн цагт нэг мэдэгдэл эмийн нэртэй, сэрүүлгийн бүтэн
дэлгэц түгжээтэй утсанд, Xiaomi «Түгжээтэй дэлгэцэнд харуулах» товч — DEVICE_TEST 15–16, POCO дээр
шалгасан. Туршилтын эмүүдийг цэвэрлэсэн.)
1. Урсгалууд POCO X3 NFC (MIUI 14) дээр: F2 скан (камер, галерейд хадгалахгүй), F4 Viber/
   Messenger/Files-аас share, F5 офлайн нэмэх (файл/бичлэг), F6 яаралтай карт (түгжээтэй
   дэлгэц, wallpaper, PDF share), F7 гарахад cache/дараалал цэвэрлэгдэх
   (`adb shell run-as mn.munkhly.labtrack.development ls cache files`).
2. Үлдсэн сануулга: R6 батарей хэмнэлт асаалттай, R11 (боломжтой бол). Чимээгүй горим —
   Q79 сэрүүлгээр шийдсэн (Android; iOS — Critical Alerts, компанийн шийдвэр). F2-ийн суурь: галерейн
   сүүлийн зураг _id=1000015228 (`content query --uri content://media/external/images/media`).
3. Олдсон алдааг засах (тест + хянагч), DEVICE_TEST.md-д бүртгэх, commit + push.
4. Q24 шалгалтын үеийн хүлээлтийн төлөв хийгдсэн — утсан дээр нэг удаа харах (интернэт удаан үед «шалгаж байна…»).

## Одоогийн төлөв (2026.11.27, салбар phase-2, 0d81311)
- R1–R4, R7–R10, R12 ✅; R5 ◐ (MIUI deep Doze adb-ээр орохгүй).
- Q79 сэрүүлэг: `mobile/modules/dose-alarm` — expo сануулгыг өөрийн мэдэгдэл болгон авч (нэг
  мэдэгдэл), 60 с дуугарч буцаана; full-screen intent → `DoseAlarmActivity` (түгжээтэй утсанд,
  FLAG_SECURE, нэрийг түгжээтэй дэлгэцийн бүх давхарга зөвшөөрвөл л). Утсан дээрх APK = e5ffce8.
- MIUI: «Түгжээтэй дэлгэцэнд харуулах» (MIUIOP 10020) шинэ апп-д унтраалттай — үгүй бол сэрүүлгийн
  дэлгэц түгжээний ард үлдэнэ; Тохиргоо → Сануулга-д товч бий. APK дахин суулгавал дахин асаана.
- Release-ийн өмнө: Play FGS (`systemExempted`) ба USE_FULL_SCREEN_INTENT declaration (STORE_RELEASE).
- Тест: mobile Jest 380, backend 1384.

## Бодит утасны тохиргоо (POCO X3 NFC, Android 12, MIUI 14)
- adb serial `8f2c0cf9`; dev APK `dist/labtrack-dev-arm64.apk` (e5ffce8, 11.27) суусан.
- APK дахин суулгавал MIUI Autostart/Battery saver тохиргоо арилна — хэрэглэгчээр асаалгана.
- `adb reverse tcp:8081 tcp:8081` ба `tcp:8080 tcp:8080`; Metro — `.claude/launch.json`
  `metro-emulator` (preview_start); апп нээх:
  `adb shell am start -a android.intent.action.VIEW -d "exp+labtrack://expo-development-client/?url=http%3A%2F%2Flocalhost%3A8081"`.
- Туршилтын сануулга: `cd backend && uv run python scripts/test_reminder.py 4 8`, дараа нь
  апп-ыг Home → урд гаргах (сүүлийн татлагаас 30 с өнгөрсөн байх ёстой — RESUME_STALE_MS).
- Нэвтрэх: demo_kidney, нууц үг `.env.demo`-оос (хэвлэхгүй, `input text`-ээр).

## Сургамж
- Утасны цаг PC-ээс ~40 с хоцорно — `adb shell date` ашигла.
- Офлайн турших: нислэгийн горим + `docker stop labtrack-caddy-1` (`adb reverse --remove`
  нээлттэй keep-alive холболтыг тасалдаггүй); дараа нь `docker start`, airplane off.
- Цагийн бүс: `settings put global auto_time_zone 0` + `service call alarm 3 s16 Asia/Tokyo`;
  буцааж `Asia/Ulaanbaatar` + `auto_time_zone 1`.
- MIUI мэдэгдлийг adb-ээр дэлгэх боломжгүй — мэдэгдлийн товчийг хэрэглэгч дарна.
- Ар талд түр лог хэрэгтэй бол `console.log` → Metro `preview_logs` (commit-оос өмнө устга).
- Native build-ийн өмнө Docker зогсоо; Metro CI горимд өөрчлөлт харахгүй — preview_stop/start.
- Jest-ийг Metro ажиллаж байхад бүү ажиллуул; `adb` гацвал `taskkill //F //IM adb.exe`.
- adb daemon дахин эхлэхэд `adb reverse` арилна (апп «Сервертэй холбогдож чадсангүй») — 8080, 8081-ийг дахин.
- `test_reminder.py` ажиллуулах бүрт шинэ «Туршилтын эм» үүсгэнэ — дараа нь DELETE `/patients/{id}/medications/{id}`-ээр цэвэрлэ.
- Сэрүүлгийн дэлгэц FLAG_SECURE тул uiautomator/screenshot хоосон — хэрэглэгчээс нүдээр асуу.
```
