# PROGRESS — LabTrack MN

> Тэмдэглэгээ: `[x]` хийгдсэн · `[ ]` хийгдээгүй · `[~]` хэсэгчлэн · `[!]` шийдвэр/саад хүлээж байна.
> Phase бүрийн төгсгөлд DoD-г **нотолгоотой** (команд, тестийн тоо, дэлгэцийн зураг) энд бичнэ. Нээлттэй асуулт → `OPEN_QUESTIONS.md`.

## Одоогийн байдал
**Phase 0 — код бүрэн, DoD-ийн 1/4 нотлогдсон** (2026.10.28). Үлдсэн 3 DoD нь таны аккаунт/төхөөрөмж шаардана (доор). Шинэ шийдвэр: Q14 (mobile styling сан).

---

## Бэлтгэл (Phase 0-ээс өмнө)
- [x] v7.1 төлөвлөлтийн багцыг үндсэн хавтсанд байршуулах, хуучныг `_archive/`-д
- [x] docs-ын 11 зөрчил засах (`11_TOOLING.md` §1.1)
- [x] Claude Code plugin-ууд (LSP, security-guidance, pr-review-toolkit, commit-commands, claude-md-management, context7, frontend-design, expo)
- [x] `ui-reviewer` agent, `phi-table` skill, cross-platform format hook, allowlist нарийсгах
- [x] `git init`, `.gitignore`, `.gitattributes`, эхний commit
- [x] Хэрэгсэл: Node 22, pnpm, Docker 29, Python 3.13, git, pyright, typescript-language-server
- [x] `just` 1.59, `uv` 0.13.6, `jq` — winget (шинэ терминал нээхэд PATH-д орно)
- [ ] `eas-cli` (`npm i -g eas-cli`) + Expo аккаунт (`eas login`)
- [ ] Android Studio + эмулятор (Android SDK олдсон — AVD үүсгэх)
- [ ] iOS: Apple Developer Program ($99/жил) + бодит iPhone-ийг `eas device:create`-ээр бүртгэх (Q1 — шийдэгдсэн)
- [ ] Maestro (Android эмулятор; iOS E2E — GitHub Actions macOS)
- [ ] Anthropic API key (Phase 4-өөс заавал; `.env`-д — Claude уншихгүй)
- [ ] GitHub private репо үүсгэж push хийх (Q3 — та хийнэ)
- [ ] Phase 4-д зориулж нэрээ нууцалсан 30+ бөөр/элэгний хариу цуглуулж эхлэх (удаан ажил)
- [ ] Админы хүн таних журам (бичгээр): эргэж залгах + РД HMAC — `04 §1`

---

## Phase 0 — Суурь
- [x] 0.1 Monorepo: pnpm workspace (hoisted, install script opt-in), Biome 2.6 (код файлд), `justfile` (Windows: `pnpm.cmd`), `.editorconfig`, `.env.example` + `just init` (санамсаргүй dev нууц)
- [x] 0.2 Compose: postgres 17 (`labtrack_owner/app/admin/maint` + `labtrack_test` DB), **Valkey 8** (Redis-ийн оронд — лиценз), SeaweedFS S3, migrate, api, worker, web, caddy — бүгд healthcheck; Caddy лог query string нууцална, аюулгүй header
- [x] 0.3 Backend (Python 3.13): FastAPI factory, `/healthz` `/readyz` (алдааны дэлгэрэнгүй гаргахгүй), pydantic-settings, structlog PHI redact, `user_transaction` (`set_config(..., true)`), `bound_text` (`sqlalchemy.text` хориотой), Sentry (бүх data collection off + URL query хасна), Celery ping, Alembic baseline (`REVOKE CREATE/TEMPORARY`), ruff + mypy --strict
- [x] 0.4 `packages/shared`: openapi-fetch client (`just gen-client`, `just check-client`), mn/en (түлхүүр тэнцүү тест), design token (бүх өнгөний хос WCAG AA — тест)
- [x] 0.5 Mobile: **Expo SDK 58** (RN 0.88), Expo Router, TanStack Query, use-intl (mn), `app.config.ts` (fingerprint runtime, env bundle ID, `allowBackup=false`), `eas.json` (development/preview/production), API төлөвийн дэлгэц (өнгө+дүрс+текст, 44pt/48dp), Jest + RNTL v14. Styling сан — Q14
- [x] 0.6 Web: **Next.js 16.4** (cache components, standalone), `lang=mn`, Noto Sans кирилл, security header, `/healthz`, төлөвийн хуудас, Vitest, Docker image. next-intl/shadcn/BFF — Phase 1 (админ самбартай хамт)
- [~] 0.7 CI `.github/workflows/ci.yml` (ruff, mypy, контейнер pytest + alembic up/down/up, biome, tsc, jest, vitest, expo-doctor, stale client) — **GitHub дээр ажиллуулаагүй** (репо байхгүй)
- [x] 0.8 `backend/CLAUDE.md`, `mobile/CLAUDE.md`, `web/CLAUDE.md`

