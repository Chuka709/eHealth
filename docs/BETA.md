# BETA.md — Phase 2 бета (Android, Play Internal testing)

Шийдвэр (2026.11.11): эхлээд **зөвхөн Android**, Google Play **Internal testing** (≤ 100 тестер, review-гүй шахуу). iOS/TestFlight — Apple Developer аккаунт бэлэн болоход. Сервер одоохондоо локал: **бетаг https сервер бэлэн болсны дараа л** тестерүүдэд нээнэ. Тестер — бөөр, элэг шилжүүлэн суулгуулсан 10–20 хүн (CLAUDE.md 10e).

## 1. Бетаг нээхийн өмнө (блокерууд)
| # | Юу | Хэн | Төлөв |
|---|---|---|---|
| B1 | https бета сервер (Монголд байрлах эсэх — Q12 хуульчтай), Caddy TLS, нөөцлөлт | компани | ☐ |
| B2 | Expo аккаунт (компанийн) → `eas init` → `EAS_PROJECT_ID` EAS env-д | компани + Claude | ☐ |
| B3 | Firebase project → FCM V1 service account → `eas credentials` (Android push); Expo Enhanced Push Security + `EXPO_ACCESS_TOKEN` серверт; `PUSH_ENABLED=true` | компани | ☐ |
| B4 | Нууцлалын бодлогын хуудас (https) → `EXPO_PUBLIC_PRIVACY_URL`; аккаунт устгах **web** хуудас (Play шаарддаг). Код бэлэн (8.1): `/privacy`, `/terms`, `/account-deletion` — компани `[...]`-ийг бөглөж, хуульч хянана | компани + хуульч (Q12) | ☐ |
| B5 | Зөвшөөрлийн текст хуульчаар, тайлбар текст эмч + лабын эмчээр (Q12 — `docs/CLINICAL_TEXTS_REVIEW.md`); Q34, Q47, Q48 — эмч шийдсэн, хэрэгжсэн (2026.11.18) | компани | ☐ |
| B6 | Бодит утасны тест матриц (Samsung, Xiaomi, хямд Android — апп хаалттай, нислэгийн горим, Doze, reboot, цагийн бүс) — 09 «Release бүрийн шалгалт» | компани + Claude | ☐ |
| B7 | Тусламжийн утас `EXPO_PUBLIC_SUPPORT_PHONE` (тестерүүд залгах) | компани | ☐ |
| B8 | iOS (Apple аккаунт бэлэн болоход): `com.apple.developer.default-data-protection = NSFileProtectionComplete` entitlement; share extension-ий App Group хавтаст хуваалцсан файл үлдэхгүй байхыг шалгах (3.4 security review); share болон document scanner-ийг бодит iPhone дээр турших | Claude + компани | ☐ |
| B9 | Share intent-ийг **preview build** болон бодит Android утсан дээр (Messenger, Viber, Files) шалгах: dev build дээр share sheet-д апп гарч intent хүлээн авсан ч файлыг уншихад `Permission Denial` (URI зөвшөөрөл dev launcher activity-д очсон бололтой); уншигдахгүй URI ирэхэд `expo-share-intent` нь `CursorIndexOutOfBoundsException`-ээр апп-ыг унагадаг — сангийн засвар/patch эсвэл шинэ хувилбар шаардлагатай | Claude | ◐ patch (8.4, `patches/expo-share-intent@9.0.0.patch`, 9.0.0 хамгийн сүүлийнх): уншигдахгүй URI-г алгасна (унахгүй — апп «уншиж чадсангүй» гэнэ), шинэ task руу дахин нээхэд `FLAG_GRANT_READ_URI_PERMISSION`, алдааны мессеж/logcat-д URI, файлын нэргүй; Kotlin compile ✅. Үлдсэн: release (preview) build дээр Messenger/Viber/Files-аас бодит шалгалт (8.5) |
| B10 | AI-аар унших (4.5) асаахаас өмнө: Valkey ACL — ai-worker-т зөвхөн `ai-input:*`/`ai-output:*` түлхүүр ба `ai` queue (бусад queue, rate-limit түлхүүрт хүрэхгүй); ai-worker-ийн гарах замыг зөвхөн `api.anthropic.com` руу proxy-оор; Anthropic-тай DPA (Q12) ба Data safety-д «эрүүл мэндийн мэдээлэл (нэргүй текст) гадаадад боловсруулагдана»; `AI_EXTRACTION_ENABLED` анхдагчаар унтраалттай | компани + Claude | ◐ код бэлэн (8.3): Valkey `ai` ACL хэрэглэгч (өөрийн түлхүүр, `ai` queue л; бусад NOPERM — шалгасан), ai-worker зөвхөн `ai-proxy`-оор (tinyproxy, CONNECT api.anthropic.com:443 л; бусад ProxyError, шууд ConnectError — шалгасан). Үлдсэн: DPA, Data safety (компани) |

