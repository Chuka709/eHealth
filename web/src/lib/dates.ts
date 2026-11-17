// One date format for the whole admin panel: 2026.03.14 (14:05), always Ulaanbaatar time.
const parts = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Ulaanbaatar",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export function formatDate(iso: string, withTime = false): string {
  const p = Object.fromEntries(parts.formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  const date = `${p.year}.${p.month}.${p.day}`;
  return withTime ? `${date} ${p.hour}:${p.minute}` : date;
}

/** A date known only to the month or the year shows only that: "2024.03", "2024"
 * (the stored day is a placeholder, never shown). */
export function formatPartial(isoDate: string, precision: string): string {
  const [y, m] = isoDate.slice(0, 10).split("-");
  if (precision === "year") return y;
  if (precision === "month") return `${y}.${m}`;
  return formatDate(isoDate);
}

/** 900 -> "15:00" */
export function minutesSeconds(seconds: number): string {
  const s = Math.max(0, seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
