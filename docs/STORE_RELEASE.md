# STORE_RELEASE.md — дэлгүүрт гаргах (Phase 8.4)

> **НООРОГ.** Тайлбар, declaration-ийг компани Play Console / App Store Connect-ийн одоогийн
> маягтаар яг сонгож бөглөнө; хуульч (Q12) ба эмч (тайлбарын текст, B5) батална. Энд байгаа
> ангиллын нэр нь маягтын нэртэй таарахгүй байж болно — таамаг биш, маягтаас сонгоно.
> Холбоотой: `BETA.md` (§2 build, §3 declaration-ий эх), `09_CLINICAL_SAFETY.md` (зориулалт),
> `web/src/legal/content.ts` (нууцлалын бодлого).

## 1. Дэлгүүрийн тайлбар
Хил (09): цэгцлэх, хадгалах, хянах, хэрэглэгчийн тохируулсан сануулга, хуваалцах. Тайлбарт
**хэрэглэхгүй**: «оношлох», «эмчилгээ», «зөвлөгөө», «AI тайлбар», «эрсдэлийг илрүүлэх»,
«эрүүл мэндийг сайжруулах», «тун тохируулах», эмнэлэг/эмчийн нэр, батлагдсан мэт үг. Дэлгэцийн
зураг — зөвхөн `just seed-review` (зохиомол) аккаунтаас, mn ба en.

### mn
- **Нэр (≤ 30):** LabTrack MN
- **Богино (≤ 80):** Шилжүүлэн суулгалтын дараах эм, шинжилгээний хариугаа нэг дор цэгцлэх апп
- **Урт:**

  LabTrack MN нь эрхтэн шилжүүлэн суулгуулсан хүмүүст эрүүл мэндийн мэдээллээ нэг дор цэгцэлж,
  хадгалахад туслах хаалттай бүлгийн апп юм. Аккаунтыг байгууллага олгоно — апп-аас өөрөө
  бүртгүүлэх боломжгүй.

  • Эмийн жагсаалт ба тунгийн түүх. Өөрийн тохируулсан цагт сануулга (түгжээтэй дэлгэцэнд
    анхдагчаар эмийн нэргүй), уусан/алгассан тэмдэглэл.
  • Шинжилгээний хариу: скан, зураг эсвэл PDF-ээ оруулахад апп утгуудыг автоматаар уншиж
    ноорог болгоно — уншилт алдаатай байж болох тул утга бүрийг баримттайгаа тулгаж
    баталсны дараа л түүх, графикт орно. Лавлах хэмжээг баримтад хэвлэснээр нь (эсвэл
    таны оруулснаар) авна — апп өөрөө нөхөхгүй.
  • Шилжүүлэн суулгалт, үйл явдал, амин үзүүлэлт, харшил, товлолыг нэг цагийн хэлхээсэнд.
  • Эмчтэйгээ хуваалцах: хугацаатай линк эсвэл QR, PDF товчоо. Асран хамгаалагч — таны
    зөвшөөрлөөр.
  • Яаралтай картанд таны сонгосон мэдээлэл.

  Анхааруулга: апп нь оношилгоо хийхгүй, эмчилгээ, эмийн тун санал болгохгүй, эмчийн
  зөвлөгөөг орлохгүй. Эмээ эмчийнхээ зааврын дагуу уугаарай. Утасны тохиргоо
  эсвэл холболтоос шалтгаалан сануулга болон асран хамгаалагчийн мэдэгдэл хоцорч эсвэл ирэхгүй
  байж болно. Яаралтай үед 103 руу залгана уу.

  Холболт шифрлэгдсэн (HTTPS), баримтын файл бүр шифрлэгдэж хадгалагдана, утсан дээрх хуулбар
  шифрлэгдсэн; апп-ын админ таны эрүүл мэндийн мэдээллийг ердийн журмаар харах боломжгүй.
  Аккаунтаа апп дотроос эсвэл [устгах хуудасны URL]-аар устгуулж болно.