**DoD — нотолгоо**
- [x] `just up` — 7 сервис healthy; `curl :8080/api/v1/readyz` → `{"status":"ok","database":true,"queue":true}`; вэб хуудас Caddy-аар "Сервер хэвийн ажиллаж байна"
- [x] Шалгалтууд: `just lint` 0 алдаа; `just test` — backend 19 (DB, migration up/down орсон), shared 6, web 3, mobile 2 — бүгд ногоон; `just check-client` цэвэр; `expo-doctor` 20/20; Android JS bundle (`expo export`) амжилттай; `next build` амжилттай
- [ ] Dev build **Android эмулятор** дээр API дуудна — AVD + `npx expo run:android` (эсвэл `eas build --profile development --platform android`) **таны машин дээр**
- [ ] Dev build **бодит iPhone** — Apple Developer + Expo аккаунт, `eas device:create`, `eas build --profile development --platform ios` (**та**)
- [ ] CI ногоон — GitHub репо үүсгэж push хийсний дараа (**та**)

## Phase 1 — Auth, супер админ, профайл
- [ ] 1.1 Migration: extensions, enum, `labtrack_owner/app/admin/maint` role, `REVOKE TEMPORARY/CREATE`; users (`account_status`, `token_version`, шифрлэлттэй утас, РД argon2 hash) + column-level эрх, activation_tokens, sessions (`revoked_reason`, `device_trusted`), auth_attempts (+индекс), patients, patient_access, consents (append-only), notifications, audit_logs (`target_user_id`, trigger, `REVOKE TRUNCATE`); definer функцууд (`search_path` хатуу): `can_read/can_write_patient`, `is_owner`, `create_self_profile`, `auth_*`, `audit_write`, `my_admin_actions`, `notify`, `lookup_user_for_share`; хүснэгт бүрт 4 үйлдлийн policy; ENABLE+FORCE RLS
- [ ] 1.2 Migration: test_catalog, test_synonyms, unit_aliases, unit_conversions, medication_catalog; `just seed`
- [ ] 1.3 `core/security`: envelope шифрлэлт (`KeyProvider`, AES-256-GCM, толгойтой формат, AAD), argon2id (+pepper РД-д), нууц үгийн бодлого (≥ 10, zxcvbn, задарсан жагсаалт), идэвхжүүлэх токен (≥ 128 бит, hash), JWT ES256 (kid, `sid`, `tv`), refresh rotation + reuse detection + 20 сек grace, device-cookie түгжээ, dummy hash — hypothesis тест
- [ ] 1.4 Repository + service: auth, admin, consents, audit
- [ ] 1.5 `/auth`: activate, login, refresh (`401 admin_reset` код), logout, change-password, sessions, delete-account request; slowapi; нэг төрлийн алдааны мессеж/хугацаа
- [ ] 1.6 `/admin/users` (`labtrack_admin` role): бүртгэх + идэвхжүүлэх QR, CSV (санах ойд) → `pending_activation`, хайх, идэвхгүй (`token_version`+1), түгжээ тайлах, таних шалгалт (тийм/үгүй, 5/өдөр, 10 мин state) → сэргээх токен (QR/SMS, шалтгаан, сесс цуцлах, хохирогчид SMS), утас нээх (аудит); `SmsSender` (dev: console); TOTP; `just create-admin`; `/admin` IP allowlist, сесс 8ц/15 мин
- [ ] 1.7 `/me`: профайл, 5 зөвшөөрөл (хувилбартай; хүүхдийн профайлд асран хамгаалагчийн зөвшөөрөл API-д шалгах), админы үйлдлийн түүх
- [ ] 1.8 Аккаунт устгах: soft delete + 30 хоногийн дараа Celery beat-ээр бүрэн устгах
- [ ] 1.9 `just gen-client`
- [ ] 1.10 Web админ: нэвтрэх + TOTP, хэрэглэгчид, бүртгэх, CSV, идэвхжүүлэх QR харуулах, нэвтрэх карт (нууц үггүй) хэвлэх, таних шалгалт → сэргээх, тайлах, идэвхгүй болгох
- [ ] 1.11 Апп: welcome, идэвхжүүлэх (QR/линк → нууц үг + хүчтэй байдлын заагч), login, `admin_reset` мэдэгдлийн дэлгэц, зөвшөөрлүүд, биометр, "нууц үгээ мартсан", профайл, тохиргоо (сесс, нууц үг, админы түүх + "Би хүсээгүй", аккаунт устгах), lock, secure-store (`WHEN_UNLOCKED_THIS_DEVICE_ONLY`), refresh single-flight, privacy overlay
- [ ] 1.12 Тест: RLS (2+ хэрэглэгч, хугацаа дууссан/цуцлагдсан, worker context, `app.user_id`-гүй, pg_temp shadowing, `users` жагсаалт задрахгүй, role өөрчлөх боломжгүй, нууц багана SELECT хориотой, хуурамч аудит, caregiver насанд хүрэгчийн өмнөөс зөвшөөрөхгүй), админ токен PHI → 403, админ өөрийн олгосон токеноор нэвтрэх → татгалзах, auth (reuse, grace, device-cookie түгжээ, идэвхгүй хэрэглэгчийн JWT шууд 401, pending/disabled ялгагдахгүй, AAD), schemathesis, Maestro идэвхжүүлэх урсгал
- [ ] 1.13 `security-reviewer`, `ui-reviewer` хяналт; PROGRESS/OPEN_QUESTIONS шинэчлэх

