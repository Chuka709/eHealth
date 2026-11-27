package expo.modules.dosealarm

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.service.notification.StatusBarNotification

/**
 * Rings on the alarm stream (sounds in silent mode, like an alarm clock - Q79) with vibration
 * for at most RING_MS, then stops by itself (H40: a reminder that never stops would get the
 * reminders turned off). Stopped earlier by its notification's stop button, or by the app
 * (a dose recorded, the app opened).
 *
 * One notification per dose time (the user's choice 2026.11.26, after a real phone showed two):
 * it takes the app's own reminder of that time over as its notification - title, medicine list,
 * "Уусан" / "10 мин дараа" and tap kept, "Дуу хаах" added - and gives it back to the tray
 * when the sound runs out or is stopped by its button, so an unanswered reminder stays. Private on the lock
 * screen: when the phone hides sensitive content only a name-free version shows (H10). When it
 * cannot start or play, the reminder itself rings loud instead (DoseAlarmFallback).
 */
class DoseAlarmService : Service() {
  private var player: MediaPlayer? = null
  private var vibrator: Vibrator? = null
  private val handler = Handler(Looper.getMainLooper())
  private val timeout = Runnable { stopRinging(giveBack = true) }

  /** the alarm ringing now (the app's reminder id) */
  private var alarmId: String? = null

  /** the app's reminder taken over as this service's notification, to give back */
  private var taken: StatusBarNotification? = null
  private var looked = 0L
  private var epoch = 0
  private val look = Runnable { takeOver() }

