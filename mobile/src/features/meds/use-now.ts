import { useEffect, useState } from "react";
import { AppState } from "react-native";

/**
 * The current time, refreshed every minute and when the app comes back to the foreground -
 * today's doses and the month never stay on the day the screen was opened.
 */
export function useNow(intervalMs = 60_000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const tick = () => setNow(new Date());
    const timer = setInterval(tick, intervalMs);
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") tick();
    });
    return () => {
      clearInterval(timer);
      sub.remove();
    };
  }, [intervalMs]);
  return now;
}
