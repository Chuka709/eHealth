# Эмнэлзүйн текстийн хяналт (Q12)

_Нийт 986 текст._

**Зорилго:** шилжүүлэн суулгалтын эмч + лабораторийн эмч апп-ын эмнэлзүйн текстийг нэг дор хянана (эмчийн шийдвэр 2026.11.18, ★). Одоогоор зөвхөн такролимусын CV%-ийн карт хянуулах хүртэл өвчтөнд нуугдсан; бусад текст апп-д харагдаж байгаа тул бетаг нээхээс өмнө хянагдсан байх ёстой (BETA B5).

**Яаж:** мөр бүрийн «Санал» баганад «OK» эсвэл засварласан монгол текстийг бичнэ. `{n}`, `{date}` зэрэг нь апп-ын орлуулах утга — хэвээр үлдээнэ. Англи текст — лавлагаа.

**Анхаар:** энэ файлыг `node packages/shared/scripts/clinical-texts.mjs` үүсгэдэг; хянуулж дууссаны дараа засварыг `packages/shared/messages/mn.json`-д оруулна. PDF хураангуйн текст (`backend/src/labtrack/summary_codes.py`) мөн эдгээр текстээс авдаг.

## Шинжилгээний хариу хянах (ноорог, тэмдэглэгээ, критик)

Хянагч: лабын эмч. Түлхүүр: `app.upload.review` (114).

