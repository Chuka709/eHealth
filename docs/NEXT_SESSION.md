# Дараагийн session-д өгөх промпт (Phase 1.6-аас)

> Шинэ Claude Code session нээгээд **Plan mode** (Shift+Tab) асаагаад доорх блокыг бүтнээр нь буулгана.
> Session бүрийн төгсгөлд энэ файлыг (төлөв, сургамж) шинэчилнэ.

```
LabTrack MN төслийн Phase 1-ийг үргэлжлүүлнэ. Надтай монголоор харилц.

## Эхлээд унш (зөвхөн эдгээрийг — токен хэмнэ)
- CLAUDE.md, backend/CLAUDE.md (автоматаар ачаалагдана)
- docs/PROGRESS.md — юу хийгдсэн, юу үлдсэн (Phase 1 хэсэг, security review-ийн тэмдэглэлүүд)
- docs/OPEN_QUESTIONS.md — шийдэгдсэн асуултууд (дахин маргалдахгүй), Q10–Q13 нээлттэй
- docs/04_RBAC_SECURITY.md §1 (auth урсгал), §6 (хэрэгжүүлэлтийн нарийвчлал, 11–12 цэг)
- docs/03_DATA_MODEL.md "Админ ба идэвхжүүлэлтийн функц (migration 0004)" ба "RLS" хэсгүүд
- backend/alembic/versions/0004_admin_and_activation.py, 0005_auth_functions.py
- backend/src/labtrack/api/{auth,deps,errors,ratelimit}.py, auth/service.py (хэв маягийн жишээ)

## Одоогийн төлөв (2026.10.28, сүүлийн commit 6b3aae2)
- Phase 0 код бүрэн; төхөөрөмж/CI-ийн 3 DoD (Android эмулятор, бодит iPhone, GitHub CI)
  хэрэглэгчийн шийдвэрээр хойшлогдсон.
- Phase 1: 1.1–1.3, 1.5 хийгдсэн (DB: 0001–0005, auth API: login/refresh/logout/activate/
  me/password/sessions). 157 backend тест ногоон. 4 удаагийн security review-ийн бүх
  олдвор засагдсан.

## Дараагийн ажил — Phase 1.6 → 1.13 (docs/PROGRESS.md-ийн дарааллаар)
1.6 Admin API `/api/v1/admin/*`:
  - Тусдаа DB engine `labtrack_admin` role-оор; хүсэлт бүрт `set_config('app.user_id', <admin>)`.
    Бүх өөрчлөлт ЗӨВХӨН 0004-ийн `admin_*` функцээр (админд хүснэгт бичих эрх байхгүй — тэгж л байх ёстой).
  - Админ нэвтрэлт: нууц үг + TOTP (pyotp), тусдаа богино сесс (8 ц / 15 мин идэвхгүй),
    `/admin` нь IP allowlist-ын ард (Caddy). `just create-admin <username>` CLI — owner role,
    TOTP secret-ийг шифрлэж хадгалах (envelope, `KeyProvider`; dev-д Docker secret KEK).
  - Endpoint: хэрэглэгч бүртгэх, CSV импорт (санах ойд, мөрийн алдаа, `pending_activation`),
    хайх, төлөв солих, таних шалгалт, идэвхжүүлэх/сэргээх токен (QR эсвэл SMS), утас нээх.
  - `SmsSender` интерфейс (dev: console лог — токенгүйгээр), Q13 шийдэгдэх хүртэл.
  - Админ өөрийн олгосон токеноор нэвтрэх оролдлогод дохио (docs/04 §6.1).
1.7 `/me`: профайл засах, 5 зөвшөөрөл (хувилбартай, append-only), админы үйлдлийн түүх.
1.8 Аккаунт устгах: soft delete → 30 хоногийн дараа Celery beat (`labtrack_maint`) бүрэн
    устгана; crypto-shredding.
1.9 `just gen-client`. 1.10 Web админ самбар (Next.js, BFF httpOnly cookie, next-intl).
1.11 Апп дэлгэцүүд (Expo SDK 58; styling = shared token + StyleSheet + @expo/ui, Q14).
1.12 Тест (Maestro идэвхжүүлэх урсгал орно). 1.13 security-reviewer + ui-reviewer.

## Ажиллах журам
- Алхам бүрийн өмнө товч төлөвлөгөө → миний зөвшөөрөл → хэрэгжүүлэх → тест → commit.
- Алхам бүрийн дараа `security-reviewer` (auth/RLS/admin), UI дээр `ui-reviewer`.
- Шинэ PHI хүснэгт → `phi-table` skill. API хэзээ ч owner (MIGRATION_DATABASE_URL) ашиглахгүй.

## Орчны онцлог (Windows) — заавал
- uv/just PATH: `export PATH="/c/Users/PC/AppData/Local/Microsoft/WinGet/Links:$PATH"`,
  `UV_PYTHON_DOWNLOADS=never` (систем Python 3.13).
- Backend тест контейнерт: `just test-api` (эсвэл `docker compose -f infra/docker-compose.yml
  --env-file .env run --rm test`). Шинэ Python dependency нэмбэл `docker compose ... build api`.
- Хэрэглэсэн migration-ыг засвал (одоохондоо deploy хийгдээгүй тул зөвшөөрөгдөнө) dev/test
  DB-г дахин үүсгэ: postgres контейнерт `drop database ... with (force)` → create → grant
  connect, дараа нь `run --rm migrate`, `run --rm migrate python -m labtrack.cli seed`.
- `.env`-г уншиж болохгүй (хориотой); шинэ нууц бол `.env.example` + `scripts/init_env.py`.

## Өмнө нь гарсан урхи (давтахгүй)
- Migration-ы f-string дотор SQL regex/quantifier: `{{1,40}}` гэж escape; ruff format
  `{1,40}`-г эвддэг. SQL `CASE x WHEN 'a','b'` буруу — `CASE WHEN x IN (...)`.
- Default ACL: `revoke execute on all functions in schema public from public` migration бүрт.
- RLS FORCE → owner-д ч policy хэрэгтэй; definer функц `search_path = pg_catalog, public, pg_temp`.
- RNTL v14: `await render(...)`, `await fireEvent...`; openapi-fetch-ийн fetch-ийг late-bind.
- Hypothesis аль хэдийн 3 бодит алдаа олсон — core функц бүрт property тест.

## Нээлттэй (хийхээр төлөвлөсөн)
HIBP top-N нууц үгийн жагсаалт · timing статистик тест · SeaweedFS JWT signing (Phase 3-аас өмнө)
· production Postgres-ийн параметр лог унтраах · Q10 bundle ID, Q11 hosting, Q12 хуульч/эмч, Q13 SMS.

Эхлэх: дээрх файлуудыг уншаад 1.6-ийн алхамчилсан төлөвлөгөөг (migration шаардлагатай
эсэх, endpoint, тест, файлууд) гарга, миний зөвшөөрлийг хүлээ.
```
