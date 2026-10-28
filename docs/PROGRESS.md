# PROGRESS — LabTrack MN

> Тэмдэглэгээ: `[x]` хийгдсэн · `[ ]` хийгдээгүй · `[~]` хэсэгчлэн · `[!]` шийдвэр/саад хүлээж байна.
> Phase бүрийн төгсгөлд DoD-г **нотолгоотой** (команд, тестийн тоо, дэлгэцийн зураг) энд бичнэ. Нээлттэй асуулт → `OPEN_QUESTIONS.md`.

## Одоогийн байдал
**Phase 0 — төлөвлөгөө батлуулахыг хүлээж байна** (2026.10.28)

---

## Бэлтгэл (Phase 0-ээс өмнө)
- [x] v7.1 төлөвлөлтийн багцыг үндсэн хавтсанд байршуулах, хуучныг `_archive/`-д
- [x] docs-ын 11 зөрчил засах (`11_TOOLING.md` §1.1)
- [x] Claude Code plugin-ууд (LSP, security-guidance, pr-review-toolkit, commit-commands, claude-md-management, context7, frontend-design, expo)
- [x] `ui-reviewer` agent, `phi-table` skill, cross-platform format hook, allowlist нарийсгах
- [x] `git init`, `.gitignore`, `.gitattributes`, эхний commit
- [x] Хэрэгсэл: Node 22, pnpm, Docker 29, Python 3.13, git, pyright, typescript-language-server
- [~] `just`, `uv`, `jq` — winget-ээр суусан, **терминалыг дахин нээх** шаардлагатай (PATH)
- [ ] `eas-cli` (`npm i -g eas-cli`) + Expo аккаунт (`eas login`)
- [ ] Android Studio + эмулятор (Windows дээр бэлэн эсэхийг шалгах)
- [!] iOS: Apple Developer аккаунт ($99/жил) + бодит iPhone (Windows дээр симулятор байхгүй — `OPEN_QUESTIONS.md` Q1)
- [ ] Maestro (Android эмуляторт; WSL2 эсвэл Windows build)
- [ ] Anthropic API key (Phase 4-өөс заавал; `.env`-д — Claude уншихгүй)
- [!] GitHub репо (CI-д) — Q3
- [ ] Phase 4-д зориулж нэрээ нууцалсан 30+ бөөр/элэгний хариу цуглуулж эхлэх (удаан ажил)
- [ ] Админы хүн таних журам (бичгээр) — Phase 1-ийн нууц үг шинэчлэлтэд

---

## Phase 0 — Суурь
- [ ] 0.1 Monorepo: `pnpm-workspace.yaml`, root `package.json`, `biome.json`, `justfile` (Windows shell), `.editorconfig`, `.env.example`
- [ ] 0.2 `infra/docker-compose.yml`: postgres 17 (+`labtrack_owner`/`labtrack_app` role init), redis 7, seaweedfs (S3), api, worker, web, caddy — бүгд healthcheck-тэй
- [ ] 0.3 `backend/`: uv, FastAPI app factory, `/healthz`, pydantic-settings, structlog (PHI redact), DB session + `SET LOCAL app.user_id` dependency, Alembic (owner role), Celery + ping task, ruff + mypy --strict, pytest + testcontainers
- [ ] 0.4 `packages/shared/`: OpenAPI → TS client (`just gen-client`), `messages/{mn,en}.json`, design token (flag өнгө AA, light/dark)
- [ ] 0.5 `mobile/`: Expo (сүүлийн SDK) + Expo Router + NativeWind + TanStack Query, `app.config.ts`, `eas.json` (development/preview/production), `/healthz` дууддаг дэлгэц, Jest + RNTL
- [ ] 0.6 `web/`: Next.js App Router + shadcn/ui + next-intl, BFF stub, Vitest
- [ ] 0.7 CI (`.github/workflows/ci.yml`): ruff, mypy, pytest, alembic up/down, biome, tsc, jest, vitest, хуучирсан OpenAPI client шалгах
- [ ] 0.8 `backend/CLAUDE.md`, `mobile/CLAUDE.md`, `web/CLAUDE.md` (токен хэмнэлт)

**DoD**
- [ ] `just up` — бүх сервис healthy
- [ ] Dev build Android эмулятор дээр API дуудна
- [ ] Dev build iPhone дээр API дуудна (Q1-ийн шийдвэрээр)
- [ ] CI ногоон

## Phase 1 — Auth, супер админ, профайл
- [ ] 1.1 Migration: extensions, enum, users, sessions, auth_attempts (+индекс), patients, patient_access, consents, audit_logs (UPDATE/DELETE хориглох trigger), notifications; `app_user_id`/`can_read_patient`/`can_write_patient`; ENABLE+FORCE RLS
- [ ] 1.2 Migration: test_catalog, test_synonyms, unit_aliases, unit_conversions, medication_catalog; `just seed`
- [ ] 1.3 `core/security`: argon2id, түр нууц үг (12, андуурагдахгүй тэмдэгт, 72 цаг), JWT ES256 (kid, iss/aud/exp, `pwd_change_only` scope), refresh rotation + reuse detection, түгжээ (5 → 15 мин ×2, ≤ 24 цаг), dummy hash — hypothesis тест
- [ ] 1.4 Repository + service: auth, admin, consents, audit
- [ ] 1.5 `/auth`: login, refresh, logout, change-password, sessions, delete-account request; slowapi; нэг төрлийн алдааны мессеж
- [ ] 1.6 `/admin/users`: бүртгэх, CSV (урьдчилан харах, мөрийн алдаа), хайх, идэвхгүй, түгжээ тайлах, нууц үг шинэчлэх (шалтгаан, сесс цуцлах, аудит, push), хүн таних шалгалт (зөвхөн тийм/үгүй); TOTP; `just create-admin`; `/admin` IP allowlist
- [ ] 1.7 `/me`: профайл, 5 зөвшөөрөл (хувилбартай), админы үйлдлийн түүх
- [ ] 1.8 Аккаунт устгах: soft delete + 30 хоногийн дараа Celery beat-ээр бүрэн устгах
- [ ] 1.9 `just gen-client`
- [ ] 1.10 Web админ: нэвтрэх + TOTP, хэрэглэгчид, бүртгэх, CSV, нэвтрэх карт (QR — нууц үггүй) хэвлэх, шинэчлэх, тайлах, идэвхгүй болгох
- [ ] 1.11 Апп: welcome, login, заавал нууц үг солих, зөвшөөрлүүд, биометр, "нууц үгээ мартсан", профайл, тохиргоо (сесс, нууц үг, админы түүх, аккаунт устгах), lock, secure-store, privacy overlay
- [ ] 1.12 Тест: RLS (2+ хэрэглэгч, хугацаа дууссан/цуцлагдсан, worker context, `app.user_id`-гүй), админ токен PHI → 403, auth (reuse, түгжээ, must_change, timing), schemathesis, Maestro анх нэвтрэх
- [ ] 1.13 `security-reviewer`, `ui-reviewer` хяналт; PROGRESS/OPEN_QUESTIONS шинэчлэх

**DoD**
- [ ] Админ бүртгэсэн хэрэглэгч ≤ 2 мин-д нэвтэрч нууц үгээ солино
- [ ] Админ нууц үг шинэчлэхэд хуучин бүх сесс цуцлагдана
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
