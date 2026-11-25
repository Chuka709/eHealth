package expo.modules.dosealarm

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build

/**
 * `setAlarmClock`: exact, kept in Doze, and the one kind of alarm allowed to start a
 * foreground service from the background. Needs the exact-alarm permission on Android 12+;
 * without it nothing is set here and the app's ordinary (inexact) notifications remain (H18).
 * Direct AlarmManager calls: no broadcast round trip (MIUI delayed those - H6, 2026.11.25).
 */
internal object DoseAlarmScheduler {
  const val ACTION_RING = "expo.modules.dosealarm.RING"

  fun canSchedule(context: Context): Boolean {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
    val manager = context.getSystemService(AlarmManager::class.java) ?: return false
    return manager.canScheduleExactAlarms()
  }

  /** Makes the OS equal to `wanted` (id -> instant): what is not wanted any more is cancelled. */
  fun sync(context: Context, wanted: Map<String, Long>) {
    val store = DoseAlarmStore(context)
    val now = System.currentTimeMillis()
    for (id in store.alarms().keys - wanted.keys) cancel(context, id)
    val future = wanted.filterValues { it > now }
    if (!canSchedule(context)) {
      store.saveAlarms(emptyMap())
      return
    }
    for ((id, at) in future) set(context, id, at)
    store.saveAlarms(future)
  }

  /** One more alarm beside the planned ones ("10 мин дараа"); the next `sync` keeps it only
   * when the app still lists it. */
  fun add(context: Context, id: String, at: Long) {
    if (at <= System.currentTimeMillis() || !canSchedule(context)) return
    val store = DoseAlarmStore(context)
    set(context, id, at)
    store.saveAlarms(store.alarms() + (id to at))
  }

  /** After a reboot or an update: the alarms still to come, set again. */
  fun restore(context: Context) {
    val store = DoseAlarmStore(context)
    val now = System.currentTimeMillis()
    val future = store.alarms().filterValues { it > now }
    if (!canSchedule(context)) return
    for ((id, at) in future) set(context, id, at)
    store.saveAlarms(future)
  }

  fun cancel(context: Context, id: String) {
    val manager = context.getSystemService(AlarmManager::class.java)
    val pending = ringIntent(context, id, PendingIntent.FLAG_NO_CREATE)
    if (pending != null) {
      manager?.cancel(pending)
      pending.cancel()
    }
    DoseAlarmStore(context).remove(id)
  }

  fun cancelAll(context: Context) {
    val store = DoseAlarmStore(context)
    for (id in store.alarms().keys) cancel(context, id)
    store.clear()
  }

  private fun set(context: Context, id: String, at: Long) {
    val manager = context.getSystemService(AlarmManager::class.java) ?: return
    // made anew: an older PendingIntent of this id would keep its old intent flags
    ringIntent(context, id, PendingIntent.FLAG_NO_CREATE)?.let {
      manager.cancel(it)
      it.cancel()
    }
    val ring = ringIntent(context, id, PendingIntent.FLAG_UPDATE_CURRENT) ?: return
    try {
      manager.setAlarmClock(AlarmManager.AlarmClockInfo(at, openApp(context)), ring)
    } catch (_: SecurityException) {
      // the permission was taken away meanwhile: the ordinary notification still comes
    }
  }

  private fun ringIntent(context: Context, id: String, flag: Int): PendingIntent? {
    val intent = Intent(context, DoseAlarmReceiver::class.java)
      .setAction(ACTION_RING)
      // the id in the data makes each alarm its own PendingIntent
      .setData(Uri.parse("labtrack-alarm://dose/" + Uri.encode(id)))
      // the foreground broadcast queue: in the shared background one it waited behind other
      // apps (real phone, MIUI) past the 10 s an alarm allows for starting the ringing service
      .addFlags(Intent.FLAG_RECEIVER_FOREGROUND)
    return PendingIntent.getBroadcast(context, 0, intent, flag or PendingIntent.FLAG_IMMUTABLE)
  }

  fun openApp(context: Context): PendingIntent? {
    val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)
      ?: return null
    return PendingIntent.getActivity(
      context,
      0,
      launch,
      PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )
  }
}