Код талд бэлэн (2.11): bundle ID `mn.munkhly.labtrack` (Q10), push-ийн тусдаа `labtrack_push` role, `eas.json` `beta` profile (AAB, store, channel `beta`), release тохиргооны шалгалт (`src/app-config.test.ts`: https заавал, dev launcher-гүй, хориотой зөвшөөрөл, нууцлалын URL), Тохиргоо → «Апп-ын тухай» (зориулалтын хил, 103, нууцлалын бодлого, тусламж).

## 2. Build ба Play Console
1. EAS env (`beta` profile, secret биш ч гэсэн EAS-д): `EXPO_PUBLIC_API_URL=https://…`, `EXPO_PUBLIC_SUPPORT_PHONE`, `EXPO_PUBLIC_PRIVACY_URL`, `EAS_PROJECT_ID`.
2. Build-ийн өмнө: `pnpm --filter mobile test` + release manifest:
   `APP_VARIANT=production EXPO_PUBLIC_API_URL=https://… EXPO_PUBLIC_SUPPORT_PHONE=… EXPO_PUBLIC_PRIVACY_URL=https://… npx expo config --type introspect --json` → `uses-permission`-д `USE_EXACT_ALARM`, `SYSTEM_ALERT_WINDOW`, `RECORD_AUDIO` нь `tools:node=remove`, `exp+labtrack` scheme байхгүй, `dataExtractionRules` байгаа.
3. `eas build --platform android --profile beta` (cloud). Package нь production-тай ижил (`mn.munkhly.labtrack`) — Internal track дараа нь production болно.
4. **Анхны AAB-г Play Console-д гараар** upload (Google-ийн шаардлага); дараа нь `eas submit --platform android --profile beta` (track `internal`, `draft`).
5. Internal testing → тестерүүдийн Gmail жагсаалт → opt-in линк.
6. Шинэчлэл: native өөрчлөлтгүй бол `eas update --channel beta` (OTA, `runtimeVersion: fingerprint`), бусад үед шинэ build.
7. **Android 17 (API 37) ба дотоод сүлжээ (2026.11.13):** `ACCESS_LOCAL_NETWORK`-ийг зарласан апп зөвшөөрөлгүйгээр дотоод хаяг (`10.0.2.2`, `192.168.x.x`) руу холбогдож чадахгүй — dev build-д `expo-dev-launcher` үүнийг зарладаг тул «ойролцоох төхөөрөмж» цонхыг **зөвшөөрнө** (татгалзвал апп сервертэй холбогдохгүй, adb reverse-ийн loopback л ажиллана). Beta/production нь нийтийн `https://` хаягтай, зөвшөөрөл зарладаггүй — targetSdk 37 болгох үед дахин шалгана.

## 3. Play Console declaration-ийн ноорог (хуульчаар батлуулна)
- **App access:** «Хаалттай бүлгийн апп: аккаунтыг байгууллага олгоно, өөрөө бүртгүүлэх боломжгүй.» Review-д: админ урьдчилан бүртгэсэн туршилтын аккаунт (зохиомол өгөгдөлтэй — `just seed-demo`-той адил), идэвхжүүлсэн, нэр + нууц үг.
- **Health apps declaration:** ангилал — эрүүл мэндийн бүртгэл хөтлөх, эмийн сануулга (нэрийг Play Console-ийн жагсаалтаас яг сонгоно — энд таамаг). Асран хамгаалагчид мэдэгдэх функцийг дурдана. Оношилгоо, эмчилгээний зөвлөмж хийхгүй (апп дотор «Апп-ын тухай» + тайлбарт).
- **Exact alarm (`SCHEDULE_EXACT_ALARM`):** «Хэрэглэгч өөрөө тохируулсан эмийн сануулгыг (дархлаа дарангуйлах эм — цаг алдвал эрсдэлтэй) яг цагт нь харуулах. Хэрэглэгч тайлбар дэлгэцээс өөрөө зөвшөөрнө; зөвшөөрөөгүй бол inexact горимоор ажиллаж, хоцрохыг анхааруулна.» `USE_EXACT_ALARM` зарлаагүй.
- **Data safety** (бета, AI-гүй — Phase 4-өөс өмнө):
  - Цуглуулдаг: Health info (эм, тун, уусан/алгассан тэмдэглэл, шилжүүлэн суулгалт, клиникийн үйл явдал, амин үзүүлэлт, харшил, товлол, эмчээс асуух асуулт, яаралтай карт), Personal info (нэр, хэрэглэгчийн нэр, утас — админ бүртгэлд; **яаралтай холбоо барих хүний** нэр, утас — гуравдагч хүн; асран хамгаалагчийн холбоос), профайлын цагийн бүсийн түүх (байршлын шинжтэй эсэхийг хуульчаар), App activity (PHI-гүй, HMAC хэрэглэгчтэй enum/тоо — 10d), Device ID (push token).
  - Хуваалцдаг: push token → Expo/Google (FCM) зөвхөн мэдэгдэл хүргэх; мэдэгдэлд эмийн нэр, PHI байхгүй (дүрэм 3). Асран хамгаалагчтай — хэрэглэгч өөрөө зөвшөөрсөн үед.
  - Дамжуулалтад шифрлэлттэй (https); хэрэглэгч устгуулах хүсэлт гаргаж болно (апп дотор + web).
  - Phase 4 (AI задлалт, Anthropic) нэмэгдэхэд Data safety-г шинэчилнэ: 4.5-аас хойш зөвшөөрсөн хэрэглэгчийн танихгүй хэлбэрийн текст PDF-ийн нэргүй текст Anthropic (АНУ) руу (B10).

