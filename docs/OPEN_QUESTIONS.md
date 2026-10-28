# OPEN QUESTIONS

> `[!]` хариу хүлээж байна · `[x]` шийдэгдсэн (шийдвэр, шалтгаан, огноо). Шийдэгдсэнийг дахин маргалдахгүй — шинэ баримт гарвал энд шинэ мөр нэмнэ.

## Шийдэгдсэн — 2026.10.28 (судалгаанд үндэслэн)

- [x] **Q1. iOS хөгжүүлэлт (Windows машин).** Өдөр тутам — Android эмулятор. iOS — **EAS cloud build** (Expo-ийн Mac) + `eas device:create`-ээр бүртгэсэн **бодит iPhone** дээр ad hoc dev build. iOS E2E (Maestro) — GitHub Actions **macOS runner**, release-ийн өмнө (минутын зардал 10×). Phase 0 DoD-г "бодит iPhone" болгосон (`01`).
  Шалтгаан: iOS симулятор зөвхөн macOS-д; macOS-ийг VM-д ажиллуулах нь Apple-ийн лицензийг зөрчинө; EAS-ийн cloud симулятор одоогоор зөвхөн сонгогдсон түншүүдэд нээлттэй preview.
  **Танаас:** Apple Developer Program ($99/жил), Expo аккаунт, 1 iPhone (UDID бүртгэх).
- [x] **Q2. `justfile` Windows дээр** — PowerShell-ээр native (`set windows-shell`). Backend-ийн тест, worker — **Linux контейнер дотор** (WeasyPrint, libmagic Windows-д native суулгахад хэцүү; production-тэй ижил орчин). WSL2 шаардахгүй. (`02`, CLAUDE.md)
- [x] **Q3. GitHub** — private репо; CI нь GitHub Actions (Linux: backend/web/mobile тест; macOS: iOS E2E зөвхөн release-д). Push-ийг та хийнэ.
  **Танаас:** репо үүсгээд `git remote add origin …` + `git push -u origin main`.
- [x] **Q4. Админы хүн таних** — эрүүл мэндийн өгөгдөл **огт ашиглахгүй**. (а) бүртгэлтэй утас руу эргэж залгах + (б) РД "тохирч байна/үгүй" — **argon2id + pepper** (HMAC биш: РД бага энтропитой, түлхүүр алдагдвал секундэд тайлагдана), хэрэглэгч 5/өдөр, админ өдрийн хязгаар, аудит; амжилттай шалгалт 10 мин state үүсгэж сэргээх endpoint үүнийг серверт шаардана. Hash байхгүй бол зөвхөн биечлэн. (`03 users.identity_check_hash`, `04 §1`)
  Шалтгаан: "админ PHI харахгүй" дүрэмтэй зөрчилдөхгүй; төрсөн он/шилжүүлэн суулгасан оныг гэр бүл, хамаатан мэдэж болно — РД+утас хослол илүү хүчтэй.
- [x] **Q5. Шифрлэлтийн түлхүүр** — envelope encryption (AES-256-GCM, `cryptography`), `KeyProvider` интерфейс: dev — Docker secrets; production — **OpenBao** transit (MPL-2.0), Монголд self-host. JWT ES256 түлхүүр `kid`-тэй rotation. (`04 §1`, `02`)
  Шалтгаан: HashiCorp Vault 1.15+ BSL лицензтэй (төслийн "AGPL/SSPL-гүй" бодлогын сүнстэй зөрчилдөнө); OpenBao нь Vault 1.14-ийн нээлттэй fork, ижил transit API.
- [x] **Q6. `contact_phone`** — шифрлэнэ (`contact_phone_enc`, AAD-тэй), `last4` маск; HMAC хадгалахгүй (8 оронтой + last4 → 1e4 хувилбар, утгагүй). Бүтэн дугаарыг `auth_reveal_phone()` (аудит) л нээнэ. `labtrack_app` эрхгүй.
- [x] **Q7. Түр нууц үгийг БҮРМӨСӨН ХАССАН (v7.2)** — security-reviewer олсон: админ түр нууц үг мэддэг бол 72 цагт хэрэглэгчийн өмнөөс нэвтэрч PHI уншина (break-glass тойрно). Оронд: нэг удаагийн **идэвхжүүлэх/сэргээх токен** — биечлэн QR (15 мин) эсвэл бүртгэлтэй утас руу SMS (24 цаг); хэрэглэгч өөрөө нууц үгээ тохируулна. CSV → `pending_activation`, санах ойд боловсруулна. (hazard H19, `04 §1`)
  **Танаас (Phase 1 дунд):** Монголын SMS gateway (операторын API эсвэл aggregator) — `SmsSender` интерфейстэй, dev-д console. Шийдэгдэх хүртэл сэргээлт зөвхөн биечлэн QR-аар.
