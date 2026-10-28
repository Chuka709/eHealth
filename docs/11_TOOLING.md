# 11 — Claude Code тохиргоо, хяналтын дүгнэлт, сайжруулалт (2026.10.28)

## 1. Хавтсын хяналтын дүгнэлт

### 1.1 Олдсон ба засагдсан
| # | Асуудал | Засвар |
|---|---|---|
| 1 | Үндсэн хавтсан дахь задгай файлууд **хуучин** байв (02 v4, 03 v6, 04 v6; `lab_tests.json` v0.1.0 нь **лавлах/критик хязгаар агуулсан** — "хязгаар зөвхөн баримтаас" дүрмийг зөрчинө). 06_DASHBOARD_UX, CLAUDE.md, `.claude/`, schema дутуу | `lab-health.zip` доторх v7.1 багцыг үндсэнд задалж, хуучныг `_archive/2026-10-28_old-loose-files/`-д (zip-тэй нь) хадгалав. Claude `_archive/`-ийг уншихыг хориглов |
| 2 | `03`: `patients.birth_date`, `sex` SQL тайлбар (`--`) дотор орчихсон → багана үүсэхгүй | Тусдаа мөр болгов |
| 3 | `03`: `users.emergency_card_unlocked` зөвхөн тайлбарт | `users` хүснэгтэд багана болгов |
| 4 | `03`, CLAUDE.md: `can_write_patient()` ашигласан ч тодорхойлоогүй | Функц нэмэв (owner, caregiver) |
| 5 | `05`: "байгууллагын синоним" — MVP-д байгууллага байхгүй | Хэрэглэгчийн синоним (`test_synonyms.user_id`) |
| 6 | `09`: H15 ба H16 хооронд хоосон мөр → хүснэгт тасарна | Засав |
| 7 | `07`, `10`: CV% "зөвхөн эмчид" гэсэн хуучин бичвэр (v7.1 шийдвэр: эмч болон өвчтөнд) | Шинэчлэв |
| 8 | `06`: "≥ 44px" ↔ бусад газар 44pt | 44pt / 48dp |
| 9 | `extraction.schema.json`: `value_numeric` JSON number (float) ↔ дүрэм 7 (Decimal) | Тайлбар нэмэв: `core` нь `raw_value`-аас Decimal-аар дахин задлана |
| 10 | `/phase` команд `pnpm typecheck…` ↔ CLAUDE.md `just lint && just test` | `just`-ээр нэгтгэв |
| 11 | Format hook нь `jq` + bash шаарддаг — энэ Windows машинд `jq` байхгүй тул чимээгүй ажиллахгүй байв | `node .claude/hooks/format.mjs` (cross-platform) |

### 1.2 Засаагүй — шийдвэр/Phase-д хийх санал
| # | Асуудал | Санал | Хэзээ |
|---|---|---|---|
| A | **iOS 64 локал мэдэгдлийн хязгаар:** 5 эм × өдөрт 2 × 7 хоног = 70 > 64 | Хуваарьлах хугацааг тунгийн тоогоор тооцох: `days = min(7, floor(60 / өдрийн_тун))`, 4-ийг товлол/системд үлдээх; hypothesis тест | Phase 2 |
| B | `medication_intakes`, `vitals` — offline + мэдэгдлийн "Уусан" товч давхар бичигдэж болно | `client_id uuid unique` + `unique(medication_id, scheduled_at)`; idempotent upsert | Phase 2 |
| C | `share_links` PIN brute-force түгжээ (04-т бий) хүснэгтэд талбаргүй | `pin_failed_count`, `locked_until` | Phase 7 |
| D | `audit_logs`, `notifications`, `consents`-ийн RLS тодорхойгүй (patient_id/user_id агуулна) | `user_id = app_user_id()` policy; audit — зөвхөн өөрт хамаарах админы үйлдэл | Phase 1 |
| E | `lab_results.collected_at` нь report-оос хуулбар | Trigger эсвэл service-д синк + тест | Phase 5 |
| F | `auth_attempts`-д индекс байхгүй | `(username, at desc)`, `(ip, at desc)` | Phase 1 |
| G | **Windows машин:** Phase 0 DoD "iOS симулятор" — Windows дээр Xcode/iOS симулятор, Maestro iOS ажиллахгүй | iOS: EAS cloud build + бодит iPhone (dev client); симулятор/Maestro iOS-д Mac (эсвэл CI macOS runner). DoD-г "iOS бодит төхөөрөмж эсвэл macOS CI" болгох | Phase 0 |
| H | Хөгжүүлэлтийн хэрэгсэл дутуу: `just`, `uv`, `pnpm`, `jq` суугаагүй (Node, Docker, Python 3.13 бий) | §3-ын командууд | Phase 0-оос өмнө |
| I | Хавтас git репо биш → `/security-check` (`git diff main...HEAD`), commit review, хянагч agent-ууд ажиллахгүй | `git init` + `.gitignore` (`.env`, `_archive/`, `eval/cases/**/raw/`) + `.gitattributes` (`* text=auto eol=lf`) | ✅ Хийгдсэн (2026.10.28) |

