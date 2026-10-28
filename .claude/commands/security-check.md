---
description: Сүүлийн өөрчлөлтийг PHI/RLS/аюулгүй байдлын үүднээс шалгах
---
`git diff main...HEAD` (эсвэл ажлын өөрчлөлт)-ийг `docs/04_RBAC_SECURITY.md`-ийн хяналтын жагсаалтаар шалга:
- RLS-гүй шинэ хүснэгт, тестгүй policy
- DB холболт `labtrack_app` биш role ашигласан, `SET LOCAL app.user_id`-гүй query, `FORCE ROW LEVEL SECURITY` дутуу
- Лог/Sentry/алдааны мессежинд PHI орсон эсэх
- Pydantic/zod-гүй гадаад оролт; Celery task-ийн аргументэд PHI
- Public bucket, удаан хугацаатай presigned URL, эрх шалгалтгүй файл татах endpoint
- Аудит лог бичигдээгүй PHI үйлдэл
- Auth: hash-гүй токен, refresh reuse detection дутуу, rate limit-гүй login/recover
- Апп: AsyncStorage/шифрлэлтгүй хадгалалтад PHI эсвэл токен, push payload-д PHI
Олдсон асуудлыг ноцтой байдлаар (Critical/High/Medium/Low) эрэмбэлж, файл:мөр, засах санал монголоор.
