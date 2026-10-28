# Claude Code-д өгөх эцсийн промпт (v7)

> Репогийн үндсэн хавтсанд энэ багцыг (`CLAUDE.md`, `docs/`, `seed/`, `.claude/`) хуулаад `claude` ажиллуулна. **Plan mode** (Shift+Tab) асаагаад доорх промптыг бүтнээр нь буулгана.
> Урьдчилан: Docker, uv, Node LTS + pnpm, just, jq, Xcode (iOS) / Android Studio, EAS CLI + Expo аккаунт, Maestro, Anthropic API key.

---

```
Чи эрүүл мэндийн программ хангамж, эрхтэн шилжүүлэн суулгалт, лабораторийн
шинжилгээний дүн шинжилгээний 20 жилийн туршлагатай эмчийн мэдлэгтэй, мөн
Python (FastAPI), React Native (Expo), Next.js дээр production түвшний, аюулгүй,
хүртээмжтэй систем бүтээдэг ахлах full-stack + mobile + UI/UX инженер.

## Төсөл
"LabTrack MN" — эхний ээлжинд ЭРХТЭН ШИЛЖҮҮЛЭН СУУЛГУУЛСАН хүмүүст зориулсан,
ГАР УТАС ҮНДСЭН, хаалттай бүлгийн апп. Хэрэглэгчийг супер админ бүртгэж, нууц
үг мартвал админ шинэчилнэ. Хэрэглэгч:
- шилжүүлэн суулгалтын мэдээллээ (хэзээ, хаана, ямар эрхтэн, донор …),
- байнга уудаг эм, тунгийн түүх (сануулгатай, асран хамгаалагчийн мэдэгдэлтэй),
- амин үзүүлэлт, харшил, товлол, эмчээс асуух асуулт, яаралтай тусламжийн карт,
- эмчилгээ/клиникийн үйл явдлаа,
- шинжилгээний хариугаа (скан, зураг, Messenger/Viber-ээс PDF) хадгална.
AI (Claude API) хариунаас утга, нэгж, БАРИМТ ДЭЭРХ лавлах ба критик хязгаарыг
задалж, хэрэглэгч баталсны дараа хандлагын график (эмийн тунтай давхардсан),
цагийн хэлхээсэд харуулна. Эмчтэй хуваалцана. Эрүүл мэндийн эмзэг өгөгдөл.

## Эхлээд бүгдийг унш
CLAUDE.md, docs/01_PLAN.md … docs/10_RESEARCH.md (ялангуяа 09_CLINICAL_SAFETY), seed/lab_tests.json,
seed/medications.json, seed/extraction.schema.json

## Стек
backend: Python 3.12+, uv, FastAPI, Pydantic v2, SQLAlchemy 2 async + asyncpg,
Alembic, Celery + Redis, pwdlib[argon2], PyJWT[crypto] (ES256), pyotp (зөвхөн
админ), pdfplumber, pypdfium2, Pillow + pillow-heif, opencv-python-headless,
python-magic, anthropic, rapidfuzz, structlog, Sentry, slowapi, boto3,
exponent-server-sdk, WeasyPrint; тест: pytest, pytest-asyncio, hypothesis,
testcontainers, schemathesis; чанар: Ruff, mypy --strict.
mobile (үндсэн): Expo (сүүлийн SDK) + Expo Router, EAS Build/Update,
NativeWind + react-native-reusables, TanStack Query, react-hook-form + zod,
react-native-document-scanner-plugin, expo-share-intent, expo-secure-store,
expo-local-authentication, expo-notifications, react-native-mmkv (шифрлэлт),
@wuba/react-native-echarts, react-native-pdf, use-intl; Jest + RNTL, Maestro.
web (хоёрдогч): Next.js App Router (BFF, httpOnly cookie), shadcn/ui, ECharts,
next-intl, Vitest, Playwright, Biome.
packages/shared: OpenAPI-аас үүсгэсэн client, zod, mn/en орчуулга, design token.
infra: PostgreSQL 17, Redis, S3 нийцтэй storage (dev: SeaweedFS), Caddy,
Docker Compose, just.
Хувилбарыг суулгахдаа хамгийн сүүлийн тогтвортойг шалгаж бэхэл. Сан, Expo SDK-ийн
API-д итгэлгүй бол албан ёсны баримт бичгийг шалга — таамаглахгүй.
AGPL/SSPL сан (PyMuPDF гэх мэт) хэрэглэхгүй. Стек өөрчлөх шалтгаан олдвол асуу.

## Auth (энгийн, гэхдээ аюулгүй)
Өөрөө бүртгүүлэх БАЙХГҮЙ. Супер админ (web самбар, TOTP) хэрэглэгчийг бүртгэж
нэг удаагийн идэвхжүүлэх QR (биечлэн) эсвэл бүртгэлтэй утас руу SMS линк өгнө →
хэрэглэгч нууц үгээ ӨӨРӨӨ тохируулна (түр нууц үг байхгүй, админ нууц үг мэдэхгүй).
Нууц үг мартвал админ хүнийг таньж (эргэж залгах + РД шалгалт) сэргээх токен
олгоно (бүх сесс цуцлах, шалтгаан, аудит, хохирогчид мэдэгдэх). docs/04 §1, §6 (v7.2).
Админ эрүүл мэндийн өгөгдлийг харахгүй. Биометр түгжээ, refresh rotation +
reuse detection, brute-force түгжээ, argon2id. Дэлгэрэнгүй: docs/04.

## Ажиллах журам
1. Одоо зөвхөн Phase 0 ба Phase 1. Дараагийнхыг би /phase N-ээр эхлүүлнэ.
2. Код бичихээс өмнө: (а) docs-ын ойлголтоо 10 мөрөнд хураангуйл,
   (б) docs хоорондын зөрчил, дутуу, эрсдэлийг жагсаа,
   (в) Phase 0–1-ийн алхамчилсан төлөвлөгөө (файл, migration, endpoint,
   дэлгэц, тест) гарга. Миний зөвшөөрлийг хүлээ.
3. Дараалал: migration → repository → core + тест → API + тест →
   just gen-client → апп дэлгэц → Maestro. Алхам бүрийн дараа
   `just lint && just test`.
4. Auth/RLS/storage → security-reviewer; эмнэлгийн логик/prompt → medical-reviewer.
5. Phase дуусахад DoD-г нотолгоотой тайлагнаж docs/PROGRESS.md,
   docs/OPEN_QUESTIONS.md шинэчил.
6. Эмнэлгийн утгад эргэлзвэл таамаглахгүй — асуу.

## Хатуу шаардлага (CLAUDE.md-д дэлгэрэнгүй)
- PHI хүснэгт бүрт ENABLE+FORCE RLS, `labtrack_app` role, `SET LOCAL app.user_id`,
  харь хэрэглэгчийн хандалтыг хориглосныг батлах тест.
- Лавлах ба критик хязгаар ЗӨВХӨН баримтаас; байхгүй бол `no_reference`.
- Утга ба хязгаар ижил коэффициентоор (Decimal). AI гаралт зөвхөн draft.
- Эмнэлгийн логик зөвхөн backend/src/labtrack/core-д, hypothesis тесттэй.
- PHI лог, Celery аргумент, push payload-д орохгүй.
- Утсан дээр: токен secure-store-д, кэш шифрлэлттэй, гарахад устгах.
- Зориулалтын хил (docs/09): AI чат, AI тайлбар, оношилгоо, эмчилгээ/тун санал,
  харилцан үйлчлэлийн дүгнэлт хийхгүй. Hazard log-ийн хяналт бүр тесттэй.
- Оношилгоо, эмчилгээний зөвлөмж, эмийн тун санал болгохгүй. Тунгийн түүхийг
  засахгүй — шинэ regimen мөр нэмнэ. Эмийн сануулга локал, түгжээтэй дэлгэцэнд нэргүй.
- UI: mobile-first, хүрэлтийн бүс ≥ 44pt, Dynamic Type, dark mode,
  VoiceOver/TalkBack, flag-ийг өнгө+дүрс+текстээр, монгол хэл үндсэн.
  Надтай монголоор харилц.

## Phase 0–1-ийн гаралт
- `just up` (postgres, redis, seaweedfs, api, worker, web, caddy) healthcheck-тэй.
- Expo dev build iOS симулятор + Android эмулятор дээр нээгдэж API-г дуудна.
- CI ногоон: ruff, mypy, pytest, alembic up/down, biome, tsc, jest, OpenAPI
  client хуучирсан эсэх.
- Alembic: users, sessions, auth_attempts, patients, patient_access, consents,
  audit_logs, test_catalog, test_synonyms, unit_aliases, unit_conversions,
  medication_catalog + RLS; `just seed` (lab_tests + medications),
  `just create-admin` (TOTP).
- /auth: activate, login, refresh, logout, change-password,
  sessions, delete-account request. /admin/users: бүртгэх + идэвхжүүлэх токен,
  CSV бөөн бүртгэл, хайх, идэвхгүй болгох, түгжээ тайлах, таних шалгалт, сэргээх токен.
- Зөвшөөрлүүд тус бүр тусдаа (terms, privacy, sensitive_data, ai_processing,
  cross_border) — Монголын хувийн мэдээллийн хуулийн дагуу.
- Web админ самбар: хэрэглэгч бүртгэх, нэвтрэх карт (QR) хэвлэх, удирдах.
- Апп: welcome, идэвхжүүлэх (QR/линк → нууц үг тохируулах), login, зөвшөөрлүүд, биометр,
  "нууц үгээ мартсан" (админтай холбогдох), профайл, тохиргоо,
  админы үйлдлийн түүх.
- Тест: RLS (2+ хэрэглэгч, хугацаа дууссан/цуцлагдсан хандалт, worker context),
  админ PHI endpoint 403, auth (reuse detection, device-cookie түгжээ, токен цуцлалт),
  Maestro анх нэвтрэх урсгал.

Баталсан шийдвэрүүд: өгөгдлийн хариуцагч — миний компани; CV% эмч болон
өвчтөнд; яаралтай карт түгжээгүй нээх анхдагч OFF; асран хамгаалагчийн
мэдэгдэл 30 мин; бета — бөөр ба элэг шилжүүлэн суулгуулагчид.

Эхлэх: docs-ыг уншаад 2-р алхмын (а)(б)(в)-г гарга.
```

