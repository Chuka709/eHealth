package expo.modules.dosealarm

import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import expo.modules.kotlin.records.Field
import expo.modules.kotlin.records.Record

class AlarmSpec : Record {
  @Field var id: String = ""

  @Field var at: Double = 0.0
}

/**
 * JS side: `mobile/modules/dose-alarm/index.ts`. The app plans the reminders; this only makes
 * the OS's alarm clocks equal to that plan (`sync`) and stops a ringing one.
 */
class DoseAlarmModule : Module() {
  private val context
    get() = appContext.reactContext ?: throw Exceptions.ReactContextLost()

  override fun definition() = ModuleDefinition {
    Name("DoseAlarm")

    Function("canSchedule") { DoseAlarmScheduler.canSchedule(context) }

    Function("sync") { alarms: List<AlarmSpec>, title: String, body: String, stopLabel: String, fallback: String, show: String ->
      DoseAlarmStore(context).saveTexts(title, body, stopLabel, fallback, show)
      DoseAlarmScheduler.sync(context, alarms.associate { it.id to it.at.toLong() })
    }

    Function("add") { id: String, at: Double -> DoseAlarmScheduler.add(context, id, at.toLong()) }

    Function("cancel") { id: String -> DoseAlarmScheduler.cancel(context, id) }

    Function("cancelAll") {
      DoseReminders.signedOut()
      DoseAlarmScheduler.cancelAll(context)
      DoseAlarmService.stop(context)
    }

    Function("stop") { DoseAlarmService.stop(context) }

    // the app opened (from the reminder, its "Уусан", or by hand): it has been heard - stopped
    // here at once, not when the JS side has loaded (12 s on the real phone)
    OnActivityEntersForeground { DoseAlarmService.stop(context) }
  }
}
