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
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager

/**
 * Rings on the alarm stream (sounds in silent mode, like an alarm clock - Q79) with vibration
 * for at most RING_MS, then stops by itself (H40: a reminder that never stops would get the
 * reminders turned off). Stopped earlier by its notification's stop button, or by the app
 * (a dose recorded, the app opened). The notification names no medicine (H10). When it cannot
 * start or play, a loud fallback notification comes instead (DoseAlarmFallback).
 */
class DoseAlarmService : Service() {
  private var player: MediaPlayer? = null
  private var vibrator: Vibrator? = null
  private val handler = Handler(Looper.getMainLooper())
  private val timeout = Runnable { stopRinging() }

  override fun onBind(intent: Intent?): IBinder? = null

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    if (intent?.action == ACTION_STOP) {
      stopRinging()
      return START_NOT_STICKY
    }
    val notification = buildNotification()
    try {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
      } else {
        startForeground(NOTIFICATION_ID, notification)
      }
    } catch (_: Exception) {
      DoseAlarmFallback.post(this) // never a silent reminder (medical review H-1)
      stopSelf()
      return START_NOT_STICKY
    }
    startRinging()
    handler.removeCallbacks(timeout)
    handler.postDelayed(timeout, RING_MS)
    return START_NOT_STICKY
  }

  private fun startRinging() {
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
        DoseAlarmFallback.post(this) // no sound possible here: the notification sound instead
        null
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
  }

  private fun stopRinging() {
    handler.removeCallbacks(timeout)
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

  private fun buildNotification(): Notification {
    val store = DoseAlarmStore(this)
    val manager = getSystemService(NotificationManager::class.java)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && manager != null) {
      // shown on top (heads-up) but quiet: the service plays the sound itself
      val channel = NotificationChannel(CHANNEL, store.title(), NotificationManager.IMPORTANCE_HIGH)
      channel.setSound(null, null)
      channel.enableVibration(false)
      channel.lockscreenVisibility = Notification.VISIBILITY_PUBLIC
      manager.createNotificationChannel(channel)
    }
    val stop = PendingIntent.getService(
      this,
      1,
      Intent(this, DoseAlarmService::class.java).setAction(ACTION_STOP),
      PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )
    val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      Notification.Builder(this, CHANNEL)
    } else {
      @Suppress("DEPRECATION")
      Notification.Builder(this)
    }
    return builder
      .setSmallIcon(applicationInfo.icon)
      .setContentTitle(store.title())
      // "only the sound": stopping it never records the dose
      .also { b -> store.body()?.let { b.setContentText(it).setStyle(Notification.BigTextStyle().bigText(it)) } }
      .setCategory(Notification.CATEGORY_ALARM)
      .setOngoing(true)
      .setVisibility(Notification.VISIBILITY_PUBLIC)
      .setContentIntent(DoseAlarmScheduler.openApp(this))
      .setDeleteIntent(stop)
      .addAction(Notification.Action.Builder(null, store.stopLabel(), stop).build())
      .build()
  }

  companion object {
    const val ACTION_START = "expo.modules.dosealarm.START"
    const val ACTION_STOP = "expo.modules.dosealarm.STOP"
    // v2: high importance for a heads-up (a channel's importance is fixed once made)
    private const val CHANNEL = "dose-alarm-ringing-v2"
    private const val NOTIFICATION_ID = 7301
    const val RING_MS = 60_000L
    private val PATTERN = longArrayOf(0, 700, 300, 700, 300, 700, 1200)

    fun stop(context: Context) {
      // the loud fallback goes too: the reminder has been answered
      DoseAlarmFallback.cancel(context)
      try {
        context.startService(Intent(context, DoseAlarmService::class.java).setAction(ACTION_STOP))
      } catch (_: Exception) {
        // not running (or not allowed to start): nothing rings
      }
    }
  }
}