### en
- **Name:** LabTrack MN
- **Short (≤ 80):** Keep medicines and lab results after a transplant in one place
- **Full:**

  LabTrack MN is a closed-group app that helps people who have had an organ transplant keep
  their health records together. Accounts are issued by the organisation — there is no sign-up
  in the app.

  • Your medicine list and dose history. Reminders at the times you set (no medicine name on
    the lock screen by default); mark doses taken or skipped.
  • Lab results: add a scan, pictures or a PDF; the app reads the values into a draft
    automatically, which can contain mistakes — each value enters your history and charts only
    after you check it against the document and confirm it. Reference ranges are taken as printed
    on the document (or as you type them) — the app never fills them in.
  • Transplants, events, vital signs, allergies and appointments on one timeline.
  • Share with your doctor: a time-limited link or QR code, a PDF summary. Caregivers — only with
    your consent.
  • An emergency card with the details you choose.

  Note: the app does not diagnose, does not suggest treatment or doses, and does not replace your
  doctor's advice. Take your medicines as your doctor told you. Reminders and caregiver alerts
  may be late or not arrive because of phone settings or connection. In an emergency call 103
  (Mongolia) or your local emergency number.

  Connections are encrypted (HTTPS), each document file is stored encrypted, and the copy on your
  phone is encrypted; the app's administrators cannot see your health records in normal operation. You
  can delete your account in the app or at [account deletion URL].

## 2. Google Play — Data safety (ноорог)
Тайлбар: «шифрлэлттэй дамжуулна» — тийм; «устгуулах хүсэлт» — тийм (апп + web
`/account-deletion`); бүх өгөгдөл **апп-ын үйл ажиллагаанд** (зар сурталчилгаа, tracking
байхгүй); бүх цуглуулалт **заавал** (аккаунт бол), харин AI-аар унших, асран хамгаалагч,
хуваалцах нь хэрэглэгчийн сонголт.

| Play ангилал | Юу | Цуглуулна | Хуваалцана (Play-ийн утгаар) |
|---|---|---|---|
| Health and fitness → Health info | эм, тун, уусан/алгассан, шилжүүлэн суулгалт, үйл явдал, амин үзүүлэлт, харшил, товлол, асуулт, шинжилгээний хариу, яаралтай карт | ✔ | Үгүй¹ |
| Files and docs | шинжилгээний PDF | ✔ | Үгүй¹ |
| Photos and videos → Photos | скан/зураг (галерейд хадгалахгүй) | ✔ | Үгүй¹ |
| Personal info → Name | хэрэглэгчийн нэр, профайлын нэр; яаралтай холбоо барих хүний нэр | ✔ | Үгүй |
| Personal info → Phone number | бүртгэлийн утас (админ), яаралтай холбоо барих хүний утас | ✔ | Үгүй |
| Personal info → User IDs | хэрэглэгчийн нэр | ✔ | Үгүй |
| App activity → App interactions | `product_events` — PHI-гүй, HMAC хэрэглэгч, enum/тоо (10d) | ✔ | Үгүй |
| Device or other IDs | push token | ✔ | Үгүй² |
| Location | **үгүй** — профайлын цагийн бүсийн түүхийг байршил гэж тооцох эсэхийг хуульч шийднэ | ? | — |

¹ Play-ийн тодорхойлолтоор хөгжүүлэгчийн өмнөөс боловсруулдаг үйлчилгээ үзүүлэгч (хостинг,
Anthropic — B10) «хуваалцах»-д тооцогдохгүй. **AI-аар унших асаалттай бол** (`AI_EXTRACTION_ENABLED`)
нэргүй текст АНУ-д боловсруулагдана гэдгийг нууцлалын бодлогод тусгаж, DPA-тай байна. Асран
хамгаалагч, эмчтэй хуваалцах нь хэрэглэгчийн өөрийн үйлдэл — Play-д «user-initiated transfer»
(хуваалцахад тооцохгүй) — хуульчаар баталгаажуулна.
² Expo/FCM — зөвхөн мэдэгдэл хүргэх; мэдэгдэлд PHI байхгүй (дүрэм 3).

