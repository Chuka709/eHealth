package expo.modules.dosealarm

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.media.AudioAttributes
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.service.notification.StatusBarNotification

/**
 * When the alarm clock cannot ring (the ringing service may not start, the sound cannot play),
 * the reminder must still be heard: while the alarm clock is on, the app's own reminder comes on
 * a silent channel (no double sound), so without this it would come silently - worse than before
 * Q79 (medical review H-1). The reminder itself is posted again on a loud channel (the alarm
 * tone on the alarm usage - not through silent mode, only a service can do that): still one
 * notification per dose time. Only when the reminder is not there a loud one of our own,
 * without a medicine name (H10).
 */
internal object DoseAlarmFallback {
  private const val CHANNEL = "dose-alarm-fallback"
  private const val NOTIFICATION_ID = 7302

  private val handler = Handler(Looper.getMainLooper())

  fun cancel(context: Context) {
    context.getSystemService(NotificationManager::class.java)?.cancel(NOTIFICATION_ID)
  }

  /**
   * Once the app's reminder `id` is in the tray (it may come a moment after the alarm); nothing
   * when a sign-out came after `epoch` (security review M1).
   */
  fun postWhenShown(
    context: Context,
    id: String?,
    epoch: Int = DoseReminders.epoch,
    done: () -> Unit,
  ) {
    if (id == null) {
      if (epoch == DoseReminders.epoch) post(context, null)
      done()
      return
    }
    var waited = 0L
    val look = object : Runnable {
      override fun run() {
        if (epoch != DoseReminders.epoch) {
          done()
          return
        }
        val found = DoseReminders.find(context, id)
        if (found == null && waited < DoseReminders.LOOK_MS) {
          waited += DoseReminders.LOOK_EVERY_MS
          handler.postDelayed(this, DoseReminders.LOOK_EVERY_MS)
          return
        }
        post(context, found)
        done()
      }
    }
    look.run()
  }

  fun post(context: Context, reminder: StatusBarNotification?) {
    val manager = context.getSystemService(NotificationManager::class.java) ?: return
    val store = DoseAlarmStore(context)
    ensureChannel(context, manager, store)
    if (reminder != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      try {
        // the same tag and id: it replaces the silent one, its buttons and tap kept
        val title = reminder.notification.extras.getCharSequence(Notification.EXTRA_TITLE)
        // the title is the time only ("10:00-ийн эмийн сануулга"), never a name (reminders.ts)
        val public = Notification.Builder(context, CHANNEL)
          .setSmallIcon(context.applicationInfo.icon)
          .setContentTitle(title ?: store.fallbackTitle())
          .build()
        // a copy: the builder writes into the notification it recovers (kept for the restore below)
        val loud = Notification.Builder.recoverBuilder(context, reminder.notification.clone())
          .setChannelId(CHANNEL)
          .setCategory(Notification.CATEGORY_ALARM)
          .setVisibility(Notification.VISIBILITY_PRIVATE)
          .setPublicVersion(public)
          .build()
        manager.notify(reminder.tag, reminder.id, loud)
        return
      } catch (_: Exception) {
        // our own one below
      }
    }
    if (reminder != null) {
      // taken over and cancelled before: back as it was ("Уусан" kept), then our loud one
      runCatching { manager.notify(reminder.tag, reminder.id, reminder.notification) }
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

  private fun ensureChannel(context: Context, manager: NotificationManager, store: DoseAlarmStore) {
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
  }
}