| Түлхүүр | Монгол | English | Санал |
|---|---|---|---|
| `title` | Уншсан хариу | Read results | |
| `open` | Уншсан утгуудыг харах | See the values read | |
| `draftNotice` | Энэ нь файлаас автоматаар уншсан ноорог. Утга бүрийг хариутайгаа тулгаж шалгана уу. Баталсны дараа л түүх, графикт орно. | This is a draft read automatically from the file. Check every value against your result. Only after you confirm it does it go into your history and charts. | |
| `byAi` | Зарим хэсгийг AI-аар уншсан тул алдаа байж болно — заавал шалгана уу. | Some of it was read by AI and may contain mistakes — please check it. | |
| `nameMismatch` | Хариунд хэвлэсэн нэр энэ профайлынхтай таарахгүй байж магадгүй. Хэний хариу болохыг шалгана уу. | The name printed on the result may not match this profile. Check whose result it is. | |
| `empty` | Энэ файлаас уншсан утга алга. | No values were read from this file. | |
| `untitled` | Шинжилгээ | Tests | |
| `collected` | Огноо: {date} | Date: {date} | |
| `dateUnknown` | Огноо уншигдаагүй | Date not read | |
| `range` | Лавлах хэмжээ: {range} | Reference range: {range} | |
| `noRange` | Лавлах хэмжээ хариунд байхгүй | No reference range on the result | |
| `check` | Шалгах | Check | |
| `issues.not_in_source` | файлаас олдсонгүй | not found in the file | |
| `issues.implausible` | уншилтын алдаа байж магадгүй | may be misread | |
| `issues.ref_suspicious` | лавлах хэмжээ эргэлзээтэй | reference range looks wrong | |
| `issues.flag_mismatch` | лавлах хэмжээг цаастай тулгана уу | check the range against the paper | |
| `issues.unknown_unit` | нэгж танигдсангүй | unit not recognised | |
| `issues.unknown_test` | шинжилгээ танигдсангүй | test not recognised | |
| `issues.date_future` | огноо ирээдүйд байна | date is in the future | |
| `issues.date_old` | огноо хэт хуучин | date is very old | |
| `issues.date_ambiguous` | огноо тодорхойгүй | date is unclear | |
| `issues.name_mismatch` | нэр таарахгүй | name does not match | |
| `issues.possible_duplicate` | давхардсан байж магадгүй | may be a duplicate | |
| `issues.large_delta` | өмнөх хариунаас их ялгаатай — уншилтыг шалгана уу | very different from the last result — check the reading | |
| `issues.low_confidence` | уншилт эргэлзээтэй | reading is unsure | |
| `issues.name_missing` | хариунд нэр алга | no name on the result | |
| `issues.date_missing` | огноо алга | no date | |
| `issues.date_inconsistent` | огноонууд зөрүүтэй | dates do not agree | |
| `issues.unit_missing` | нэгж алга | no unit | |
| `issues.truncated` | текст таслагдсан | text cut off | |
| `issues.other` | шалгана уу | please check | |
| `issues.possible_critical` | яаралтай хянах утга байж болзошгүй | may need prompt review | |
| `issues.critical_unreadable` | критик хязгаар уншигдсангүй | critical limit could not be read | |
| `issues.critical_inside_reference` | критик хязгаар лавлах хэмжээн дотор — баганыг шалгана уу | critical limit inside the reference range — check the columns | |
| `issues.no_conversion` | нэгжийг хөрвүүлэх боломжгүй — графикт орохгүй | unit cannot be converted — not on the charts | |
| `issues.ref_not_used` | хүйс/насаар ялгаатай лавлах хэмжээнээс алийг нь хэрэглэхийг тодорхойлж чадсангүй | could not tell which of the ranges printed by sex or age applies | |
| `issues.critical_edited` | критик гэж уншсан утгыг зассан — засвараа шалгана уу | a value read as critical was corrected — check the correction | |
| `draftLabel` | Ноорог — батлаагүй | Draft — not confirmed | |
| `nameMissing` | Хариунаас нэр уншигдсангүй. Энэ профайлын хариу мөн эсэхийг шалгана уу. | No name could be read from the result. Check that it belongs to this profile. | |
| `critical` | Критик хязгаар (хариунд): {range} | Critical limit (on the result): {range} | |
| `criticalBanner` | Яаралтай хянах утга байж болзошгүй. Утгыг хариутайгаа тулгана уу. Хариутай ижил бол эмч эсвэл шилжүүлэн суулгалтын багтайгаа холбогдоно уу. Энэ мэдээлэл эмчийн зөвлөгөөг орлохгүй. Биеийн байдал муу бол 103 руу залгана уу. | A value may need prompt review. Check it against the printed result. If it matches, contact your doctor or transplant team. This does not replace a doctor's advice. If you feel unwell, call 103. | |
| `openCount` | {count, plural, =0 {Бүх мөр шалгагдсан} other {# мөр шалгах шаардлагатай}} | {count, plural, =0 {All rows checked} one {# row needs checking} other {# rows need checking}} | |
| `confirm` | Батлах | Confirm | |
| `confirmHint` | Баталсан утга л түүх, графикт орно. | Only confirmed values go into the history and charts. | |
| `confirmed` | Батлагдсан | Confirmed | |
| `rejected` | Татгалзсан — түүх, графикт орохгүй | Rejected — not in the history or charts | |
| `reject` | Энэ хариуг татгалзах | Reject this result | |
| `rejectConfirm` | Татгалзсан хариу түүх, графикт орохгүй. Татгалзах уу? | A rejected result does not go into the history or charts. Reject it? | |
| `rejectCritical` | Энэ хариунд яаралтай хянах утга байж болзошгүй. Үүнийг харснаа баталгаажуулаад татгалзах уу? | This result may hold a value that needs prompt review. Confirm you have seen it and reject? | |
| `matches` | Хариутай ижил | Matches the printout | |
| `matchesLabel` | «{issue}»: хариутай ижил гэж тэмдэглэх | “{issue}”: mark as matching the printout | |
| `accepted` | Хариутай тулгасан | Checked against the printout | |
| `edit` | Засах | Edit | |
| `addRow` | Мөр нэмэх | Add a row | |
| `deleteRow` | Энэ мөрийг устгах | Delete this row | |
| `deleteConfirm` | Энэ мөрийг ноорогоос устгах уу? | Delete this row from the draft? | |
| `deleteCritical` | Энэ мөрөнд яаралтай хянах утга байж болзошгүй. Үүнийг харснаа баталгаажуулаад устгах уу? | This row may hold a value that needs prompt review. Confirm you have seen it and delete? | |
| `correctedFrom` | Засагдсан. Уншсан утга: {value} | Corrected. Value as read: {value} | |
| `typed` | Гараар оруулсан | Typed in by hand | |
| `lastDose` | Дээж авахаас өмнөх сүүлийн тэмдэглэсэн тун ({medicine}): {time}, дээжээс {hours} цаг {minutes} минутын өмнө | Last logged dose before the sample ({medicine}): {time}, {hours} h {minutes} min before the sample | |
| `lastDoseExtra` | Энэ тунг өөр {count} удаа тэмдэглэсэн | {count, plural, one {logged # more time} other {logged # more times}} | |
| `lastDoseUnknown` | {medicine}: дээж авсан цаг хариунд байхгүй тул сүүлийн тунг харуулах боломжгүй | {medicine}: the sample time is not printed, so the last dose cannot be shown | |
| `dateTitle` | Дээж авсан огноо | Date the sample was taken | |
| `dateNeeded` | Огноог хариунаас харж сонгоно уу (огноо тодорхойгүй эсвэл алга). | Pick the date from the printed result (it is unclear or missing). | |
| `precision` | Хариунд цаг бичигдсэн үү? | Is a time printed? | |
| `precisionDay` | Зөвхөн өдөр | Day only | |
| `precisionMinute` | Өдөр ба цаг | Day and time | |
| `date` | Өдөр | Day | |
| `time` | Цаг | Time | |
| `saveDate` | Огноог хадгалах | Save the date | |
| `nameConfirm` | Энэ хариу «{name}» профайлынх мөн | This result belongs to the profile “{name}” | |
| `wrongProfile` | Өөр хүний хариу уу? Зөв профайл руу шилжүүлэх | Someone else's result? Move it to the right profile | |
| `moveTo` | Аль профайлынх вэ? | Whose result is it? | |
| `move` | Шилжүүлэх | Move | |
| `noOtherProfile` | Шилжүүлэх өөр профайл алга. | There is no other profile to move it to. | |
| `testPick` | Шинжилгээг жагсаалтаас сонгох | Pick the test from the list | |
| `testNone` | Сонгоогүй | Not picked | |
| `value` | Утга (хариунд бичсэнээр) | Value (as printed) | |
| `unit` | Нэгж | Unit | |
| `ref` | Лавлах хэмжээ (хариунд бичсэнээр) | Reference range (as printed) | |
| `criticalField` | Критик хязгаар (хариунд байвал) | Critical limit (if printed) | |
| `name` | Шинжилгээний нэр (хариунд бичсэнээр) | Test name (as printed) | |
| `save` | Хадгалах | Save | |
| `rowTitle` | Мөр засах | Edit row | |
| `newRowTitle` | Мөр нэмэх | Add a row | |
| `newTitle` | Хариу гараар оруулах | Type in a result | |
| `newHint` | Цаасан эсвэл зурган хариунаас утга бүрийг хэвлэснээр нь бичнэ үү. Лавлах хэмжээг хариунд байгаагаар л бичнэ — байхгүй бол хоосон үлдээнэ. | Type each value as printed on the paper or photo. Type the reference range only as printed — leave it empty if there is none. | |
| `addAnother` | Өөр мөр нэмэх | Add another row | |
| `removeRow` | Мөрийг хасах | Remove the row | |
| `create` | Ноорог хадгалах | Save the draft | |
| `typeIn` | Утгыг гараар оруулах | Type the values in | |
| `lab` | Лаборатори (заавал биш) | Laboratory (optional) | |
| `required` | Бөглөнө үү | Fill this in | |
| `flags.normal` | Лавлах хэмжээнд | Within the reference range | |
| `flags.low` | Лавлахаас бага | Below the reference range | |
| `flags.high` | Лавлахаас их | Above the reference range | |
| `flags.critical_low` | Критик хязгаараас бага | Below the critical limit | |
| `flags.critical_high` | Критик хязгаараас их | Above the critical limit | |
| `flags.abnormal` | Лавлахаас ялгаатай | Differs from the reference | |
| `flags.no_reference` | Лавлах хэмжээгүй | No reference range | |
| `flags.unknown` | Тулгах боломжгүй | Cannot be compared | |
| `cancel` | Болих | Cancel | |
| `call103` | 103 руу залгах | Call 103 | |
| `moveConfirm` | Энэ хариуг «{name}» профайл руу шилжүүлэх үү? | Move this result to the profile “{name}”? | |
| `possibleCritical` | Яаралтай хянах утга байж болзошгүй | May need prompt review | |
| `typedNotice` | Энэ нь гараар оруулсан ноорог. Утга бүрийг хариутайгаа дахин тулгаж шалгана уу. Баталсны дараа л түүх, графикт орно. | This is a draft typed in by hand. Check each value against the result again. Only confirmed values go into the history and charts. | |
| `retype.label` | Хэвлэсэн хариун дээрх утгыг дахин бичнэ үү | Type the value again from the printed report | |
| `retype.hint` | Энэ утга апп-ын хүлээх хэмжээнээс хол байна — ихэнхдээ уншилт эсвэл нэгжийн алдаа. Цаасан/PDF хариугаа хараад тоог яг тэр хэвээр нь бичиж, нэгжийг ({unit}) мөн тулгана уу. Хариун дээр өөр тоо эсвэл нэгж байвал «Засах»-аар засна уу. | This value is far from what the app expects — most often a misread or a wrong unit. Look at the paper/PDF report, type the number exactly as printed and check the unit ({unit}) too. If the report shows another number or unit, use "Edit". | |
| `retype.confirm` | Хариутай тулгасан | Checked against the report | |
| `retype.hidden` | (уншсан утгыг нуусан — хариунаасаа бичнэ үү) | (the value read is hidden — type it from your report) | |
| `sampleTime.why` | Эмийн түвшний хариунд дээж авсан цаг бичигдээгүй байна. Цагийг баримтаас (жишээ нь лабын баримт) мэдэж байвал нэмбэл сүүлийн тунгаас хэдэн цагийн дараа авсныг харуулна. Санамжаар бүү бичээрэй — мэдэхгүй бол хоосон үлдээнэ үү. Цаг нэмбэл энэ хариуны шалгасан мөрүүдийг дахин тулгана. | This drug level result has no sample time. If you know it from a document (for example the lab's slip), adding it shows how many hours after the last dose it was taken. Do not guess — leave it empty if you are not sure. Adding a time asks you to check this report's rows again. | |
| `sampleTime.add` | Дээж авсан цагийг нэмэх | Add the sample time | |
| `sampleTime.time` | Дээж авсан цаг | Sample time | |
| `sampleTime.save` | Цагийг хадгалах | Save the time | |

## Нүүр: шинжилгээ, «Анхаарах»

Хянагч: эмч, лабын эмч. Түлхүүр: `app.home.lab` (17).

| Түлхүүр | Монгол | English | Санал |
|---|---|---|---|
| `loading` | Шинжилгээний хариу ачаалж байна… | Loading lab results… | |
| `attention` | Хязгаараас гадуур эсвэл лаборатори тэмдэглэсэн | Outside the range or marked by the lab | |
| `attentionHint` | Сүүлийн 90 хоногийн хариунаас хариу дээрх хязгаараас гадуур, эсвэл лаборатори тэмдэглэсэн утгууд. Хариугаа эмчтэйгээ ярилцана уу. | Values from the last 90 days that the result marked outside its range, or that the lab marked. Talk them over with your doctor. | |
| `cards` | Гол үзүүлэлтүүд | Key results | |
| `noDefaults` | Шилжүүлэн суулгалтаа бүртгэвэл эрхтэнд тохирох гол үзүүлэлтүүд энд гарна. Картаа өөрөө ч сонгож болно. | Once you record your transplant, the key results for the organ appear here. You can also choose the cards yourself. | |
| `noneChosen` | Карт сонгоогүй байна. | No cards chosen. | |
| `edit` | Картуудыг засах | Edit cards | |
| `noValue` | Батлагдсан хариу алга | No confirmed result | |
| `range` | Лавлах: {range} | Reference: {range} | |
| `noRange` | Хариу дээр лавлах хэмжээ бичигдээгүй | No reference range printed on the result | |
| `change` | Өмнөхөөс өөрчлөлт: {percent} ({date}: {value}) | Change from the previous: {percent} ({date}: {value}) | |
| `checkSource` | Лаборатори критик гэж тэмдэглэсэн эсвэл критик хязгаарыг уншиж чадаагүй — эх хариугаа шалгана уу. | The lab marked it critical, or its critical limit could not be read - check the source result. | |
| `openTrend` | Хандлагын графикийг нээх | Open the trend chart | |
| `criticalHelp` | Хариу дээр бичигдсэн критик хязгаараас гадуур утга байна. Эмч эсвэл шилжүүлэн суулгалтын багтайгаа энэ талаар ярилцаагүй бол холбогдоно уу. Биеийн байдал муу бол 103 руу залгана уу. | A value is outside the critical limit printed on the result. If you have not talked about it with your doctor or transplant team, contact them. If you feel unwell, call 103. | |
| `defaultsNote` | Эрхтний төрлөөр апп-ын санал болгосон жагсаалт — эмчийн хяналтын төлөвлөгөө биш. Аль шинжилгээг хэзээ өгөхийг эмчтэйгээ тохирно уу. | A list the app suggests for the organ - not your doctor's monitoring plan. Agree with your doctor which tests to take and when. | |
| `stale` | Сүлжээгүй — {when}-ны байдлаар | Offline - as of {when} | |
| `changeOtherLab` | Өмнөх утга өөр лабынх ({date}: {value}) — арга нь ялгаатай байж болзошгүй тул өөрчлөлтийг тоогоор харуулахгүй. | The previous value is another lab's ({date}: {value}) — methods may differ, so no change is shown as a number. | |

## Хандлагын график

Хянагч: эмч, лабын эмч. Түлхүүр: `app.trends` (44).

| Түлхүүр | Монгол | English | Санал |
|---|---|---|---|
| `title` | Хандлага | Trends | |
| `search` | Шинжилгээ хайх | Search tests | |
| `empty` | Батлагдсан шинжилгээний хариу одоогоор алга. Хариугаа оруулж баталсны дараа энд хандлага харагдана. | No confirmed lab results yet. Trends appear here once you add and confirm results. | |
| `noMatch` | Хайлтад тохирох шинжилгээ олдсонгүй. | No test matches the search. | |
| `count` | {count} хариу · сүүлийнх {date} | {count} results · latest {date} | |
| `period` | Хугацаа | Period | |
| `periods.3m` | 3 сар | 3 months | |
| `periods.6m` | 6 сар | 6 months | |
| `periods.1y` | 1 жил | 1 year | |
| `periods.5y` | 5 жил | 5 years | |
| `periods.all` | Бүгд | All | |
| `axis` | Тэнхлэг | Axis | |
| `axes.date` | Огноо | Date | |
| `axes.days` | Суулгалтаас хойш (хоног) | Since transplant (days) | |
| `daysApprox` | Шилжүүлэн суулгасан огноо зөвхөн сар/он тул хоногийн тоо ойролцоо (бодит хугацаанаас илүү гарахгүй). | The transplant date is known only to the month or year, so the day count is approximate (never more than the real time). | |
| `chartLabel` | {name}-ийн хандлагын график, {count} хариу. Утга бүр доорх жагсаалтад байна. | Trend chart of {name}, {count} results. Every value is in the list below. | |
| `legend` | Нарийн саарал шат — тухайн хариу дээр бичигдсэн лавлах хэмжээ (лаборатори солигдоход өөрчлөгдөж болно). Улаан тасархай — хариу дээр бичигдсэн критик хязгаар. Цэгийн дүрс: ● лавлах хэмжээнд, ▲ лавлахаас гадуур, ◆ критик, хоосон дүрс — лавлах хэмжээгүй эсвэл «<», «>» утга. Цэгэн босоо шугам — шилжүүлэн суулгалт, үйл явдал. | Thin grey steps: the reference range printed on each result (it may change with the lab). Red dashed: the critical limit printed on the result. Point shapes: ● within range, ▲ outside range, ◆ critical, hollow - no range, or a "<"/">" value. Dotted vertical lines: transplant, events. | |
| `legendDose` | Тасархай шат (баруун тэнхлэг) — бүртгэсэн {medicine}: өдрийн тун. | Dashed steps (right axis): the recorded daily dose of {medicine}. | |
| `doseNote` | Тунг бүртгэсэнээр нь харуулав. Тун ба шинжилгээний хариуны холбоог эмч тайлбарлана; тунгийн өөрчлөлтийг эмчтэйгээ ярилцана уу. | Doses are shown as recorded. Your doctor interprets how dose and results relate; talk to your doctor about any dose change. | |
| `aroundTransplant` | шилжүүлэн суулгалтын үе (огноо тодорхойгүй) | around the transplant (date not exact) | |
| `daysAfter` | шилжүүлэн суулгаснаас хойш {days} хоног | {days} days after the transplant | |
| `daysBefore` | шилжүүлэн суулгахаас {days} хоногийн өмнө | {days} days before the transplant | |
| `values` | Хариунууд | Results | |
| `openSource` | Эх хариуг нээх | Open the source result | |
| `lab` | Лаборатори: {lab} | Lab: {lab} | |
| `truncated` | Хамгийн сүүлийн {limit} хариуг харуулав. Хугацааг богиносгоно уу. | The latest {limit} results are shown. Choose a shorter period. | |
| `noValues` | Энэ хугацаанд хариу алга. | No results in this period. | |
| `doses` | Тунгийн түүх ({medicine}) | Dose history ({medicine}) | |
| `doseStep` | {from} өдрөөс: өдөрт {amount} {unit} | From {from}: {amount} {unit} a day | |
| `doseStepWeekly` | {from} өдрөөс: тун уух өдөрт {amount} {unit} | From {from}: {amount} {unit} on dosing days | |
| `doseNone` | {from} өдрөөс: тун бүртгээгүй | From {from}: no dose recorded | |
| `dosePlanned` | Төлөвлөсөн | Planned | |
| `seriesLabels.value` | Хариу | Result | |
| `seriesLabels.refLow` | Лавлахын доод | Reference low | |
| `seriesLabels.refHigh` | Лавлахын дээд | Reference high | |
| `seriesLabels.criticalLow` | Критик доод | Critical low | |
| `seriesLabels.criticalHigh` | Критик дээд | Critical high | |
| `seriesLabels.dose` | Тун | Dose | |
| `seriesLabels.days` | хоног | days | |
| `doseNotDrawn` | Ирээдүйд товлосон, 7 хоногийн хуваарьтай эсвэл өөр нэгжээр бүртгэсэн тун графикт ороогүй — тунгийн түүхэд бий. | Doses planned ahead, on a weekly schedule or in another unit are not on the chart - they are in the dose history. | |
| `daysAfterApprox` | ≈ шилжүүлэн суулгаснаас хойш {days} хоног | ≈ {days} days after the transplant | |
| `daysBeforeApprox` | ≈ шилжүүлэн суулгахаас {days} хоногийн өмнө | ≈ {days} days before the transplant | |
| `notDrawn` | Графикт ороогүй (нэгжийг хөрвүүлэх боломжгүй) | Not on the chart (the unit cannot be converted) | |
| `noProfile` | Профайл сонгоно уу. | Choose a profile. | |

## Цагийн хэлхээс, харьцуулалт

Хянагч: эмч. Түлхүүр: `app.timeline` (41).

| Түлхүүр | Монгол | English | Санал |
|---|---|---|---|
| `title` | Цагийн хэлхээс | Timeline | |
| `rowHint` | Шилжүүлэн суулгалт, эм, үйл явдал, шинжилгээний хариу нэг дор | Transplant, medicines, events and lab results in one place | |
| `show` | Харуулах | Show | |
| `groups.transplant` | Шилжүүлэн суулгалт | Transplant | |
| `groups.medication` | Эм | Medicines | |
| `groups.event` | Эмчилгээ, үйл явдал | Treatments, events | |
| `groups.report` | Шинжилгээний хариу | Lab results | |
| `lab` | Лаборатори | Lab | |
| `allLabs` | Бүх лаборатори | All labs | |
| `noneShown` | Харуулах төрлөө сонгоно уу. | Choose what to show. | |
| `empty` | Одоогоор бүртгэл алга. | Nothing recorded yet. | |
| `month` | {year} оны {month}-р сар | {month}/{year} | |
| `year` | {year} он | {year} | |
| `dayYear` | {year} он (сар, өдөр тодорхойгүй) | {year} (month and day not known) | |
| `dayMonth` | {year}.{month} (өдөр тодорхойгүй) | {year}.{month} (day not known) | |
| `planned` | Төлөвлөсөн | Planned | |
| `transplant` | Шилжүүлэн суулгалт: {organ} | Transplant: {organ} | |
| `graft` | Залгаасны төлөв: {status} | Graft status: {status} | |
| `started` | {name} — эхэлсэн | {name} - started | |
| `stopped` | {name} — энэ өдрөөс эхлэн уугаагүй | {name} - not taken from this day | |
| `changed` | {name} — тун эсвэл хуваарь шинэчлэгдсэн | {name} - dose or schedule updated | |
| `until` | Дууссан: {date} | Ended: {date} | |
| `report` | Шинжилгээний хариу | Lab result | |
| `results` | {count} утга | {count} values | |
| `flagged` | Хязгаараас гадуур гэж тэмдэглэгдсэн: {flagged} / {count} | Marked outside the range: {flagged} / {count} | |
| `unflagged` | Лавлахтай тулгаагүй: {count} | Not checked against a range: {count} | |
| `typed` | Гараар оруулсан | Typed in | |
| `compare` | Хоёр хариу харьцуулах | Compare two results | |
| `pickTwo` | Харьцуулах хоёр хариугаа жагсаалтаас сонгоно уу. | Choose the two results to compare from the list. | |
| `compareGo` | Харьцуулах ({n}/2) | Compare ({n}/2) | |
| `compareCancel` | Болих | Cancel | |
| `compareScreen.title` | Хариу харьцуулах | Compare results | |
| `compareScreen.note` | Утга бүр тухайн хариу дээр бичигдсэнээрээ. Лаборатори өөр бол лавлах хэмжээ, нэгж өөр байж болно. | Each value is as its result printed it. Another lab may print another range or unit. | |
| `compareScreen.noDate` | Огноогүй | No date | |
| `compareScreen.noLab` | Лаборатори бичигдээгүй | No lab printed | |
| `compareScreen.absent` | Энэ хариунд байхгүй | Not in this result | |
| `compareScreen.notConfirmed` | Зөвхөн батлагдсан хариуг харьцуулна. | Only confirmed results are compared. | |
| `startsAhead` | {name} — эхлэх | {name} - starts | |
| `stopsAhead` | {name} — энэ өдрөөс эхлэн уухгүй | {name} - not taken from this day | |
| `changesAhead` | {name} — тун эсвэл хуваарь шинэчлэгдэнэ | {name} - dose or schedule changes | |
| `untilAhead` | Дуусах: {date} | Ends: {date} | |

## Эмчийн зорилт, тэмдэглэл, такролимусын CV%

Хянагч: эмч. Түлхүүр: `app.clinician` (67).

| Түлхүүр | Монгол | English | Санал |
|---|---|---|---|
| `row` | Эмчийн зорилт, тэмдэглэл | Doctor's targets and notes | |
| `rowHint` | Эмчийн тогтоосон шинжилгээний зорилт, тэмдэглэл | Lab targets and notes from your doctor | |
| `intro` | Таны профайлыг хуваалцсан эмчийн тогтоосон шинжилгээний зорилт, тэмдэглэл энд харагдана. Эдгээрийг зөвхөн эмч бичнэ. Асуулт байвал эмчтэйгээ ярилцана уу. | Lab targets and notes from a doctor you shared your profile with appear here. Only the doctor writes them. Ask your doctor if you have questions. | |
| `introDoctor` | Энэ профайлд зорилт, тэмдэглэл бичих боломжтой. Профайлын эзэн болон түүнд хуваалцсан хүмүүс таны нэртэйгээр харна. Апп зөвхөн утгыг зорилттой харьцуулж тэмдэглэнэ. | You can write targets and notes on this profile. The owner and the people it is shared with see them under your name. The app only marks values against the target. | |
| `level.title` | Такролимусын түвшин (тоогоор) | Tacrolimus level (numbers) | |
| `level.what` | Баталгаажсан такролимусын хариунаас тооцсон дундаж, хэлбэлзэл (CV% = стандарт хазайлт ÷ дундаж × 100), эмчийн зорилтын доторх утгын тоо. Шилжүүлэн суулгалтаас {months} сарын дараах (огноо нь зөвхөн сар/онтой бол хамгийн хожуу байж болох өдрөөс), тоо нь яг бичигдсэн, нэг өдрийн эхний утгыг л тоолно. | Mean, variability (CV% = standard deviation ÷ mean × 100) and the number of values inside the doctor's target, from confirmed tacrolimus results. Only values from {months} months after the transplant (from its latest possible day when only the month or year is known), with an exact number, and the first value of each day count. | |
| `level.period` | Хугацаа | Period | |
| `level.months` | Сүүлийн {n} сар | Last {n} months | |
| `level.n` | Тоологдсон утга | Values counted | |
| `level.mean` | Дундаж | Mean | |
| `level.sd` | Стандарт хазайлт | Standard deviation | |
| `level.cv` | Хэлбэлзэл (CV%) | Variability (CV%) | |
| `level.inTarget` | Эмчийн зорилтын дотор | Inside the doctor's target | |
| `level.inTargetValue` | {n}/{of} ({pct}%) | {n}/{of} ({pct}%) | |
| `level.countedFrom` | Тоолж эхэлсэн өдөр: {date} | Counted from {date} | |
| `level.notAVerdict` | Зөвхөн тоо — апп босго, үнэлгээ, тунгийн санал гаргахгүй. | Numbers only — the app gives no threshold, judgement or dose suggestion. | |
| `level.reason.no_transplant` | Шилжүүлэн суулгалтын огноо бүртгэгдээгүй тул тооцоогүй. | Not calculated: no transplant date is recorded. | |
| `level.reason.too_few` | Тооцоход хангалттай утга алга (дор хаяж 5 хэрэгтэй). | Not enough values to calculate (at least 5 are needed). | |
| `level.reason.zero_mean` | Утгуудаас тоо гаргах боломжгүй байна. | No number can be calculated from these values. | |
| `level.reason.no_unit` | Энэ шинжилгээний нэгж каталогт алга тул тооцоогүй. | Not calculated: this test has no unit in the catalog. | |
| `level.leftOut.bounds_left_out` | {n} утгыг хассан: «< 2» гэх мэт хязгаар, яг тоо биш | {n} left out: a bound such as "< 2", not an exact number | |
| `level.leftOut.not_numeric_left_out` | {n} утгыг хассан: тоо биш | {n} left out: not a number | |
| `level.leftOut.other_unit_left_out` | {n} утгыг хассан: өөр нэгжтэй | {n} left out: another unit | |
| `level.leftOut.no_date_left_out` | {n} утгыг хассан: сорьц авсан огноогүй | {n} left out: no sample date | |
| `level.leftOut.early_left_out` | {n} утгыг хассан: шилжүүлэн суулгалтаас {months} сарын дотор | {n} left out: within {months} months of the transplant | |
| `level.leftOut.duplicates_left_out` | {n} утгыг хассан: давхар оруулсан | {n} left out: entered twice | |
| `level.leftOut.same_day_left_out` | {n} утгыг хассан: нэг өдрийн хоёр дахь утга | {n} left out: a second value on the same day | |
| `level.inTargetCount` | {n}/{of} | {n}/{of} | |
| `level.showValues` | Тоолсон {n} утгыг харах | Show the {n} counted values | |
| `level.hideValues` | Тоолсон утгуудыг нуух | Hide the counted values | |
| `level.labsMixed` | Утгууд өөр лабуудаас ({labs}) — хэмжих арга ялгаатай байж болзошгүй тул CV%-д нөлөөлж болно. | Values come from different labs ({labs}) — their methods may differ, which can affect CV%. | |
| `level.labUnknown` | {n} утгын лаб тодорхойгүй — өөр лабынх байж болзошгүй. | {n, plural, one {# value has} other {# values have}} no lab named — it may come from another lab. | |
| `targets.title` | Эмчийн зорилт | Doctor's targets | |
| `targets.hint` | Зорилт тогтоосон шинжилгээнд утга зорилтоос гадуур бол лабын лавлахаас гадна «зорилтоос гадуур» гэж тэмдэглэнэ. | For a test with a target, a value outside it is marked "outside target" besides the lab's reference range. | |
| `targets.none` | Эмч зорилт тогтоогоогүй байна. | No targets set by a doctor. | |
| `targets.between` | {low} – {high} {unit} | {low} – {high} {unit} | |
| `targets.atLeast` | Доод хязгаар {low} {unit} | Lower limit {low} {unit} | |
| `targets.atMost` | Дээд хязгаар {high} {unit} | Upper limit {high} {unit} | |
| `targets.since` | {from}-с хойш | From {from} | |
| `targets.period` | {from} – {to} | {from} – {to} | |
| `targets.by` | Тогтоосон: {name} | Set by {name} | |
| `targets.end` | Зорилтыг дуусгах | End target | |
| `targets.endLabel` | {name}-ийн зорилтыг дуусгах | End the target for {name} | |
| `targets.endBody` | Зорилт өнөөдрөөр дуусна. Өмнөх утгуудын тэмдэглэгээ хэвээр үлдэнэ. | The target ends today. Earlier values keep their marks. | |
| `targets.form.title` | Шинэ зорилт | New target | |
| `targets.form.search` | Шинжилгээ хайх (нэр эсвэл код) | Find a test (name or code) | |
| `targets.form.test` | Шинжилгээ | Test | |
| `targets.form.low` | Доод хязгаар ({unit}) | Lower limit ({unit}) | |
| `targets.form.high` | Дээд хязгаар ({unit}) | Upper limit ({unit}) | |
| `targets.form.from` | Эхлэх өдөр | Starts on | |
| `targets.form.note` | Тэмдэглэл (заавал биш) | Note (optional) | |
| `targets.form.save` | Зорилт хадгалах | Save target | |
| `targets.form.checkTitle` | Зорилтоо шалгана уу | Check the target | |
| `targets.form.checkBody` | {name}: доод {low}, дээд {high} {unit}, {from}-с. Хадгалах уу? | {name}: lower {low}, upper {high} {unit}, from {from}. Save? | |
| `targets.form.saved` | Зорилт хадгалагдлаа. | Target saved. | |
| `targets.form.number` | Тоог зөв бичнэ үү (жишээ нь 7,5). | Enter a valid number (for example 7.5). | |
| `targets.form.order` | Доод хязгаар дээд хязгаараас их байж болохгүй. | The lower limit cannot be above the upper limit. | |
| `targets.formerDoctor` | Өмнөх эмч | A former doctor | |
| `notes.title` | Эмчийн тэмдэглэл | Doctor's notes | |
| `notes.none` | Тэмдэглэл алга. | No notes. | |
| `notes.meta` | {name} · {date} | {name} · {date} | |
| `notes.formerDoctor` | Өмнөх эмч | A former doctor | |
| `notes.remove` | Тэмдэглэлийг устгах | Delete note | |
| `notes.removeTitle` | Энэ тэмдэглэлийг устгах уу? | Delete this note? | |
| `notes.new` | Шинэ тэмдэглэл | New note | |
| `notes.newHint` | Профайлын эзэн болон түүнд хуваалцсан хүмүүс таны нэртэйгээр харна. | The owner and the people the profile is shared with see it under your name. | |
| `notes.add` | Тэмдэглэл нэмэх | Add note | |

## Эм, тун, сануулга, каталоггүй эмийн ангилал

Хянагч: эмч. Түлхүүр: `app.meds` (198).

| Түлхүүр | Монгол | English | Санал |
|---|---|---|---|
| `title` | Эм | Medicines | |
| `today` | Өнөөдрийн тунгууд | Today's doses | |
| `todayEmpty` | Өнөөдөр товлосон тун алга. | No doses planned today. | |
| `noMeds` | Эм нэмээгүй байна. | No medicines added yet. | |
| `current` | Одоо уудаг | Taking now | |
| `past` | Өмнө нь уусан | Taken before | |
| `add` | Эм нэмэх | Add a medicine | |
| `prnHint` | Шаардлагатай үед | When needed | |
| `noDose` | Тун оруулаагүй | No dose entered | |
| `dose.taken` | Уусан | Taken | |
| `dose.skipped` | Алгассан | Skipped | |
| `dose.markTaken` | Уусан — {time} {name} | Taken — {time} {name} | |
| `dose.markSkipped` | Алгассан — {time} {name} | Skipped — {time} {name} | |
| `dose.stateTaken` | Уусан гэж тэмдэглэсэн | Recorded as taken | |
| `dose.stateSkipped` | Алгассан гэж тэмдэглэсэн | Recorded as skipped | |
| `dose.stateNone` | Тэмдэглээгүй | Not recorded | |
| `dose.queueFull` | Сүлжээгүй удсан тул тэмдэглэл хадгалах зай дүүрсэн. Сүлжээнд холбогдоод дахин оролдоно уу. | Offline for too long: there is no room to keep more records. Connect and try again. | |
| `dose.undo` | Буцаах | Undo | |
| `dose.undoLabel` | Буцаах — {time} {name} | Undo — {time} {name} | |
| `dose.upcoming` | Цаг нь болоогүй | Not yet due | |
| `dose.saveFailed` | Тэмдэглэл хадгалагдсангүй. Дахин оролдоно уу. | The record was not saved. Try again. | |
| `dose.undoFailed` | Буцааж чадсангүй. Сүлжээнд холбогдсон үед дахин оролдоно уу. | Could not undo. Try again when connected. | |
| `dose.stateTakenBy` | Уусан — {who}, {time} | Taken — {who}, {time} | |
| `dose.alsoRecorded` | Мөн тэмдэглэсэн: {who}, {time} | Also logged: {who}, {time} | |
| `dose.alreadyTitle` | Энэ тун аль хэдийн тэмдэглэгдсэн | This dose is already logged | |
| `dose.alreadyBody` | {time}-д {who} «уусан» гэж тэмдэглэсэн байна. Та ч мөн тэмдэглэх үү? Таны тэмдэглэл тусад нь хадгалагдана. | {who} logged it as taken at {time}. Log it too? Your entry is kept separately. | |
| `dose.alreadyCancel` | Болих | Cancel | |
| `dose.alreadyRecord` | Мөн тэмдэглэх | Log it too | |
| `dose.who.you` | та | you | |
| `dose.who.owner` | профайлын эзэн | the profile's owner | |
| `dose.who.caregiver` | асран хамгаалагч | a caregiver | |
| `dose.who.someone` | өөр хэн нэгэн | someone else | |
| `dose.alreadyBodyYou` | Та энэ тунг {time}-д «уусан» гэж аль хэдийн тэмдэглэсэн байна. Дахин тэмдэглэх үү? Шинэ тэмдэглэл тусад нь хадгалагдана. | You already logged this dose as taken at {time}. Log it again? The new entry is kept separately. | |
| `dose.uncheckedTitle` | Энэ тунг өмнө нь тэмдэглэсэн эсэхийг шалгаж чадсангүй | Could not check whether this dose is already recorded | |
| `dose.uncheckedBody` | Өөр хүн тэмдэглэсэн байж магадгүй. «Уусан» гэж тэмдэглэх үү? | Someone else may have recorded it. Record it as taken? | |
| `dose.takenAfter` | Товлосон цагаас {hours, plural, =0 {} other {# цаг }}{minutes} минутын дараа уусан | Taken {hours, plural, =0 {} one {# hour } other {# hours }}{minutes} min after its time | |
| `dose.takenBefore` | Товлосон цагаас {hours, plural, =0 {} other {# цаг }}{minutes} минутын өмнө уусан | Taken {hours, plural, =0 {} one {# hour } other {# hours }}{minutes} min before its time | |
| `summary.title` | Энэ сарын тэмдэглэл | This month's records | |
| `summary.body` | Уусан гэж тэмдэглэсэн: {taken} / товлосон тун: {planned}. Тэмдэглэсэн эсвэл тэмдэглэх хугацаа нь дууссан {due} тунгийн {percent}% нь «уусан». | Recorded as taken: {taken} / planned doses: {planned}. {percent}% of the {due} doses already recorded or whose recording time has ended are "taken". | |
| `summary.bodyNoPercent` | Уусан гэж тэмдэглэсэн: {taken} / товлосон тун: {planned}. | Recorded as taken: {taken} / planned doses: {planned}. | |
| `summary.skipped` | Алгассан гэж тэмдэглэсэн: {n} | Recorded as skipped: {n} | |
| `summary.unrecorded` | Тэмдэглээгүй: {n} | Not recorded: {n} | |
| `summary.open` | Одоо ч тэмдэглэж болох: {n} | Can still be recorded: {n} | |
| `summary.none` | Энэ сард товлосон тун алга. | No doses planned this month. | |
| `summary.note` | Зөвхөн таны тэмдэглэлийн тоо. Эмийг апп-д нэмсэн өдрөөс тоолно. | Counts of your records only, from the day each medicine was added to the app. | |
| `summary.offline` | Сарын тэмдэглэл сүлжээнд холбогдсон үед харагдана. | This month's records show when you are connected. | |
| `summary.definition` | Хувь гэдэг нь товлосон тунгаас «уусан» гэж тэмдэглэсэн тунгийн хувь (тэмдэглэх хугацаа нь дууссан тунгаас). Сануулгагүй эмийг ч тоолно, шаардлагатай үед уудаг эмийг тоолохгүй. Ямар ч хувийг «хангалттай» гэж үнэлэхгүй — эмчтэйгээ ярилцана уу. | The percent is the share of scheduled doses recorded as taken (of the doses whose time to record has passed). Medicines without reminders count too; as-needed medicines do not. No percent is judged "enough" — talk it over with your doctor. | |
| `form.search` | Эмийн нэрээр хайх | Search by medicine name | |
| `form.searchHint` | Монгол, англи эсвэл худалдааны нэрээр | Mongolian, English or brand name | |
| `form.searchEmpty` | Олдсонгүй. Доор гараар бичиж болно. | Not found. You can type it below. | |
| `form.manual` | Жагсаалтад алга — гараар бичих | Not in the list — type it | |
| `form.chosen` | Сонгосон: {name} | Chosen: {name} | |
| `form.change` | Өөр эм сонгох | Choose another medicine | |
| `form.name` | Эмийн нэр | Medicine name | |
| `form.brand` | Худалдааны нэр (сонголттой) | Brand name (optional) | |
| `form.form` | Хэлбэр (сонголттой) | Form (optional) | |
| `form.formHint` | Жишээ нь шахмал, капсул | For example tablet, capsule | |
| `form.strength` | Агуулга (сонголттой) | Strength (optional) | |
| `form.strengthHint` | Саван дээр бичсэнээр, жишээ нь 1 мг | As on the pack, for example 1 mg | |
| `form.scheduleType` | Хэр олон уух вэ? | How often? | |
| `form.daily` | Өдөр бүр | Every day | |
| `form.weekly` | Долоо хоногийн тодорхой өдрүүдэд | On certain days of the week | |
| `form.prn` | Шаардлагатай үед | When needed | |
| `form.unsupported` | Өдөр алгасах, N хоног тутам гэх мэт хуваарь одоогоор дэмжигдэхгүй. «Шаардлагатай үед» сонгоод зааварт бичнэ үү — ингэвэл сануулга ирэхгүй. | Schedules like every other day or every N days are not supported yet. Choose “When needed” and write it in the instructions — no reminders will come then. | |
| `form.days` | Аль өдрүүдэд? | Which days? | |
| `form.times` | Уух цаг ба тун | Times and doses | |
| `form.amount` | {n}-р цагийн тун | Dose at time {n} | |
| `form.amountHint` | Тоо: 2, 1,5 эсвэл 0.25 | A number: 2, 1.5 or 0,25 | |
| `form.addTime` | Цаг нэмэх | Add a time | |
| `form.removeTime` | {n}-р цагийг хасах | Remove time {n} | |
| `form.unit` | Нэгж | Unit | |
| `form.unitOther` | Нэгжийн нэр | Unit name | |
| `form.instructions` | Заавар (сонголттой) | Instructions (optional) | |
| `form.instructionsHint` | Эмчийн хэлснээр, жишээ нь хоолны өмнө | As your doctor said, for example before meals | |
| `form.startedOn` | Уух эхэлсэн өдөр | Started on | |
| `form.plannedEnd` | Курс дуусах сүүлийн өдөр (сонголттой) | Last day of the course (optional) | |
| `form.plannedEndClear` | Курсын өдрийг арилгах | Clear the course end | |
| `form.done` | Болсон | Done | |
| `form.reminders` | Сануулга авах | Remind me | |
| `form.tzMode` | Сануулгын цаг | Reminder time | |
| `form.tzHome` | Улаанбаатарын цагаар | Ulaanbaatar time | |
| `form.tzLocal` | Байгаа газрынхаа цагаар | Time where I am | |
| `form.tzHint` | Гадаадад явахдаа эмчтэйгээ ярилцаж сонгоно уу. | When travelling abroad, decide this with your doctor. | |
| `form.disclaimer` | Тун, хуваарийг эмчийнхээ хамгийн сүүлийн зааврын дагуу оруулна уу. Апп тун санал болгохгүй, шалгахгүй. | Enter the dose and schedule from your doctor's latest instructions. The app does not suggest or check doses. | |
| `form.save` | Хадгалах | Save | |
| `form.errors.name` | Эмийн нэрээ бичнэ үү. | Enter the medicine name. | |
| `form.errors.time` | Дор хаяж нэг цаг сонгоно уу. | Choose at least one time. | |
| `form.errors.amount` | Тоо буруу байна. 2, 1,5 эсвэл 1.5 гэж бичнэ үү. 1,000 мэт мянгатын тусгаарлагч хэрэглэхгүй. | Not a valid number. Write 2, 1.5 or 1,5. Do not use thousands separators like 1,000. | |
| `form.errors.amountAll` | Тунг бүх цагт бичих эсвэл аль нэгэнд ч бичихгүй байна уу. | Enter a dose for every time, or for none. | |
| `form.errors.unit` | Нэгжээ сонгоно уу. | Choose a unit. | |
| `form.errors.unitOther` | Нэгжийн нэрээ бичнэ үү. | Enter the unit name. | |
| `form.errors.days` | Дор хаяж нэг өдөр сонгоно уу. | Choose at least one day. | |
| `form.errors.duplicate` | Нэг цагийг хоёр удаа сонгосон байна. | The same time is chosen twice. | |
| `form.errors.summary` | Тэмдэглэсэн талбаруудыг засна уу. | Please correct the marked fields. | |
| `form.errors.date` | Огноогоо сонгоно уу. | Choose a date. | |
| `form.timeLabel` | {n}-р цаг | Time {n} | |
| `form.more` | Нэмэлт мэдээлэл (сонголттой) | More details (optional) | |
| `form.amountUnit` | {n}-р цагийн тун ({unit}) | Dose at time {n} ({unit}) | |
| `form.results` | {n} илэрц | {n} results | |
| `form.category.question` | Энэ эм дархлаа дарангуйлагч эсвэл уух/тарих стероид даавар (жишээ нь преднизолон, метилпреднизолон) мөн үү? | Is this medicine an immunosuppressant or a steroid hormone taken by mouth or injection (for example prednisolone, methylprednisolone)? | |
| `form.category.immunosuppressant` | Дархлаа дарангуйлагч | Immunosuppressant | |
| `form.category.corticosteroid` | Стероид даавар (уух/тарих) | Steroid hormone (by mouth or injection) | |
| `form.category.other` | Үгүй, бусад эм | No, another medicine | |
| `form.category.unknown` | Мэдэхгүй | I don't know | |
| `form.category.why` | Каталогоос сонгоогүй эмийн төрлийг апп нэрээр нь таамаглахгүй. Дархлаа дарангуйлагч, стероидыг яаралтай картад тунтай нь харуулна. Мэдэхгүй бол эмчээсээ асуугаад дараа нь эмийн хуудаснаас сонгож болно. | The app never guesses what a medicine typed by hand is from its name. Immunosuppressants and steroids are shown with their dose on the emergency card. If you are not sure, ask your doctor and choose later on the medicine's page. | |
| `units.mg` | мг | mg | |
| `units.mcg` | мкг | mcg | |
| `units.g` | г | g | |
| `units.ml` | мл | ml | |
| `units.iu` | ОУН | IU | |
| `units.unit` | нэгж | unit | |
| `units.tablet` | шахмал | tablet | |
| `units.capsule` | капсул | capsule | |
| `units.drop` | дусал | drop | |
| `units.puff` | шүршилт | puff | |
| `units.sachet` | уут | sachet | |
| `units.patch` | наалт | patch | |
| `units.other` | Бусад | Other | |
| `weekday.1` | Даваа | Monday | |
| `weekday.2` | Мягмар | Tuesday | |
| `weekday.3` | Лхагва | Wednesday | |
| `weekday.4` | Пүрэв | Thursday | |
| `weekday.5` | Баасан | Friday | |
| `weekday.6` | Бямба | Saturday | |
| `weekday.7` | Ням | Sunday | |
| `detail.title` | Эмийн дэлгэрэнгүй | Medicine details | |
| `detail.currentDose` | Одоогийн тун | Current dose | |
| `detail.nextDose` | {date}-нээс эхлэх тун | Dose from {date} | |
| `detail.voidNext` | Энэ өөрчлөлтийг буруу оруулсан | This change was entered by mistake | |
| `detail.voidReason` | Шалтгаан (заавал) | Reason (required) | |
| `detail.voidConfirm` | Буруу гэж тэмдэглэх | Mark as a mistake | |
| `detail.history` | Тунгийн түүх | Dose history | |
| `detail.from` | {date}-нээс | From {date} | |
| `detail.voided` | Буруу оруулсан гэж тэмдэглэсэн | Marked as entered by mistake | |
| `detail.changeDose` | Тун өөрчлөх | Change the dose | |
| `detail.stop` | Уухаа больсон | Stopped taking it | |
| `detail.stoppedOn` | Уухаа больсон анхны өдөр | First day no longer taken | |
| `detail.stopReason` | Шалтгаан (сонголттой) | Reason (optional) | |
| `detail.stoppedText` | {date}-нээс уугаагүй | Not taken since {date} | |
| `detail.courseEnds` | Курс {date}-нд дуусна | Course ends on {date} | |
| `detail.delete` | Эмийг түүхтэй нь устгах | Delete the medicine and its history | |
| `detail.deleteConfirm` | Энэ эм, түүний тунгийн түүх, тэмдэглэлүүд бүгд устна. Буцаах боломжгүй. | This medicine, its dose history and records will all be deleted. This cannot be undone. | |
| `detail.deleteYes` | Тийм, устгах | Yes, delete | |
| `detail.notFound` | Эм олдсонгүй. | Medicine not found. | |
| `detail.reminderOn` | Сануулга асаалттай | Reminders on | |
| `detail.reminderOff` | Сануулга унтраалттай | Reminders off | |
| `detail.stopTitle` | Эмийг зогсоох | Stop this medicine | |
| `detail.stopSave` | Уухаа больсон гэж хадгалах | Save as stopped | |
| `detail.stopNote` | Хадгалсны дараа энэ эмийн сануулга зогсоно. | Once saved, reminders for this medicine stop. | |
| `change.title` | Тун өөрчлөх | Change the dose | |
| `change.effectiveFrom` | Шинэ тун хэзээнээс | New dose from | |
| `change.note` | Шалтгаан (сонголттой) | Reason (optional) | |
| `change.latest` | Эмчийн хамгийн сүүлийн зааврыг оруулна уу. Хуучин тун түүхэнд хадгалагдана. | Enter your doctor's latest instructions. The old dose stays in the history. | |
| `failed.title` | Хадгалагдаагүй тэмдэглэл | Records not saved | |
| `failed.item` | {time} {name}: сервер хүлээж аваагүй. | {time} {name}: not accepted by the server. | |
| `failed.dismiss` | Ойлголоо | Got it | |
| `notify.channel` | Эмийн сануулга | Medicine reminders | |
| `notify.title` | Эм уух цаг боллоо | Time for your medicine | |
| `notify.timedTitle` | {time}-ийн эмийн сануулга | {time} medicine reminder | |
| `notify.count` | {n} тун | {n, plural, one {# dose} other {# doses}} | |
| `notify.item` | {name} {amount} | {name} {amount} | |
| `notify.taken` | Уусан | Taken | |
| `notify.takenAll` | Бүгдийг уусан | All taken | |
| `notify.snooze` | 10 мин дараа | In 10 min | |
| `notify.renewTitle` | Сануулгаа сэргээх цаг боллоо | Time to renew your reminders | |
| `notify.renewBody` | Апп-аа нээж сануулгаа сэргээнэ үү. | Open the app to renew your reminders. | |
| `notify.apptTitle` | Танд товлол байна | You have an appointment | |
| `notify.ubTime` | {time} (Улаанбаатарын цагаар) | {time} (Ulaanbaatar time) | |
| `reminders.title` | Сануулга | Reminders | |
| `reminders.open` | Сануулга | Reminders | |
| `reminders.openHint` | Түгжээтэй дэлгэц, цагийн бүс | Lock screen, time zone | |
| `reminders.showNames` | Мэдэгдэлд эмийн нэрийг харуулах | Show medicine names in reminders | |
| `reminders.showNamesHint` | Анхдагчаар унтраалттай: мэдэгдэлд зөвхөн «Эм уух цаг боллоо» гэж гарна. Асаавал утсыг тань харсан хүн эмийн нэрийг харж болно. | Off by default: reminders only say “Time for your medicine”. When on, anyone who sees your phone may see the medicine names. | |
| `reminders.zoneNow` | Сануулгын цагийн бүс: {zone} | Reminder time zone: {zone} | |
| `reminders.zoneHome` | «Улаанбаатарын цагаар» гэж тохируулсан эмүүд үргэлж Улаанбаатарын цагаар сануулна. | Medicines set to “Ulaanbaatar time” always remind on Ulaanbaatar time. | |
| `reminders.showDetails` | Товлолын сануулгад нэр, газрыг харуулах | Show the appointment's name and place in reminders | |
| `reminders.showDetailsHint` | Анхдагчаар унтраалттай: товлолын сануулгад зөвхөн «Танд товлол байна» болон цаг гарна. Асаавал утсыг тань харсан хүн товлолын нэр (жишээ нь биопси), газрыг харж болно. | Off by default: appointment reminders only say “You have an appointment” and the time. When on, anyone who sees your phone may see the appointment's name (for example a biopsy) and place. | |
| `zone.askTitle` | Цагийн бүс өөрчлөгдсөн байна | Your time zone has changed | |
| `zone.askBody` | Утас тань одоо {zone} цагийн бүсэд байна. «Байгаа газрынхаа цагаар» гэж тохируулсан эмүүдийн сануулгыг энэ цагаар шилжүүлэх үү? Тунгийн хоорондын завсрыг эмчтэйгээ ярилцана уу. | Your phone is now in the {zone} time zone. Move reminders of medicines set to “Time where I am” to this time? Talk about the time between doses with your doctor. | |
| `zone.switch` | Шилжүүлэх | Move | |
| `zone.keep` | Өөрчлөхгүй | Don't change | |
| `zone.failed` | Цагийн бүсийг хадгалж чадсангүй. Дахин оролдоно уу. | Could not save the time zone. Try again. | |
| `health.notificationsOff` | Эмийн сануулга ажиллахгүй байна: апп-ын мэдэгдэл унтраалттай. Эмээ хуваарийнхаа дагуу уусаар байгаарай. | Medicine reminders are not working: notifications are off for the app. Keep taking your medicines on your schedule. | |
| `health.notificationsOn` | Мэдэгдлийг асаах | Turn on notifications | |
| `health.exactOff` | Эмийн сануулга хоцорч болно — нэг цаг, заримдаа түүнээс ч их: «Сэрүүлэг ба сануулга» зөвшөөрөл өгөөгүй байна. | Medicine reminders may come late - by an hour, sometimes more: the “Alarms & reminders” permission is not given. | |
| `health.exactMore` | Тайлбар ба тохиргоо | Explanation and settings | |
| `health.exactTitle` | Сануулга яг цагтаа ирэх | Reminders on time | |
| `health.exactBody` | Эмийн сануулга цагтаа ирэхийн тулд Android-ийн «Сэрүүлэг ба сануулга» (Alarms & reminders) зөвшөөрөл хэрэгтэй. Зөвшөөрөөгүй бол сануулга ирсээр байх боловч Android түүнийг нэг цаг, заримдаа түүнээс ч удаан хойшлуулж болно. | For medicine reminders to come on time, Android needs the “Alarms & reminders” permission. Without it reminders still come, but Android may delay them by an hour or more. | |
| `health.exactAllow` | Зөвшөөрөл өгөх | Give permission | |
| `health.exactOk` | ✓ Сануулга яг цагтаа ирнэ. | ✓ Reminders come on time. | |
| `health.batteryTitle` | Батарей хэмнэлт | Battery saving | |
| `health.batteryBody` | Зарим утас батарей хэмнэхийн тулд апп-ын сануулгыг саатуулдаг. Сануулга хоцорч эсвэл огт ирэхгүй бол энэ апп-ыг батарей хэмнэлтээс чөлөөлнө үү. Цэс, шошгын нэр утасны загвар, хувилбараас хамаарч өөр байж болно: | Some phones delay app reminders to save battery. If reminders come late or not at all, exempt this app from battery saving. Menu and label names differ by phone model and version: | |
| `health.batterySamsung` | Samsung: Тохиргоо → Апп → LabTrack → Батарей → «Хязгааргүй» (Unrestricted). | Samsung: Settings → Apps → LabTrack → Battery → “Unrestricted”. | |
| `health.batteryXiaomi` | Xiaomi: Тохиргоо → Апп → Апп удирдах → LabTrack → Батарей хэмнэгч → «Хязгаарлалтгүй» (No restrictions); мөн «Автоматаар эхлэх» (Autostart)-ыг асаана. | Xiaomi: Settings → Apps → Manage apps → LabTrack → Battery saver → “No restrictions”, and turn on “Autostart”. | |
| `health.batteryOppo` | Oppo / Realme: Тохиргоо → Апп → Апп удирдах → LabTrack → Батарейн хэрэглээ → «Арын дэвсгэрт ажиллахыг зөвшөөрөх» (Allow background activity). | Oppo / Realme: Settings → Apps → App management → LabTrack → Battery usage → “Allow background activity”. | |
| `health.batteryOther` | Бусад утас: Тохиргоо → Апп → LabTrack → Батарей → хязгаарлалтгүй. | Other phones: Settings → Apps → LabTrack → Battery → unrestricted. | |
| `health.openSettings` | Апп-ын тохиргоог нээх | Open the app's settings | |
| `zoneWait` | {names} — тухайн газрын цагаар уудаг эм. Цагийн бүсийн мэдээлэл ачаалагдсаны дараа өнөөдрийн тун нь энд гарна. | {names}: taken by local time. Today's doses show here once the time zone is loaded. | |

## Асран хамгаалагч, тунгийн мэдэгдэл

Хянагч: эмч. Түлхүүр: `app.caregivers` (71).

| Түлхүүр | Монгол | English | Санал |
|---|---|---|---|
| `title` | Асран хамгаалагчид | Caregivers | |
| `rowOwner` | Асран хамгаалагчид | Caregivers | |
| `rowOwnerHint` | Урих, мэдэгдлийг түр зогсоох, эрх цуцлах | Invite, pause alerts, end access | |
| `rowCaregiver` | Миний мэдэгдэл | My alerts | |
| `rowCaregiverHint` | Эм уусан тэмдэглэл бүртгэгдээгүй үед хэзээ мэдэгдэх | When to hear about a dose not logged | |
| `intro` | Асран хамгаалагч таны профайлыг харж, бичлэг нэмж, эм уусан тэмдэглэл бүртгэгдээгүй үед мэдэгдэл авч болно. Хуваалцах, устгах эрхгүй. Мэдэгдэл ирээгүй нь эм уусан гэсэн үг биш. | A caregiver can see your profile, add records and be notified when a dose has not been logged. They cannot share or delete. No alert does not mean a dose was taken. | |
| `ownerOnly` | Асран хамгаалагчдыг зөвхөн профайлын эзэн удирдана. | Only the profile's owner manages its caregivers. | |
| `minor` | Хүүхдийн профайлд одоогоор асран хамгаалагч урих боломжгүй. | Caregivers cannot be invited to a child's profile yet. | |
| `listTitle` | Асран хамгаалагчид | Caregivers | |
| `none` | Одоогоор асран хамгаалагч алга. | No caregivers yet. | |
| `since` | Хэзээнээс: {date} | Since {date} | |
| `alerts.on` | Мэдэгдэл: эм уусан тэмдэглэл {minutes} минут бүртгэгдээгүй бол | Alerts: if a dose is not logged within {minutes} minutes | |
| `alerts.off` | Мэдэгдэл: унтраалттай (асран хамгаалагч өөрөө сонгоно) | Alerts: off (the caregiver chooses) | |
| `alerts.paused` | Мэдэгдэл: таны түр зогсоосон — сэргээх хүртэл ирэхгүй | Alerts: paused by you — none until you resume | |
| `pause` | Мэдэгдлийг түр зогсоох | Pause alerts | |
| `resume` | Мэдэгдлийг сэргээх | Resume alerts | |
| `pauseLabel` | Мэдэгдлийг түр зогсоох — {name} | Pause alerts to {name} | |
| `resumeLabel` | Мэдэгдлийг сэргээх — {name} | Resume alerts to {name} | |
| `end.button` | Эрхийг цуцлах | End access | |
| `end.title` | Асран хамгаалагчийн эрхийг цуцлах: {name} | End caregiver access: {name} | |
| `end.body` | Тэр таны профайлыг цааш харах, мэдэгдэл авах боломжгүй болно. Дахин хуваалцахын тулд та шинээр урих хэрэгтэй. Аль хэдийн харсан мэдээллийг буцаах боломжгүй. | They will no longer see your profile or get alerts. To share again, you need to invite them anew. What they have already seen cannot be taken back. | |
| `end.confirm` | Цуцлах | End | |
| `pendingTitle` | Хүлээгдэж буй урилга | Pending invitations | |
| `expires` | {date} хүртэл хүчинтэй | Valid until {date} | |
| `cancelInvite` | Урилгыг цуцлах | Cancel invitation | |
| `cancelInviteLabel` | Урилгыг цуцлах — {username} | Cancel the invitation to {username} | |
| `invite.title` | Урих | Invite | |
| `invite.hint` | Асран хамгаалагчийнхаа LabTrack хэрэглэгчийн нэрийг бичнэ үү. Тэр зөвшөөрсний дараа л таны профайлд хандана. | Enter your caregiver's LabTrack username. They get access only after they accept. | |
| `invite.username` | Хэрэглэгчийн нэр | Username | |
| `invite.invalid` | Хэрэглэгчийн нэр 3–32 тэмдэгт: латин жижиг үсэг, тоо, цэг, доогуур зураас. | A username is 3–32 characters: lowercase Latin letters, digits, dots, underscores. | |
| `invite.button` | Урих | Invite | |
| `invite.checkTitle` | Хэрэглэгчийн нэрээ шалгана уу | Check the username | |
| `invite.checkBody` | «{username}» — зөв үү? Буруу бичвэл таны нэр өөр хүнд урилга болон очиж болно. | “{username}” — is this right? A wrong one could send your name to someone else as an invitation. | |
| `invite.send` | Илгээх | Send | |
| `invite.sent` | Илгээгдлээ. Хэрэглэгчийн нэр зөв бол урилга дээрх жагсаалтад харагдана. | Sent. If the username is right, the invitation shows in the list above. | |
| `invite.needsConsent` | Урихын өмнө «Асран хамгаалагчтай хуваалцах» зөвшөөрлөө өгнө үү. | Before inviting, give the “Sharing with caregivers” consent. | |
| `invite.openConsents` | Зөвшөөрөл рүү очих | Go to consents | |
| `invitations.title` | Асран хамгаалагчийн урилга | Caregiver invitations | |
| `invitations.open` | Асран хамгаалагчийн урилга | Caregiver invitations | |
| `invitations.openHint` | Танд ирсэн урилгууд | Invitations you received | |
| `invitations.none` | Одоогоор урилга алга. | No invitations. | |
| `invitations.from` | {name} таныг асран хамгаалагчаар урьж байна | {name} invites you to be a caregiver | |
| `invitations.expires` | {date} хүртэл хүчинтэй | Valid until {date} | |
| `invitations.accept` | Зөвшөөрөх | Accept | |
| `invitations.decline` | Татгалзах | Decline | |
| `invitations.declineLabel` | Урилгаас татгалзах — {name} | Decline the invitation from {name} | |
| `invitations.acceptTitle` | Урилгыг зөвшөөрөх — {name} | Accept the invitation from {name} | |
| `invitations.acceptBody` | Та тухайн профайлын шинжилгээ, эм, шилжүүлэн суулгалт, яаралтай картын мэдээллийг харж, бичлэг нэмж чадна; хуваалцах, устгах эрхгүй. Мэдэгдлээ дараа нь өөрөө тохируулна. Хүссэн үедээ гарч болно. | You will see that profile's lab results, medicines, transplant and emergency card information and can add records; you cannot share or delete. You set your own alerts afterwards. You can leave at any time. | |
| `alertSettings.title` | Миний мэдэгдэл | My alerts | |
| `alertSettings.delay` | Эм уусан тэмдэглэл хэр удаан бүртгэгдээгүй бол мэдэгдэх вэ | How long a dose may go unlogged before you are alerted | |
| `alertSettings.minutes` | {minutes} минут | {minutes} minutes | |
| `alertSettings.off` | Мэдэгдэхгүй | No alerts | |
| `alertSettings.shortNote` | Утасны сануулга 10 хүртэл минут хоцорч болох тул 15–20 минут сонговол өвчтөн тэмдэглэж амжаагүй үед ч мэдэгдэл ирж болно. | Phone reminders can be up to 10 minutes late, so with 15–20 minutes an alert may come before the patient had time to log the dose. | |
| `alertSettings.watched` | Хянагдаж буй эм: {count} | Medicines watched: {count} | |
| `alertSettings.onlyReminders` | Зөвхөн сануулга нь асаалттай эмийг хянана. Сануулгагүй эм мэдэгдэлд орохгүй. | Only medicines with reminders on are watched. Medicines without reminders give no alerts. | |
| `alertSettings.noAlertNote` | Мэдэгдэл ирээгүй нь эм уусан гэсэн үг биш, мэдэгдэл ирсэн нь уугаагүй гэсэн үг биш — зөвхөн апп-д тэмдэглэгдсэн эсэхийг харуулна. | No alert does not mean a dose was taken, and an alert does not mean it was not — it only shows whether it was logged in the app. | |
| `alertSettings.paused` | Профайлын эзэн таны мэдэгдлийг түр зогсоосон байна. | The profile's owner has paused your alerts. | |
| `alertSettings.save` | Хадгалах | Save | |
| `alertSettings.saved` | Хадгалагдлаа. | Saved. | |
| `alertSettings.leave` | Асран хамгаалагчаас гарах | Stop being a caregiver | |
| `alertSettings.leaveTitle` | Асран хамгаалагчаас гарах: {name} | Stop being a caregiver: {name} | |
| `alertSettings.leaveBody` | Та энэ профайлыг цааш харах, мэдэгдэл авах боломжгүй болно. Эргэж орохын тулд эзэн шинээр урина. | You will no longer see this profile or get alerts. To come back, the owner invites you anew. | |
| `alertSettings.leaveConfirm` | Гарах | Stop | |
| `alertSettings.notCaregiver` | Та энэ профайлын асран хамгаалагч биш байна. | You are not a caregiver of this profile. | |
| `alertSettings.changed` | Энэ дэлгэцийг нээсний дараа профайл солигдсон. Буцаад дахин нээнэ үү. | The profile changed after this screen was opened. Go back and open it again. | |
| `alertSettings.watchedNone` | Одоогоор хянагдаж буй эм алга, тиймээс мэдэгдэл ирэхгүй. | No medicines are watched right now, so no alerts will come. | |
| `alertSettings.latePhone` | Профайлын эзний утас эмийн сануулгыг цагт нь харуулж чадахгүй байж магадгүй («Сэрүүлэг ба сануулга» зөвшөөрөл унтраалттай). Тиймээс эзэнд сануулга хүрэхээс өмнө танд мэдэгдэл очихгүйн тулд мэдэгдэл эм уух товлосон цагаас хамгийн багадаа 90 минутын дараа ирнэ. | The profile owner's phone may not be able to show medicine reminders on time (the "Alarms & reminders" permission is off). So that you are not alerted before the reminder reaches them, alerts come at least 90 minutes after the scheduled time. | |
| `reminderOffNote` | Энэ эмийн сануулга унтраалттай тул асран хамгаалагчийн мэдэгдэл энэ эмд ажиллахгүй. | This medicine's reminders are off, so caregivers get no alerts for it. | |
| `pauseTitle` | Мэдэгдлийг түр зогсоох — {name} | Pause alerts — {name} | |
| `pauseBody` | Сэргээх хүртэл тэр эм уусан тэмдэглэл бүртгэгдээгүй үед мэдэгдэл авахгүй. | Until you resume, they get no alert when a dose has not been logged. | |
| `changed` | Энэ дэлгэцийг нээсний дараа профайл солигдсон. Буцаад дахин нээнэ үү. | The profile changed after this screen was opened. Go back and open it again. | |

## Шилжүүлэн суулгалт

Хянагч: эмч. Түлхүүр: `app.transplant` (116).

| Түлхүүр | Монгол | English | Санал |
|---|---|---|---|
| `title` | Шилжүүлэн суулгалт | Transplant | |
| `listTitle` | Шилжүүлэн суулгалтууд | Transplants | |
| `open` | Шилжүүлэн суулгалт | Transplant | |
| `openHint` | Эрхтэн, огноо, эмнэлэг, донор | Organ, date, hospital, donor | |
| `add` | Шилжүүлэн суулгалт нэмэх | Add a transplant | |
| `empty` | Шилжүүлэн суулгалтын мэдээлэл алга. Нэмбэл эм, шинжилгээг түүнтэй холбож хянахад тустай. | No transplant recorded yet. Adding it helps you follow medications and tests against it. | |
| `editTitle` | Шилжүүлэн суулгалт засах | Edit transplant | |
| `wizardIntro` | Шилжүүлэн суулгалтынхаа үндсэн мэдээллийг оруулна уу. Мэдэхгүй зүйлээ алгасаж, дараа нь нөхөж болно. | Enter the main facts of your transplant. Skip anything you do not know and add it later. | |
| `step` | Алхам {current} / {total} | Step {current} of {total} | |
| `next` | Үргэлжлүүлэх | Continue | |
| `back` | Өмнөх алхам | Previous step | |
| `skip` | Одоохондоо алгасах | Skip for now | |
| `skipHint` | Дараа нь Тохиргоо → Шилжүүлэн суулгалт хэсгээс нэмж болно. | You can add it later in Settings → Transplant. | |
| `save` | Хадгалах | Save | |
| `saved` | Шилжүүлэн суулгалт хадгалагдлаа. | Transplant saved. | |
| `anotherQuestion` | Өөр шилжүүлэн суулгалт (дахин шилжүүлэн суулгалт) бий юу? | Have you had another transplant (a re-transplant)? | |
| `anotherYes` | Тийм, нэмэх | Yes, add it | |
| `anotherNo` | Үгүй, дууслаа | No, done | |
| `delete` | Устгах | Delete | |
| `deleteConfirmTitle` | Энэ шилжүүлэн суулгалтыг устгах уу? | Delete this transplant? | |
| `deleteConfirmBody` | Бүртгэл бүрмөсөн устна. Холбогдсон эмүүд үлдэнэ. | The record is deleted for good. Linked medications stay. | |
| `organ.question` | Ямар эрхтэн шилжүүлэн суулгуулсан бэ? | Which organ did you receive? | |
| `organ.kidney` | Бөөр | Kidney | |
| `organ.liver` | Элэг | Liver | |
| `organ.heart` | Зүрх | Heart | |
| `organ.lung` | Уушги | Lung | |
| `organ.pancreas` | Нойр булчирхай | Pancreas | |
| `organ.kidney_pancreas` | Бөөр + нойр булчирхай | Kidney + pancreas | |
| `organ.intestine` | Гэдэс | Intestine | |
| `organ.cornea` | Эвэрлэг бүрхүүл | Cornea | |
| `organ.hsct` | Цусны үүдэл эс | Stem cells (blood) | |
| `organ.other` | Бусад | Other | |
| `organ.detail` | Нэмэлт тодорхойлолт (сонголттой) | More detail (optional) | |
| `organ.detailHint` | Жишээ нь: зүүн бөөр, элэгний баруун дэлбэн | For example: left kidney, right liver lobe | |
| `organ.required` | Эрхтнээ сонгоно уу. | Choose the organ. | |
| `date.question` | Хэзээ шилжүүлэн суулгуулсан бэ? | When was the transplant? | |
| `date.precision` | Огноогоо хэр нарийн мэдэх вэ? | How exactly do you know the date? | |
| `date.day` | Яг өдрөөр | The exact day | |
| `date.month` | Он, сараар | Year and month | |
| `date.year` | Зөвхөн оноор | The year only | |
| `date.pick` | Огноо сонгох | Choose the date | |
| `date.picked` | Огноо: {date} | Date: {date} | |
| `date.year_label` | Он | Year | |
| `date.month_label` | Сар | Month | |
| `date.required` | Огноогоо сонгоно уу. | Choose the date. | |
| `date.yearHint` | 4 оронтой он, жишээ нь 2019 | 4 digits, for example 2019 | |
| `date.yearInvalid` | {from}–{to} оны хооронд он бичнэ үү. | Enter a year from {from} to {to}. | |
| `date.monthName` | {n}-р сар | Month {n} | |
| `date.done` | Болсон | Done | |
| `place.question` | Хаана шилжүүлэн суулгуулсан бэ? | Where was the transplant? | |
| `place.country` | Улс | Country | |
| `place.city` | Хот (сонголттой) | City (optional) | |
| `place.hospital` | Эмнэлэг | Hospital | |
| `place.hospitalRequired` | Эмнэлгийн нэрийг бичнэ үү. | Enter the hospital's name. | |
| `place.recent` | Өмнө оруулсан эмнэлэг: | Hospitals entered before: | |
| `place.otherCountry` | Бусад улс | Another country | |
| `place.countryCode` | Улсын код (2 латин үсэг) | Country code (2 Latin letters) | |
| `place.countryCodeHint` | Жишээ нь: MY (Малайз), VN (Вьетнам) | For example: MY (Malaysia), VN (Vietnam) | |
| `place.countryCodeInvalid` | 2 латин үсгээр бичнэ үү. | Use 2 Latin letters. | |
| `place.choose` | {label}: {value} | {label}: {value} | |
| `country.MN` | Монгол | Mongolia | |
| `country.KR` | Солонгос | South Korea | |
| `country.IN` | Энэтхэг | India | |
| `country.CN` | Хятад | China | |
| `country.TR` | Турк | Türkiye | |
| `country.RU` | Орос | Russia | |
| `country.JP` | Япон | Japan | |
| `country.DE` | Герман | Germany | |
| `country.US` | АНУ | United States | |
| `country.TH` | Тайланд | Thailand | |
| `country.SG` | Сингапур | Singapore | |
| `country.KZ` | Казахстан | Kazakhstan | |
| `donor.question` | Донор хэн байсан бэ? | Who was the donor? | |
| `donor.living_related` | Амьд донор — хамаатан | Living donor - a relative | |
| `donor.living_unrelated` | Амьд донор — хамаатан бус | Living donor - not a relative | |
| `donor.deceased_dbd` | Нас барсан донор (тархины үхэл) | Deceased donor (brain death) | |
| `donor.deceased_dcd` | Нас барсан донор (зүрх зогссон) | Deceased donor (circulatory death) | |
| `donor.unknown` | Мэдэхгүй | I do not know | |
| `donor.relation` | Донорын хамаарал (сонголттой) | Relation to you (optional) | |
| `donor.relationHint` | Жишээ нь: ах, ээж, эхнэр | For example: brother, mother, wife | |
| `extra.question` | Нэмэлт мэдээлэл (сонголттой) | More details (optional) | |
| `extra.intro` | Мэдэхгүй бол хоосон орхино уу. Шилжүүлэн суулгалтын бичиг баримтаасаа харж нөхөж болно. | Leave blank what you do not know. Your transplant papers may have it. | |
| `extra.show` | Нэмэлт мэдээлэл нээх | Show more details | |
| `extra.hide` | Нэмэлт мэдээлэл хаах | Hide more details | |
| `extra.recipientBlood` | Таны цусны бүлэг | Your blood group | |
| `extra.donorBlood` | Донорын цусны бүлэг | Donor's blood group | |
| `extra.notSet` | Сонгоогүй | Not set | |
| `extra.cmvDonor` | CMV — донор | CMV - donor | |
| `extra.cmvRecipient` | CMV — та | CMV - you | |
| `extra.pos` | Эерэг (+) | Positive (+) | |
| `extra.neg` | Сөрөг (−) | Negative (−) | |
| `extra.unknown` | Мэдэхгүй | Unknown | |
| `extra.hla` | HLA зөрүү (жишээ нь 3/6) | HLA mismatch (for example 3/6) | |
| `extra.induction` | Индукц эмчилгээ (жишээ нь басиликсимаб) | Induction therapy (for example basiliximab) | |
| `extra.primaryDisease` | Шилжүүлэн суулгахад хүргэсэн өвчин | Disease that led to the transplant | |
| `extra.dialysis` | Шилжүүлэн суулгалтаас өмнөх диализ | Dialysis before the transplant | |
| `extra.followUpCenter` | Хянадаг эмнэлэг | Follow-up hospital | |
| `extra.followUpDoctor` | Хянагч эмч | Follow-up doctor | |
| `extra.notes` | Тэмдэглэл | Notes | |
| `summary.since` | Ойролцоогоор {years} жил {months} сар өнгөрсөн | About {years} y {months} mo ago | |
| `summary.sinceExact` | {years} жил {months} сар өнгөрсөн | {years} y {months} mo ago | |
| `summary.sinceYearOnly` | {year} онд | in {year} | |
| `summary.sinceMonths` | {months} сар өнгөрсөн | {months, plural, one {# month} other {# months}} ago | |
| `summary.number` | {number}-р шилжүүлэн суулгалт | Transplant no. {number} | |
| `summary.sinceMonthsApprox` | Ойролцоогоор {months} сар өнгөрсөн | About {months, plural, one {# month} other {# months}} ago | |
| `summary.sinceDays` | {days} хоног өнгөрсөн | {days, plural, one {# day} other {# days}} ago | |
| `summary.sinceMonthOnly` | {year} оны {month}-р сард | In {month}/{year} | |
| `saveNow` | Хадгалах | Save | |
| `addMore` | Нэмэлт мэдээлэл нэмэх | Add more details | |
| `skipConfirmTitle` | Оруулсан мэдээллээ хадгалахгүй алгасах уу? | Skip without saving what you entered? | |
| `skipConfirmBody` | Бөглөсөн мэдээлэл хадгалагдахгүй. | What you filled in will not be saved. | |
| `skipConfirm` | Алгасах | Skip | |
| `unsavedTitle` | Хадгалаагүй өөрчлөлт байна | Unsaved changes | |
| `unsavedBody` | Гарвал өөрчлөлт хадгалагдахгүй. | If you leave, the changes are not saved. | |
| `discard` | Хадгалахгүй гарах | Leave without saving | |
| `fixErrors` | Улаанаар тэмдэглэсэн талбаруудыг засна уу. | Fix the fields marked in red. | |

## Амин үзүүлэлт, эрүүл мэндийн бүртгэл

Хянагч: эмч. Түлхүүр: `app.health` (155).

| Түлхүүр | Монгол | English | Санал |
|---|---|---|---|
| `title` | Профайл | Profile | |
| `transplants` | Шилжүүлэн суулгалт | Transplants | |
| `appointments` | Товлол | Appointments | |
| `vitals` | Амин үзүүлэлт | Vitals | |
| `events` | Эмчилгээ, үйл явдал | Treatments and events | |
| `allergies` | Харшил | Allergies | |
| `contacts` | Яаралтай холбоо барих | Emergency contacts | |
| `questions` | Эмчээс асуух асуулт | Questions for the doctor | |
| `nextAppointment` | Дараагийн товлол: {when} | Next appointment: {when} | |
| `noAppointment` | Товлол алга | No appointments | |
| `noAllergy` | Харшил тэмдэглээгүй | No allergies recorded | |
| `contactCount` | {n} хүн | {n, plural, one {# person} other {# people}} | |
| `openQuestions` | {n} асуулт асуугаагүй | Questions not asked yet: {n} | |
| `openQuestionsNone` | Асуугаагүй асуулт алга | No open questions | |
| `add` | Нэмэх | Add | |
| `save` | Хадгалах | Save | |
| `delete` | Устгах | Delete | |
| `deleteConfirm` | Энэ бичлэгийг устгах уу? Буцаах боломжгүй. | Delete this record? This cannot be undone. | |
| `deleteYes` | Тийм, устгах | Yes, delete | |
| `empty` | Одоогоор бичлэг алга. | Nothing recorded yet. | |
| `notFound` | Бичлэг олдсонгүй. | Record not found. | |
| `required` | Энэ талбарыг бөглөнө үү. | Fill in this field. | |
| `summary` | Тэмдэглэсэн талбаруудыг засна уу. | Please correct the marked fields. | |
| `event.new` | Үйл явдал нэмэх | Add an event | |
| `event.edit` | Үйл явдал | Event | |
| `event.kind` | Төрөл | Kind | |
| `event.kinds.biopsy` | Биопси | Biopsy | |
| `event.kinds.rejection` | Татгалзал | Rejection | |
| `event.kinds.infection` | Халдвар | Infection | |
| `event.kinds.hospitalization` | Хэвтэн эмчлүүлэлт | Hospital stay | |
| `event.kinds.dialysis` | Диализ | Dialysis | |
| `event.kinds.plasmapheresis` | Плазмаферез | Plasmapheresis | |
| `event.kinds.ivig` | IVIG | IVIG | |
| `event.kinds.surgery` | Мэс засал | Surgery | |
| `event.kinds.procedure` | Ажилбар | Procedure | |
| `event.kinds.vaccination` | Вакцин | Vaccination | |
| `event.kinds.complication` | Хүндрэл | Complication | |
| `event.kinds.other` | Бусад | Other | |
| `event.title` | Гарчиг | Title | |
| `event.titleHint` | Жишээ нь «Бөөрний биопси» | For example “Kidney biopsy” | |
| `event.startedOn` | Эхэлсэн өдөр | Started on | |
| `event.endedOn` | Дууссан өдөр (сонголттой) | Ended on (optional) | |
| `event.place` | Газар (сонголттой) | Place (optional) | |
| `event.description` | Тайлбар (сонголттой) | Description (optional) | |
| `event.outcome` | Үр дүн (эмчийн хэлснээр, сонголттой) | Outcome (as your doctor said, optional) | |
| `allergy.new` | Харшил нэмэх | Add an allergy | |
| `allergy.edit` | Харшил | Allergy | |
| `allergy.substance` | Юунд харшилтай вэ | Allergic to | |
| `allergy.substanceHint` | Эм, хоол, бодис — жишээ нь пенициллин | A medicine, food or substance — for example penicillin | |
| `allergy.reaction` | Ямар урвал гардаг (сонголттой) | Reaction (optional) | |
| `allergy.severity` | Хүнд эсэх (сонголттой) | Severity (optional) | |
| `allergy.severities.mild` | Хөнгөн | Mild | |
| `allergy.severities.moderate` | Дунд зэрэг | Moderate | |
| `allergy.severities.severe` | Хүнд | Severe | |
| `allergy.severities.unknown` | Мэдэхгүй | Unknown | |
| `allergy.notedOn` | Тэмдэглэсэн өдөр (сонголттой) | Noted on (optional) | |
| `contact.new` | Холбоо барих хүн нэмэх | Add a contact | |
| `contact.edit` | Холбоо барих хүн | Contact | |
| `contact.name` | Нэр | Name | |
| `contact.relation` | Хэн болох (сонголттой) | Who they are (optional) | |
| `contact.relationHint` | Жишээ нь ах, эхнэр | For example brother, wife | |
| `contact.phone` | Утас | Phone | |
| `contact.phoneHint` | Жишээ нь +976 9911 2233 | For example +976 9911 2233 | |
| `contact.phoneInvalid` | Утасны дугаар буруу байна. | Not a valid phone number. | |
| `contact.center` | Шилжүүлэн суулгалтын төв | Transplant centre | |
| `contact.call` | Залгах — {name} | Call {name} | |
| `contact.centerMark` | Шилжүүлэн суулгалтын төв | Transplant centre | |
| `contact.callFailed` | Залгаж чадсангүй. Утасны дугаар: {phone} | Could not call. The number: {phone} | |
| `appointment.new` | Товлол нэмэх | Add an appointment | |
| `appointment.edit` | Товлол | Appointment | |
| `appointment.kind` | Төрөл | Kind | |
| `appointment.kinds.lab` | Шинжилгээ | Lab test | |
| `appointment.kinds.clinic_visit` | Үзлэг | Clinic visit | |
| `appointment.kinds.biopsy` | Биопси | Biopsy | |
| `appointment.kinds.imaging` | Дүрс оношилгоо | Imaging | |
| `appointment.kinds.other` | Бусад | Other | |
| `appointment.title` | Гарчиг | Title | |
| `appointment.titleHint` | Жишээ нь «Такролимусын түвшин» | For example “Tacrolimus level” | |
| `appointment.date` | Өдөр | Date | |
| `appointment.time` | Цаг | Time | |
| `appointment.place` | Газар (сонголттой) | Place (optional) | |
| `appointment.notes` | Тэмдэглэл (сонголттой) | Notes (optional) | |
| `appointment.remind` | Сануулах | Remind me | |
| `appointment.offsets.0` | Цагт нь | At the time | |
| `appointment.offsets.60` | 1 цагийн өмнө | 1 hour before | |
| `appointment.offsets.120` | 2 цагийн өмнө | 2 hours before | |
| `appointment.offsets.1440` | 1 өдрийн өмнө | 1 day before | |
| `appointment.status` | Төлөв | Status | |
| `appointment.statuses.planned` | Товлосон | Planned | |
| `appointment.statuses.done` | Болсон | Done | |
| `appointment.statuses.cancelled` | Цуцалсан | Cancelled | |
| `appointment.remindHint` | Сануулга энэ утсанд ирнэ. Түгжээтэй дэлгэцэнд товлолын нэр харагдахгүй (Тохиргоо → Сануулга). | Reminders come on this phone. The lock screen does not show the appointment's name (Settings → Reminders). | |
| `question.new` | Асуулт нэмэх | Add a question | |
| `question.edit` | Асуулт | Question | |
| `question.text` | Асуулт | Question | |
| `question.answer` | Хариулт (эмчийн хэлснээр, сонголттой) | Answer (as your doctor said, optional) | |
| `question.appointment` | Аль товлолд асуух (сонголттой) | Which appointment (optional) | |
| `question.noAppointment` | Товлолгүй | No appointment | |
| `question.status` | Төлөв | Status | |
| `question.statuses.open` | Асуугаагүй | Not asked yet | |
| `question.statuses.answered` | Хариулсан | Answered | |
| `question.statuses.dropped` | Хэрэггүй болсон | No longer needed | |
| `vital.title` | Амин үзүүлэлт | Vitals | |
| `vital.latest` | Сүүлийн утгууд | Latest values | |
| `vital.recent` | Сүүлийн 90 хоног | Last 90 days | |
| `vital.add` | Хэмжилт нэмэх | Add a reading | |
| `vital.choose` | Юу хэмжсэн бэ? | What did you measure? | |
| `vital.kinds.bp` | Даралт | Blood pressure | |
| `vital.kinds.bp_systolic` | Дээд даралт | Upper pressure | |
| `vital.kinds.bp_diastolic` | Доод даралт | Lower pressure | |
| `vital.kinds.pulse` | Судасны цохилт | Pulse | |
| `vital.kinds.weight` | Жин | Weight | |
| `vital.kinds.temperature` | Биеийн халуун | Body temperature | |
| `vital.kinds.glucose` | Цусан дахь сахар | Blood glucose | |
| `vital.kinds.spo2` | Хүчилтөрөгч (SpO2) | Oxygen (SpO2) | |
| `vital.kinds.urine_output` | Шээсний хэмжээ (энэ удаагийн) | Urine (this time) | |
| `vital.kinds.fluid_intake` | Уусан шингэн (энэ удаагийн) | Fluid drunk (this time) | |
| `vital.units.mmHg` | мм МУБ | mmHg | |
| `vital.units.bpm` | цохилт/мин | bpm | |
| `vital.units.kg` | кг | kg | |
| `vital.units.C` | °C | °C | |
| `vital.units.mmol_L` | ммоль/л | mmol/L | |
| `vital.units.percent` | % | % | |
| `vital.units.ml` | мл | ml | |
| `vital.value` | {kind} ({unit}) | {kind} ({unit}) | |
| `vital.systolic` | Дээд даралт (мм МУБ) | Upper pressure (mmHg) | |
| `vital.diastolic` | Доод даралт (мм МУБ) | Lower pressure (mmHg) | |
| `vital.pulseOptional` | Судасны цохилт (цохилт/мин, сонголттой) | Pulse (bpm, optional) | |
| `vital.note` | Тэмдэглэл (сонголттой) | Note (optional) | |
| `vital.save` | Хадгалах | Save | |
| `vital.queueFull` | Сүлжээгүй удсан тул хадгалах зай дүүрсэн. Сүлжээнд холбогдоод дахин оролдоно уу. | Offline for too long: there is no room to keep more. Connect and try again. | |
| `vital.reading` | {value} {unit} | {value} {unit} | |
| `vital.bpReading` | {sys}/{dia} мм МУБ | {sys}/{dia} mmHg | |
| `vital.glucoseAsk` | Таны сахар хэмжигч ямар нэгжээр харуулдаг вэ? | Which unit does your glucose meter show? | |
| `vital.glucoseMmol` | ммоль/л (жишээ нь 5,6) | mmol/L (for example 5.6) | |
| `vital.glucoseMgdl` | мг/дл (жишээ нь 100) | mg/dL (for example 100) | |
| `vital.glucoseMgdlNote` | Энэ апп сахарыг зөвхөн ммоль/л-ээр хадгална. Мг/дл-ээр харуулсан утгыг энд оруулахгүй. Хэмжигчээ ммоль/л болгох талаар эмчээсээ асууна уу. | This app keeps glucose in mmol/L only. A value shown in mg/dL is not entered here. Ask your doctor about setting your meter to mmol/L. | |
| `vital.noValue` | Утга оруулаагүй | No value entered | |
| `vital.deleteReading` | Устгах — {what} | Delete — {what} | |
| `vital.plausibleOnly` | Апп утгыг үнэлэхгүй, зөвхөн бичилтийн алдааг шалгана. | The app does not judge values; it only checks for typos. | |
| `vital.refused` | Сүлжээгүй үед оруулсан хэмжилтийг сервер хүлээж аваагүй ({what}) — буруу бичигдсэн байж магадгүй. Дахин оруулна уу. | A reading entered offline was not accepted by the server ({what}) — it may have been mistyped. Enter it again. | |
| `vital.refusedDismiss` | Ойлголоо | Got it | |
| `vital.glucoseUnitIs` | Таны хэмжигч ммоль/л-ээр харуулдаг гэж тэмдэглэсэн. | You noted that your meter shows mmol/L. | |
| `vital.glucoseChange` | Нэгжийг өөрчлөх | Change the unit | |
| `vital.pendingSome` | {n} хэмжилт сүлжээнд холбогдмогц илгээгдэнэ. | {n, plural, one {# reading} other {# readings}} will be sent once connected. | |
| `vital.waiting` | Илгээхийг хүлээж байна | Waiting to be sent | |
| `vital.chartKind` | Аль үзүүлэлт | Which reading | |
| `vital.chartLabel` | {kind}-ийн график, {count} хэмжилт. Хэмжилт бүр доорх жагсаалтад байна. | Chart of {kind}, {count} readings. Every reading is in the list below. | |
| `vital.chartBpLegend` | Тасралтгүй шугам, тойрог — дээд даралт; тасархай шугам, гурвалжин — доод даралт. | Solid line, circles: systolic; dashed line, triangles: diastolic. | |
| `vital.chartPeriod` | Сүүлийн 90 хоногийн хэмжилт. Шээс, шингэний нэг удаагийн хэмжээг графикт оруулаагүй — жагсаалтад бий. | Readings of the last 90 days. One-off urine and fluid amounts are not charted - they are in the list. | |
| `loadFailed` | Ачаалж чадсангүй | Could not load | |
| `deleteTitle` | «{name}»-г устгах уу? | Delete “{name}”? | |
| `groups.care` | Шилжүүлэн суулгалт ба эмчилгээ | Transplant and care | |
| `groups.health` | Эрүүл мэнд | Health | |
| `groups.people` | Хүмүүс | People | |

## Амин үзүүлэлтийн алдааны мессеж (сахарын нэгж г.м.)

Хянагч: эмч, лабын эмч. Түлхүүр: `error.vital` (6).

| Түлхүүр | Монгол | English | Санал |
|---|---|---|---|
| `not_found` | Энэ хэмжилт олдсонгүй. | This reading was not found. | |
| `implausible` | Энэ тоо буруу бичигдсэн байж магадгүй. Дахин шалгаад оруулна уу. | This number may have been mistyped. Check it and enter it again. | |
| `format` | Тоо буруу байна. Жишээ нь 128 эсвэл 36,6 гэж бичнэ үү. | Not a valid number. Write it like 128 or 36.6. | |
| `too_many` | Сонгосон хугацаанд хэт олон хэмжилт байна. Богино хугацаа сонгоно уу. | There are too many readings in this period. Choose a shorter one. | |
| `glucose_unit` | Сахарыг ммоль/л-ээр оруулна уу (жишээ нь 5,6). Таны багаж мг/дл харуулдаг бол тэр тоог энд бүү оруулаарай. | Enter glucose in mmol/L (e.g. 5.6). If your meter shows mg/dL, do not enter that number here. | |
| `bp_order` | Дээд даралт доод даралтаас их байх ёстой. Талбарууд солигдсон эсэхийг шалгана уу. | The upper pressure must be higher than the lower one. Check whether the fields are swapped. | |

## Яаралтай карт

Хянагч: эмч. Түлхүүр: `app.emergency` (91).

| Түлхүүр | Монгол | English | Санал |
|---|---|---|---|
| `title` | Яаралтай тусламжийн карт | Emergency card | |
| `open` | Яаралтай | Emergency | |
| `openLabel` | Яаралтай тусламжийн карт нээх | Open the emergency card | |
| `switchTo` | English | Монгол | |
| `switchToLabel` | Show the card in English | Картыг монголоор харуулах | |
| `introTransplant` | Би шилжүүлэн суулгалт хийлгэсэн. | I have had a transplant. | |
| `name` | Нэр | Name | |
| `birthDate` | Төрсөн огноо | Date of birth | |
| `transplants` | Шилжүүлэн суулгалт | Transplants | |
| `graft.functioning` | Ажиллаж байгаа | Functioning | |
| `graft.unknown` | Төлөв бүртгэгдээгүй | Status not recorded | |
| `graft.failed` | Ажиллахаа больсон | No longer functioning | |
| `graft.removed` | Мэс заслаар авсан | Removed (graftectomy) | |
| `followUp` | Хяналтын эмнэлэг, эмч: {value} | Follow-up: {value} | |
| `bloodType` | Цусны бүлэг | Blood type | |
| `bloodNote` | Хэрэглэгчийн бүртгэлээс. Цус сэлбэхийн өмнө лабораторийн шинжилгээгээр баталгаажуулна уу. | As recorded by the user. Confirm by laboratory testing before any transfusion. | |
| `bloodConflict` | Бүртгэлд зөрүүтэй тул харуулаагүй. Лабораторид тодорхойлно уу. | Not shown: the records disagree. Determine by laboratory testing. | |
| `bloodHsct` | Цусны үүдэл эс шилжүүлэн суулгасны дараа цусны бүлэг өөрчлөгдсөн байж болох тул харуулаагүй. Лабораторид тодорхойлно уу. | Not shown: the blood type may have changed after a stem cell transplant. Determine by laboratory testing. | |
| `meds` | Тогтмол уудаг эм | Regular medicines | |
| `category.immunosuppressant` | Дархлаа дарангуйлагч | Immunosuppressant | |
| `category.corticosteroid` | Кортикостероид | Corticosteroid | |
| `doseNote` | Тунг хэрэглэгч эмчийн зааврын дагуу гэж бүртгэсэн; одоогийн жортой зөрж болно. | Doses as entered by the user from their doctor's instructions; may differ from the current prescription. | |
| `noDose` | Тун бүртгэгдээгүй | No dose recorded | |
| `upcoming` | {date} өдрөөс эхлэх тун: {dose} | Planned from {date}: {dose} | |
| `endsOn` | Төлөвлөсөн дуусах огноо: {date} | Planned end: {date} | |
| `noDosed` | Дархлаа дарангуйлагч, кортикостероид эм апп-д бүртгэгдээгүй — уудаггүй гэсэн үг биш. | No immunosuppressant or corticosteroid recorded in the app — this does not mean none are taken. | |
| `otherMeds` | Бусад эм | Other medicines | |
| `allergies` | Харшил | Allergies | |
| `noAllergy` | Харшлын мэдээлэл оруулаагүй — харшилгүй гэсэн үг биш. | No allergy information entered — this does not mean no allergies. | |
| `contacts` | Холбоо барих | Contacts | |
| `notRecorded` | Бүртгэгдээгүй. | Not recorded. | |
| `updated` | Шинэчилсэн: {when} | Updated: {when} | |
| `offline` | Сервертэй холбогдож чадсангүй. Утсанд хадгалсан хувилбар ({when}) — хуучирсан байж болно. | Could not reach the server. Showing the copy saved on this phone ({when}) — it may be out of date. | |
| `noCopy` | Карт утсан дээр хараахан хадгалагдаагүй байна. Интернэтэд холбогдоод дахин оролдоно уу. | The card is not saved on this phone yet. Connect to the internet and try again. | |
| `disclaimer` | Мэдээллийг хэрэглэгч өөрөө оруулсан, эмчээр баталгаажаагүй. Оношилгоо, эмчилгээний зөвлөмж биш. | Entered by the user, not verified by a doctor. Not a diagnosis or treatment advice. | |
| `introImmunosuppressed` | Дархлаа дарангуйлах эм тогтмол уудаг. | I take immunosuppressant medicines regularly. | |
| `graftLabel` | Шилжүүлэн суулгасан эрхтэн: {status} | Graft: {status} | |
| `noProfile` | Таны эрүүл мэндийн профайл хараахан үүсээгүй байна. Шилжүүлэн суулгалтын мэдээллээ оруулсны дараа карт гарна. | Your health profile has not been created yet. The card appears once your transplant details are entered. | |
| `backToLock` | Түгжээний дэлгэц рүү буцах | Back to the lock screen | |
| `saved` | Утсанд хадгалсан хувилбар ({when}) — хуучирсан байж болно. | Copy saved on this phone ({when}) — it may be out of date. | |
| `unlocked.openHint` | Түгжээтэй үед картыг нээх эсэх | Whether the card opens while the app is locked | |
| `unlocked.body` | Асаавал аппын биометр түгжээний дэлгэц дээр «🆘 Яаралтай» товч гарч, утсанд хадгалсан яаралтай картыг аппын түгжээг тайлалгүйгээр нээнэ. Утасны өөрийн түгжээг (PIN, хурууны хээ) тайлсны дараа л энэ товч харагдана. Хэзээ ч дахин унтрааж болно. | When on, the app's lock screen shows a “🆘 Emergency” button that opens the emergency card saved on this phone without unlocking the app. It is only reachable after the phone's own lock (PIN, fingerprint) is passed. You can turn it off at any time. | |
| `unlocked.risk` | Анхаар: утсыг тайлсан хэн ч (гэр бүлийн гишүүн, утсаа алдвал олсон хүн) энэ картыг харна: нэр, төрсөн огноо, эм, харшил, шилжүүлэн суулгалт, холбоо барих хүмүүсийн утасны дугаар. Аппын бусад мэдээлэл түгжээтэй хэвээр үлдэнэ. | Note: anyone who can unlock your phone (a family member, someone who finds a lost phone) will be able to see this card: your name, date of birth, medicines, allergies, transplants and your contacts' phone numbers. The rest of the app stays locked. | |
| `unlocked.switch` | Түгжээтэй үед яаралтай картыг нээх | Open the emergency card while locked | |
| `unlocked.noProfile` | Эрүүл мэндийн профайл үүссэний дараа тохируулж болно. | You can set this once your health profile exists. | |
| `unlocked.failed` | Тохиргоог хадгалж чадсангүй. Дахин оролдоно уу. | Could not save the setting. Please try again. | |
| `unlocked.noLock` | Биометр түгжээ унтраалттай тул карт Нүүр дээрх «🆘 Яаралтай» товчоор аль хэдийн нээгдэнэ. | The biometric lock is off, so the card already opens with the “🆘 Emergency” button on Home. | |
| `unlocked.phoneLock` | Утасны өөрийн түгжээтэй дэлгэц дээр апп юу ч харуулж чадахгүй. Тэнд зориулж iPhone-ийн Medical ID, Android-ийн «Яаралтай мэдээлэл»-д мэдээллээ гараар нэмж болно. | No app can show anything on the phone's own lock screen. For that, you can add your details by hand to Medical ID on iPhone or Emergency information on Android. | |
| `unlocked.view` | Яаралтай картыг харах | View the emergency card | |
| `unlocked.offerTitle` | Яаралтай үед картаа нээлттэй болгох уу? | Make your card available in an emergency? | |
| `unlocked.offerYes` | Асаах | Turn on | |
| `unlocked.offerNo` | Одоо биш | Not now | |
| `unlocked.offerLater` | Дараа нь Тохиргоо → Яаралтай тусламжийн картаас өөрчилж болно. | You can change this later in Settings → Emergency card. | |
| `lockOpen` | 🆘 Яаралтай · Emergency | 🆘 Emergency | |
| `lockOpenLabel` | Яаралтай тусламжийн карт нээх. Open the emergency card | Open the emergency card | |
| `export.wallet` | Түрийвчний карт (PDF) | Wallet card (PDF) | |
| `export.walletLabel` | Түрийвчний картыг PDF-ээр үүсгэж хэвлэх, хадгалах | Make the wallet card as a PDF to print or save | |
| `export.wallpaper` | Түгжээтэй дэлгэцийн зураг | Lock screen wallpaper | |
| `export.wallpaperHint` | Утас түгжээтэй байхад ч харагдана | Visible even while the phone is locked | |
| `export.medicalId` | iPhone Medical ID, Android яаралтай мэдээлэл | iPhone Medical ID, Android emergency information | |
| `export.medicalIdHint` | Утасны өөрийн яаралтай мэдээлэлд гараар нэмэх заавар | How to add it by hand to the phone's own emergency information | |
| `export.failed` | Файлыг үүсгэж чадсангүй. Дахин оролдоно уу. | Could not make the file. Please try again. | |
| `export.unavailable` | Энэ утсан дээр хуваалцах боломжгүй байна. | Sharing is not available on this phone. | |
| `wallpaper.warning` | Энэ зургийг түгжээтэй дэлгэцэнд тавибал утсыг барьсан хэн ч түгжээ тайлалгүйгээр таны эм, харшил, шилжүүлэн суулгалт, холбоо барих хүмүүсийн нэр, утасны дугаарыг харна. | As a lock screen wallpaper, this image shows anyone holding the phone, without unlocking it, your medicines, allergies, transplant and your contacts' names and phone numbers. | |
| `wallpaper.intro` | Доорх зураг яг хадгалагдах хэлбэр. Нэр, төрсөн огноо анхдагчаар ороогүй. | The image below is exactly what will be saved. Your name and date of birth are left out by default. | |
| `wallpaper.showName` | Нэрийг оруулах | Include my name | |
| `wallpaper.showBirthDate` | Төрсөн огноог оруулах | Include my date of birth | |
| `wallpaper.inEnglish` | Зургийг англиар харуулах | Show the image in English | |
| `wallpaper.inMongolian` | Зургийг монголоор харуулах | Show the image in Mongolian | |
| `wallpaper.tooLong` | Бүх мэдээлэл зурагт багтсангүй: доод хэсэг нь таслагдана. Үлдсэнийг түрийвчний карт болон аппын картаас харна уу. | Not everything fits on the image: the bottom is cut off. The wallet card and the card in the app show the rest. | |
| `wallpaper.share` | Зургийг хуваалцах, хадгалах | Share and save the image | |
| `wallpaper.howTo` | Хуваалцах цонхноос iPhone-д «Зураг хадгалах» (Save Image), Android-д «Зургийн санд хадгалах» эсвэл «Файлд хадгалах»-ыг сонгоод, утасны Тохиргоо → Дэлгэцийн зураг хэсгээс түгжээтэй дэлгэцэд тавина. Апп өөрөө зургийн санд юу ч хадгалахгүй. Эм, харшил өөрчлөгдвөл зургийг дахин үүсгэнэ үү. | In the share sheet choose “Save Image” on iPhone, or “Save to Photos” / “Save to Files” on Android, then set it as the lock screen in the phone's Settings → Wallpaper. The app saves nothing to your photos itself. Make a new image when your medicines or allergies change. | |
| `wallpaper.failed` | Зургийг үүсгэж чадсангүй. Дахин оролдоно уу. | Could not make the image. Please try again. | |
| `wallpaper.unavailable` | Энэ утсан дээр хуваалцах боломжгүй байна. | Sharing is not available on this phone. | |
| `wallpaper.previewLabel` | Түгжээтэй дэлгэцийн зургийн урьдчилсан харагдац | Preview of the lock screen image | |
| `wallpaper.shareNote` | Хуваалцахаасаа өмнө: энэ зураг түгжээтэй дэлгэцэд нээлттэй харагдана. Зургийн санд хадгалбал iCloud, Google Photos-той ижилсэж болно. | Before sharing: this image will be visible on the locked screen. Saved to your photos, it may sync to iCloud or Google Photos. | |
| `medicalId.intro` | Утасны өөрийн яаралтай мэдээлэл түгжээтэй дэлгэцээс нээгддэг. Апп тэнд өөрөө бичиж чадахгүй тул доорх текстийг гараар хуулж оруулна уу. | The phone's own emergency information opens from the lock screen. No app can write there itself, so copy the text below by hand. | |
| `medicalId.iosTitle` | iPhone — Medical ID | iPhone — Medical ID | |
| `medicalId.ios1` | 1. «Health» (Эрүүл мэнд) апп-ыг нээж, «Summary» (Хураангуй) таб дээрх баруун дээд буланд байрлах зураг дээрээ дарна. | 1. Open the Health app and, on the “Summary” tab, tap your picture at the top right. | |
| `medicalId.ios2` | 2. «Medical ID» → «Edit»-ийг сонгоно. | 2. Choose “Medical ID” → “Edit”. | |
| `medicalId.ios3` | 3. Medical Conditions, Medications, Allergies & Reactions, Blood Type хэсэгт доорх текстийг хуулна. Emergency Contacts-д хүмүүсээ утасны Харилцагчаас нэмнэ. | 3. Copy the text below into Medical Conditions, Medications, Allergies & Reactions and Blood Type. Add people under Emergency Contacts from your contacts. | |
| `medicalId.ios4` | 4. «Show When Locked» болон «Share During Emergency Call»-ыг асааж, «Done» дарна. | 4. Turn on “Show When Locked” and “Share During Emergency Call”, then tap “Done”. | |
| `medicalId.androidTitle` | Android — Яаралтай мэдээлэл | Android — Emergency information | |
| `medicalId.android1` | 1. Тохиргоо → «Safety & emergency» (Samsung: «Safety and emergency» → «Medical info») → «Medical information»-ийг нээнэ. Нэр нь утасны загвар, хэлнээс хамаарч өөр байж болно. | 1. Open Settings → “Safety & emergency” (Samsung: “Safety and emergency” → “Medical info”) → “Medical information”. The names differ between phone makers and languages. | |
| `medicalId.android2` | 2. Эм, харшил, цусны бүлэг, тэмдэглэлд доорх текстийг хуулна. Яаралтай холбоо барих хүмүүсээ нэмнэ. | 2. Copy the text below into medicines, allergies, blood type and notes. Add your emergency contacts. | |
| `medicalId.android3` | 3. Түгжээтэй дэлгэцээс (эсвэл яаралтай дуудлагаас) харагдах сонголтыг асаана. Нэр нь утасны загвараас хамаарна. | 3. Turn on showing it from the lock screen (or the emergency call screen). The name depends on the phone. | |
| `medicalId.copyTitle` | Хуулах текст | Text to copy | |
| `medicalId.noCard` | Карт хараахан хадгалагдаагүй байна. Интернэтэд холбогдоод дахин нээнэ үү. | The card is not saved yet. Connect to the internet and open this again. | |
| `medicalId.keepCurrent` | Утасны энэ мэдээлэл автоматаар шинэчлэгдэхгүй: эм, харшил өөрчлөгдвөл гараар засна уу. Хуулж дууссаны дараа хуулсан текстээ (clipboard) цэвэрлэвэл зүгээр. | The phone does not update this by itself: change it by hand when your medicines or allergies change. After copying, you may want to clear your clipboard. | |
| `medicalId.inEnglish` | Текстийг англиар харуулах | Show the text in English | |
| `medicalId.inMongolian` | Текстийг монголоор харуулах | Show the text in Mongolian | |

## Апп-ын тухай (зориулалт, хийдэггүй зүйлс)

Хянагч: эмч. Түлхүүр: `app.about` (15).

| Түлхүүр | Монгол | English | Санал |
|---|---|---|---|
| `title` | Апп-ын тухай | About the app | |
| `open` | Апп-ын тухай | About the app | |
| `hint` | Зориулалт, нууцлалын бодлого, тусламж | Purpose, privacy policy, help | |
| `purposeTitle` | Энэ апп юунд зориулагдсан бэ | What this app is for | |
| `purpose` | LabTrack MN нь эрхтэн шилжүүлэн суулгуулсан хүмүүст эрүүл мэндийн мэдээллээ цэгцлэх, хадгалах, хянах, өөрөө тохируулсан эмийн сануулга авах, уусан тунгаа тэмдэглэх, яаралтай тусламжийн карт хадгалах, сонгосон асран хамгаалагчтайгаа хуваалцахад туслах хэрэгсэл юм. | LabTrack MN helps people who have had an organ transplant keep their health information in order, store and follow it, get the medicine reminders they set themselves, record the doses they take, keep an emergency card and share with a caregiver they choose. | |
| `notTitle` | Энэ апп юу хийдэггүй вэ | What this app does not do | |
| `not` | Оношилгоо хийхгүй, эмчилгээ болон эмийн тун санал болгохгүй, эмийн харилцан үйлчлэлийг шалгахгүй. Эмчийн зөвлөгөөг орлохгүй. Эмээ өөрчлөх, зогсоохоосоо өмнө эмчдээ хандана уу. | It does not diagnose, does not suggest treatment or medicine doses, and does not check medicine interactions. It does not replace your doctor's advice. Talk to your doctor before you change or stop a medicine. | |
| `reliability` | Эмийн сануулга утасны тохиргоо, батарей хэмнэлтээс болж хоцорч эсвэл ирэхгүй байж болно. Асран хамгаалагчийн мэдэгдэл ч баталгаатай биш. Эмээ эмчийн зааврын дагуу цагт нь уугаарай. | Medicine reminders can come late or not at all because of phone settings or battery saving. Caregiver notifications are not guaranteed either. Take your medicines on time as your doctor told you. | |
| `emergency` | Биеийн байдал гэнэт муудвал 103 руу залгана уу, эсвэл ойрын эмнэлэгт хандана уу. Апп-ын сануулга, мэдэгдэл яаралтай тусламжийг орлохгүй. | If you suddenly feel much worse, call 103 or go to the nearest hospital. The app's reminders and notifications do not replace emergency care. | |
| `call103` | 103 руу залгах | Call 103 | |
| `privacyTitle` | Нууцлал | Privacy | |
| `privacy` | Нууцлалын бодлого | Privacy policy | |
| `privacyFailed` | Холбоосыг нээж чадсангүй. Интернэтээ шалгаад дахин оролдоно уу. | The link could not be opened. Check your internet connection and try again. | |
| `support` | Тусламж | Help | |
| `version` | Хувилбар {version} | Version {version} | |

## Web-ээр хуваалцсан мэдээлэл (эмч харна)

Хянагч: эмч, лабын эмч. Түлхүүр: `web.share` (51).

| Түлхүүр | Монгол | English | Санал |
|---|---|---|---|
| `title` | Хуваалцсан эрүүл мэндийн мэдээлэл | Shared health record | |
| `intro` | Профайлын эзнээс авсан 6 оронтой PIN кодоо оруулна уу. | Enter the 6-digit PIN you got from the profile's owner. | |
| `pin` | PIN код | PIN | |
| `pinHint` | PIN кодыг линкээс тусад нь (жишээ нь амаар) өгдөг. 5 удаа буруу оруулбал линк хаагдана. | The PIN is given separately from the link (for example, said aloud). The link closes after 5 wrong PINs. | |
| `open` | Нээх | Open | |
| `opening` | Нээж байна… | Opening… | |
| `openFailed` | Линк эсвэл PIN код буруу, эсвэл линкийн хугацаа дууссан байна. Профайлын эзнээс шалгуулна уу. | The link or PIN is wrong, or the link has ended. Ask the profile's owner to check. | |
| `tooMany` | Хэт олон оролдлого. Түр хүлээгээд дахин оролдоно уу. | Too many attempts. Please wait a while and try again. | |
| `noLink` | Линк бүтэн биш байна. Профайлын эзнээс авсан линкээ бүтнээр нь нээнэ үү. | The link is incomplete. Open the whole link you got from the profile's owner. | |
| `endedTitle` | Үзэх хугацаа дууссан | Viewing has ended | |
| `ended` | Та харахаа дуусгалаа. Дахин харахын тулд линкээ PIN кодоор дахин нээнэ үү. | You finished viewing. To see it again, open the link with its PIN. | |
| `noSession` | Үзэх хугацаа дууссан эсвэл линк хаагдсан байна. Линкээ PIN кодоор дахин нээнэ үү. | Viewing time is over or the link was closed. Open the link again with its PIN. | |
| `recordOf` | {name} — хуваалцсан мэдээлэл | {name} — shared record | |
| `until` | {time} хүртэл харах боломжтой | Viewable until {time} | |
| `range` | {from} – {to} хоорондох мэдээлэл | Records from {from} to {to} | |
| `disclaimer` | Энэ мэдээллийг өвчтөн өөрөө оруулж, шинжилгээний хариуг өөрөө хянаж баталсан. Тэмдэглэгээг тухайн лабын лавлах хэмжээтэй харьцуулан гаргасан — үнэлгээ биш. Эмнэлгийн шийдвэр гаргахдаа эх баримт, лабораторийн хариутай тулгана уу. | This information was entered by the patient, who also checked and confirmed the lab results. Flags compare each value with that lab's own range — they are not an assessment. For clinical decisions, check against the source documents and the lab's own reports. | |
| `end` | Харахаа дуусгах | Finish viewing | |
| `sections.summary` | Тойм | Summary | |
| `sections.labs` | Шинжилгээний хариу | Lab results | |
| `sections.meds` | Эм | Medicines | |
| `sections.transplant` | Шилжүүлэн суулгалт | Transplant | |
| `sections.events` | Үйл явдал | Events | |
| `sections.vitals` | Амин үзүүлэлт | Vital signs | |
| `birthDate` | Төрсөн огноо | Date of birth | |
| `allergies` | Харшил | Allergies | |
| `noAllergies` | Харшил бүртгээгүй. | No allergy recorded. | |
| `none` | Бүртгэл алга. | Nothing recorded. | |
| `organ` | Эрхтэн | Organ | |
| `date` | Огноо | Date | |
| `transplantField.hospital` | Эмнэлэг | Hospital | |
| `transplantField.donor` | Донорын төрөл | Donor type | |
| `transplantField.bloodTypes` | Цусны бүлэг (хүлээн авагч / донор) | Blood group (recipient / donor) | |
| `transplantField.cmv` | CMV (хүлээн авагч / донор) | CMV (recipient / donor) | |
| `transplantField.ebv` | EBV (хүлээн авагч / донор) | EBV (recipient / donor) | |
| `transplantField.primaryDisease` | Үндсэн өвчин | Primary disease | |
| `transplantField.induction` | Индукц эмчилгээ | Induction therapy | |
| `transplantField.graft` | Шилжүүлсэн эрхтний байдал | Graft status | |
| `transplantField.followUp` | Хяналтын эмнэлэг, эмч | Follow-up centre, doctor | |
| `medDates` | {from} – {to} | {from} – {to} | |
| `doseFrom` | {date} · {dose} | {date} · {dose} | |
| `when` | Хэзээ | When | |
| `test` | Шинжилгээ | Test | |
| `value` | Утга (хэвлэснээр) | Value (as printed) | |
| `reference` | Лабын лавлах | Lab's range | |
| `flag` | Лабын лавлахтай харьцуулсан | Against the lab's range | |
| `measure` | Үзүүлэлт | Measure | |
| `critical` | Критик: {text} | Critical: {text} | |
| `medSince` | {from}-с хойш | Since {from} | |
| `rangeFrom` | {from}-с хойших мэдээлэл | Records from {from} | |
| `rangeTo` | {to} хүртэлх мэдээлэл | Records up to {to} | |
| `notShared` | Энэ линкээр хуваалцаагүй хэсэг: {sections}. | Not shared by this link: {sections}. | |

