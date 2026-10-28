import assert from "node:assert/strict";
import { test } from "node:test";

import { colors, type Flag, type Scheme } from "./tokens.ts";

// WCAG 2.x relative luminance and contrast ratio.
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = Number.parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

const AA_TEXT = 4.5;

for (const scheme of ["light", "dark"] as Scheme[]) {
  const p = colors[scheme];
  test(`${scheme}: body and muted text meet AA on background and surface`, () => {
    for (const bg of [p.background, p.surface]) {
      assert.ok(contrast(p.text, bg) >= AA_TEXT);
      assert.ok(contrast(p.textMuted, bg) >= AA_TEXT);
    }
    assert.ok(contrast(p.onPrimary, p.primary) >= AA_TEXT);
  });

  test(`${scheme}: every flag badge meets AA`, () => {
    for (const [flag, { fg, bg }] of Object.entries(p.flag) as [Flag, { fg: string; bg: string }][]) {
      assert.ok(contrast(fg, bg) >= AA_TEXT, `${scheme}/${flag}: ${contrast(fg, bg).toFixed(2)}`);
    }
  });
}
