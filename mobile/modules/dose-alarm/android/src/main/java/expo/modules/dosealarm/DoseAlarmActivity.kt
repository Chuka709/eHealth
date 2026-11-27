package expo.modules.dosealarm

import android.app.Activity
import android.app.ActivityOptions
import android.app.KeyguardManager
import android.app.Notification
import android.app.NotificationManager
import android.app.admin.DevicePolicyManager
import android.app.PendingIntent
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.lang.ref.WeakReference

/**
 * The alarm screen (the user's choice 2026.11.27: a heads-up hid itself after 4-5 s): opened by
 * the ringing notification's full-screen intent while the phone is locked or asleep - on an
 * unlocked phone in use Android keeps the notification on top instead. Shows what rings: the
 * reminder's time, its medicines, and its own buttons ("Уусан", "10 мин дараа" - the app's
 * actions, unchanged) and "Дуу хаах". Its own task (not the app's): opening it neither brings the
 * app forward nor stops the sound. Closed when the ringing stops.
 *
 * Lock screen (H10): the medicine list only where the phone shows sensitive notification content
 * on the lock screen; else "Эмийг харах", which asks to unlock first. The app's actions ask to
 * unlock too (they open the app).
 */
class DoseAlarmActivity : Activity() {
  private var unlocked = false

  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
      setShowWhenLocked(true)
      setTurnScreenOn(true)
    } else {
      @Suppress("DEPRECATION")
      window.addFlags(
        WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
          WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON,
      )
    }
    window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    // its own task and window: the app's screenshot guard does not reach it (security review L1)
    window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) setRecentsScreenshotEnabled(false)
    current = WeakReference(this)
  }

  // drawn on every return: locked again (screen off) hides the names again (security review M1)
  override fun onResume() {
    super.onResume()
    render()
  }

  override fun onStop() {
    unlocked = false
    super.onStop()
  }

  override fun onDestroy() {
    if (current?.get() === this) current = null
    super.onDestroy()
  }

  /** What rings now, drawn again when the service takes the reminder over a moment later. */
  fun render() {
    val ringing = DoseAlarmService.ringing
    if (ringing == null) {
      finishAndRemoveTask()
      return
    }
    val store = DoseAlarmStore(this)
    val showNames = unlocked || namesAllowedHere()
    val column = LinearLayout(this).apply {
      orientation = LinearLayout.VERTICAL
      gravity = Gravity.CENTER_HORIZONTAL
      val pad = dp(24)
      setPadding(pad, dp(48), pad, pad)
    }
    column.addView(text(ringing.title ?: store.title(), 30f, bold = true))
    if (ringing.text != null && showNames) {
      column.addView(text(ringing.text, 24f, bold = false))
    } else if (ringing.text != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      // before Android 8 there is no asking to unlock from here: the names stay hidden
      column.addView(button(store.showLabel()) { unlockThen { unlocked = true; render() } })
    }
    for (action in ringing.actions) {
      val intent = action.actionIntent ?: continue
      column.addView(button(action.title?.toString() ?: continue) { unlockThen { send(intent) } })
    }
    column.addView(button(store.stopLabel()) { DoseAlarmService.stopFromScreen(this) })
    store.body()?.let { column.addView(text(it, 18f, bold = false)) }
    setContentView(ScrollView(this).apply { addView(column) })
  }

  private fun send(intent: PendingIntent) {
    runCatching {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
        val options = ActivityOptions.makeBasic()
          .setPendingIntentBackgroundActivityStartMode(
            ActivityOptions.MODE_BACKGROUND_ACTIVITY_START_ALLOWED,
          )
        intent.send(this, 0, null, null, null, null, options.toBundle())
      } else {
        intent.send()
      }
    }
    finishAndRemoveTask()
  }

  /** The phone's own choice: sensitive notification content on the lock screen or not. */
  private fun namesAllowedHere(): Boolean {
    val keyguard = getSystemService(KeyguardManager::class.java) ?: return false
    if (!keyguard.isKeyguardLocked) return true
    // every layer must allow it, as for the notification itself; anything unreadable or off:
    // hidden - the safe side (security review L3, automated review 2026.11.27)
    return try {
      val policy = getSystemService(DevicePolicyManager::class.java)
      val redacted = policy != null &&
        policy.getKeyguardDisabledFeatures(null) and
        DevicePolicyManager.KEYGUARD_DISABLE_UNREDACTED_NOTIFICATIONS != 0
      val channelHides = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
        getSystemService(NotificationManager::class.java)
          ?.getNotificationChannel(DoseAlarmService.CHANNEL)
          ?.lockscreenVisibility == Notification.VISIBILITY_SECRET
      !redacted && !channelHides &&
        Settings.Secure.getInt(contentResolver, SHOW_ON_LOCK_SCREEN, 0) != 0 &&
        Settings.Secure.getInt(contentResolver, PRIVATE_ON_LOCK_SCREEN, 0) != 0
    } catch (_: Exception) {
      false
    }
  }

  private fun unlockThen(then: () -> Unit) {
    val keyguard = getSystemService(KeyguardManager::class.java)
    // before Android 8: the app's own screen asks to unlock when it opens
    if (keyguard == null || !keyguard.isKeyguardLocked || Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
      then()
      return
    }
    keyguard.requestDismissKeyguard(
      this,
      object : KeyguardManager.KeyguardDismissCallback() {
        override fun onDismissSucceeded() {
          then()
        }
      },
    )
  }

  private fun text(value: CharSequence, sp: Float, bold: Boolean): TextView = TextView(this).apply {
    text = value
    setTextSize(TypedValue.COMPLEX_UNIT_SP, sp)
    gravity = Gravity.CENTER
    if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
    setPadding(0, dp(8), 0, dp(16))
  }

  private fun button(label: String, onClick: () -> Unit): Button = Button(this).apply {
    text = label
    isAllCaps = false
    setTextSize(TypedValue.COMPLEX_UNIT_SP, 22f)
    minHeight = dp(64)
    layoutParams = LinearLayout.LayoutParams(
      LinearLayout.LayoutParams.MATCH_PARENT,
      LinearLayout.LayoutParams.WRAP_CONTENT,
    ).apply { topMargin = dp(12) }
    setOnClickListener(View.OnClickListener { onClick() })
  }

  private fun dp(value: Int): Int =
    TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value.toFloat(), resources.displayMetrics)
      .toInt()

  companion object {
    private const val PRIVATE_ON_LOCK_SCREEN = "lock_screen_allow_private_notifications"
    private const val SHOW_ON_LOCK_SCREEN = "lock_screen_show_notifications"

    @Volatile
    private var current: WeakReference<DoseAlarmActivity>? = null

    /** The ringing stopped: the screen goes with it. */
    fun close() {
      current?.get()?.let { it.runOnUiThread { it.finishAndRemoveTask() } }
      current = null
    }

    /** The service took the reminder over: its medicines and buttons come in. */
    fun refresh() {
      current?.get()?.let { it.runOnUiThread { it.render() } }
    }
  }
}
