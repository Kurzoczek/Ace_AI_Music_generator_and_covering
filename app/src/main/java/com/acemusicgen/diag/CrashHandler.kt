package com.acemusicgen.diag

import android.app.Application
import com.acemusicgen.AceApp
import com.acemusicgen.data.DumpType

/** Writes an app crash to the diagnostic log (and a state dump, if enabled) before Android ends the process. */
object CrashHandler {
    fun install(app: Application) {
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, e ->
            try {
                Diagnostics.appendNow("[CRASH] uncaught ${e.javaClass.name} in thread \"${thread.name}\": ${e.message}\n" +
                    e.stackTraceToString().lines().take(60).joinToString("\n") { "    $it" })
                val s = (app as? AceApp)?.settings?.state?.value
                if (s != null && s.dumpType != DumpType.NONE && s.dumpOnUnexpectedEnd) {
                    StateDump.write(app, "crash", "uncaught ${e.javaClass.simpleName} in ${thread.name}: ${e.message}", emptyList(), crash = e)
                }
            } catch (_: Throwable) {
            } finally {
                previous?.uncaughtException(thread, e)
            }
        }
    }
}