## 2. Суулгасан Claude Code өргөтгөлүүд (project scope → `.claude/settings.json`)
| Plugin | Юунд | Анхаарах |
|---|---|---|
| `pyright-lsp`, `typescript-lsp` | Тодорхойлолт/лавлагаа руу шууд үсрэх, type алдаа — Grep-ээр олон файл уншихаас **хамаагүй бага токен** | `npm i -g pyright typescript-language-server typescript` шаардлагатай (§3) |
| `security-guidance` | Edit бүрт аюултай хэв маягийн анхааруулга; `git commit` бүрт agentic аюулгүй байдлын хяналт (IDOR, auth bypass) | Turn бүрийн LLM хяналтыг `ENABLE_STOP_REVIEW=0`-оор унтраав (токен); commit хяналт идэвхтэй |
| `pr-review-toolkit` | `silent-failure-hunter`, `pr-test-analyzer`, `type-design-analyzer` гэх мэт хянагч agent-ууд | Phase бүрийн төгсгөлд |
| `commit-commands` | `/commit` — Conventional Commits | `git push` хориотой хэвээр |
| `claude-md-management` | CLAUDE.md-г шахаж, сессийн сургамжийг нэмэх (`/revise-claude-md`) | Phase бүрийн төгсгөлд |
| `context7` | Expo SDK, FastAPI, SQLAlchemy-ийн **хувилбарт тохирсон** албан ёсны баримт ("таамаглахгүй" дүрэм) | Анх ашиглахад нэвтрэх хүсэлт гарна |
| `frontend-design` | Web админ самбар, UI-ийн дизайн чанар | |
| **Expo** (`expo@expo-plugins`) | Албан ёсны Expo skill-үүд: expo-router, eas-update, eas-workflows, expo-upgrade, expo-ui… | Суусан (2026.10.28) |

Аль хэдийн бэлэн (суулгах шаардлагагүй): `/code-review`, `/security-review`, `/simplify`, `design:accessibility-review`, `design:ux-copy`, `design:user-research`, `engineering:testing-strategy`, `engineering:deploy-checklist`.

**Санаатайгаар суулгаагүй:** playwright MCP (Phase 1-ийн web хүртэл хэрэггүй; built-in browser хангалттай), asana/linear/notion гэх мэт — MCP сервер бүр хэрэглүүрийн тодорхойлолтоороо turn бүрт токен зарцуулна.

### Төсөлд нэмсэн
- `.claude/agents/ui-reviewer.md` (sonnet) — хүртээмж, 44pt, Dynamic Type, flag өнгө+дүрс+текст, mn.json, эмнэлгийн хил, FlashList
- `.claude/agents/{medical,security}-reviewer.md` → `model: opus` (клиник/аюулгүй байдал — хамгийн хүчтэй загвар)
- `.claude/skills/phi-table/` — PHI хүснэгт: migration → ENABLE+FORCE RLS → 4 policy → 7 RLS тест → аудит → hazard log
- `.claude/hooks/format.mjs` — Ruff/Biome, Windows дээр ажиллана, хэрэгсэл байхгүй бол чимээгүй алгасна
- `permissions.deny`: `_archive/`, `node_modules/`, lock файлууд (уншвал их токен, ашиггүй)

## 3. Таны ажиллуулах командууд (PowerShell)
```powershell
claude plugin install expo@expo-plugins --scope project
npm install -g pyright typescript-language-server typescript pnpm
winget install Casey.Just astral-sh.uv jqlang.jq
git init
```
Дараа нь Claude Code-г дахин эхлүүлж `/plugin`-оор идэвхтэй эсэхийг шалгана.

