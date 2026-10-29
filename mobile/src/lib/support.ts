/**
 * The organisation's support phone, shown on "forgot password" and the admin-reset notice
 * (docs/04 §1). Build-time config (app.config.ts requires it outside development, same rule).
 */
export function parseSupportPhone(
  raw: string | undefined,
): { display: string; url: string } | null {
  const display = raw?.trim() ?? "";
  if (!/^\+?[0-9 ()-]+$/.test(display)) return null;
  const digits = display.replace(/\D/g, "");
  // At least a local number's worth of digits ("0000" would not reach anyone).
  if (digits.length < 7 || digits.length > 15) return null;
  return { display, url: `tel:${display.startsWith("+") ? "+" : ""}${digits}` };
}

const phone = parseSupportPhone(process.env.EXPO_PUBLIC_SUPPORT_PHONE);

export const supportPhone: string | null = phone?.display ?? null;
export const supportPhoneUrl: string | null = phone?.url ?? null;
