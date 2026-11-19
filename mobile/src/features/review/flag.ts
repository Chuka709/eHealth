import type { Flag } from "@labtrack/shared";

/** The server's flags (result_flag) - the app never computes one (rule 6). */
export const FLAGS = new Set([
  "normal",
  "low",
  "high",
  "critical_low",
  "critical_high",
  "abnormal",
  "no_reference",
  "unknown",
]);
export const CRITICAL_FLAGS = new Set(["critical_low", "critical_high"]);

/** The colour/glyph token of a server flag (colour + glyph + text, never colour alone). */
export function flagToken(flag: string): Flag {
  if (CRITICAL_FLAGS.has(flag)) return "critical";
  if (flag === "normal" || flag === "low" || flag === "high" || flag === "abnormal") return flag;
  return "no_reference";
}

/** The message key of a flag's text (`app.upload.review.flags.*`). */
export function flagKey(flag: string): string {
  return FLAGS.has(flag) ? flag : "unknown";
}
