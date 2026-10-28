---
name: phi-table
description: Эрүүл мэндийн (PHI) шинэ хүснэгт эсвэл багана нэмэх үед ашигла — Alembic migration, ENABLE+FORCE RLS, policy, repository, харь хэрэглэгчийн RLS тест, аудит, hazard log-ийг нэг дор, дутуу орхилгүй хийх журам. "шинэ хүснэгт", "migration нэмэх", "RLS" гэх үед.
---
# PHI хүснэгт нэмэх журам

Нэг ч алхмыг алгасахгүй. Төгсгөлд `security-reviewer`-ээр хянуул.

## 1. Migration (`backend/alembic/versions/`)
- `labtrack_owner` role-оор ажиллана. Тоо → `numeric` (float биш), огноо → `timestamptz` (UTC).
- `patient_id uuid not null references patients on delete cascade` + `(patient_id, <огноо> desc)` индекс.
- Offline-оос ирж болох мөрөнд `client_id uuid unique` (давхардлаас сэргийлэх, idempotent upsert).
- Түүх хадгалах өгөгдөл (эмийн тун гэх мэт) — UPDATE биш шинэ мөр.
- `downgrade()` заавал; `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` ажиллана.

```sql
alter table <t> enable row level security;
alter table <t> force row level security;
create policy <t>_select on <t> for select using (can_read_patient(patient_id));
create policy <t>_insert on <t> for insert with check (can_write_patient(patient_id));
create policy <t>_update on <t> for update using (can_write_patient(patient_id)) with check (can_write_patient(patient_id));
create policy <t>_delete on <t> for delete using (can_write_patient(patient_id));
grant select, insert, update, delete on <t> to labtrack_app;
```
`super_admin`/`support` токеноор хандах policy НЭМЭХГҮЙ.

## 2. Код
- SQLAlchemy model (`db/models/`) ба Pydantic schema (`api/schemas/`) тусдаа; JSON-д тоо string.
- Repository нь session-ийг dependency-ээс авна (`SET LOCAL app.user_id` аль хэдийн хийгдсэн).
- Бичих/устгах/харах үйлдэл бүр `audit_logs`-д (зөвхөн ID, утга биш).
- Лог, Sentry, Celery аргументэд талбарын утга оруулахгүй.

## 3. Тест (`backend/tests/rls/test_<t>.py`) — заавал
- [ ] owner унших/бичих ✓
- [ ] харь хэрэглэгч SELECT → 0 мөр, INSERT/UPDATE/DELETE → алдаа
- [ ] хугацаа дууссан (`expires_at < now()`) ба цуцлагдсан (`revoked_at`) хандалт → 0 мөр
- [ ] `viewer`/`doctor` бичих → алдаа (scope-оос хамаарч)
- [ ] `super_admin` токеноор API → 403, RLS-ээр 0 мөр
- [ ] `app.user_id` тохируулаагүй session → 0 мөр
- [ ] Worker context (`actor_user_id`) зөв ажиллана

## 4. Баримт
- `docs/03_DATA_MODEL.md`-д хүснэгтийг нэм.
- Шинэ аюул үүсгэж байвал `docs/09_CLINICAL_SAFETY.md` hazard log-д мөр + тест.
- `just gen-client` → апп/web-ийн type шинэчлэгдэнэ.
- `just lint && just test-rls`.