Q79-ийн сэрүүлэг Data safety-г **өөрчлөхгүй:** сэрүүлгийн цаг ба мэдэгдлийн текст (эмийн нэргүй)
зөвхөн утсан дээр (`DoseAlarmStore`, SharedPreferences, гарахад устана), сервер рүү юу ч илгээхгүй —
«цуглуулах» гэдэг нь утаснаас гадагш дамжуулахыг хэлдэг тул шинэ мөр нэмэхгүй.

Crash: апп-д crash SDK байхгүй; серверийн Sentry (DSN тохируулсан үед) PHI-гүй (`scrub_event`) —
«App info and performance → Crash logs/Diagnostics» нь апп-аас цуглуулахгүй тул сонгохгүй.

## 3. Google Play — бусад declaration
- **Health apps declaration:** апп-ын онцлог — эрүүл мэндийн бүртгэл/мэдээлэл хөтлөх,
  эмийн сануулга/менежмент (маягтын жагсаалтаас яг сонгоно). «Эмнэлгийн хэрэгсэл биш»
  (09 зориулалт): оношлох, эмчилгээ/тун санал болгох функц байхгүй. Зохицуулалтын баталгаа
  шаардвал — хуульч (Q12).
- **Foreground service (Q79 сэрүүлэг, 2026.11.25-нд эх сурвалжаар шалгасан):**
  - Одоо `mediaPlayback`. Play-ийн тодорхойлолтоор media playback нь *хэрэглэгчийн эхлүүлсэн*
    тоглуулалт байх ёстой, «автомат дуу» тохирохгүй
    ([answer/13392821](https://support.google.com/googleplay/android-developer/answer/13392821)) —
    цагтаа өөрөө дуугарах сануулга review-д татгалзагдах эрсдэлтэй.
  - Android-ийн баримт `systemExempted`-ийг *SCHEDULE_EXACT_ALARM эсвэл USE_EXACT_ALARM эзэмшигч*
    апп-д зөвшөөрдөг
    ([service-types](https://developer.android.com/develop/background-work/services/fgs/service-types));
    Play-ийн declaration-ийн жагсаалтад энэ төрлийн мөр байхгүй. Манай сэрүүлэг зөвхөн exact alarm
    зөвшөөрөлтэй үед товлогддог (`alarmClockAvailable` → `canScheduleExactAlarms`) тул нөхцөл таарна.
  - **Санал (release-ийн өмнө, код):** төрлийг `systemExempted` болгох —
    `FOREGROUND_SERVICE_SYSTEM_EXEMPTED` зөвшөөрөл, manifest-ийн `foregroundServiceType`,
    `startForeground`-д API 34+ дээр `FOREGROUND_SERVICE_TYPE_SYSTEM_EXEMPTED`;
    `FOREGROUND_SERVICE_MEDIA_PLAYBACK`-ийг хасах. Зөвшөөрөл цуцлагдсан үед
    `ForegroundServiceTypeNotAllowedException` → одоогийн нөөц мэдэгдэл (`DoseAlarmFallback`).
    Android 14+ эмулятор (Pixel API 36) ба POCO (Android 12) дээр шалгана — dev build дахин хийх.
  - Сэрүүлгийн broadcast-аас FGS эхлүүлэх нь баримтын үл хамаарах нөхцөл (*exact alarm-аар
    хэрэглэгчийн хүссэн үйлдэл*,
    [restrictions-bg-start](https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start)).
    Android 15-ийн `BOOT_COMPLETED`-ээс FGS эхлүүлэх хязгаар бидэнд хамаарахгүй — boot-д зөвхөн
    сэрүүлгийг дахин товлоно, FGS эхлүүлэхгүй.
  - Play Console App content → Foreground service: `systemExempted`-д мөр байхгүй бол
    Console-ийн асуулгыг тухайн үед нь дагана; `mediaPlayback` хэвээр үлдвэл доорх текст +
    видео (≤ 1 мин: эмийн сануулга тохируулах → утас чимээгүй → цагтаа дуугарах → «Уусан»):
    > **Description (en):** At a medicine time the user set, the app rings an alarm tone for at most
    > 60 seconds so the reminder is heard even in silent mode, like an alarm clock. It starts from
    > the user's own exact alarm, shows an ongoing notification with "Stop sound", and stops when the
    > user taps "Taken", "Stop sound" or opens the app. Users can turn it off in Settings →
    > Medicine reminders.
    > **If deferred:** the reminder would ring late; a missed or late immunosuppressant dose can harm
    > a transplant recipient. **If interrupted:** the sound stops and only a silent notification
    > remains, so the dose may be missed.
- **App access:** §4-ийн аккаунт + тэмдэглэл.
- **Exact alarm, Ads (байхгүй), Target audience** (18+; хүүхдийн профайлыг эцэг эх хөтөлнө —
  хүүхэд өөрөө хэрэглэгч биш), **Content rating** (асуулгад «эрүүл мэндийн мэдээлэл» гэж
  хариулна) — `BETA.md` §3.
- **Account deletion URL:** `https://[домэйн]/account-deletion`; **Privacy policy:** `/privacy`.

## 4. Review-ийн аккаунт ба жишээ баримт
1. Серверт (beta/production): `just seed-review https://[сервер]` — super admin гараар нэвтэрнэ
   (нууц үг, TOTP — скрипт хадгалахгүй). `review_store` аккаунт: зохиомол бөөр шилжүүлэн
   суулгуулсан хүн, 3 эм сануулгатай, тунгийн тэмдэглэл, амин үзүүлэлт, харшил, холбоо барих,
   товлол, 6 сарын батлагдсан хариу (график). Нууц үг `.env.review`-д (git-д орохгүй,
   терминалд хэвлэгдэхгүй) — үүнийг дэлгүүрийн «App access»-д хуулна.
   Энэ аккаунт хүн биш тул нууц үгийг ажиллуулсан хүн мэднэ — дүрэм 2 нь хүмүүсийн аккаунтад.
2. Жишээ баримт: `docs/store/review-sample-lab.pdf` — зохиомол, хуудас бүрт «SAMPLE», бүх утга
   лавлах хэмжээнд (критик баннер гарахгүй). Дахин үүсгэх: `backend/scripts/make_review_sample.py`.
   Review тэмдэглэлд: «PDF-ийг [линк]-ээс татаж, апп-ын "Хариу оруулах → Файл (PDF)"-аар
   эсвэл өөр апп-аас Share-ээр оруулна».
3. **Review notes (en):**
   > Closed-group app for organ transplant recipients: accounts are created by the organisation;
   > there is no self sign-up. Use the test account below (made-up data only). The app records and
   > organises the user's own information and user-set medicine reminders; it does not diagnose or
   > suggest treatment or doses, does not check drug interactions and is not a medical device;
   > reference ranges come only from the user's documents. To test adding a lab result, use the sample PDF at [link] via
   > "Add a result → File (PDF)" or the Android share sheet. Reminders: Settings → Medicine
   > reminders (exact alarm permission is optional; without it reminders run inexact). With
   > "Ring like an alarm" on and exact alarms allowed, a dose time rings for up to 1 minute on
   > Android even in silent mode (an alarm-clock foreground service); "Taken", "Stop sound" or
   > opening the app stops it.
4. Review дууссаны дараа: аккаунтыг admin web-ээр **идэвхгүй болгож**, `.env.review`-ийг устгана
   (нууц үг операторын машинд хугацаагүй үлдэхгүй). Дараагийн review-д шинэ нэрээр:
   `REVIEW_USERNAME=review_store2 just seed-review https://…` (нэр `review_`-ээр эхэлнэ — админ
   жагсаалтад ялгагдана). Скрипт super admin сессийг төгсгөлд нь хаана.
5. Хүлээн зөвшөөрсөн эрсдэл: шүүгч review аккаунтаас хуваалцах линк үүсгэж, эсвэл мэддэг
   хэрэглэгчийн нэр рүү асран хамгаалагчийн урилга илгээж чадна (өгөгдөл нь зохиомол; урилгыг
   хүлээн авагч зөвшөөрөхгүй бол юу ч нээгдэхгүй). Review дуусмагц идэвхгүй болгох нь хяналт.

## 5. Шат дараалсан гаргалт (staged rollout)
Урьдчилсан нөхцөл:
- `just release-check` ногоон (алгассан алхамтай бол release биш): хуулийн хуудсанд `[...]`
  үлдээгүй (`LEGAL_RELEASE=1`), store app config тест, release manifest (`expo config --type
  introspect`: хориотой зөвшөөрөл `tools:node="remove"`, `exp+` scheme байхгүй, `allowBackup=false`,
  `dataExtractionRules`), `pip-audit` + `pnpm audit` (CI-ийн `audit` job ч), `eval --check`,
  hazard log бүтэн. Хүлээн зөвшөөрсөн npm advisory — `pnpm-workspace.yaml` `auditConfig`
  (шалтгаантай, 2027.02.01-нд дахин хянана).
- Build-ийн дараа AAB-ийн эцсийн зөвшөөрлүүд (Gradle-ийн merge-ийн дараа — introspect харахгүй):
  `aapt2 dump permissions <apk>` (`bundletool build-apks --mode=universal`-аас) — `USE_EXACT_ALARM`,
  `SYSTEM_ALERT_WINDOW`, `RECORD_AUDIO` байхгүй. Q79-ийн сэрүүлэг (`mobile/modules/dose-alarm`)
  `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MEDIA_PLAYBACK`, `RECEIVE_BOOT_COMPLETED` нэмдэг —
  **release-ийн өмнө:** `systemExempted` руу шилжүүлж Android 14+ дээр шалгах, Play Console-ийн
  foreground service declaration — §3 «Foreground service» (security review M3; Data safety
  өөрчлөгдөхгүй — §2).
- 09 «Release бүрийн шалгалт» (B6 утасны матриц, medical-reviewer); `just restore-drill` энэ
  сард; internal → closed testing дээр ≥ 7 хоног асуудалгүй.

| Шат | Хувь | Хугацаа | Дараагийн шатанд орох нөхцөл |
|---|---|---|---|
| 1 | 10% | ≥ 72 цаг | crash-free хэрэглэгч ≥ 99.5% (Play vitals), ANR < 0.47%, серверийн 5xx шинэ өсөлтгүй (Sentry), клиникийн/аюулгүй байдлын шинэ гомдол **0** |
| 2 | 50% | ≥ 72 цаг | ижил; сануулга хоцорсон гомдол өмнөх хувилбараас олшроогүй (H6, H18) |
| 3 | 100% | — | ижил |

- **Зогсоох (Halt rollout) нөхцөл — аль нэг нь:** буруу хүний мэдээлэл харагдсан; эмийн
  сануулга/тун буруу харагдсан; сануулга ирэхгүй байгаа тухай гомдол; шинжилгээний утга, нэгж,
  лавлах хэмжээ эсвэл тэмдэглэгээ буруу харагдсан, критик баннер гарах ёстой үед гараагүй (эсвэл
  буруу гарсан); яаралтай карт нээгдэхгүй/буруу мэдээлэлтэй; нэвтрэх/синк эвдэрсэн;
  crash-free < 99%. Зогсоосон даруйд `BETA.md` §5 (аюулгүй байдал → `BREACH_PROCEDURE.md`,
  клиникийн → hazard log + тестерт/хэрэглэгчид залгах).
- **Буцаах:** Play дээр хуучин хувилбар руу буцаах боломжгүй — засвартай шинэ `versionCode`
  (`autoIncrement`). Зөвхөн JS алдаа бол `eas update --channel production` (тухайн
  `runtimeVersion`-д). OTA-г ч шатлан (EAS Update-ийн rollout хувь) — CLI-ийн одоогийн
  командыг ашиглахын өмнө баримтаас шалгана.
- **iOS:** App Store-ийн phased release (7 хоног, автомат хувь), шаардлагатай бол «Pause»
  (≤ 30 хоног); ижил нөхцөл.
- Шат бүрийн шийдвэрийг [хариуцагч] гаргаж, огноо/тоог энд бичнэ:

| Огноо | Хувилбар | Шат | Crash-free | ANR | Гомдол | Шийдвэр | Хэн |
|---|---|---|---|---|---|---|---|
