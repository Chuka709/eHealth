# 03 — Өгөгдлийн загвар (v7)

> v7: Бүх хүснэгт бүрэн тодорхойлогдсон ("v3-тай ижил" гэсэн дутуу хэсэггүй). Нэмэгдсэн: амин үзүүлэлт, харшил, үзлэг/шинжилгээний товлол, эмчээс асуух асуулт, яаралтай холбоо барих хүн, хуваалцах линк, зөвшөөрөл, асран хамгаалагчийн мэдэгдэл, бүтээгдэхүүний PHI-гүй event.

> v6: Хэрэглэгчийг **супер админ бүртгэнэ**, нууц үгийг админ сэргээнэ (сэргээх код хасагдсан). **Шилжүүлэн суулгалт, эм, эмчилгээний** хүснэгтүүд MVP-д орсон.

> v5: Auth FastAPI дотор (users, sessions, auth_attempts). Байгууллага MVP-д байхгүй — `patients.org_id` nullable, дараа клиникт зориулж нэмнэ.

> v4 өөрчлөлт: **Лавлах ба критик хязгаарын үндсэн эх сурвалж = оруулсан баримт.** Каталог анхдагч лавлах хязгаар агуулахгүй (буруу flag үүсгэх эрсдэлтэй). Каталогт зөвхөн тестийг таних, нэгж хөрвүүлэх, боломжгүй утгыг барих мэдээлэл үлдэнэ.

## Гол ойлголтууд
- **user** — нэр + нууц үгээр нэвтэрдэг аккаунт (`users`).
- **patient** — шинжилгээ нь хамаарах хүн. Нэг хэрэглэгч олон patient удирдана.
- **organization** — (MVP-ийн дараа) эмнэлэг/клиник.
- **document** → **lab_report** → **lab_result** (мөр бүрт лабын лавлах/критик хязгаар хамт).
- **test_catalog** — таних, нэгж, физиологийн боломжит хязгаар (ЛАВЛАХ БИШ).

