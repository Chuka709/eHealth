# Дараагийн session-д өгөх промпт (Phase 8.4-өөс)

> Шинэ Claude Code session нээгээд (`/clear`) доорх блокыг бүтнээр нь буулгана.
> Session бүрийн төгсгөлд энэ файлыг (төлөв, сургамж) шинэчилнэ.

```
LabTrack MN төслийн Phase 8.4-ийг хэрэгжүүл: дэлгүүрийн бэлтгэл. Төлөвлөгөө баталсан
(docs/PROGRESS.md «Phase 8»). Надтай монголоор харилц. Эхлээд 4–6 мөр төлөвлөгөө өгч батлуул.

## Эхлээд унш (зөвхөн эдгээрийг)
- docs/PROGRESS.md — «Phase 8» (8.1–8.3 мөр, тэдний «Үлдсэн»)
- docs/BETA.md (B9 share intent, §2 build, §3 declaration), docs/08_MOBILE.md «Дэлгүүрт гаргах»
- docs/09_CLINICAL_SAFETY.md «Release бүрийн шалгалт»; docs/OPS_RUNBOOK.md §5.6 (дахин устгах)
- mobile/app.config.ts, eas.json, src/app-config.test.ts

## Хийх
1. B9: expo-share-intent-ийн Permission Denial / CursorIndexOutOfBounds (patch эсвэл шинэ хувилбар).
2. Дэлгүүрийн тайлбар (mn/en), Data safety + Health apps declaration ноорог, review-ийн
   зохиомол аккаунт + жишээ баримт, staged rollout (10→50→100%) журам.
3. `just release-check`: LEGAL_RELEASE=1 web тест, release manifest (app.config introspect),
   хамаарлын скан (pip-audit, pnpm audit) CI-д, hazard/eval шалгалт.
4. Дахин устгах скрипт (OPS_RUNBOOK §5.6: логийн user_id-аар).
5. Хянагчид, PROGRESS 8.4, commit + `git push origin phase-2`.

## Одоогийн төлөв (2026.11.18, салбар phase-2)
- Phase 0–7, D1–D5b, 8.1 (f8f6e2e), 8.2 (04e38a7), 8.3 (8fab48a) дууссан. Migration 0048 хүртэл.
- Тест: backend 1376, Jest 321, shared 13, web 21 (+1 LEGAL_RELEASE); fuzz 8983+8162; load 50 хэрэглэгч алдаагүй.
- Нээлттэй: Q65, Q66 (эмч), Q67 (SIM swap), Q12 (хуульч, эмч), BETA B1–B10 (компани).

## Сургамж
- Jest-ийг Metro/эмулятор ажиллаж байхад бүү ажиллуул — олон тест хуурамчаар унана.
- `TaskStop` нь Metro-гийн node процессыг зогсоодоггүй — порт эзэлсэн хэвээр (taskkill //F //T //PID).
- Эмулятор: Medium_Phone_API_37.0, `-no-snapshot-load -memory 3072 -gpu swiftshader_indirect
  -feature -Vulkan`; ANR цонхонд «Wait»; dev client-ийн хөвөгч товч header-ийн баруун талыг
  таглана (🆘-ийг x≈800-д товш).
- Backup: `just backup` / `just restore-drill <identity>`; dev-д туршилтын түлхүүрийг
  scratchpad-д үүсгэж `-e BACKUP_AGE_RECIPIENT=` дамжуулна (.env-д бичихгүй).
- `just load-test` / `just fuzz-api` — dev stack дээр; Windows-д `127.0.0.1` (localhost ::1 → 2 с).
- `.env`-д шинэ түлхүүр нэмэх: `python scripts/init_env.py` (утгыг хэвлэхгүй); Valkey ACL өөрчлөхөд
  valkey-г дараа нь бүх worker-ийг `--force-recreate`.
```
