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
0. **Эхлээд v7 Q79 сэрүүлгийн богино шалгалт** (DEVICE_TEST 13): утас чимээгүйд,
   `test_reminder.py 3` → цагтаа дуугарах, heads-up-д «Дууг унтраах» + тайлбар, «Уусан»/апп
   нээхэд зогсох, «10 мин дараа» дахин сэрүүлгээр дуугарах. Дараа нь утсыг энгийн горимд буцаа.
1. Урсгалууд POCO X3 NFC (MIUI 14) дээр: F2 скан (камер, галерейд хадгалахгүй), F4 Viber/
   Messenger/Files-аас share, F5 офлайн нэмэх (файл/бичлэг), F6 яаралтай карт (түгжээтэй
   дэлгэц, wallpaper, PDF share), F7 гарахад cache/дараалал цэвэрлэгдэх
   (`adb shell run-as mn.munkhly.labtrack.development ls cache files`).
2. Үлдсэн сануулга: R6 батарей хэмнэлт асаалттай, R11 (боломжтой бол). Чимээгүй горим —
   Q79 сэрүүлгээр шийдсэн (Android; iOS — Critical Alerts, компанийн шийдвэр). F2-ийн суурь: галерейн
   сүүлийн зураг _id=1000015228 (`content query --uri content://media/external/images/media`).
3. Олдсон алдааг засах (тест + хянагч), DEVICE_TEST.md-д бүртгэх, commit + push.
4. Боломжтой бол: Q24 шалгалтын үеийн (0–8 с) хүлээлтийн төлөв — ui-reviewer.

## Одоогийн төлөв (2026.11.25, салбар phase-2, Q79 сэрүүлэг commit хийгдсэн)
- R1–R4 (11.19), R5 ◐ (MIUI deep Doze adb-ээр орохгүй), R7, R8, R9, R10, R12 ✅ (11.25).
- 11.25-ны засварууд: e785e72 expo-notifications foreground broadcast patch
  (`patches/expo-notifications.patch` + `mobile/package.json` buildFromSource — үгүй бол
  patch build-д орохгүй): синк 51 сануулга 0.7 с, хүргэлт <1 с; 4c28c24 офлайн дараалал 30 с,
  Q24 шалгалт 8 с (дараа нь асууна), refresh 20 с timeout; тэмдэглэсэн тунгийн сануулга
  tray-ээс арилна.
- Q11: Supabase руу шилжихийг цуцалсан (11.25) — одоогийн стек (Postgres, Celery + Valkey,
  S3, Caddy) хэвээр; production-ийн байршил нээлттэй.
- Q79: `mobile/modules/dose-alarm` (local Expo module, `setAlarmClock` + mediaPlayback FGS,
  USAGE_ALARM, 60 с, `FLAG_RECEIVER_FOREGROUND`); v7 APK утсанд суусан (`dist/labtrack-dev-arm64.apk`).
  Release-ийн өмнө: Play FGS declaration, Android 14+ `systemExempted` (STORE_RELEASE §5).
- Тест: mobile Jest 359, backend 1384.

## Бодит утасны тохиргоо (POCO X3 NFC, Android 12, MIUI 14)
- adb serial `8f2c0cf9`; dev APK `dist/labtrack-dev-arm64.apk` (patch-тай, 11.25) суусан.
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
```