## Лавлах / критик хязгаарын эх сурвалжийн дараалал
```
1. patient_targets   — эмчийн тогтоосон хувийн зорилт (жишээ: такролимус 5–8 ng/mL)  [зорилт гэж тусад нь харуулна]
2. document          — баримт дээрх лавлах/критик хязгаар (ҮНДСЭН)
3. байхгүй           — flag = 'no_reference'; утга харагдана, өнгөгүй. Хэзээ ч зохиохгүй
```
- Лабын өөрийн тэмдэг (H/L/↑/↓/*) `lab_flag`-д хадгалагдаж, тооцоолсон flag-тай **зөрвөл review issue**.
- Гараар оруулахад хэрэглэгч хязгаарыг цааснаас нь хамт оруулна (заавал биш).
- Нэгж хөрвүүлэхэд **утга ба хязгаар хамт** хөрвөнө → график дээр цэг бүр өөрийн хүрээтэй.

## Хүснэгтүүд (SQLAlchemy model-ийн суурь; Alembic migration)

```sql
create extension if not exists pg_trgm;
create extension if not exists pgcrypto;
create extension if not exists citext;

-- Enum-ууд
create type access_level  as enum ('owner','caregiver','doctor','viewer');
create type sex           as enum ('male','female','unknown');
create type doc_status    as enum ('uploaded','queued','processing','needs_review','confirmed','failed','rejected');
create type report_status as enum ('needs_review','confirmed','archived');
create type value_kind    as enum ('numeric','qualitative','text');
create type result_flag   as enum ('normal','low','high','critical_low','critical_high',
                                   'abnormal','no_reference','unknown');

create type user_role as enum ('user','doctor','support','super_admin');

create table users (
  id uuid primary key default gen_random_uuid(),
  username citext unique not null check (username ~ '^[a-z0-9._]{3,32}$'),
  password_hash text,                          -- argon2id; хэрэглэгч ӨӨРӨӨ тохируулна (админ хэзээ ч мэдэхгүй — түр нууц үг байхгүй)
  account_status text not null default 'pending_activation'
    check (account_status in ('pending_activation','active','locked','disabled')),   -- нэвтрэх шалгалтын ЦОРЫН ГАНЦ эх сурвалж
  check (account_status <> 'pending_activation' or password_hash is null),
  token_version int not null default 0,        -- нэмэгдэхэд бүх access JWT шууд хүчингүй (идэвхгүй болгох, reset)
  contact_phone_enc bytea,                     -- envelope шифрлэлт (формат: 04 §6.4); админд зөвхөн last4, бүтнээр нээх = аудит
  contact_phone_last4 text,
  identity_check_hash text,                    -- bcrypt(РД + pepper) — DB өөрөө (pgcrypto) тооцож шалгана, админ зөвхөн тийм/үгүй; null бол зөвхөн биечлэн таних
  created_by uuid references users,            -- бүртгэсэн админ
  display_name text not null, locale text not null default 'mn',
  role user_role not null default 'user',
  totp_secret_enc bytea,                       -- зөвхөн admin/support
  emergency_card_unlocked boolean not null default false,   -- яаралтай картыг түгжээгүй нээх (анхдагч OFF)
  password_changed_at timestamptz,
  created_at timestamptz not null default now(), deleted_at timestamptz
);

create table identity_checks (                 -- админы хүн таних шалгалт (зөвхөн тийм/үгүй); activation_tokens-д холбогдоно
  id bigserial primary key,
  user_id uuid not null references users on delete cascade,
  admin_id uuid not null references users,
  success boolean not null,
  at timestamptz not null default now()
);

create table activation_tokens (               -- нэг удаагийн идэвхжүүлэх/сэргээх токен (түр нууц үгийн оронд)
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users on delete cascade,
  token_hash text not null unique,             -- sha256(≥128 бит); токен өөрөө зөвхөн QR/SMS-д
  purpose text not null check (purpose in ('activation','admin_reset')),
  channel text not null check (channel in ('in_person_qr','sms')),
  issued_by uuid not null references users,
  identity_check_id bigint,                    -- admin_reset: ≤ 10 мин дотор амжилттай таних шалгалт заавал
  expires_at timestamptz not null,             -- QR: 15 мин, SMS: 24 цаг
  used_at timestamptz, revoked_at timestamptz,
  created_at timestamptz not null default now()
);
create unique index on activation_tokens (user_id) where used_at is null and revoked_at is null;   -- нэг л идэвхтэй

create table sessions (                        -- refresh token (hash), төхөөрөмж бүрт
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users on delete cascade,
  family_id uuid not null,                     -- rotation гэр бүл (reuse detection)
  token_hash text not null unique,             -- sha256(refresh)
  device_name text, platform text check (platform in ('ios','android','web')),
  push_token text,                             -- Expo push token
  created_at timestamptz not null default now(), last_used_at timestamptz,
  expires_at timestamptz not null, revoked_at timestamptz, replaced_by uuid,
  revoked_reason text check (revoked_reason in ('logout','user_revoke','admin_reset','disabled','reuse_detected','expired')),
  device_trusted boolean not null default false   -- амжилттай нэвтэрсэн төхөөрөмж (OWASP device cookie) — 04 §6.2
);

create table auth_attempts (                   -- rate limit + аудит
  id bigserial primary key, at timestamptz not null default now(),
  username citext, ip inet,                    -- IPv6-г /64-ээр нэгтгэж хадгална
  share_link_id uuid,                          -- kind='share_pin' үед (username биш)
  kind text check (kind in ('login','activation','change_password','identity_check','share_pin')),
  success boolean not null
);
create index on auth_attempts (username, at desc);
create index on auth_attempts (ip, at desc);
-- 90 хоногоос хуучныг Celery beat `labtrack_maint` role-оор устгана (`labtrack_app`-д DELETE эрхгүй)

-- organizations, memberships — MVP-ийн дараа (клиник/эмнэлэг)

create table patients (
  id uuid primary key default gen_random_uuid(),
  org_id uuid,                                 -- MVP-д null; клиник нэмэхэд FK
  full_name text not null, relation text,      -- 'self','child','parent','spouse','other'
  -- насанд хүрээгүй эсэхийг хадгалахгүй: is_minor_patient() шалгах мөчид birth_date-ээс тооцно (18 нас хүрмэгц автоматаар дуусна);
  -- хүүхдийн birth_date зөвхөн үүсгэхэд; дараа нь хоосныг зөвхөн 18+ огноогоор бөглөнө, өөрчлөхийг trigger хориглоно (support засна)
  archived_at timestamptz,                     -- нас барсан / идэвхгүй (админ эсвэл гэр бүл)
  birth_date date, sex sex not null default 'unknown',
  national_id_enc bytea, national_id_hmac text,
  created_by uuid references users, created_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table patient_access (
  patient_id uuid references patients on delete cascade,
  user_id uuid references users on delete cascade,
  level access_level not null,
  scopes text[] not null default '{results:read}',
  granted_by uuid references users, expires_at timestamptz, revoked_at timestamptz,
  primary key (patient_id, user_id)
);

create table documents (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients on delete cascade,
  storage_key text not null, mime_type text not null, size_bytes int not null,
  page_count int, sha256 text not null, has_text_layer boolean,
  quality_score numeric(3,2),                 -- бүдгэрэл/гэрэлтэлтийн үнэлгээ
  status doc_status not null default 'uploaded', error_code text,
  uploaded_by uuid not null references users,
  created_at timestamptz not null default now(),
  unique (patient_id, sha256)
);

create table extraction_runs (
  id uuid primary key default gen_random_uuid(),
  document_id uuid references documents on delete cascade,
  model text not null, prompt_version text not null, pipeline_version text not null,
  input_tokens int, output_tokens int, cost_usd numeric(10,5), duration_ms int,
  raw_output jsonb, issues jsonb, error text, created_at timestamptz not null default now()
);

create table lab_reports (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients on delete cascade,
  document_id uuid references documents on delete set null,
  lab_name text, panel_name text,
  collected_at timestamptz, reported_at timestamptz, date_ambiguous boolean default false,
  source_patient_name text, name_match_score numeric(3,2),
  has_unconfirmed_critical boolean not null default false,   -- review дэлгэцэд яаралтай баннер
  status report_status not null default 'needs_review',
  confirmed_by uuid references users, confirmed_at timestamptz,
  created_at timestamptz not null default now()
);

create table test_catalog (
  code text primary key, loinc text,
  name_mn text not null, name_en text not null, name_ru text,
  category text not null, kind value_kind not null default 'numeric',
  canonical_unit text, decimals int not null default 2,
  physio_min numeric, physio_max numeric,      -- ЗӨВХӨН боломжгүй утга барих (уншилтын алдаа)
  delta_check_pct numeric,                     -- өмнөхөөс огцом өөрчлөлтийн босго (уншилтын алдаа илрүүлэх)
  is_active boolean not null default true
);

create table test_synonyms (
  id bigserial primary key,
  test_code text not null references test_catalog on delete cascade,
  synonym text not null, synonym_norm text not null,   -- нормчилсон (жижиг үсэг, кирилл/латин нэгтгэсэн)
  user_id uuid references users,                       -- null = глобал; утгатай = тухайн хэрэглэгчийн сурсан синоним
  unique (synonym_norm, user_id)
);
create index on test_synonyms using gin (synonym_norm gin_trgm_ops);

create table unit_aliases (                            -- 'ммоль/л','mmol/l' → 'mmol/L'
  alias_norm text primary key, unit text not null
);

create table unit_conversions (
  test_code text references test_catalog on delete cascade,
  from_unit text not null, to_unit text not null, factor numeric not null,
  primary key (test_code, from_unit, to_unit)
);

create table lab_results (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references lab_reports on delete cascade,
  patient_id uuid not null references patients on delete cascade,
  test_code text references test_catalog,
  raw_name text not null, raw_value text not null, raw_unit text,
  -- утга
  value_numeric numeric, comparator text check (comparator in ('<','<=','>','>=')),
  value_text text, qualitative text check (qualitative in ('positive','negative','equivocal')),
  -- баримт дээрх хязгаар (ЭХ нэгжээр, яг бичигдсэнээр)
  ref_text text, ref_low numeric, ref_high numeric,
  critical_text text, critical_low numeric, critical_high numeric,
  lab_flag text,                                -- баримт дээрх тэмдэг
  -- нормчилсон (каталогийн нэгжээр; хязгаар ч мөн хөрвүүлэгдсэн)
  unit_canonical text, value_canonical numeric,
  ref_low_canonical numeric, ref_high_canonical numeric,
  critical_low_canonical numeric, critical_high_canonical numeric,
  -- үр дүн
  flag result_flag not null default 'unknown',
  flag_source text check (flag_source in ('computed_document_range','lab_flag','patient_target','none')),
  flag_mismatch boolean not null default false, -- тооцоолсон ≠ лабын тэмдэг
  confidence numeric(3,2), issues text[] not null default '{}',
  source_page int, source_snippet text,
  edited_by_user boolean not null default false,
  collected_at timestamptz,                     -- report-оос (trend индекс)
  created_at timestamptz not null default now()
);
create index on lab_results (patient_id, test_code, collected_at desc);

create table patient_targets (
  patient_id uuid references patients on delete cascade,
  test_code text references test_catalog,
  low numeric, high numeric, valid_from date not null, valid_to date,
  set_by uuid references users, note text,
  primary key (patient_id, test_code, valid_from)
);

-- ============ ШИЛЖҮҮЛЭН СУУЛГАЛТ ============
create type organ as enum ('kidney','liver','heart','lung','pancreas','kidney_pancreas',
                           'intestine','cornea','hsct','other');   -- hsct = цусны үүдэл эс
create type donor_type as enum ('living_related','living_unrelated','deceased_dbd','deceased_dcd','unknown');
create type graft_status as enum ('functioning','failed','removed','unknown');

create table transplants (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients on delete cascade,
  organ organ not null,
  organ_detail text,                       -- 'зүүн бөөр', 'элэгний баруун дэлбэн' гэх мэт
  transplant_date date not null,
  date_precision text not null default 'day' check (date_precision in ('day','month','year')),
  country text not null,                   -- ISO 3166 (MN, KR, IN, CN, TR …)
  city text, hospital text not null, surgeon text,
  transplant_number int not null default 1,          -- 1-р, 2-р (дахин шилжүүлэн суулгалт)
  donor_type donor_type not null default 'unknown',
  donor_relation text,                     -- 'ах', 'ээж', 'эхнэр' …
  recipient_blood_type text, donor_blood_type text,
  abo_incompatible boolean,
  cmv_donor text check (cmv_donor in ('pos','neg','unknown')),
  cmv_recipient text check (cmv_recipient in ('pos','neg','unknown')),
  ebv_donor text, ebv_recipient text,
  hla_mismatch text,                       -- '3/6' гэх мэт, эх бичлэгээр
  primary_disease text,                    -- шилжүүлэн суулгахад хүргэсэн өвчин (хэрэглэгчийн бичсэнээр)
  pre_transplant_dialysis text,            -- 'гемодиализ 2 жил' гэх мэт
  induction_therapy text,                  -- 'басиликсимаб', 'ATG' гэх мэт
  graft_status graft_status not null default 'functioning',
  -- clinical_events-д 'rejection' гэх мэт; DSA/HLA эсрэгбиеийн тайланг баримтаар хавсаргана (MVP-д задлахгүй)
  graft_status_date date, graft_failure_reason text,
  follow_up_center text, follow_up_doctor text,
  notes text,
  created_at timestamptz not null default now(), updated_at timestamptz
);

-- ============ ЭМ ============
create table medication_catalog (            -- seed/medications.json
  code text primary key,
  generic_mn text not null, generic_en text not null,
  brands text[] not null default '{}',
  category text not null,                  -- immunosuppressant, antiviral, antifungal, antibiotic_prophylaxis,
                                           -- antihypertensive, lipid, diabetes, bone, gi, hepatitis, other
  forms text[] not null default '{}',      -- capsule, tablet, extended_release, solution, injection
  related_test_code text references test_catalog,   -- такролимус → TAC (эмийн түвшин)
  is_active boolean not null default true
);

create table medications (                   -- өвчтөний эм (одоо ба өмнө нь уусан)
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients on delete cascade,
  unique (id, patient_id),                     -- хүүхэд хүснэгтүүдийн composite FK-д (өөр өвчтөний эмтэй холбохоос сэргийлнэ)
  catalog_code text references medication_catalog,  -- null = каталогт байхгүй, гараар
  name text not null,                      -- хэрэглэгчийн харах нэр (худалдааны нэрээр байж болно)
  brand text, form text, strength text,    -- '1 мг', '500 мг' — хэрэглэгчийн бичсэнээр
  route text default 'oral',
  purpose text,                            -- хэрэглэгчийн бичсэн зорилго
  prescribed_by text,
  transplant_id uuid references transplants on delete set null,
  started_on date, stopped_on date, stop_reason text,
  is_long_term boolean not null default true,
  reminders_enabled boolean not null default false,
  reminder_timezone_mode text not null default 'home' check (reminder_timezone_mode in ('home','local')),
  -- 'home': гадаадад явсан ч Улаанбаатарын цагаар (тунгийн завсар тогтмол); цагийн бүс солигдоход апп асууна
  notes text,
  created_at timestamptz not null default now(), updated_at timestamptz
);

create table medication_regimens (           -- тун, хуваарийн түүх (тун өөрчлөгдөх бүрт шинэ мөр)
  id uuid primary key default gen_random_uuid(),
  medication_id uuid not null references medications on delete cascade,
  effective_from date not null, effective_to date,
  dose_amount numeric, dose_unit text,     -- 2, 'мг' | 1, 'шахмал'
  schedule jsonb not null,                 -- {"type":"daily","times":["08:00","20:00"]} | {"type":"weekly","days":[1,4],"times":["09:00"]} | {"type":"prn"}
  instructions text,                       -- 'хоолноос 1 цагийн өмнө' (хэрэглэгч/эмчийн бичсэнээр)
  changed_by_note text,                    -- 'эмч такролимусын түвшнээр бууруулсан'
  created_at timestamptz not null default now()
);

create table medication_intakes (            -- уусан/алгассан тэмдэглэл (сонголттой)
  id bigserial primary key,
  medication_id uuid not null,
  patient_id uuid not null references patients on delete cascade,
  foreign key (medication_id, patient_id) references medications (id, patient_id) on delete cascade,   -- IDOR хамгаалалт
  scheduled_at timestamptz, taken_at timestamptz,
  status text not null check (status in ('taken','skipped','late')),
  note text,
  client_id uuid not null,                     -- төхөөрөмж үүсгэнэ; давтан илгээвэл хадгалсан мөрийг буцаана (idempotent)
  recorded_by uuid references users,           -- өвчтөн эсвэл асран хамгаалагч
  unique (patient_id, client_id),
  unique (medication_id, scheduled_at)         -- нэгтгэх дүрэм: `taken` давамгайлна (хамгийн эрт taken_at), `skipped` нь `taken`-ийг хэзээ ч дарахгүй — core/intakes.py + тест
);
create index on medication_intakes (patient_id, scheduled_at desc);

-- ============ ЭМЧИЛГЭЭ, КЛИНИКИЙН ҮЙЛ ЯВДАЛ ============
create type clinical_event_kind as enum (
  'biopsy','rejection','infection','hospitalization','dialysis','plasmapheresis','ivig',
  'surgery','procedure','vaccination','complication','other');

create table clinical_events (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients on delete cascade,
  transplant_id uuid references transplants on delete set null,
  kind clinical_event_kind not null,
  title text not null,                     -- 'Цочмог эсийн татгалзал (биопсиор батлагдсан)'
  started_on date not null, ended_on date,
  place text, description text, outcome text,
  related_document_id uuid references documents on delete set null,   -- биопсийн хариу, гарах тойм
  created_at timestamptz not null default now()
);

create table pending_uploads (                -- апп offline-оос ирсэн давхардлыг барих
  client_upload_id uuid primary key, user_id uuid references users, document_id uuid references documents,
  created_at timestamptz default now()
);

create table notifications (
  id bigserial primary key, user_id uuid references users on delete cascade,
  kind text not null,                          -- 'review_ready','critical_pending','share_invite','reminder'
  patient_id uuid, entity_id text, title_key text not null,   -- i18n түлхүүр; PHI биш
  read_at timestamptz, sent_push_at timestamptz, created_at timestamptz default now()
);

-- ============ АМИН ҮЗҮҮЛЭЛТ (гараар; дараа нь Apple Health / Health Connect) ============
create type vital_kind as enum ('bp_systolic','bp_diastolic','pulse','weight','temperature',
  'glucose','spo2','urine_output','fluid_intake');
create table vitals (
  id bigserial primary key,
  patient_id uuid not null references patients on delete cascade,
  kind vital_kind not null, value numeric not null, unit text not null,
  measured_at timestamptz not null,
  group_id uuid,                               -- даралтын systolic+diastolic+pulse нэг хэмжилт
  source text not null default 'manual' check (source in ('manual','apple_health','health_connect')),
  client_id uuid not null,                     -- offline idempotency
  unique (patient_id, client_id),
  note text, created_at timestamptz not null default now()
);
create index on vitals (patient_id, kind, measured_at desc);

-- ============ ХАРШИЛ ============
create table allergies (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients on delete cascade,
  substance text not null,                     -- 'Пенициллин' (хэрэглэгчийн бичсэнээр)
  reaction text, severity text check (severity in ('mild','moderate','severe','unknown')),
  noted_on date, created_at timestamptz not null default now()
);

-- ============ ТОВЛОЛ (үзлэг, шинжилгээ) ============
create table appointments (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients on delete cascade,
  kind text not null check (kind in ('lab','clinic_visit','biopsy','imaging','other')),
  title text not null, scheduled_at timestamptz not null,
  place text, notes text,
  reminder_offsets_min int[] not null default '{1440,120}',   -- 1 өдөр, 2 цагийн өмнө
  status text not null default 'planned' check (status in ('planned','done','cancelled')),
  linked_report_id uuid references lab_reports on delete set null,
  created_at timestamptz not null default now()
);

-- ============ ЭМЧЭЭС АСУУХ АСУУЛТ ============
create table doctor_questions (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients on delete cascade,
  text text not null, answer text,
  appointment_id uuid references appointments on delete set null,
  status text not null default 'open' check (status in ('open','answered','dropped')),
  created_at timestamptz not null default now()
);

-- ============ ЯАРАЛТАЙ ХОЛБОО БАРИХ ============
-- users.emergency_card_unlocked (анхдагч OFF) — дээрх users хүснэгтэд

create table emergency_contacts (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients on delete cascade,
  name text not null, relation text, phone text not null,
  is_transplant_center boolean not null default false,
  sort_order int not null default 0
);

-- ============ АСРАН ХАМГААЛАГЧИЙН МЭДЭГДЭЛ (opt-in) ============
create table caregiver_alert_settings (
  patient_id uuid references patients on delete cascade,
  caregiver_user_id uuid references users on delete cascade,
  missed_dose_after_min int default 30,        -- анхдагч 30 мин; null = унтраалттай
  critical_result boolean not null default true,
  primary key (patient_id, caregiver_user_id)
);

-- ============ ЗӨВШӨӨРӨЛ ============
create table consents (
  id bigserial primary key,
  user_id uuid not null references users on delete cascade,
  patient_id uuid references patients on delete cascade,     -- хүүхдийн профайлд асран хамгаалагч өгнө
  kind text not null check (kind in ('terms','privacy','sensitive_data','ai_processing',
                                     'cross_border','caregiver_sharing','research')),
  version text not null, granted boolean not null,
  created_at timestamptz not null default now()
);

-- ============ ХУВААЛЦАХ ЛИНК ============
create table share_links (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients on delete cascade,
  token_hash text not null unique,              -- sha256; токен өөрөө хадгалагдахгүй
  scopes text[] not null,                       -- 'summary','labs','meds','transplant','events','vitals'
  date_from date, date_to date,
  expires_at timestamptz not null, max_views int, view_count int not null default 0,
  pin_hash text,                                -- сонголттой 6 оронтой PIN (argon2id)
  pin_failed_count int not null default 0,      -- 5 буруу → линк автоматаар цуцлагдана + эзэнд мэдэгдэл; тоолуурыг verify-ээс ӨМНӨ атомаар нэмнэ (04 §6.7)
  created_by uuid not null references users, revoked_at timestamptz,
  created_at timestamptz not null default now()
);

-- ============ ӨГӨГДӨЛ ЭКСПОРТ (хэрэглэгчийн хандах эрх) ============
create table data_exports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users on delete cascade,
  format text not null check (format in ('pdf','json','fhir')),
  status text not null default 'queued', storage_key text, expires_at timestamptz,
  created_at timestamptz not null default now()
);

-- ============ БҮТЭЭГДЭХҮҮНИЙ EVENT (PHI-гүй) ============
create table product_events (                   -- идэвх, апп орхих (attrition) хэмжих
  id bigserial primary key,
  user_hash text not null,                      -- HMAC(user_id) — PHI биш
  name text not null,                           -- 'app_open','dose_logged','upload_started','review_confirmed'
  props jsonb not null default '{}',            -- зөвхөн тоо/enum, утга нэр биш
  at timestamptz not null default now()
);

create table audit_logs (
  id bigserial primary key, at timestamptz not null default now(),
  actor_id uuid, actor_role text, org_id uuid, action text not null,
  target_user_id uuid,                          -- админы үйлдэл аль хэрэглэгчид хамаарах (хэрэглэгч өөрөө харна)
  patient_id uuid, entity text, entity_id text, ip inet, user_agent text,
  request_id text, diff jsonb                   -- diff-д талбарын нэр + ID; PHI утга бол шифрлэлттэй
);  -- UPDATE/DELETE-г trigger хориглоно
create index on audit_logs (target_user_id, at desc);
create index on audit_logs (patient_id, at desc);
```

## Админ ба идэвхжүүлэлтийн функц (migration 0004)
`labtrack_admin` хүснэгтэд **бичих эрхгүй** — бүх өөрчлөлт зөвхөн эдгээрээр (actor = `app.user_id`, идэвхтэй админ; зорилт зөвхөн `user`/`doctor`):
`admin_create_user` (super_admin; "Би" профайл үүснэ, админд хандалтгүй) · `admin_identity_check` (DB тооцно; хэрэглэгч 5/өдөр, админ 50/өдөр) · `admin_issue_token` (activation — зөвхөн pending; admin_reset — тухайн админы ≤ 10 мин амжилттай шалгалт; QR 15 мин / SMS 24 ц; reset үед хуучин нууц үг null, бүх сесс цуцлагдана, мэдэгдэл) · `admin_set_status` (support — зөвхөн locked→active) · `admin_reveal_phone` (аудит). Хэрэглэгч талд: `activation_consume(token_hash, argon2id_hash)`.
API нь хэзээ ч owner URL ашиглахгүй — шинэ auth үйлдэл бүрт definer функц нэмнэ.

**Migration 0008 (устгах):** `request_account_deletion()` (app) · `admin_cancel_deletion(user)` (super_admin, 30 хоногт → `locked` + `reset_required`) · `maint_purge_deleted_users(limit)` (`labtrack_maint`; эзэмшдэг профайл, аккаунт, түлхүүр; setof id) · `user_keys` (FK-гүй, owner-only; `user_key_get`/`user_key_put` — админ API) — хэрэглэгчийн `*_enc` талбарын DEK-ийг ороож, purge-д устгана (crypto-shredding; envelope-ийн kek_id = `u:<id>`).

**Migration 0007 (/me):** `report_unwanted_admin_action()` ("Би хүсээгүй", админы үйлдлээс 30 хоногт) · `users.reset_required` — `suspected_compromise` шалтгаантай түгжих/идэвхгүй болгох эсвэл хэрэглэгчийн мэдэгдэл тохируулна; тохируулсан үед аль ч төлөвөөс `active` болгохгүй; зөвхөн `activation_consume` (шинэ нууц үг) цэвэрлэнэ.

**Migration 0006 (админ нэвтрэлт):** шинэ role **`labtrack_admin_login`** — зөвхөн `admin_login_lookup`, `admin_login_failure`, `admin_session_create` (TOTP алхам ±1, нэг удаа — `users.totp_last_step`; 24 цагт 10 алдаа → татгалзана; админд ≤ 3 амьд сесс), `auth_failure_counts`; `labtrack_admin` сесс үүсгэж чадахгүй · `admin_sessions` (зөвхөн hash, 8 ц / 15 мин идэвхгүй; шууд эрх 0) · `admin_actor` нь `app.user_id` + `app.admin_sid` + **тухайн транзакцад** `admin_session_begin(token_hash)` хийсэн байхыг (`begun_xid = pg_current_xact_id()`) шаардана — `set_config`-оор хуурах боломжгүй · `admin_issue_token(..., p_reason, p_admin_ip)` · РД-г тохируулсан админ өөрөө 7 хоног reset олгохгүй, хэрэглэгчид `admin_action` мэдэгдэл · support `suspected_compromise` түгжээг тайлахгүй · `session_check`/`session_rotate` админ role-ыг хасна, өмнөх админы user сесс цуцлагдсан · `admin_token_is_live` (app role — `/auth/activate`-д админ credential мөн эсэх) · `admin_create_user(p_user_id, …)` (утасны AAD-д id урьдчилан хэрэгтэй) · шалтгаан enum: сэргээх `forgot_password|lost_device|suspected_compromise|other`, төлөв `user_request|identity_verified|suspected_compromise|left_program|other` · `admin_set_identity` (зөвхөн хоосон үед) · `admin_clear_lockout` · `admin_log_import(sha256, rows)` · `admin_security_events` · `activation_consume(hash, pw, ip, admin_present)` → `ok|invalid|refused`: олгосон админы сүлжээнээс SMS токен эсвэл админ credential-тэй хүсэлт → цуцлах + `security.admin_token_self_use`; QR ижил сүлжээнээс → зөвшөөрч `security.admin_network_activation` · `auth_login_lookup`/`session_create` админ role-ыг хасна (админ хэрэглэгчийн JWT авахгүй).

## RLS (SQLAlchemy + Postgres)
- Апп DB-д **`labtrack_app`** role-оор холбогдоно (superuser биш, `BYPASSRLS` байхгүй).
- Хүсэлт бүрийн transaction эхэнд: `select set_config('app.user_id', :uid, true)` — **bind параметрээр** (`SET LOCAL`-д f-string хориотой); pool-д буцаахад `DISCARD ALL`. RLS нь SQL injection-оос хамгаалахгүй (халдагч `set_config` дуудаж чадна) — `text()` дотор string format-ийг Ruff/semgrep дүрмээр хориглоно.
- **Worker** нь файл оруулсан хэрэглэгчийн нэрийн өмнөөс ажиллана: task-д `actor_user_id` дамжуулж мөн `SET LOCAL` хийнэ → worker ч RLS-ээс гадуур гарахгүй.
- Migration-ийг тусдаа `labtrack_owner` role хийнэ.
- **DB role-ууд** (бүгд `BYPASSRLS`-гүй, superuser биш):
  | Role | Хэн | Эрх |
  |---|---|---|
  | `labtrack_owner` | Alembic | Схем, функцийн эзэн |
  | `labtrack_app` | API (хэрэглэгчийн хүсэлт), worker | PHI хүснэгт — RLS-ээр; нууц багана (`password_hash`, `totp_secret_enc`, `contact_phone_enc`, `identity_check_hash`)-д **эрхгүй** |
  | `labtrack_admin` | `/admin/*` API | `users`-ийн нууц бус багана, `activation_tokens`, admin аудит; PHI хүснэгтэд **эрхгүй** |
  | `labtrack_maint` | Celery beat (цэвэрлэгээ) | Зөвхөн хуучин `auth_attempts`, устгах хугацаа болсон аккаунт |
  Нууц баганыг **шууд хэн ч уншихгүй** — зөвхөн `security definer` функцээр: `auth_verify_login(username, pw_hash_check…)`, `auth_set_password(user_id, hash)`, `auth_identity_check(user_id, candidate)` (boolean), `auth_reveal_phone(user_id)` (аудиттай). "Би" профайл — `create_self_profile(user_id)`.
- **Хүснэгт бүрийн RLS (SELECT/INSERT/UPDATE/DELETE тусдаа):**
  - `users`: SELECT/UPDATE `id = app_user_id()`; `GRANT UPDATE (display_name, locale, emergency_card_unlocked)` л (role, status эрх нэмэгдүүлэх боломжгүй). Нэрээр хуваалцахдаа `lookup_user_for_share(username)` → зөвхөн id (яг таарсан нэр, rate limit).
  - `sessions`: SELECT (`token_hash`-гүй баганууд), `UPDATE (revoked_at, revoked_reason)` `user_id = app_user_id()`; INSERT/DELETE — зөвхөн auth функц.
  - `consents`: **append-only** (UPDATE/DELETE хориотой — хуулийн нотолгоо). INSERT `WITH CHECK (user_id = app_user_id() and (patient_id is null or (is_owner(patient_id) and is_minor_patient(patient_id))))` — caregiver насанд хүрэгчийн өмнөөс зөвшөөрөл өгөхгүй.
  - `notifications`: SELECT, `UPDATE (read_at)` `user_id = app_user_id()`; INSERT — зөвхөн `notify(user_id, kind, …)` definer функц (worker бусдад илгээх).
  - `data_exports`: SELECT/INSERT өөрийнх; `status/storage_key/expires_at`-ийг зөвхөн worker функц.
  - `patients`: SELECT `can_read_patient(id)`, UPDATE/DELETE `is_owner(id)`; INSERT — `create_patient()` функц (үүсгэгчийг owner болгоно).
  - `patient_access`: SELECT өөрийн мөр эсвэл `is_owner(patient_id)`; INSERT/UPDATE/DELETE зөвхөн owner, **өөрийгөө owner болгох хориотой**; recursion-оос сэргийлж `is_owner()` definer функц.
  - `test_synonyms`: SELECT `user_id is null or user_id = app_user_id()` (бусдын сурсан синоним задрахгүй). Бусад каталог: бүгд SELECT.
  - `audit_logs`: шууд INSERT/SELECT **хориотой** — `audit_write(action, entity, entity_id, patient_id, diff)` (`actor_id := app_user_id()` хүчээр; `admin_*` үйлдлийг зөвхөн `labtrack_admin`), `my_admin_actions()`, `patient_access_log(p)` (зөвхөн owner, бусдын ip/user_agent-гүй). `REVOKE TRUNCATE`.
  - `extraction_runs` (raw_output = PHI), `pending_uploads`, `share_links`: `can_read_patient`/`can_write_patient`-аар; аккаунтгүй үзэгч — `share_view(token_hash, pin)` definer функц.
  - `product_events`: зөвхөн INSERT.

```sql
create function app_user_id() returns uuid language sql stable as
$$ select nullif(current_setting('app.user_id', true), '')::uuid $$;

-- Бүх security definer функц: search_path = pg_catalog, public, pg_temp; хүснэгтийг public.* бүрэн нэрээр;
-- owner = labtrack_owner; REVOKE EXECUTE ... FROM PUBLIC, зөвхөн хэрэгтэй role-д GRANT.
-- REVOKE TEMPORARY ON DATABASE labtrack FROM PUBLIC; REVOKE CREATE ON SCHEMA public FROM PUBLIC;  (pg_temp shadowing-оос)
create function can_read_patient(p uuid) returns boolean
language sql stable security definer set search_path = pg_catalog, public, pg_temp as $$
  select exists (select 1 from public.patient_access a
    where a.patient_id = p and a.user_id = app_user_id()
      and a.revoked_at is null and (a.expires_at is null or a.expires_at > now()));
$$;

alter table lab_results enable row level security;
alter table lab_results force row level security;
create policy lr_select on lab_results for select using (can_read_patient(patient_id));

-- Бичих эрх: owner, caregiver (doctor/viewer — үгүй; doctor-ийн тэмдэглэл/patient_targets тусдаа policy)
create function can_write_patient(p uuid) returns boolean
language sql stable security definer set search_path = pg_catalog, public, pg_temp as $$
  select exists (select 1 from public.patient_access a
    where a.patient_id = p and a.user_id = app_user_id() and a.level in ('owner','caregiver')
      and a.revoked_at is null and (a.expires_at is null or a.expires_at > now()));
$$;
```

## Тэмдэглэл
- Батлагдсан утгыг засвал хуучин утга `audit_logs.diff`-д.
- `lab_results.collected_at` нь `lab_reports.collected_at`-ийн хуулбар (trend индекс) — тайлангийн огноо өөрчлөгдөхөд trigger-ээр синк, тесттэй.
- `latest_results` materialized view — батлах үед refresh (дашбоардын хурд).
- Seed: `seed/lab_tests.json` → test_catalog, test_synonyms, unit_aliases, unit_conversions.

## Шилжүүлэн суулгалт ба эмийн тэмдэглэл
- Бүх шинэ хүснэгт PHI → RLS (`can_read_patient`/`can_write_patient`) + тест.
- Талбаруудын ихэнх нь **сонголттой** — хэрэглэгч мэдэхгүй зүйлээ хоосон орхино. Заавал: эрхтэн, огноо (нарийвчлалтай), улс, эмнэлэг.
- Эмийн тун өөрчлөгдөхөд хуучин мөрийг засахгүй — `medication_regimens`-д шинэ мөр (түүх хадгалагдана, график дээр тун ↔ эмийн түвшин харьцуулна).
- Систем эмийн тун санал болгохгүй, эм хоорондын харилцан үйлчлэл шалгахгүй (MVP). Хэрэглэгч эмчийнхээ зааврыг өөрөө бичнэ.
- Шинжилгээний утга (`lab_results.collected_at`), эмийн тун, клиникийн үйл явдал, шилжүүлэн суулгалтын огноо — бүгд нэг **цагийн хэлхээс**-нд нийлнэ.
- "Шилжүүлэн суулгалтаас хойш X хоног" — `core/timeline.py` (графикийн тэнхлэгт сонголт).

## Хэмжээний таамаг (инфраг зөв хэмжих)
Эхний 2 жилд: ≤ 2 000 хэрэглэгч, хэрэглэгч бүр ~ 30 тайлан/жил, ~ 15 утга/тайлан → ~ 1 сая `lab_results` мөр. Нэг Postgres instance, 1 API + 2 worker хангалттай. Хэтрүүлж хэмжихгүй.
