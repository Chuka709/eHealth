# ASVS_L2.md — OWASP ASVS 4.0.3 Level 2 дотоод шалгалт (Phase 8.3)

> Бүлэг бүрийн гол шаардлага, хяналт, нотолгоо (тест, файл). Төлөв: ✅ хэрэгжсэн, нотолгоотой ·
> ◐ хэсэгчлэн / production-д (B1) · ☐ дутуу. Гадны pentest (`PENTEST_SCOPE.md`) үүнийг баталгаажуулна.
> Бүрэн хамрагдсан гэсэн үг биш: L2-ийн ~280 шаардлагаас энэ төсөлд хамаатай голыг нь.

## V1 Архитектур, аюулын загвар
- ✅ Аюулын загвар, итгэлцлийн хил — `docs/04_RBAC_SECURITY.md`, hazard log `docs/09`.
- ✅ Эрх хуваарилалт DB түвшинд: RLS (`ENABLE`+`FORCE`) PHI хүснэгт бүрт, role тус бүр (app/admin/maint/push/backup) — `tests/rls/test_function_hardening.py` (бүх хүснэгт RLS-тэй, definer функц бүр `search_path`-тай, grant-ын snapshot).
- ✅ Үйлчилгээ тусгаарлалт: ai-worker — Valkey `ai` хэрэглэгч (тодорхой командын жагсаалт; өөрийн оролт/гаралт, `ai` queue, өөрийн unacked түлхүүр; нийтлэг unacked, SCAN, binding өөрчлөх, бусдын хариу унших — NOPERM, 2026.11.18 шалгасан), egress зөвхөн api.anthropic.com:443 (tinyproxy); maint/push worker тусдаа role, сүлжээ `internal`. Үлдэгдэл: ai хэрэглэгч бүх `ai-input:*`-ийг (нэргүйжүүлсэн текст) уншина — үүрэг нь; kombu-гийн түгжээ Lua (EVALSHA) шаарддаг тул эвдэрсэн ai-worker төгсгөлгүй скриптээр Valkey-г түр гацааж болно (хүртээмж, өгөгдөл биш) — production-д мониторинг/дохио (B1).

## V2 Нэвтрэлт
- ✅ Өөрөө бүртгүүлэх байхгүй; нэг удаагийн идэвхжүүлэх токен (hash), түр нууц үг байхгүй.
- ✅ Нууц үг ≥ 10, zxcvbn ≥ 3, задарсан жагсаалт; argon2id; нэг янзын алдааны мессеж, dummy hash.
- ✅ Brute-force: device cookie загвар, нэр/IP тоолуур, танихгүй төхөөрөмжийн түгжээ — `tests/api/test_auth*.py`.
- ✅ Админ: TOTP заавал, 8 цаг / 15 мин идэвхгүй, IP allowlist (Caddy) — `tests/api/test_admin_auth.py`.
- ◐ Хэрэглэгчийн MFA: ASVS 4.0.3 L2 нь NIST AAL2 (олон хүчин зүйл)-тай дүйцдэг — **хүлээн зөвшөөрсөн эрсдэл**, орлох хяналт: төхөөрөмжтэй холбосон refresh (rotation + reuse detection), итгэмжлэгдсэн төхөөрөмжийн cookie, апп-ын биометр түгжээ, админ сэргээлтэд эргэж залгалт + РД. Серверийн MFA (жишээ нь TOTP сонголттой) — дараа.

## V3 Сесс
- ✅ JWT ES256, богино access, refresh rotation + reuse detection, `sid`+`token_version` (шууд цуцлалт), бүх сессийг цуцлах.
- ✅ Web: BFF httpOnly `__Host-` cookie, браузерт токен байхгүй; хуваалцах сесс 30 мин, PIN.
- ✅ Апп: secure-store, гарахад бүгд устна.

## V4 Хандалтын хяналт
- ✅ Профайлын хаалга (`PatientReadDb`/`PatientWriteDb`) бүх эрүүл мэндийн route-д — `test_every_health_route_*` (шинэ route автоматаар шалгагдана).
- ✅ Админ PHI харахгүй (API 403 + RLS) — тест; break-glass 2 админ.
- ✅ IDOR: composite FK, харь хэрэглэгчийн RLS тест хүснэгт бүрт.

