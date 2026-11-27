# 05 — Шинжилгээний хариу задлах pipeline (v4, Python)

## Зарчим
1. **AI гаралт = draft.** Хүн баталсан утга л дашбоардад.
2. **Зохиохоос "мэдэхгүй" дээр.** Уншигдахгүй бол `null`.
3. **Лавлах ба критик хязгаар баримтаас.** Баримтад байхгүй бол `no_reference` — каталогоос нөхөхгүй.
4. **Эх сурвалж хадгалах:** хуудас, эх текстийн хэсэг, эх утга/нэгж/хязгаар.
5. **Тооцоолол AI биш:** нэгж, flag, харьцуулалт → `labtrack.core` (цэвэр Python, hypothesis тест).

## Celery task: `extract_document(document_id, actor_user_id)`
Queue: `extraction` (concurrency тохиргоотой), retry: 3 (exponential backoff, зөвхөн түр алдаанд — 429/5xx/timeout).

```
1. load       : DB (RLS context = actor_user_id), S3-аас файл
2. guard      : ai_processing зөвшөөрөл, хуудас ≤ 30, хэмжээ, status → processing
3. preprocess : (extraction/preprocess.py)
   Зураг : Pillow + pillow-heif → EXIF transpose → RGB
           OpenCV: бүдгэрэл (Laplacian variance), гэрэлтэлт, хазайлт засах
           quality_score < босго → хэрэглэгчид "дахин зураг авах" санал (гэхдээ үргэлжлүүлнэ)
           API-ийн санал болгосон хэмжээнд resize; маш нягт хүснэгт бол хэсэгчлэн (tile)
   PDF   : pdfplumber → текст давхарга (has_text_layer), мөр бүрийн текст
           pypdfium2 → хуудас бүрийг PNG (review дэлгэц ба шаардлагатай бол AI-д)
4. extract    : Claude API (extraction/llm.py)
           PDF → document блок; зураг → image блок
           tool use: `record_lab_report`, input_schema = Pydantic model-оос үүсгэсэн (seed/extraction.schema.json-тэй ижил)
           temperature 0; system prompt + schema-д prompt caching
5. parse      : Pydantic-аар шалгах; алдаатай бол алдааг хавсаргаж 1 удаа дахин хүсэх
6. validate   : (доорх хүснэгт) → мөр бүрт issues[]
7. normalize  : тест таних → нэгж → хязгаар хөрвүүлэх → flag
8. persist    : нэг transaction: lab_reports + lab_results + extraction_runs + audit
9. notify     : status → needs_review; Redis pub/sub → SSE → web
              критик утга илэрсэн бол `has_unconfirmed_critical = true` → тусгай мэдэгдэл (доор)
```

## Загвар сонголт
- `EXTRACTION_MODEL` (анхдагч: Claude Sonnet-ийн сүүлийн хувилбар), `ESCALATION_MODEL` (Opus).
- Escalation: дундаж confidence < 0.8, эсвэл issue-тэй мөр > 20%, эсвэл Pydantic 2 удаа бүтэлгүйтвэл.
- Загварын нэрийг Anthropic docs-оос шалгаж env-д. Кодонд hard-code хийхгүй.

## Системийн prompt (ноорог — `extraction/prompts/v1.md`)
```
Та эмнэлгийн лабораторийн шинжилгээний хариуг бүтэцтэй өгөгдөл болгох мэргэжилтэн.
Баримт монгол (кирилл), орос, англи эсвэл холимог хэлтэй байж болно.

ДҮРЭМ:
- Зөвхөн баримтад БИЧИГДСЭН зүйлийг гарга. Таамаглах, тооцоолох, нөхөх ХОРИОТОЙ.
- Утгыг яг бичигдсэнээр raw_value-д ("<0.5", "12,4", "Сөрөг", "++").
- value_numeric: аравтын таслалыг цэг болгох (12,4 → 12.4) л зөвшөөрнө, өөр хөрвүүлэлтгүй.
- Нэгжийг яг бичигдсэнээр.
- ЛАВЛАХ ХЯЗГААР: тухайн мөрийн лавлах утгыг ref_text-д яг хуулж, ref_low/ref_high-д задал.
  "< 5" → ref_high=5; "> 1.0" → ref_low=1.0; "3.5-5.1" → 3.5 ба 5.1.
  Хүйс/насаар олон хязгаар бичигдсэн бол ref_text-д бүгдийг хуулж, ref_low/high-г хоосон үлдээ.
- КРИТИК ХЯЗГААР: баримтад "критик/panic/тревожные/критические значения" гэх мэт
  багана, тайлбар эсвэл доод хэсэгт бичигдсэн бол тухайн тестэд critical_text, critical_low,
  critical_high-д. Баримтын ерөнхий критик утгын жагсаалт байвал critical_legend-д.
- Баримт дээрх H/L/↑/↓/*/!/тодруулсан тэмдгийг lab_flag-д.
- Огноо: raw-г хуул; ISO-д хөрвүүлэхдээ өдөр/сар тодорхойгүй бол date_ambiguous=true.
- Нэг баримтад олон огноо/тайлан байвал reports-д тусад нь.
- Хувийн мэдээллээс зөвхөн нэр, нас/төрсөн огноо, хүйс. РД-г гаргахгүй.
- Уншигдахгүй бол null, confidence бага. ХЭЗЭЭ Ч ЗОХИОХГҮЙ.
record_lab_report хэрэгслийг ЗААВАЛ нэг удаа дууд.
```

