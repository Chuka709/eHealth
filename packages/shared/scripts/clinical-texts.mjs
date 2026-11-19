// Writes docs/CLINICAL_TEXTS_REVIEW.md: the app's clinical wording in Mongolian and English,
// for the transplant physician and the laboratory physician to review in one sitting (Q12,
// physician decision 2026-11-18). Run again after any change to these texts:
//   node packages/shared/scripts/clinical-texts.mjs
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const read = (lang) =>
  JSON.parse(readFileSync(join(here, "..", "messages", `${lang}.json`), "utf8"));
const mn = read("mn");
const en = read("en");

// [section title, namespace, who reviews]
const SECTIONS = [
  ["Шинжилгээний хариу хянах (ноорог, тэмдэглэгээ, критик)", "app.upload.review", "лабын эмч"],
  ["Нүүр: шинжилгээ, «Анхаарах»", "app.home.lab", "эмч, лабын эмч"],
  ["Хандлагын график", "app.trends", "эмч, лабын эмч"],
  ["Цагийн хэлхээс, харьцуулалт", "app.timeline", "эмч"],
  ["Эмчийн зорилт, тэмдэглэл, такролимусын CV%", "app.clinician", "эмч"],
  ["Эм, тун, сануулга, каталоггүй эмийн ангилал", "app.meds", "эмч"],
  ["Асран хамгаалагч, тунгийн мэдэгдэл", "app.caregivers", "эмч"],
  ["Мэдэгдлийн текст", "notification", "эмч"],
  ["Шилжүүлэн суулгалт", "app.transplant", "эмч"],
  ["Амин үзүүлэлт, эрүүл мэндийн бүртгэл", "app.health", "эмч"],
  ["Амин үзүүлэлтийн алдааны мессеж (сахарын нэгж г.м.)", "error.vital", "эмч, лабын эмч"],
  ["Яаралтай карт", "app.emergency", "эмч"],
  ["Апп-ын тухай (зориулалт, хийдэггүй зүйлс)", "app.about", "эмч"],
  ["Web-ээр хуваалцсан мэдээлэл (эмч харна)", "web.share", "эмч, лабын эмч"],
];

const at = (obj, path) => path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);
const flat = (obj, prefix, out = []) => {
  for (const [k, v] of Object.entries(obj ?? {})) {
    const key = `${prefix}.${k}`;
    if (v && typeof v === "object") flat(v, key, out);
    else out.push(key);
  }
  return out;
};
const cell = (s) => (s == null ? "—" : String(s).replaceAll("|", "\\|").replaceAll("\n", " "));

const lines = [
  "# Эмнэлзүйн текстийн хяналт (Q12)",
  "",
  "**Зорилго:** шилжүүлэн суулгалтын эмч + лабораторийн эмч апп-ын эмнэлзүйн текстийг нэг дор хянана (эмчийн шийдвэр 2026.11.18, ★). Одоогоор зөвхөн такролимусын CV%-ийн карт хянуулах хүртэл өвчтөнд нуугдсан; бусад текст апп-д харагдаж байгаа тул бетаг нээхээс өмнө хянагдсан байх ёстой (BETA B5).",
  "",
  "**Яаж:** мөр бүрийн «Санал» баганад «OK» эсвэл засварласан монгол текстийг бичнэ. `{n}`, `{date}` зэрэг нь апп-ын орлуулах утга — хэвээр үлдээнэ. Англи текст — лавлагаа.",
  "",
  "**Анхаар:** энэ файлыг `node packages/shared/scripts/clinical-texts.mjs` үүсгэдэг; хянуулж дууссаны дараа засварыг `packages/shared/messages/mn.json`-д оруулна. PDF хураангуйн текст (`backend/src/labtrack/summary_codes.py`) мөн эдгээр текстээс авдаг.",
  "",
];
let total = 0;
for (const [title, ns, who] of SECTIONS) {
  const keys = flat(at(mn, ns), ns);
  if (keys.length === 0) continue;
  total += keys.length;
  lines.push(`## ${title}`, "", `Хянагч: ${who}. Түлхүүр: \`${ns}\` (${keys.length}).`, "");
  lines.push("| Түлхүүр | Монгол | English | Санал |", "|---|---|---|---|");
  for (const key of keys) {
    lines.push(
      `| \`${key.slice(ns.length + 1)}\` | ${cell(at(mn, key))} | ${cell(at(en, key))} | |`,
    );
  }
  lines.push("");
}
lines.splice(1, 0, "", `_Нийт ${total} текст._`);
writeFileSync(
  join(here, "..", "..", "..", "docs", "CLINICAL_TEXTS_REVIEW.md"),
  `${lines.join("\n")}\n`,
);
console.log(`docs/CLINICAL_TEXTS_REVIEW.md: ${total} texts`);
