# Дараагийн session-д өгөх промпт (Phase 8.2-оос)

> Шинэ Claude Code session нээгээд (`/clear`) доорх блокыг бүтнээр нь буулгана.
> Session бүрийн төгсгөлд энэ файлыг (төлөв, сургамж) шинэчилнэ.

```
LabTrack MN төслийн Phase 8.2-ыг хэрэгжүүл: ажиллагааны бэлэн байдал. Төлөвлөгөө баталсан
(docs/PROGRESS.md «Phase 8»). Надтай монголоор харилц. Эхлээд 4–6 мөр төлөвлөгөө өгч батлуул.

## Эхлээд унш (зөвхөн эдгээрийг)
- docs/PROGRESS.md — «Phase 8» (8.1 мөрийн «8.2-т» үлдэгдэл)
- docs/04_RBAC_SECURITY.md §1 (админы хүн таних журам), §5 (зөрчлийн журам)
- docs/02_ARCHITECTURE.md — нөөцлөлт, storage; infra/ (compose, Postgres, SeaweedFS)
- backend/src/labtrack/keys.py, documents/service.py, user_keys.py, worker/maintenance.py
- web/src/legal/content.ts — «нөөц [N] хоногт дарагдана», «[хугацаа]» мөрүүд

## Хийх
1. Нөөцлөлт: Postgres (pg_dump/WAL) + storage, шифрлэлттэй, хадгалах хугацаа N (бодлогод
   бичигдэнэ); сэргээх скрипт (`just backup`, `just restore-drill`) ба сургуулилтын нотолгоо.
2. Шийдвэр (хэрэглэгчээс асуу): баримтын файлын түлхүүрийг хэрэглэгчийн түлхүүрээр боох уу
   (устгахад нөөц уншигдахгүй болно) — эсвэл зөвхөн нөөцийн хугацаагаар.
3. Журам (docs/): зөрчлийн мэдэгдэл (хэн, хэдэн цагт, загвар), админы хүн таних (эргэж
   залгахдаа өөр дугаар руу хэзээ ч үгүй; утас + үнэмлэх хамт алдагдсан → биечлэн, нэмэлт шалгалт).
4. security-reviewer, PROGRESS 8.2, commit + `git push origin phase-2`.

## Одоогийн төлөв (2026.11.18, салбар phase-2)
- Phase 0–7, эмчийн шийдвэр D1–D5b, 8.1 (f8f6e2e) дууссан. Migration 0048 хүртэл.
- Тест: backend 1376, Jest 321, shared 13, web 21 (+1 LEGAL_RELEASE).
- Нээлттэй: Q65, Q66 (эмч), Q12 (хуульч, эмч), BETA B1–B10 (компани).

## Сургамж
- Jest-ийг Metro/эмулятор ажиллаж байхад бүү ажиллуул — олон тест хуурамчаар унана.
- `TaskStop` нь Metro-гийн node процессыг зогсоодоггүй — порт эзэлсэн хэвээр (taskkill //F //T //PID).
- Эмулятор: Medium_Phone_API_37.0, `-no-snapshot-load -memory 3072 -gpu swiftshader_indirect
  -feature -Vulkan`; ANR цонхонд «Wait»; dev client-ийн хөвөгч товч header-ийн баруун талыг
  таглана (🆘-ийг x≈800-д товш).
```
