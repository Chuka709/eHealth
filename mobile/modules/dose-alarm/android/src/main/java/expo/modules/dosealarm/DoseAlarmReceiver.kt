package expo.modules.dosealarm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build

/** The alarm itself (starts the ringing service) and restoring alarms after a reboot/update. */
class DoseAlarmReceiver : BroadcastReceiver() {
  override fun onReceive(context: Context, intent: Intent) {
    when (intent.action) {
      DoseAlarmScheduler.ACTION_RING -> {
        val id = intent.data?.lastPathSegment?.let { Uri.decode(it) }
        if (id != null) DoseAlarmStore(context).remove(id)
        val ring = Intent(context, DoseAlarmService::class.java)
          .setAction(DoseAlarmService.ACTION_START)
          // the service takes the app's reminder of this id over as its notification
          .putExtra(DoseAlarmService.EXTRA_ID, id)
        try {
          if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(ring)
          } else {
            context.startService(ring)
          }
        } catch (_: Exception) {
          // not allowed to start now: the app's reminder is silent meanwhile - ring it loud,
          // once it is in the tray (kept alive meanwhile)
          val pending = goAsync()
          DoseAlarmFallback.postWhenShown(context.applicationContext, id) { pending.finish() }
        }
      }
      Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED ->
        DoseAlarmScheduler.restore(context)
    }
  }
}
