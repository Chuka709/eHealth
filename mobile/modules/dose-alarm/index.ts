import { requireOptionalNativeModule } from "expo";

/**
 * Android alarm clock for dose reminders (Q79): rings on the alarm stream, so silent mode does
 * not mute it. Absent on iOS, web and in Jest - every call is then a no-op and the ordinary
 * notification sound applies. A failing native call never throws into the caller (a sign-out
 * must clear everything else even then - security review M1).
 */
type DoseAlarmNative = {
  canSchedule(): boolean;
  sync(
    alarms: { id: string; at: number }[],
    title: string,
    body: string,
    stopLabel: string,
    fallback: string,
  ): void;
  add(id: string, at: number): void;
  cancel(id: string): void;
  cancelAll(): void;
  stop(): void;
};

export type AlarmTexts = {
  /** the ringing notification: "Эмийн сануулга дуугарч байна" */
  title: string;
  /** under it: stopping the sound does not record the dose */
  body: string;
  /** its button: "Дууг унтраах" */
  stop: string;
  /** the loud fallback when the alarm cannot ring: the reminder title */
  fallback: string;
};

const native = requireOptionalNativeModule<DoseAlarmNative>("DoseAlarm");

function quietly(call: (n: DoseAlarmNative) => void): void {
  if (!native) return;
  try {
    call(native);
  } catch {
    // the app's notifications still come; the next sync tries again
  }
}

/** Whether alarms can ring here: Android with the exact-alarm permission. */
export function alarmClockAvailable(): boolean {
  try {
    return native?.canSchedule() ?? false;
  } catch {
    return false;
  }
}

/** The OS's alarm clocks made equal to `alarms` (others cancelled). */
export function syncAlarmClocks(
  alarms: readonly { id: string; at: number }[],
  texts: AlarmTexts,
): void {
  quietly((n) => n.sync([...alarms], texts.title, texts.body, texts.stop, texts.fallback));
}

/** One alarm beside the plan ("10 мин дараа"). */
export function addAlarmClock(id: string, at: number): void {
  quietly((n) => n.add(id, at));
}

export function cancelAlarmClock(id: string): void {
  quietly((n) => n.cancel(id));
}

/** Sign-out: nothing of this account may ring on the phone (rule 8). */
export function cancelAllAlarmClocks(): void {
  quietly((n) => n.cancelAll());
}

/** Silence one ringing now (a dose recorded, the app opened). */
export function stopRinging(): void {
  quietly((n) => n.stop());
}
