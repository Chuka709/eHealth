# 02 — Архитектур ба технологийн сонголт (v6)

> v6: **Шилжүүлэн суулгуулсан хүмүүс, гар утас үндсэн.** Expo апп = үндсэн; Next.js web = супер админ самбар + хуваалцсан линк. Auth — FastAPI дотор, админ бүртгэдэг нэр + нууц үг (өөрөө бүртгүүлэх, сэргээх код байхгүй). Шалтгаан: `07_CRITIQUE.md`.

## Хэлний хуваарилалт
| Хэсэг | Хэл | Шалтгаан |
|---|---|---|
| API, auth, баримт боловсруулалт, AI задлалт, нормчлол, эмнэлгийн тооцоолол, job | **Python 3.12+** | PDF/зургийн сангууд, pydantic, hypothesis; эмнэлгийн логик нэг газарт |
| Гар утасны апп (үндсэн), web | **TypeScript** | Expo + Next.js код, type, орчуулга хуваалцана |
| Холбоос | **OpenAPI → TS client codegen** | Гэрээ нэг эх сурвалжтай |

Эмнэлгийн тооцоолол зөвхөн Python-д. Апп ба web бэлэн утга харуулна.

## Backend (Python)
| Хэрэгцээ | Сан |
|---|---|
| Төсөл | **uv** |
| API | **FastAPI** |
| Схем | **Pydantic v2**, pydantic-settings |
| ORM / migration | **SQLAlchemy 2.0 async + asyncpg**, **Alembic** |
| Auth | **pwdlib[argon2]** (нууц үг, РД таних hash), **zxcvbn**, **PyJWT[crypto]** (ES256 access token), `secrets` (refresh token), **pyotp** (зөвхөн платформын админд) |
| Background job | **Celery 5 + Redis** (+ Flower) |
| PDF | **pdfplumber** (текст), **pypdfium2** (хуудас → зураг). *PyMuPDF (AGPL) хэрэглэхгүй* |
| Зураг | **Pillow + pillow-heif**, **opencv-python-headless** |
| Файлын төрөл | **python-magic** |
| AI | **anthropic** SDK |
| Fuzzy / транслит | **rapidfuzz**, өөрсдийн кирилл↔латин хүснэгт |
| Storage | **boto3** (S3 API) |
| Push мэдэгдэл | **exponent-server-sdk** (Expo Push) — payload-д PHI оруулахгүй |
| PDF хураангуй | **WeasyPrint** |
| Rate limit | **slowapi** + Redis |
| Шифрлэлт | **cryptography** (AES-256-GCM envelope, HMAC); production KEK — **OpenBao** transit (MPL-2.0) |
| Лог / ажиглалт | **structlog** (PHI redact), **Sentry**, OpenTelemetry |
| Тест | pytest, pytest-asyncio, **hypothesis**, **testcontainers**, **schemathesis** |
| Чанар | **Ruff**, **mypy --strict** |

## Гар утасны апп — `mobile/` (үндсэн)
Дэлгэрэнгүй: `08_MOBILE.md`.
| Хэрэгцээ | Сан |
|---|---|
| Framework | **Expo** (сүүлийн SDK) + **Expo Router**, EAS Build / Submit / **Update (OTA)** |
| UI | **NativeWind** (Tailwind) + **react-native-reusables** (shadcn загвар) |
| API | openapi-fetch (shared) + **TanStack Query** |
| Форм | react-hook-form + zod |
| Баримт скан | **react-native-document-scanner-plugin** (ирмэг олох, хазайлт засах, олон хуудас) |
| Бусад апп-аас хүлээн авах | **expo-share-intent** (Messenger, Viber, имэйлээс PDF/зураг) |
| Файл | expo-document-picker, expo-image-picker, expo-file-system |
| Токен хадгалах | **expo-secure-store** |
| Биометр түгжээ | **expo-local-authentication** |
| Мэдэгдэл | **expo-notifications** |
| График | **@wuba/react-native-echarts** (Skia) — web-тэй ижил ECharts тохиргоо |
| PDF / зураг харах | **react-native-pdf**, gesture-handler + reanimated (zoom) |
| Offline дараалал | **react-native-mmkv** (шифрлэлттэй) |
| i18n | **use-intl** (next-intl-ийн цөм) — web-тэй ижил `mn.json` |
| Эмийн сануулга | **expo-notifications** локал хуваарь (сервергүй, offline) |
| Тест | Jest + React Native Testing Library, **Maestro** (E2E) |

