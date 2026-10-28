# LabTrack MN — төлөвлөлтийн багц (v7)

Эрхтэн шилжүүлэн суулгуулсан хүмүүст зориулсан, гар утас үндсэн, хаалттай бүлгийн апп: шилжүүлэн суулгалтын мэдээлэл, эм (тунгийн түүх, сануулга), эмчилгээ, шинжилгээний хариу. Хэрэглэгчийг супер админ бүртгэнэ.
Expo (React Native) апп + Python (FastAPI, Celery) backend + Next.js web (хуваалцсан линк) · PostgreSQL RLS · Claude API.

## Агуулга
| Файл | Юу вэ |
|---|---|
| `CLAUDE_CODE_PROMPT.md` | Claude Code-д буулгах эцсийн промпт + дараагийн phase-ийн промптууд |
| `CLAUDE.md` | Claude Code автоматаар уншдаг дүрэм, командууд |
| `.claude/settings.json` | Зөвшөөрөл (`.env` унших, `git push`, дэлгүүрт илгээх, production OTA хориглосон), Ruff/Biome hook (`.claude/hooks/format.mjs`), идэвхтэй plugin-ууд |
| `.claude/commands/` | `/phase N`, `/security-check` |
| `.claude/agents/` | `medical-reviewer`, `security-reviewer`, `ui-reviewer` |
| `.claude/skills/phi-table/` | PHI хүснэгт нэмэх журам (migration, RLS, тест) |
| `docs/01_PLAN.md` | Үе шат, алхам, хүлээн авах шалгуур, эрсдэл |
| `docs/02_ARCHITECTURE.md` | Стек ба шалтгаан, бүдүүвч, repo бүтэц |
| `docs/03_DATA_MODEL.md` | Хүснэгтүүд, RLS |
| `docs/04_RBAC_SECURITY.md` | Auth (админ бүртгэл, админ нууц үг шинэчлэл), эрх, аюулгүй байдал, хууль, апп дэлгүүр |
| `docs/05_EXTRACTION.md` | AI pipeline, лавлах/критик хязгаар баримтаас, eval |
| `docs/06_DASHBOARD_UX.md` | Дэлгэцүүд, UX зарчим |
| `docs/07_CRITIQUE.md` | v1→v7 шүүмжлэлт хяналт, нээлттэй асуултууд |
| `docs/08_MOBILE.md` | Expo апп: навигаци, шилжүүлэн суулгалтын wizard, эм ба сануулга, скан, share, offline, аюулгүй байдал, дэлгүүр |
| `docs/09_CLINICAL_SAFETY.md` | Зориулалтын хил, клиникийн аюулын бүртгэл (hazard log), release шалгалт |
| `docs/10_RESEARCH.md` | Ижил төстэй апп, клиникийн судалгаа, хууль — эх сурвалжтай |
| `docs/11_TOOLING.md` | Claude Code plugin/skill, токен хэмнэлт, бүтээмж, UI/UX санал, хяналтын дүгнэлт |
| `_archive/` | Хуучин хувилбарууд (Claude уншихгүй) |
| `seed/lab_tests.json` | 61 шинжилгээ: mn/en/ru нэр, синоним, нэгжийн alias, хөрвүүлэлт, боломжгүй утга барих хязгаар (лавлах/критик хязгааргүй) |
| `seed/medications.json` | Шилжүүлэн суулгалтад түгээмэл 30 эм: монгол/англи нэр, худалдааны нэр, ангилал, эмийн түвшний шинжилгээтэй холбоос (тун агуулахгүй) |
| `seed/extraction.schema.json` | AI-ийн бүтэцтэй гаралтын JSON Schema |

## Эхлэх
1. Шинэ репо үүсгэж энэ багцыг үндсэн хавтсанд хуул.
2. Docker, uv, Node LTS + pnpm, just, jq (командууд: `docs/11_TOOLING.md` §3), Xcode / Android Studio, EAS CLI, Maestro суулга; Anthropic API key, Expo аккаунт бэлд.
3. `claude` → Plan mode → `CLAUDE_CODE_PROMPT.md`-ийн промптыг буулга.
4. Phase 4-өөс өмнө **нэрээ нууцалсан 30+ бодит шилжүүлэн суулгалтын хяналтын хариу** цуглуул (утсаар авсан зураг, Messenger-ээс ирсэн PDF, гадаадын эмнэлгийнх, лавлах/критик хязгаартай).
5. Phase 2-оос (эм, сануулга бэлэн болмогц) TestFlight / Play Internal-аар бета хэрэглэгчидтэй турш.
6. Админы хүн таних журмыг (нууц үг шинэчлэхэд) бичгээр тогтоо.

## ⚠️ Анхааруулга
Лавлах ба критик хязгаарыг систем зөвхөн оруулсан баримтаас авна. Нэгж хөрвүүлэх коэффициент, LOINC кодыг лабораторийн эмчээр, хууль зүйн хэсгийг хуульчаар хянуулна.  Апп эмийн тун санал болгохгүй — хэрэглэгч эмчийнхээ хамгийн сүүлийн зааврыг дагана. `seed/medications.json`-ийн худалдааны нэрийг Монголын эмийн бүртгэлээр, эм зүйчээр шалгуулна.