## 4. Токен хэмнэх
1. **Кирилл текст англиас ~2–3 дахин их токен.** CLAUDE.md turn бүрт ачаалагддаг → ≤ 150 мөр байлга. "Бүх docs заавал унших"-ыг **Phase → docs хүснэгтээр** солив (phase бүрт ~60–70% бага унших).
2. Phase 0-д `backend/CLAUDE.md`, `mobile/CLAUDE.md`, `web/CLAUDE.md` үүсгэ — тухайн хавтсанд ажиллахад л ачаалагдана. Root CLAUDE.md-ээс хэсэг тус бүрийн дүрмийг тийш зөөнө.
3. **Phase хооронд `/clear`**; төлөвийг `docs/PROGRESS.md` дамжуулна. Урт сессэд `/compact`.
4. Олон файлын хайлт → `Explore` subagent; код навигаци → LSP; сангийн API → context7 (вэб хайлтаас бага).
5. Тестийн гаралт: `pytest -q --no-header -x`, `jest --silent`, `vitest --reporter=dot` — `justfile`-д тохируул.
6. Хянагч agent-ууд зөвхөн `git diff`-ийг үзнэ (ui-reviewer-д бичсэн).
7. Загвар: төлөвлөлт, эмнэлэг/аюулгүй байдал — Opus; энгийн CRUD, UI засвар — Sonnet (`/model`).
8. OpenAPI-аас үүсгэсэн client-ийг бүү унш — type-ийг LSP-ээр ав.

## 5. Ажлын бүтээмж
1. Phase бүр: **Plan mode** (Shift+Tab) → `/phase N` → батлах → хэрэгжүүлэх → хянагчид → `/commit` → `/revise-claude-md` → `/clear`.
2. **Зэрэгцээ ажил:** API гэрээ (`just gen-client`) тогтсоны дараа backend ба mobile-ийг тусдаа git worktree / сессэд зэрэг хий (файл давхцахгүй).
3. `justfile`-д `just check` = lint + type + test-ийг нэг командаар; CI-д мөн адил.
4. Phase 4-өөс өмнө eval кейсүүдийг цуглуулж эхэл (хамгийн удаан саатал).
5. Phase бүрийн төгсгөлд `pr-review-toolkit`-ийн `silent-failure-hunter` (try/except-ээр алдаа нуухыг барина — эмнэлгийн өгөгдөлд чухал).

## 6. Чанар
- `core/`-д TDD: эхлээд hypothesis property (жишээ: "хөрвүүлээд буцааж хөрвүүлэхэд утга ба хязгаар хадгалагдана", "flag нь хязгаараас гадуурх утгад хэзээ ч normal биш").
- RLS тест — `phi-table` skill-ийн 7 кейс шинэ хүснэгт бүрт.
- Hazard H1–H17 бүрт тестийн нэрийг 09-д бич (`test_h6_...`) — release шалгалтыг автоматжуулна.
- Eval регресс gate (05) + security-guidance commit review + `/security-check` + `/code-review` давхар.
- Sentry release health, crash-free ≥ 99.5% gate.

## 7. UI/UX сайжруулах санал
1. **Design token-ийг Phase 0-д** `packages/shared/tokens`-д: semantic өнгө (flag: normal/high/low/critical/no_reference) light/dark хоёуланд AA контрасттай; кирилл дэмждэг фонт (Noto Sans / Inter), үндсэн текст ≥ 16pt, "Том фонт" горимд ×1.3.
2. **Нүүр = "Өнөөдөр":** дараагийн тун + том "Уусан" товч (нэг товшилт, haptic, 5 сек "Буцаах" snackbar — баталгаажуулах цонхгүй), дараа нь анхаарах карт. 🆘 үргэлж дээд буланд.
3. **Review (60 сек зорилт):** асуудалтай мөр эхэнд, итгэл өндөр мөрүүд "N мөр асуудалгүй" гэж эвхэгдэнэ; мөр дээр дарахад эх зургийн тухайн хэсэг тодорно; доод тогтмол "Батлах".
4. **Optimistic UI** (TanStack Query) — "Уусан", амин үзүүлэлт offline-д ч шууд харагдана; skeleton loading; алдааны текст бүр дараагийн алхмыг хэлнэ.
5. **Монгол нэр томьёоны толь** (`packages/shared/messages/GLOSSARY.md`): "шинжилгээний хариу", "лавлах хязгаар", "критик утга", "тун" — нэг л хэллэг; `design:ux-copy` skill-ээр хянуул.
6. **Ахмад настан, харааны бэрхшээл:** VoiceOver-д утгыг "Креатинин 1.2 миллиграмм, өндөр" гэж бүтэн уншуулах `accessibilityLabel`; график бүрт хүснэгт хувилбар.
7. Phase 2, 5-ын төгсгөлд 5 хэрэглэгчтэй usability тест (`design:user-research`), дүгнэлтийг `design:research-synthesis`-ээр.
8. Яаралтай карт OFF (H17) — onboarding-д "Яаралтай үед эмч танихад тусална" гэсэн нэг дэлгэцтэй тайлбар + түгжээтэй дэлгэцийн зураг шууд үүсгэх товч.
