/** Ulaanbaatar has one offset all year (+08:00, no daylight saving). */
const ULAANBAATAR = "+08:00";

/**
 * A date the person picked from a printed result, as the API takes it: the day, and the time
 * only when one is printed (a day alone is never given a made-up time - H30).
 */
export function localMoment(day: string, time: string | null): string {
  return `${day}T${time ?? "00:00"}:00${ULAANBAATAR}`;
}