## Web — `web/` (хоёрдогч)
Next.js App Router · shadcn/ui + Tailwind · Apache ECharts · TanStack Query/Table · react-pdf · next-intl · Vitest · Playwright · Biome.
Үүрэг: (1) **супер админ самбар** (хэрэглэгч бүртгэх, нэвтрэх карт хэвлэх, нууц үг шинэчлэх), (2) эмчид хуваалцсан линкийг апп суулгалгүй нээх, (3) компьютерээр ашиглах хэрэглэгч.
Auth: **BFF загвар** — Next.js route handler токенийг httpOnly cookie-д хадгалж, API руу дамжуулна. Браузерын JS токен харахгүй.

## Хуваалцсан код — `packages/shared/` (TS)
OpenAPI-аас үүсгэсэн type + client, zod схем, `messages/{mn,en}.json`, design token (өнгө, фонт, зай), ECharts-ийн нийтлэг тохиргоо.

## Дэд бүтэц
PostgreSQL 17 (pg_trgm, pgcrypto, RLS) · Redis 7 · S3 нийцтэй storage (dev: SeaweedFS) · Caddy · Docker Compose · pgBackRest · OpenBao (production) · GitHub Actions + EAS.

**Хөгжүүлэлтийн орчин (Windows):** `justfile` PowerShell-ээр native ажиллана. Backend-ийн тест, worker нь **Linux контейнер дотор** (`docker compose run --rm api pytest`) — WeasyPrint (Pango), python-magic (libmagic) Windows-д native суулгахад хэцүү, production-тэй ижил орчин. Локал `uv sync` зөвхөн LSP, Ruff, mypy-д. Mobile: Android эмулятор локал; iOS — EAS cloud build + бодит iPhone; iOS E2E — GitHub Actions macOS runner.

## Бүдүүвч
```
[Expo апп (үндсэн)]            [Next.js web (BFF)]
   │ Bearer access JWT             │ httpOnly cookie → Bearer
   │ refresh: secure-store          │
   └──────────────┬────────────────┘
                  ▼
        [FastAPI /api/v1]  ── /auth/* (login, refresh, change-password)  /admin/* (бүртгэх, шинэчлэх)
           │        │ presigned URL ≤ 5 мин
           │        ▼
           │     [S3 storage]
  SET LOCAL│        ▲
 app.user_id        │
           ▼        │
   [PostgreSQL + RLS] ◄── [Celery worker] ──► [Claude API]
           ▲                   │
        [Redis] ◄──────────────┘  явц: Redis pub/sub → SSE
                               └──► [Expo Push] (PHI-гүй мэдэгдэл)
```

## Repo бүтэц
```
labtrack/
├─ backend/src/labtrack/{api,auth,admin,worker,core,extraction,db,storage,notify}/   # core/: units, flags, ranges, matching, timeline
├─ backend/alembic/  backend/tests/{unit,integration,rls,api,eval}
├─ mobile/                      # Expo (үндсэн)
│  └─ app/(auth)/…  onboarding/…  (tabs)/{index,trends,upload,meds,profile}  transplants/  meds/  events/  timeline  review/[id]  share/
├─ web/                         # Next.js: /admin (супер админ), /s/[token] (хуваалцсан линк)
├─ packages/shared/             # api client, zod, i18n, tokens
├─ infra/docker-compose.yml     # postgres, redis, seaweedfs, api, worker, web, caddy
├─ seed/  eval/cases/  docs/
├─ pnpm-workspace.yaml  justfile  CLAUDE.md
```

## Байршуулалт
Монгол дахь дата төв / VPS дээр Docker Compose (өгөгдөл Монголд). Апп — App Store, Google Play (EAS Submit), алдааны засвар EAS Update-ээр. AI задлалт гадаад API руу явна → тусгай зөвшөөрөл (04).