- [x] **Q8. Push Phase 1-д** — хийхгүй. Хохирогчид мэдэгдэх (дараа нэвтэрсэн хүн нь залилагч байж болно): хуучин төхөөрөмжийн refresh → `401 admin_reset` → "Та хүсээгүй бол {утас}" дэлгэц + бүртгэлтэй утас руу SMS + шинэ нууц үг тохируулсны дараа "Би хүсээгүй" товч → аккаунт `locked`. Expo Push (FCM v1 + APNs key, EAS credentials) — Phase 2, асран хамгаалагчийн мэдэгдэлтэй хамт, бета-гаас өмнө.
- [x] **Q9. Хүүхдийн профайл** — Phase 1: схем (`is_minor`, `consents.patient_id`) + API хамгаалалт (хүүхдийн профайлд асран хамгаалагчийн зөвшөөрөлгүйгээр өгөгдөл бичихгүй, тесттэй). UI (профайл нэмэх) — Phase 2. 18 нас хүрэхэд шилжүүлэх — админы гар урсгал, Phase 9.
- [x] **Нэмэлт — Android exact alarm** — `USE_EXACT_ALARM` зарлахгүй (Google Play зөвхөн сэрүүлэг/хуанли апп-д зөвшөөрдөг → татгалзах эрсдэл); `SCHEDULE_EXACT_ALARM` + тайлбар дэлгэц + inexact (≤ 10 мин) fallback + Нүүрэнд анхааруулга. Hazard H18. (`08`)
- [x] **Нэмэлт — iOS 64 мэдэгдэл** — хоног = `min(7, floor(56 / өдрийн_мэдэгдэл))`, hypothesis тесттэй. (`08`)
- [x] **Нэмэлт — brute-force** — OWASP device-cookie: итгэмжлэгдсэн төхөөрөмж (нэр, төхөөрөмж)-өөр; танихгүй төхөөрөмж (нэр, IP /64) + нэрээр нийт 10/24ц давбал танихгүй төхөөрөмжөөс бүрэн хаана (IP эргүүлэх тусгүй, жинхэнэ хэрэглэгч итгэмжлэгдсэн утаснаасаа нэвтэрсээр). Нууц үг ≥ 10, zxcvbn ≥ 3, задарсан жагсаалт. (`04`)
- [x] **Нэмэлт — DB role** — `labtrack_owner/app/admin/maint`; нууц багана зөвхөн definer функцээр; `users` RLS + column-level UPDATE (эрх нэмэгдүүлэлтгүй); хүснэгт бүрт SELECT/INSERT/UPDATE/DELETE тусдаа policy; `consents` append-only; `audit_write()` (хуурамч actor-гүй); definer функц `search_path = pg_catalog, public, pg_temp` + `REVOKE TEMPORARY/CREATE/TRUNCATE`; `set_config` bind параметрээр. (`03`)
- [x] **Нэмэлт — токен** — JWT `sid` + `token_version` (идэвхгүй болгох/сэргээх шууд), refresh 20 сек grace + апп single-flight. (`04`)
- [x] **Нэмэлт — шифрлэлтийн формат** — `ver|kek_id|wrapped_dek|nonce|ct`, AAD = `table:column:row_id`, зорилго тус бүр тусдаа түлхүүр, аккаунт устгахад crypto-shredding. (`04`)
- [x] **Нэмэлт — idempotency, IDOR, share PIN, collected_at** — `unique (patient_id, client_id)`; composite FK `(medication_id, patient_id)`; `taken` давамгайлах нэгтгэлт (H20); PIN тоолуур verify-ээс өмнө атомаар, токен ≥ 128 бит URL fragment-д, `Referrer-Policy: no-referrer`; trigger-ээр синк. (`03`, `04 §6`)
- [x] **Нэмэлт — Expo SDK** — Phase 0-д тухайн үеийн хамгийн сүүлийн тогтвортой SDK (2026.10: SDK 57, React Native 0.86)-г `expo-overview` skill + context7-оор шалгаж бэхэлнэ. `react-native-mmkv` — New Architecture, шифрлэлтийн түлхүүр `expo-secure-store`-д.

## Хариу хүлээж байна (Phase 0-г саатуулахгүй)
- [!] **Q10. Нэр, bundle ID:** Компанийн нэр/домэйн? Түр `mn.labtrack.app` (`app.config.ts` env-ээр). **Анхны TestFlight/Play build-ээс өмнө (Phase 2)** заавал — дэлгүүрт гарсны дараа bundle ID солигдохгүй.
- [!] **Q11. Production хостинг:** Монгол дахь дата төв/VPS (өгөгдөл Монголд үлдэх — хуулийн шаардлага). Phase 8-аас өмнө.
- [!] **Q12. Хуульч, эмч-хянагч:** Зөвшөөрлийн текст (хуульч), тестийн тайлбар ба CV%-ийн текст (шилжүүлэн суулгалтын эмч) — Phase 2-оос өмнө хянуулах хүн.
- [!] **Q13. SMS gateway (Монгол):** идэвхжүүлэх/сэргээх линк, хохирогчид мэдэгдэх. Phase 1 дунд хүртэл; тэр болтол сэргээлт зөвхөн биечлэн QR.
- [!] **Q14. Mobile styling сан (SDK 58):** NativeWind 4.2.7 (сүүлийн тогтвортой) нь react-native-css-interop 0.2 + Tailwind v3 дээр, SDK 58-ийн Reanimated 4.7-тэй нийцэл эргэлзээтэй; NativeWind 5 — зөвхөн RC. Сонголт: (а) **shared token + StyleSheet + `@expo/ui`** (санал — нэмэлт хамааралгүй, Expo-ийн албан ёсны native компонент, тест/контраст аль хэдийн token-д), (б) Uniwind (Tailwind 4, RN ≥ 0.81), (в) NativeWind 5 RC. Phase 1-ийн UI эхлэхээс өмнө.
