# Дараагийн session-д өгөх промпт (Phase 8.3-аас)

> Шинэ Claude Code session нээгээд (`/clear`) доорх блокыг бүтнээр нь буулгана.
> Session бүрийн төгсгөлд энэ файлыг (төлөв, сургамж) шинэчилнэ.

```
LabTrack MN төслийн Phase 8.3-ыг хэрэгжүүл: аюулгүй байдал ба ачаалал. Төлөвлөгөө баталсан
(docs/PROGRESS.md «Phase 8»). Надтай монголоор харилц. Эхлээд 4–6 мөр төлөвлөгөө өгч батлуул.

## Эхлээд унш (зөвхөн эдгээрийг)
- docs/PROGRESS.md — «Phase 8» (8.1, 8.2 мөр, үлдэгдэл)
- docs/BETA.md B10 (Valkey ACL, ai-worker egress зөвхөн api.anthropic.com)
- docs/04_RBAC_SECURITY.md (аюулын загвар, checklist), docs/11_TOOLING.md (fuzz, /security-check)
- infra/docker-compose.yml (сүлжээ: backend/ai-handoff/egress), backend/scripts/fuzz_api.py

## Хийх
1. B10: Valkey ACL — ai-worker зөвхөн `ai-input:*`/`ai-output:*` ба `ai` queue; ai-worker-ийн
   гарах замыг egress proxy-оор зөвхөн api.anthropic.com руу.
2. Ачааллын тест (k6, AGPL биш эсэхийг шалга — k6 нь AGPL! өөр хэрэгсэл: locust MIT эсвэл
   Python скрипт): нэвтрэх, нүүр, тун тэмдэглэх, баримт оруулах; p95 ба алдааны хувь, 8.2-ын RPO/PITR шийдвэрт.
3. Дотоод pentest: OWASP ASVS L2 жагсаалт (docs/), `just fuzz-api`, `/security-check`, засвар.
4. Гадны pentest-ийн хамрах хүрээ (docs/PENTEST_SCOPE.md).
5. security-reviewer, PROGRESS 8.3, commit + `git push origin phase-2`.

## Одоогийн төлөв (2026.11.18, салбар phase-2)
- Phase 0–7, эмчийн шийдвэр D1–D5b, 8.1 (f8f6e2e), 8.2 (04e38a7) дууссан. Migration 0048 хүртэл.
- Тест: backend 1376, Jest 321, shared 13, web 21 (+1 LEGAL_RELEASE).
- Нээлттэй: Q65, Q66 (эмч), Q67 (SIM swap), Q12 (хуульч, эмч), BETA B1–B10 (компани).

## Сургамж
- Jest-ийг Metro/эмулятор ажиллаж байхад бүү ажиллуул — олон тест хуурамчаар унана.
- `TaskStop` нь Metro-гийн node процессыг зогсоодоггүй — порт эзэлсэн хэвээр (taskkill //F //T //PID).
- Эмулятор: Medium_Phone_API_37.0, `-no-snapshot-load -memory 3072 -gpu swiftshader_indirect
  -feature -Vulkan`; ANR цонхонд «Wait»; dev client-ийн хөвөгч товч header-ийн баруун талыг
  таглана (🆘-ийг x≈800-д товш).
- Backup: `just backup` / `just restore-drill <identity>`; dev-д туршилтын түлхүүрийг
  scratchpad-д үүсгэж `-e BACKUP_AGE_RECIPIENT=` дамжуулна (.env-д бичихгүй).
```
