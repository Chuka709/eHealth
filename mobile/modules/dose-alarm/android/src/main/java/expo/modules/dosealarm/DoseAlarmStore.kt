package expo.modules.dosealarm

import android.content.Context
import org.json.JSONObject

/**
 * What is set on the OS, kept to restore it after a reboot and to cancel what is no longer
 * planned. Only reminder ids ("dose.<instant>.<hash>") and instants - never a medicine name or
 * a profile (CLAUDE.md rule 3). The texts are the app's own words (ringing notification title,
 * its explanation and stop button, the fallback reminder title), sent in the user's language on
 * every sync; the built-in ones below only cover the moments before the first sync.
 */
internal class DoseAlarmStore(context: Context) {
  private val prefs = context.getSharedPreferences("labtrack_dose_alarm", Context.MODE_PRIVATE)

  fun alarms(): Map<String, Long> {
    val raw = prefs.getString(KEY_ALARMS, null) ?: return emptyMap()
    return try {
      val json = JSONObject(raw)
      json.keys().asSequence().associateWith { json.getLong(it) }
    } catch (_: Exception) {
      emptyMap()
    }
  }

  fun saveAlarms(alarms: Map<String, Long>) {
    val json = JSONObject()
    for ((id, at) in alarms) json.put(id, at)
    // at once: an id lost to a process killed right after setting would leave an alarm no
    // sign-out can find (security review L3)
    prefs.edit().putString(KEY_ALARMS, json.toString()).commit()
  }

  fun remove(id: String) {
    val left = alarms() - id
    saveAlarms(left)
  }

  fun saveTexts(title: String, body: String, stop: String, fallback: String) {
    prefs.edit()
      .putString(KEY_TITLE, title)
      .putString(KEY_BODY, body)
      .putString(KEY_STOP, stop)
      .putString(KEY_FALLBACK, fallback)
      .apply()
  }

  fun title(): String = prefs.getString(KEY_TITLE, null) ?: "Эмийн сануулга дуугарч байна"

  fun body(): String? = prefs.getString(KEY_BODY, null)

  fun stopLabel(): String = prefs.getString(KEY_STOP, null) ?: "Дуу хаах"

  fun fallbackTitle(): String = prefs.getString(KEY_FALLBACK, null) ?: "Эм уух цаг боллоо"

  fun clear() {
    prefs.edit().clear().apply()
  }

  private companion object {
    const val KEY_ALARMS = "alarms.v1"
    const val KEY_TITLE = "text.title"
    const val KEY_STOP = "text.stop"
    const val KEY_BODY = "text.body"
    const val KEY_FALLBACK = "text.fallback"
  }
}