## V5 Оролт шалгах, кодлох
- ✅ Pydantic strict (`extra="forbid"`), SQL зөвхөн bind параметр (`bound_text`, ruff TID251), HTML escape (summary PDF, web React).
- ✅ Файл: агуулгаар төрөл (libmagic), хэмжээ, ClamAV, тусгаарлагдсан задлагч — 3.2–4.4.
- ✅ Fuzz: `just fuzz-api` (schemathesis, 5xx байхгүй, схемд нийцсэн) — 2026.11.18: нэвтрээгүй 8983, нэвтэрсэн 8162 тохиолдол, бүгд давсан (хуваалцах сессийн route ба зөвшөөрөл татах route-ыг нэвтэрсэн ажиллуулалтаас хассан — өөрсдийн тесттэй).

## V6 Криптограф
- ✅ Envelope шифрлэлт (AES-GCM, DEK/KEK), файл бүр өөрийн түлхүүр; хэрэглэгчийн түлхүүр (утас).
- ◐ KEK production-д OpenBao — хэрэгжээгүй (B1); dev-д env.
- ✅ Нөөц age-ээр шифрлэгдсэн (8.2).

## V7 Алдаа, лог
- ✅ structlog `redact_phi` (түлхүүрээр), PHI логлохгүй, Sentry өгөгдөл цуглуулалт унтраалттай; алдаа `{code, message_key}`.
- ✅ Аудит: зөвхөн ID, append-only.
- ◐ Төвлөрсөн лог, дохиолол — B1.

## V8 Өгөгдөл хамгаалах
- ✅ Утас: шифрлэлттэй MMKV, галерейд хадгалахгүй, screen-capture хамгаалалт, түгжээтэй дэлгэцэнд эмийн нэргүй.
- ✅ `Cache-Control: no-store` (API, web /admin, /s, хуулийн хуудас).
- ✅ Устгах: 30 хоног, нөөц 35 хоног (8.2).

## V9 Харилцаа
- ◐ TLS — Caddy (production сертификат B1); дотоод сүлжээ `internal`.
- ✅ Production build-д https заавал (`app-config.test.ts`).

## V10 Хортой код
- ✅ AGPL/SSPL хориотой (дүрэм 11), lockfile, pnpm minimumReleaseAge, CI.
- ☐ Хамаарлын эмзэг байдлын автомат скан (pip-audit / pnpm audit) CI-д — 8.4-т.

## V11 Бизнес логик
- ✅ Хурдны хязгаар (нэвтрэх, идэвхжүүлэх, хуваалцах, оруулах, экспорт), AI өдрийн хязгаар.
- ✅ AI гаралт = ноорог, батлахгүй бол дашбоардад орохгүй.

## V12 Файл, нөөц
- ✅ Upload ≤ 20 MB (Caddy 21 MB), төрөл шалгалт, вирус, storage-д шифрлэгдсэн, нэр нь UUID.
- ✅ Файл татахад эрх шалгалт, `Content-Disposition: attachment`.

## V13 API
- ✅ OpenAPI-аас client (`just gen-client`), CORS байхгүй (BFF), JSON л.
- ✅ Хуваалцах линк: 256 бит токен fragment-д, PIN argon2id, оролдлогын түгжээ.

## V14 Тохиргоо
- ✅ Нууц `.env`/Docker secret, repo-д байхгүй; CSP nonce (web), security header-ууд (`next.config.ts`).
- ◐ Production hardening (container read-only FS, non-root — backend `USER app` ✅; бусад) — B1.
- ☐ Valkey: default хэрэглэгч бүх эрхтэй хэвээр (API, workers) — зөвхөн ai хэрэглэгч хязгаарлагдсан (B10). Дараа нь worker тус бүрд хэрэглэгч. Valkey одоо root биш (`setpriv`).

## Дутуу (☐) → дараагийн алхам
1. Хамаарлын скан CI-д (8.4).
2. Valkey-ийн бусад үйлчилгээнд тусдаа ACL хэрэглэгч.
3. Production: OpenBao KEK, TLS, лог/дохиолол, container hardening (B1).