  override fun onBind(intent: Intent?): IBinder? = null

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    if (intent?.action == ACTION_STOP) {
      stopRinging(giveBack = intent.getBooleanExtra(EXTRA_GIVE_BACK, false))
      return START_NOT_STICKY
    }
    // another alarm while one rings: the earlier reminder goes back to the tray first
    giveBack()
    alarmId = intent?.getStringExtra(EXTRA_ID)
    epoch = DoseReminders.epoch
    val found = alarmId?.let { DoseReminders.find(this, it) }
    val merged = found?.let { takeOverNotification(it) }
    val notification = merged ?: buildNotification()
    try {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
        // Android 14+: allowed while the app holds the exact-alarm permission; without it this
        // throws and the loud fallback below rings instead
        startForeground(
          NOTIFICATION_ID,
          notification,
          ServiceInfo.FOREGROUND_SERVICE_TYPE_SYSTEM_EXEMPTED,
        )
      } else {
        // before Android 14 only location/camera/microphone types are checked; the manifest's
        // systemExempted bit (0x400) is ignored there - no Build.VERSION_CODES.Q branch needed
        startForeground(NOTIFICATION_ID, notification)
      }
    } catch (_: Exception) {
      // never a silent reminder (medical review H-1)
      DoseAlarmFallback.postWhenShown(applicationContext, alarmId, epoch) {}
      alarmId = null
      stopSelf()
      return START_NOT_STICKY
    }
    ringing = Ringing(null, null, emptyList())
    if (found != null && merged != null) {
      taken = found
      ringing = snapshot(found)
      DoseReminders.cancel(this, found)
    } else if (alarmId != null) {
      looked = 0
      handler.removeCallbacks(look)
      handler.postDelayed(look, DoseReminders.LOOK_EVERY_MS)
    }
    if (!startRinging()) return START_NOT_STICKY
    wakeScreen()
    handler.removeCallbacks(timeout)
    handler.postDelayed(timeout, RING_MS)
    return START_NOT_STICKY
  }

  /**
   * The screen on for a few seconds, like an alarm clock: a notification alone does not wake it
   * (real phone 2026.11.27: it rang with the screen dark, nothing to read). The lock screen then
   * shows the reminder (its name-free version where the phone hides sensitive content - H10).
   */
  private fun wakeScreen() {
    val power = getSystemService(PowerManager::class.java) ?: return
    if (power.isInteractive) return
    runCatching {
      @Suppress("DEPRECATION") // still turns the screen on; an activity would open the app
      power.newWakeLock(
        PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP or
          PowerManager.ON_AFTER_RELEASE,
        "labtrack:dose-alarm",
      ).acquire(WAKE_MS)
    }
  }

  /** The reminder came a moment after the alarm: it becomes this notification now. */
  private fun takeOver() {
    val id = alarmId ?: return
    if (taken != null || epoch != DoseReminders.epoch) return
    val found = DoseReminders.find(this, id)
    if (found == null) {
      looked += DoseReminders.LOOK_EVERY_MS
      if (looked < DoseReminders.LOOK_MS) handler.postDelayed(look, DoseReminders.LOOK_EVERY_MS)
      return
    }
    val merged = takeOverNotification(found) ?: return // two notifications, never none
    try {
      getSystemService(NotificationManager::class.java)?.notify(NOTIFICATION_ID, merged)
      taken = found
      ringing = snapshot(found)
      DoseAlarmActivity.refresh()
      DoseReminders.cancel(this, found)
    } catch (_: Exception) {
      // the reminder stays as it is
    }
  }

  /** The reminder back in the tray as it was (its own silent channel - no second sound). */
  private fun giveBack() {
    handler.removeCallbacks(look)
    val sbn = taken ?: return
    taken = null
    if (epoch != DoseReminders.epoch) return // signed out meanwhile: the tray stays empty
    try {
      getSystemService(NotificationManager::class.java)?.notify(sbn.tag, sbn.id, sbn.notification)
    } catch (_: Exception) {
      // notifications turned off meanwhile: nothing to show it in
    }
  }

  /** false when nothing could ring here: the reminder rang loud on its own and this stopped */
  private fun startRinging(): Boolean {
    if (player == null) {
      val attributes = AudioAttributes.Builder()
        .setUsage(AudioAttributes.USAGE_ALARM)
        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
        .build()
      player = try {
        MediaPlayer().apply {
          setAudioAttributes(attributes)
          setDataSource(this@DoseAlarmService, soundUri())
          isLooping = true
          prepare()
          start()
        }
      } catch (_: Exception) {
        null
      }
      if (player == null) {
        // no sound possible here: the reminder rings loud on its own instead, once
        val sbn = taken
        taken = null
        if (sbn != null) {
          DoseAlarmFallback.post(this, sbn)
        } else {
          DoseAlarmFallback.postWhenShown(applicationContext, alarmId, epoch) {}
        }
        stopRinging(giveBack = false)
        return false
      }
    }
    if (vibrator == null) {
      vibrator = vibratorService()?.also { v ->
        val effect = VibrationEffect.createWaveform(PATTERN, 0)
        val attributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).build()
        @Suppress("DEPRECATION")
        v.vibrate(effect, attributes)
      }
    }
    return true
  }

  /**
   * giveBack: the reminder returns to the tray - only when the sound ran out or the user
   * pressed "Дуу хаах" or swiped it away (unanswered, it must stay - medical review M2:
   * swiping an alarm is how people silence it). Never when the app stops it: the app was
   * opened, a dose recorded or snoozed ("Уусан" must not leave a copy behind - security
   * review M2), or a sign-out.
   */
  private fun stopRinging(giveBack: Boolean) {
    handler.removeCallbacks(timeout)
    if (giveBack) {
      giveBack()
    } else {
      handler.removeCallbacks(look)
      taken = null
    }
    alarmId = null
    ringing = null
    DoseAlarmActivity.close()
    player?.let {
      runCatching { it.stop() }
      runCatching { it.release() }
    }
    player = null
    vibrator?.cancel()
    vibrator = null
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
      stopForeground(STOP_FOREGROUND_REMOVE)
    } else {
      @Suppress("DEPRECATION")
      stopForeground(true)
    }
    stopSelf()
  }

  override fun onDestroy() {
    handler.removeCallbacks(timeout)
    // however it ends: no names kept, no screen left (security review M3)
    ringing = null
    DoseAlarmActivity.close()
    giveBack()
    player?.let { runCatching { it.release() } }
    player = null
    vibrator?.cancel()
    vibrator = null
    super.onDestroy()
  }

  /** The app's own bundled tone (res/raw/dose_alarm), else the phone's alarm sound. */
  private fun soundUri(): Uri {
    val id = resources.getIdentifier("dose_alarm", "raw", packageName)
    return if (id != 0) {
      Uri.parse("android.resource://$packageName/$id")
    } else {
      RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
    }
  }

  private fun vibratorService(): Vibrator? =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
      getSystemService(VibratorManager::class.java)?.defaultVibrator
    } else {
      @Suppress("DEPRECATION")
      getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
    }

  private fun ensureChannel(store: DoseAlarmStore) {
    val manager = getSystemService(NotificationManager::class.java)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && manager != null) {
      // shown on top (heads-up) but quiet: the service plays the sound itself; private on the
      // lock screen - it carries the reminder's own text (H10)
      manager.deleteNotificationChannel(OLD_CHANNEL)
      val channel = NotificationChannel(CHANNEL, store.title(), NotificationManager.IMPORTANCE_HIGH)
      channel.setSound(null, null)
      channel.enableVibration(false)
      channel.lockscreenVisibility = Notification.VISIBILITY_PRIVATE
      manager.createNotificationChannel(channel)
    }
  }

  private fun stopIntent(giveBack: Boolean): PendingIntent = PendingIntent.getService(
    this,
    if (giveBack) 1 else 2,
    Intent(this, DoseAlarmService::class.java)
      .setAction(ACTION_STOP)
      .putExtra(EXTRA_GIVE_BACK, giveBack),
    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
  )

  /** The alarm screen: opened by the OS when the phone is locked or asleep (Android 14+: only
   * while the app may use full-screen intents - else the notification alone, as before). */
  private fun screenIntent(): PendingIntent = PendingIntent.getActivity(
    this,
    3,
    Intent(this, DoseAlarmActivity::class.java)
      .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_NO_USER_ACTION),
    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
  )

  /** What the alarm screen shows: the reminder's own title, list and buttons (memory only). */
  private fun snapshot(sbn: StatusBarNotification): Ringing {
    val n = sbn.notification
    return Ringing(
      n.extras.getCharSequence(Notification.EXTRA_TITLE),
      n.extras.getCharSequence(Notification.EXTRA_TEXT),
      n.actions?.toList() ?: emptyList(),
    )
  }

  private fun newBuilder(): Notification.Builder =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      Notification.Builder(this, CHANNEL)
    } else {
      @Suppress("DEPRECATION")
      Notification.Builder(this)
    }

  private fun stopAction(store: DoseAlarmStore): Notification.Action =
    Notification.Action.Builder(null, store.stopLabel(), stopIntent(giveBack = true)).build()

  /**
   * The app's reminder as the ringing notification. Under its medicine list the note that
   * stopping the sound records nothing. Swiping it away silences it; the reminder stays.
   * null when it cannot be made: the service's own notification instead.
   */
  private fun takeOverNotification(sbn: StatusBarNotification): Notification? {
    val store = DoseAlarmStore(this)
    return try {
      ensureChannel(store)
      val original = sbn.notification
      val title = original.extras.getCharSequence(Notification.EXTRA_TITLE)
      val text = original.extras.getCharSequence(Notification.EXTRA_TEXT)
      // a copy: the builder writes into the notification it recovers, and the original is
      // given back as it was (emulator 2026.11.26: it came back ongoing on the ringing channel)
      val builder = Notification.Builder.recoverBuilder(this, original.clone())
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) builder.setChannelId(CHANNEL)
      store.body()?.let { note ->
        builder.setStyle(
          Notification.BigTextStyle().bigText(if (text != null) "$text\n$note" else note),
        )
      }
      val public = newBuilder()
        .setSmallIcon(applicationInfo.icon)
        .setContentTitle(title ?: store.title())
        .setContentText(store.title())
        .setCategory(Notification.CATEGORY_ALARM)
        .addAction(stopAction(store))
        .build()
      builder
        .setCategory(Notification.CATEGORY_ALARM)
        .setOngoing(true)
        .setAutoCancel(false)
        .setOnlyAlertOnce(true)
        .setVisibility(Notification.VISIBILITY_PRIVATE)
        .setPublicVersion(public)
        .setDeleteIntent(stopIntent(giveBack = true))
        // on top until answered while the phone is in use; the alarm screen when locked
        .setFullScreenIntent(screenIntent(), true)
        .addAction(stopAction(store))
        .build()
    } catch (_: Exception) {
      null
    }
  }

  /** Before the reminder is found (it may come a moment later) or when it cannot be: no name. */
  private fun buildNotification(): Notification {
    val store = DoseAlarmStore(this)
    ensureChannel(store)
    return newBuilder()
      .setSmallIcon(applicationInfo.icon)
      .setContentTitle(store.title())
      // "only the sound": stopping it never records the dose
      .also { b ->
        store.body()?.let { b.setContentText(it).setStyle(Notification.BigTextStyle().bigText(it)) }
      }
      .setCategory(Notification.CATEGORY_ALARM)
      .setOngoing(true)
      .setVisibility(Notification.VISIBILITY_PUBLIC)
      .setContentIntent(DoseAlarmScheduler.openApp(this))
      .setDeleteIntent(stopIntent(giveBack = true))
      .setFullScreenIntent(screenIntent(), true)
      .addAction(stopAction(store))
      .build()
  }

  /** What rings, for the alarm screen: null when nothing does. Never stored (rule 3). */
  data class Ringing(
    val title: CharSequence?,
    val text: CharSequence?,
    val actions: List<Notification.Action>,
  )

  companion object {
    @Volatile
    var ringing: Ringing? = null
      private set

    /** "Дуу хаах" on the alarm screen: as the notification's button - the reminder stays. */
    fun stopFromScreen(context: Context) {
      ringing = null
      DoseAlarmActivity.close()
      try {
        context.startService(
          Intent(context, DoseAlarmService::class.java)
            .setAction(ACTION_STOP)
            .putExtra(EXTRA_GIVE_BACK, true),
        )
      } catch (_: Exception) {
        // not running: nothing rings
      }
    }

    const val ACTION_START = "expo.modules.dosealarm.START"
    const val ACTION_STOP = "expo.modules.dosealarm.STOP"
    const val EXTRA_ID = "expo.modules.dosealarm.ID"
    private const val EXTRA_GIVE_BACK = "expo.modules.dosealarm.GIVE_BACK"

    // v3: private on the lock screen - it now carries the reminder's own text (a channel's
    // settings are fixed once made); v2 was public with a name-free text only
    internal const val CHANNEL = "dose-alarm-ringing-v3"
    private const val OLD_CHANNEL = "dose-alarm-ringing-v2"
    private const val NOTIFICATION_ID = 7301
    const val RING_MS = 60_000L
    private const val WAKE_MS = 10_000L
    private val PATTERN = longArrayOf(0, 700, 300, 700, 300, 700, 1200)

    /** From the app (opened, answered, signed out): the reminder is not given back. */
    fun stop(context: Context) {
      // the loud fallback goes too: the reminder has been answered
      DoseAlarmFallback.cancel(context)
      // at once: a screen opening meanwhile finds nothing to show (security review M3)
      ringing = null
      DoseAlarmActivity.close()
      // at once, not after the service's turn on the main thread (a sign-out clears the tray)
      runCatching { context.getSystemService(NotificationManager::class.java)?.cancel(NOTIFICATION_ID) }
      try {
        context.startService(Intent(context, DoseAlarmService::class.java).setAction(ACTION_STOP))
      } catch (_: Exception) {
        // not running (or not allowed to start): nothing rings
      }
    }
  }
}
