# Дараагийн session-д өгөх промпт (Phase 8.5-аас)

> Шинэ Claude Code session нээгээд (`/clear`) доорх блокыг бүтнээр нь буулгана.
> Session бүрийн төгсгөлд энэ файлыг (төлөв, сургамж) шинэчилнэ.

```
LabTrack MN төслийн Phase 8.5-ийг хэрэгжүүл: Phase 8 DoD. Төлөвлөгөө баталсан
(docs/PROGRESS.md «Phase 8»). Надтай монголоор харилц. Эхлээд 4–6 мөр төлөвлөгөө өгч батлуул.

## Эхлээд унш (зөвхөн эдгээрийг)
- docs/PROGRESS.md — «Phase 8» (8.4 мөр, «Үлдсэн»)
- docs/STORE_RELEASE.md §5 (release-check, AAB зөвшөөрөл, rollout), docs/BETA.md §1 (B2, B9), §2
- docs/09_CLINICAL_SAFETY.md «Release бүрийн шалгалт»
- docs/ANDROID_EMULATOR.md

## Хийх
1. Локал release build (Expo аккаунтгүй): `APP_VARIANT=production` + https placeholder-оор
   `mobile/android`-д `gradlew assembleRelease` (эсвэл bundleRelease + bundletool) →
   `aapt2 dump permissions` (USE_EXACT_ALARM, SYSTEM_ALERT_WINDOW, RECORD_AUDIO байхгүй);
   `release-manifest.mjs`-тэй тулгах.
2. B9: тэр build-ийг эмулятор дээр Files апп-аас PDF/зураг share хийж шалгах (patch: уншигдахгүй
   URI → «уншиж чадсангүй», апп унахгүй); dev build дээрх Permission Denial дахин гарах эсэх.
3. `just release-check` — legal-аас бусад ногоон; 09-ийн гараар хийх шалгалтуудын нотолгоо
   (medical-reviewer бүх шинэ текст, restore-drill бүртгэл).
4. EAS beta build — компанийн Expo аккаунт (B2) бэлэн бол; үгүй бол BETA §1-д тэмдэглэнэ.
5. Phase 8 DoD нотолгоо PROGRESS-т, commit + `git push origin phase-2`.

## Одоогийн төлөв (2026.11.18, салбар phase-2)
- Phase 0–7, D1–D5b, 8.1–8.4 дууссан. Migration 0048 хүртэл.
- Тест: backend 1384, Jest 327, shared 13, web 21 (+1 LEGAL_RELEASE); release-check legal-аас бусад ногоон.
- Нээлттэй: Q65, Q66 (эмч), Q67 (SIM swap), Q12 (хуульч, эмч), BETA B1–B8, B10 (компани).

## Сургамж
- Jest-ийг Metro/эмулятор эсвэл бүтэн `just test-api` ажиллаж байхад бүү ажиллуул — тестүүд
  timeout-оор хуурамчаар унана.
- `node_modules` унших эрхгүй (тохиргоо): сангийн эхийг `pnpm patch <pkg> --edit-dir <scratchpad>`
  хавтаснаас уншиж засна → `pnpm patch-commit`.
- Python heredoc доторх `\n` бодит мөр таслалт болж кодыг эвддэг — Python файлыг Write/Edit-ээр.
- `just seed-review` — dev-д `just seed-demo`-ийн админ хэрэгтэй; `.env.review` git-д орохгүй.
- `TaskStop` нь Metro-гийн node процессыг зогсоодоггүй — порт эзэлсэн хэвээр (taskkill //F //T //PID).
- Эмулятор: Medium_Phone_API_37.0, `-no-snapshot-load -memory 3072 -gpu swiftshader_indirect
  -feature -Vulkan`; ANR цонхонд «Wait»; dev client-ийн хөвөгч товч header-ийн баруун талыг
  таглана (🆘-ийг x≈800-д товш). JDK: `E:/Android/Android Studio/jbr`.
- `.env`-д шинэ түлхүүр нэмэх: `python scripts/init_env.py` (утгыг хэвлэхгүй).
```
