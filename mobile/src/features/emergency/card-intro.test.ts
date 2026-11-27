import { translatorFor, transplantIntro } from "./card-text";

type Organ = Parameters<typeof transplantIntro>[0][number];
const tr = (organ: string) => ({ organ }) as unknown as Organ;

// DEVICE_TEST 2026.11.27: "I have had a transplant" did not say which organ
test.each([
  ["mn", ["kidney"], "Би бөөр шилжүүлэн суулгуулсан."],
  ["mn", ["kidney", "liver", "kidney"], "Би бөөр, элэг шилжүүлэн суулгуулсан."],
  ["mn", ["hsct"], "Би цусны үүдэл эс шилжүүлэн суулгуулсан."],
  ["mn", ["kidney_pancreas", "kidney"], "Би бөөр ба нойр булчирхай шилжүүлэн суулгуулсан."],
  ["mn", ["cornea"], "Би эвэрлэг бүрхүүл шилжүүлэн суулгуулсан."],
  ["mn", ["other", "kidney"], "Би бөөр шилжүүлэн суулгуулсан."],
  ["mn", [], "Би шилжүүлэн суулгалт хийлгэсэн."],
  ["en", ["hsct"], "I have had a transplant: blood stem cell (bone marrow)."],
  ["mn", ["other"], "Би шилжүүлэн суулгалт хийлгэсэн."],
  ["en", ["liver"], "I have had a transplant: liver."],
  ["en", ["other"], "I have had a transplant."],
] as const)("%s %j -> %s", (locale, organs, expected) => {
  const t = translatorFor(locale);
  const e = (key: string, values?: Record<string, string | number>) =>
    t(`app.emergency.${key}`, values);
  expect(transplantIntro(organs.map(tr), e)).toBe(expected);
});