## Баталгаажуулалт (`extraction/validate.py`)
| Шалгалт | Үр дүн |
|---|---|
| Эх текстэд тулгах (текст PDF): raw_value, ref_text эх текстэд байгаа эсэх | Байхгүй → confidence × 0.5, `not_in_source` |
| Физиологийн боломжит хязгаар (`physio_min/max`) | `implausible` (таслал/нэгжийн алдаа) |
| Хязгаарын логик: ref_low ≥ ref_high, утга хязгаараас 1000 дахин зөрүүтэй | `ref_suspicious` |
| Лабын тэмдэг ↔ тооцоолсон flag | `flag_mismatch` (жишээ: лаб H гэсэн ч утга хүрээнд) |
| Нэгж мэдэгдэх эсэх | `unknown_unit` |
| Огноо: ирээдүй, 1990-ээс өмнө, ambiguous | `date_*` |
| Нэр тааруулах (кирилл/латин транслит + rapidfuzz) | < 0.85 → `name_mismatch` (батлахаас өмнө заавал) |
| Давхардал (ижил өвчтөн+огноо+тест+утга confirmed) | `possible_duplicate` |
| Delta check (өмнөх confirmed утгаас `delta_check_pct`-ээс их) | `large_delta` |

## Нормчлол (`labtrack.core`)
1. **Тест таних:** нэр нормчлох (жижиг үсэг, хаалт/цэг, кирилл-латин ижил хэлбэрийн үсэг) → хэрэглэгчийн синоним (`test_synonyms.user_id`) → глобал синоним → rapidfuzz (≥ 88) + `pg_trgm` → олдохгүй бол `null` (review-д хэрэглэгч сонгоно → хэрэглэгчийн синоним болж хадгалагдана).
2. **Нэгж:** `unit_aliases` → `unit_conversions` (тест тус бүр). Утга, ref, critical **бүгд** ижил коэффициентоор (`Decimal`).
3. **Flag (`core/flags.py`)** — дараалал:
   - qualitative: positive → `abnormal` (тест "эерэг = хэвийн бус" бол), negative → `normal`
   - critical хязгаар баримтад байвал → `critical_low/high`
   - ref хязгаар баримтад байвал → `low/high/normal`
   - comparator: "<0.5" ба ref_high=5 → normal; ">1000" ба ref_high=200 → high; тодорхойгүй бол `unknown`
   - хязгааргүй, лабын тэмдэг байгаа бол → лабын тэмдгээр (`flag_source=lab_flag`)
   - юу ч байхгүй → `no_reference`
   - patient_target нь тусдаа "зорилтоос гадуур" шошго (flag-ийг дарахгүй)

## Критик утгын урсгал
Критик утга AI задлалтаар илэрвэл (баталгаажаагүй ч):
- Тайлангийн жагсаалт ба review дэлгэцэд **улаан баннер**: "Критик байж болзошгүй утга — нэн даруй шалгана уу".
- Өвчтөний эзэн болон `caregiver_alert_settings.critical_result` идэвхтэй асран хамгаалагчид push: "Шинэ хариуг яаралтай хянана уу" (утгыг мэдэгдэлд оруулахгүй — PHI).
- Батлагдсаны дараа хандалттай эмчид мэдэгдэл.
- Мэдэгдлийн текст: "Энэ мэдээлэл нь эмчийн зөвлөгөөг орлохгүй. Биеийн байдал муу бол 103 руу залгана уу."

## Хамрах хүрээнээс гадуур (MVP)
HLA/DSA эсрэгбиеийн (MFI) тайлан, биопсийн гистологи, гарах тойм — баримт хэлбэрээр хадгалж `clinical_events`-д хавсаргана, утгыг задлахгүй (бүтэц нь хэт олон янз, буруу уншвал эрсдэл өндөр).

## Eval
- `eval/cases/<id>/{input.words.json, expected.json}` — зохиомол кейс (репод; `eval/make_synthetic.py` үүсгэнэ: байрлалтай үгс, PDF текст давхаргыг л алгасна). Бодит баримт — `eval/local/<id>/{input.pdf, expected.json}`, **git-ignored** (PHI), worker-тэй адил child process-оор уншина.
- `just eval` → мөр бүрээр утга, нэгж, **ref, critical**, тест, огноо (олдоогүй мөр бүх хэмжүүрт буруу) + precision, хуудас тутмын p95 → `eval/report.md` (git-ignored; зөвхөн кейсийн id, тоо). `--details` — буруу мөрийг дэлгэцэнд л; `--check` — DoD-оос доош бол алдаа; `--ai` — танихгүй хэлбэрийг AI-аар (нэргүйжүүлж, илгээсэн тексттэй тулгана; төлбөртэй; key/загвар env-ээс).
- Prompt/загвар/pipeline өөрчлөхөд eval доошилбол merge хийхгүй.
- Зорилт: тоон утга ≥ 98%, лавлах хязгаар ≥ 95%, тест таних ≥ 95%.

## Зардал
SHA-256 давхардал, хэрэглэгч/өдөр квот, prompt caching, их хэмжээний архивт Batch API.
