/**
 * Dates as shown in the app: Asia/Ulaanbaatar, `YYYY.MM.DD` and `YYYY.MM.DD HH:mm` (24 h),
 * the same in both languages (CLAUDE.md: DB is UTC, display is Ulaanbaatar time).
 */
const parts = (iso: string) => {
  const formatted = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Ulaanbaatar",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    formatted.find((part) => part.type === type)?.value ?? "";
  return { y: get("year"), m: get("month"), d: get("day"), h: get("hour"), min: get("minute") };
};

export function formatDate(iso: string): string {
  const { y, m, d } = parts(iso);
  return `${y}.${m}.${d}`;
}

export function formatDateTime(iso: string): string {
  const { y, m, d, h, min } = parts(iso);
  return `${y}.${m}.${d} ${h}:${min}`;
}
