---
description: docs/01_PLAN.md-ийн тодорхой үе шатыг хэрэгжүүлэх (жишээ: /phase 3)
argument-hint: <phase дугаар>
---
Phase $ARGUMENTS-г хэрэгжүүлнэ.

1. `docs/01_PLAN.md`-ийн зөвхөн Phase $ARGUMENTS хэсгийг, мөн `CLAUDE.md`-ийн "Phase → унших docs" хүснэгтэд заасан файлуудыг л унш (бусдыг бүү уншаарай — токен хэмнэ). `docs/PROGRESS.md`, `docs/OPEN_QUESTIONS.md` байвал унш.
2. Өмнөх phase-ийн DoD биелсэн эсэхийг `docs/PROGRESS.md`-ээс шалга. Үгүй бол юу дутуу байгааг монголоор мэдэгдээд зогс.
3. Ажлыг 5–15 жижиг алхам болгон задалж, файл, migration, endpoint, дэлгэц, тест бүхий **товч төлөвлөгөө** монголоор бич. Хэрэглэгчээр батлуул.
4. Батлагдсаны дараа алхам алхмаар хэрэгжүүл. Алхам бүрийн дараа `just lint && just test`. PHI хүснэгт нэмэхдээ `phi-table` skill-ийг дага.
5. Хянуулах: auth/RLS/storage → `security-reviewer`; эмнэлгийн логик/prompt → `medical-reviewer`; дэлгэц/UI текст → `ui-reviewer`. Олон файлын хайлтыг `Explore` subagent-аар хий.
6. Төгсгөлд DoD-г нотолгоотой (командын гаралт, тестийн тоо) шалгаж `docs/PROGRESS.md`-г шинэчил, нээлттэй асуултыг `docs/OPEN_QUESTIONS.md`-д бич. Дараагийн phase-ийг `/clear`-ийн дараа эхлүүлэхийг санал болго.