---

## Дараагийн промптууд
```
/phase 2
Шилжүүлэн суулгалт, эм, амин үзүүлэлт, товлол, асран хамгаалагч, яаралтай карт.
Эмийн сануулгыг тест матрицаар (iOS 2 хувилбар, Samsung, Xiaomi, хямд Android;
апп хаалттай, нислэгийн горим, цагийн бүс солих, reboot) батал. docs/09-ийн
H6–H10 хяналтыг тестээр нотол. medical-reviewer-ээр хянуул.
```
```
/phase 3
Share intent-ийг iOS share extension болон Android intent filter-ээр бодит
төхөөрөмж дээр (Messenger-ээс PDF) туршиж, offline дараалал давхардалгүй
ажиллахыг батал.
```
```
/phase 4
eval/cases-д нэрээ нууцалсан бөөр ба элэг шилжүүлэн суулгалтын хяналтын
хариунууд (лавлах ба критик хязгаартай, Монгол болон гадаадын) тавьсан.
Эхлээд eval runner бичиж baseline хэмж, дараа нь сайжруул.
```
```
/phase 5
Review дэлгэцийг iPhone SE хэмжээний дэлгэц болон том фонт горимд шалгаж,
1 хуудсыг 60 секундэд хянаж батлах боломжтой эсэхийг үнэл.
```
```
/phase 7
Такролимус CV% ба зорилтот хүрээнд байсан хувийг core-д тооцож hypothesis
тест бич; эмч болон өвчтөнд босго/өнгөгүй, docs/06-ийн тайлбартай харуул. FHIR R4 экспортыг шалгагчаар баталгаажуул.
```
```
/security-check
```
