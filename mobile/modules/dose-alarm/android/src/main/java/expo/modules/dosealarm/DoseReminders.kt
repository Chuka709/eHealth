package expo.modules.dosealarm

import android.app.NotificationManager
import android.content.Context
import android.service.notification.StatusBarNotification

/**
 * The app's own dose reminder (expo-notifications posts it with the reminder id as its tag),
 * found so the alarm clock can take it over instead of showing a second notification of its
 * own - one notification per dose time (the user's choice 2026.11.26, after a real phone
 * showed two). The alarm and the reminder fire at the same instant, so the reminder may come a
 * moment later: callers look again for up to LOOK_MS.
 */
internal object DoseReminders {
  const val LOOK_MS = 4_000L
  const val LOOK_EVERY_MS = 250L

  /** Raised by a sign-out: work started before it never shows a reminder again (security
   * review H1 2026.11.26 - a reminder with names given back after the tray was cleared). */
  @Volatile
  var epoch = 0
    private set

  fun signedOut() {
    epoch += 1
  }

  fun find(context: Context, id: String): StatusBarNotification? {
    val manager = context.getSystemService(NotificationManager::class.java) ?: return null
    return try {
      manager.activeNotifications.firstOrNull { it.tag == id }
    } catch (_: Exception) {
      null
    }
  }

  fun cancel(context: Context, sbn: StatusBarNotification) {
    context.getSystemService(NotificationManager::class.java)?.cancel(sbn.tag, sbn.id)
  }
}
