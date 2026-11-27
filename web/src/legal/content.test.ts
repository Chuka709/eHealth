import { describe, expect, test } from "vitest";

import { LEGAL, type LegalPage, legalLocale } from "./content";

const pages = Object.keys(LEGAL) as LegalPage[];
const text = (page: LegalPage, locale: "mn" | "en") =>
  JSON.stringify(LEGAL[page][locale]).toLowerCase();

describe("legal pages (8.1)", () => {
  test.each(pages)("%s: Mongolian and English say the same, section by section", (page) => {
    const { mn, en } = LEGAL[page];
    expect(en.sections.length).toBe(mn.sections.length);
    mn.sections.forEach((s, i) => {
      const other = en.sections[i];
      expect(other.blocks.length).toBe(s.blocks.length);
      s.blocks.forEach((b, j) => {
        const o = other.blocks[j];
        expect(typeof o).toBe(typeof b);
        if (Array.isArray(b)) expect((o as readonly string[]).length).toBe(b.length);
      });
    });
    expect(en.updated).toBe(mn.updated);
  });

  test.each(pages)("%s: marked as a draft until the lawyer has reviewed it", (page) => {
    expect(LEGAL[page].mn.draft).toMatch(/^НООРОГ/);
    expect(LEGAL[page].en.draft).toMatch(/^DRAFT/);
  });

  test("the policy states the app's boundary and the facts users rely on", () => {
    const mn = text("privacy", "mn");
    const en = text("privacy", "en");
    // rule 10: no diagnosis, treatment or dose advice; no interaction checks
    expect(mn).toContain("онош тавихгүй");
    expect(en).toContain("does not diagnose");
    // AI reading is optional, two consents, de-identified, drafts only (rule 4)
    expect(en).toContain("two separate consents");
    expect(en).toContain("draft");
    // administrators never see health data (rule 2a); deletion after 30 days
    expect(en).toContain("administrators (company staff) cannot see your health data");
    expect(en).toContain("30 days");
    expect(mn).toContain("30 хоногийн");
  });

  test("the deletion page never offers a request form or an account lookup", () => {
    const en = text("deletion", "en");
    expect(en).toContain("cannot check whether an account exists");
    expect(en).toContain("never ask you for a code or password");
    // the support path re-identifies by call-back to the registered number and the ID number
    expect(en).toContain("never call another number");
    expect(en).toContain("national id number");
  });

  test("no promise the code does not keep (8.1 security review)", () => {
    for (const page of pages) {
      for (const locale of ["mn", "en"] as const) {
        const all = text(page, locale);
        // document keys are per file, not per user: backups are not made unreadable by deletion
        expect(all).not.toMatch(/per user|backups become unreadable|хэрэглэгч бүрийн тусдаа/);
        expect(all).not.toMatch(/уншигдахгүй болно|уншигдах боломжгүй/);
      }
    }
  });

  test("the medical notice keeps the app's boundary (rule 10, H5, H16-H18)", () => {
    const en = text("terms", "en");
    for (const fact of [
      "does not diagnose",
      "do not take it twice",
      "no mark does not mean normal",
      "no alert does not mean a dose was taken",
      "may be out of date",
      "call 103",
    ]) {
      expect(en).toContain(fact);
    }
    expect(text("terms", "mn")).toContain("103");
  });

  // Before the store listing (8.4 release check): LEGAL_RELEASE=1 pnpm --filter web test
  test.runIf(process.env.LEGAL_RELEASE === "1")("no placeholder is left for release", () => {
    for (const page of pages) {
      for (const locale of ["mn", "en"] as const) {
        expect(JSON.stringify(LEGAL[page][locale])).not.toMatch(/\[[^\]]+\]/);
        expect(LEGAL[page][locale].draft).toBe("");
      }
    }
  });

  test("only ?lang=en switches to English", () => {
    expect(legalLocale("en")).toBe("en");
    for (const raw of [undefined, "mn", "EN", ["en"], "fr"]) expect(legalLocale(raw)).toBe("mn");
  });
});