## 4. Тестер бүртгэх (админ)
1. Web админ (`/admin`) → хэрэглэгч үүсгэх (нэр, утас) → нэг удаагийн идэвхжүүлэх QR/SMS (`labtrack://activate#…`). Админ нууц үг хэзээ ч мэдэхгүй (дүрэм 2).
2. Тестер Play-ийн opt-in линкээр апп суулгана → QR уншуулна (эсвэл SMS линк) → нууц үгээ өөрөө тохируулна → зөвшөөрлүүд → wizard (≤ 3 мин).
3. Нууц үг мартвал: тусламжийн утас → админ бүртгэлтэй утас руу эргэж залгаж баталгаажуулна (H12) → шинэ нэг удаагийн токен; бүх сесс цуцлагдаж хэрэглэгчид мэдэгдэнэ.
4. Тестер бүрт: «Апп-ын тухай» хэсгийг уншуулах; эмээ апп-ын дагуу биш, эмчийн зааврын дагуу уух; сануулга хоцорч эсвэл ирэхгүй байж болно, асран хамгаалагчийн мэдэгдэл баталгаагүй (H6, H16, H18); оруулсан тун, цагаа жортойгоо тулгаж шалгах (H23); exact alarm зөвшөөрөл, батарей хэмнэлтийн заавар (Тохиргоо → Эмийн сануулга).

## 5. Санал хүсэлт, асуудал
- Суваг: тусламжийн утас + тестер бүртэй **ганцаарчилсан** суваг (нийтлэг групп гишүүдийн шилжүүлэн суулгуулсныг бусдад илчилж, бие биедээ тун/эмчилгээний зөвлөгөө өгөх газар болно — хэрэглэхгүй). Скриншотод эрүүл мэндийн мэдээлэл явуулахгүй байхыг сануулна (апп screen-capture хамгаалалттай).
- Тусламжийн утасны ажилтан эмнэлгийн зөвлөгөө өгөхгүй: шинж тэмдэг хэлбэл 103 эсвэл тухайн хүний эмч рүү шилжүүлнэ.
- Сануулга ирээгүй / хоцорсон: утасны загвар, Android хувилбар, exact alarm зөвшөөрөл, батарей горим, апп хаалттай байсан эсэх — B6 матрицад нэмнэ (H6, H18). Үүнээс болж тун алдсан эсвэл давхар уусан бол **клиникийн асуудал** (доорх мөр).
- Аюулгүй байдлын зөрчил (буруу хүний мэдээлэл харагдсан г.м.): бетаг зогсоох (Play-д track-ийг түр хаах, серверт `PUSH_ENABLED=false`), сесс цуцлах, `security-reviewer` + 04-ийн зөрчлийн журам.
- Клиникийн асуудал (буруу тун/цаг харагдсан, тун алдсан, давхар уусан): тухайн тестерт шууд залгаж эмчийн зааврыг баримтлахыг хэлэх, hazard log (09: H6, H18, Q24 г.м.)-д бичих, засварын өмнө `medical-reviewer`. Клиникийн хариуцлагатай эмч (нэр, үүрэг) — бетаг нээхээс өмнө тодорхойлно (B5).

## 6. Хэмжүүр (01_PLAN)
30 хоногийн идэвхтэй / бүртгэлтэй ≥ 60%; wizard дуусгасан хувь; сануулгын дараах «Уусан» тэмдэглэлийн хувь (тоо л, PHI-гүй — `product_events`).
