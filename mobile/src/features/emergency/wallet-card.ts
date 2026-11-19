import * as Print from "expo-print";

import type { Locale } from "@/lib/i18n";

import { type CardSection, cardText } from "./card-text";
import { keepForSharing, type ShareResult, shareFile, startExport } from "./export-files";
import type { EmergencyCard } from "./snapshot";

/**
 * The wallet card (docs/08, H17): one A4 page made on the phone (expo-print, offline), so no
 * health data takes a new path to the server (user decision 2.7 (b)). Each language gets one
 * strip to cut out and fold: the front (who, blood type, transplant) and the back (allergies,
 * medicines, contacts, date and limits), each the size of a bank card. A strip grows taller
 * rather than cutting text off, so nothing on the card is ever hidden.
 * Everything the user typed is escaped. The page loads nothing from outside.
 */

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const sections = (parts: CardSection[]) =>
  parts
    .filter((s) => s.lines.length > 0)
    .map(
      (s) =>
        `<section>${s.heading ? `<h3>${escapeHtml(s.heading)}</h3>` : ""}${s.lines
          .map((l) => `<p>${escapeHtml(l)}</p>`)
          .join("")}</section>`,
    )
    .join("");

function strip(card: EmergencyCard, locale: Locale): string {
  const text = cardText(card, locale);
  const lang = locale === "en" ? "en" : "mn"; // never anything else in the markup
  // "SOS" as text: an emoji may print as an empty box without an emoji font
  return `<div class="strip" lang="${lang}">
  <div class="side"><h2>SOS · ${escapeHtml(text.title)}</h2>${sections(text.front)}</div>
  <div class="side">${sections(text.back)}</div>
</div>`;
}

export function walletCardHtml(card: EmergencyCard, locales: Locale[] = ["mn", "en"]): string {
  return `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<style>
  @page { size: A4; margin: 12mm; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, Roboto, "Noto Sans", Arial, sans-serif; color: #000; margin: 0; }
  .strip { display: flex; width: 171.2mm; margin: 0 0 10mm 0; border: 0.3mm dashed #555;
           page-break-inside: avoid; }
  .side { width: 85.6mm; min-height: 54mm; padding: 2.5mm; }
  .side + .side { border-left: 0.3mm dotted #999; } /* fold here */
  h2 { font-size: 10pt; margin: 0 0 1.5mm 0; }
  h3 { font-size: 8pt; margin: 1.2mm 0 0.4mm 0; }
  p { font-size: 8pt; line-height: 1.25; margin: 0; }
</style></head>
<body>${locales.map((l) => strip(card, l)).join("")}</body></html>`;
}

/** Makes the PDF and opens the share sheet (print, Files, mail). */
export async function shareWalletCard(card: EmergencyCard): Promise<ShareResult> {
  const ticket = startExport();
  const { uri } = await Print.printToFileAsync({
    html: walletCardHtml(card),
    width: 595,
    height: 842,
  });
  const file = await keepForSharing(ticket, uri, "emergency-card.pdf");
  return shareFile(ticket, file, "application/pdf");
}
