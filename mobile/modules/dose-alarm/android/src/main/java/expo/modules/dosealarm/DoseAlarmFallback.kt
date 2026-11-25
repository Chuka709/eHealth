package expo.modules.dosealarm

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.media.AudioAttributes
import android.net.Uri
import android.os.Build

/**
 * When the alarm clock cannot ring (the ringing service may not start, the sound cannot play),
 * the reminder must still be heard: while the alarm clock is on, the app's own reminder comes on
 * a silent channel (no double sound), so without this it would come silently - worse than before
 * Q79 (medical review H-1). A loud notification of our own instead: the alarm tone on the alarm
 * usage (not through silent mode - only a service can do that), no medicine name (H10).
 */
internal object DoseAlarmFallback {
  private const val CHANNEL = "dose-alarm-fallback"
  private const val NOTIFICATION_ID = 7302

  fun cancel(context: Context) {
    context.getSystemService(NotificationManager::class.java)?.cancel(NOTIFICATION_ID)
  }

  fun post(context: Context) {
    val manager = context.getSystemService(NotificationManager::class.java) ?: return
    val store = DoseAlarmStore(context)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      val channel = NotificationChannel(CHANNEL, store.fallbackTitle(), NotificationManager.IMPORTANCE_HIGH)
      val sound = context.resources.getIdentifier("dose_alarm", "raw", context.packageName)
      if (sound != 0) {
        channel.setSound(
          Uri.parse("android.resource://${context.packageName}/$sound"),
          AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_ALARM)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build(),
        )
      }
      channel.enableVibration(true)
      channel.lockscreenVisibility = Notification.VISIBILITY_PRIVATE
      manager.createNotificationChannel(channel)
    }
    val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      Notification.Builder(context, CHANNEL)
    } else {
      @Suppress("DEPRECATION")
      Notification.Builder(context).setPriority(Notification.PRIORITY_MAX)
    }
    val notification = builder
      .setSmallIcon(context.applicationInfo.icon)
      .setContentTitle(store.fallbackTitle())
      .setCategory(Notification.CATEGORY_ALARM)
      .setAutoCancel(true)
      .setContentIntent(DoseAlarmScheduler.openApp(context))
      .build()
    try {
      manager.notify(NOTIFICATION_ID, notification)
    } catch (_: Exception) {
      // notifications are off for the app: the app's own warning says so (H6)
    }
  }
}