**DoD**
- [ ] Админ бүртгэсэн хэрэглэгч ≤ 2 мин-д QR-аар идэвхжүүлж өөрийн нууц үгээр нэвтэрнэ (админ нууц үг мэдэхгүй)
- [ ] Сэргээх токен олгоход хуучин бүх сесс шууд цуцлагдаж, хуучин төхөөрөмж `admin_reset` мэдэгдэл харуулна
- [ ] Админ токеноор PHI endpoint → 403 (RLS-ээр ч 0 мөр)

## Phase 2 — Шилжүүлэн суулгалт, эм, амин үзүүлэлт, товлол
- [ ] PHI хүснэгтүүд + RLS (`phi-table`), idempotency түлхүүр (`11_TOOLING` B)
- [ ] Wizard ≤ 3 мин; эм, тунгийн түүх (шинэ regimen)
- [ ] Локал сануулга: iOS 64 хязгаарын тооцоо (`11_TOOLING` A), цагийн бүсийн горим, түгжээтэй дэлгэцэнд нэргүй
- [ ] Амин үзүүлэлт, харшил, яаралтай карт, товлол, эмчээс асуух асуулт, асран хамгаалагчийн мэдэгдэл
- [ ] Сануулгын тест матриц (iOS 2, Samsung, Xiaomi, хямд Android; хаалттай, нислэгийн горим, цагийн бүс, reboot)
- [ ] H6–H10 тестээр нотлох; `medical-reviewer`
- [ ] TestFlight / Play Internal — 10–20 бета (бөөр, элэг)

## Phase 3 — Оруулах
- [ ] Presigned upload, python-magic, давхардал, ClamAV, Celery
- [ ] Scanner, зургийн сан, PDF, share intent (iOS + Android бодит төхөөрөмж), offline дараалал
- [ ] DoD: нислэгийн горимд скан → давхардалгүй илгээгдэнэ; Messenger-ээс PDF share

## Phase 4 — AI задлалт
- [ ] Eval runner + baseline (30+ кейс, бөөр/элэг ≥ 50/50)
- [ ] Pipeline (`05_EXTRACTION.md`), prompt caching, escalation
- [ ] DoD: тоон утга ≥ 98%, лавлах ≥ 95%, тест таних ≥ 95%, p95 ≤ 30 сек

## Phase 5 — Нормчлол, Review
- [ ] `core/units.py`, `flags.py`, `ranges.py`, `matching.py` + hypothesis
- [ ] Review дэлгэц, критик баннер, `critical_pending` push, гараар оруулах
- [ ] DoD: 5 хүнтэй usability — 1 хуудас ≤ 60 сек (iPhone SE, том фонт)

## Phase 6 — Дашбоард, цагийн хэлхээс
- [ ] Эрхтнээс хамаарах картууд, хандлага (step band + тун + үйл явдал), цагийн хэлхээс
- [ ] DoD: 3000 утга + 5 жил эм — Нүүр p95 < 1.5 сек (дунд Android)

## Phase 7 — Хуваалцах, PDF, web viewer
- [ ] Нэрээр/линк+QR (PIN түгжээ — `11_TOOLING` C), web read-only, "хэн хэзээ үзсэн"
- [ ] Такролимус CV% + зорилтот хүрээнд байсан хувь (эмч болон өвчтөнд, босгогүй)
- [ ] "Эмчид үзүүлэх" PDF, экспорт PDF/JSON/FHIR R4 (шалгагчаар)

## Phase 8 — Дэлгүүрт гаргах
- [ ] `08_MOBILE.md` жагсаалт, `09` release шалгалт, staged rollout
- [ ] Хууль: нууцлалын бодлого, DPA (Anthropic, hosting), зөрчлийн журам, хуульчийн хяналт
- [ ] Pentest, ачааллын тест, нөөц сэргээх сургуулилт
