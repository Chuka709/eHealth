# Дараагийн session-д өгөх промпт (Phase 8 код талаас дууссаны дараа)

> Шинэ Claude Code session нээгээд (`/clear`) доорх блокыг бүтнээр нь буулгана.
> Session бүрийн төгсгөлд энэ файлыг (төлөв, сургамж) шинэчилнэ.

```
LabTrack MN төсөл: Phase 8 код талаас дууссан (8.1–8.5). Надтай монголоор харилц.
Эхлээд юуг хийхийг надаас асуу (доорх хоёрын аль нэг), дараа нь 4–6 мөр төлөвлөгөө батлуул.

А. Компанийн блокер бэлэн болсон бол: B2 Expo аккаунт → `eas init`, `eas build --profile beta`,
   AAB-ийн зөвшөөрлийг STORE_RELEASE.md §5-аар; B1 https сервер → `just seed-review https://…`,
   Play Console маягт (STORE_RELEASE.md §1–4); legal `[...]` бөглөгдсөн бол `just release-check` бүтэн ногоон.
Б. Phase 9 төлөвлөлт (docs/01_PLAN.md «Phase 9+»): өргөтгөлүүдээс эхнийхийг сонгож,
   эрсдэл/зохицуулалтын үнэлгээтэй хамт төлөвлөнө.

## Эхлээд унш (зөвхөн эдгээрийг)
- docs/PROGRESS.md — «Phase 8» (8.4, 8.5 мөр)
- docs/BETA.md §1 (B1–B10 төлөв), docs/STORE_RELEASE.md (А бол)
- docs/01_PLAN.md «Phase 9+» (Б бол)

## Одоогийн төлөв (2026.11.18, салбар phase-2)
- Phase 0–8 код талаас дууссан. Migration 0048 хүртэл.
- Тест: backend 1384, Jest 330, shared 13, web 21 (+1 LEGAL_RELEASE); release-check legal-аас бусад ногоон.
- Нээлттэй: Q65, Q66 (эмч), Q67 (SIM swap), Q12 (хуульч, эмч), BETA B1–B8, B10 (компани), B6 утасны матриц.

## Сургамж
- Expo SDK 58-д `File.copy()`/`move()`/`write()` async — заавал await (8.5-д upload алдагдаж байсан).
- Локал release build: `dist/mobile-release` хуулбарт (ANDROID_EMULATOR.md), dev-ийн `mobile/android`-ыг бүү дар.
- `adb emu kill` гацдаг — taskkill qemu + `adb kill-server`.
- Jest-ийг Metro/эмулятор эсвэл бүтэн `just test-api` ажиллаж байхад бүү ажиллуул.
- `node_modules` унших эрхгүй: сангийн эхийг `pnpm patch <pkg> --edit-dir <scratchpad>`-аас уншина.
- Python heredoc доторх `\n` бодит мөр таслалт болдог — код засварыг Write/Edit-ээр.
- Эмулятор: Medium_Phone_API_37.0, `-no-snapshot-load -memory 3072 -gpu swiftshader_indirect
  -feature -Vulkan`; adb reverse 8081/8080 + `metro-emulator` launch config (EXPO_PUBLIC_API_URL=localhost);
  dev client-ийн хөвөгч товч header-ийн баруун талыг таглана.
```
