package com.acemusicgen.diag

import android.app.Application
import android.content.BroadcastReceiver
import android.content.ComponentCallbacks2
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.res.Configuration
import android.os.Build
import android.os.PowerManager
import com.acemusicgen.AceApp
import com.acemusicgen.BuildConfig
import com.acemusicgen.data.AppSettings
import com.acemusicgen.data.SessionStore
import com.acemusicgen.engine.JobRepository
import com.acemusicgen.engine.ResourceGovernor
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Diagnostic journal. Every line of the Log tab, task start/end times, errors, system events (screen, charger,
 * battery saver, doze, thermal status, memory warnings, service lifecycle), engine process starts/ends with their
 * exit signal, and a state snapshot every 10 minutes (temperatures, CPU, memory, power state) are appended with a
 * time stamp to a private file (filesDir/diag/logs, one file per day, kept 14 days).
 *
 * The private file is always written (it feeds the state dumps). When "Save logs" is on, it is also copied every
 * minute - and at once after errors - to the "app logs" folder (DiagExport). Each line is flushed to disk
 * immediately, so even a hard kill by Android loses nothing; the copy is completed at the next app start.
 */
object Diagnostics {
    const val SNAPSHOT_MINUTES = 10L
    private const val KEEP_DAYS = 14
    private const val MAX_TOTAL_BYTES = 40L * 1024 * 1024

    @Volatile private var app: Application? = null
    private val exec = Executors.newSingleThreadScheduledExecutor { r -> Thread(r, "ace-diag").apply { isDaemon = true } }
    private val stamp = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)
    private val day = SimpleDateFormat("yyyy-MM-dd", Locale.US)
    private val tasks = ConcurrentHashMap<String, Long>()
    @Volatile private var dirty = false
    @Volatile private var syncedDay: String? = null
    private var lastPauseDump = 0L

    private fun settings(): AppSettings? = (app as? AceApp)?.settings?.state?.value

    fun logDir(ctx: Context) = File(ctx.filesDir, "diag/logs").apply { mkdirs() }
    fun currentLogFile(ctx: Context) = File(logDir(ctx), "ace_log_${day.format(Date())}.txt")

    // ------------------------------------------------------------------ setup

    fun init(a: Application) {
        if (app != null) return
        app = a
        CrashHandler.install(a)
        registerSystemEvents(a)
        exec.execute { safe { startupReport(a) } }
        exec.scheduleWithFixedDelay({ safe { snapshotNow("every $SNAPSHOT_MINUTES min") } }, SNAPSHOT_MINUTES, SNAPSHOT_MINUTES, TimeUnit.MINUTES)
        exec.scheduleWithFixedDelay({ safe { sync(force = false) } }, 60, 60, TimeUnit.SECONDS)
    }

    private inline fun safe(block: () -> Unit) { try { block() } catch (_: Throwable) { } }

    // ------------------------------------------------------------------ writing

    /** Every line shown in the Log tab. */
    fun log(line: String) = event("LOG", line)

    fun event(tag: String, text: String) {
        val a = app ?: return
        val line = "${stamp.format(Date())} [$tag] $text"
        exec.execute { safe { append(a, line) } }
    }

    /** Errors are written and copied to the logs folder at once. */
    fun error(where: String, t: Throwable?, text: String = "") {
        event("ERROR", "$where: ${text.ifEmpty { t?.let { "${it.javaClass.simpleName}: ${it.message}" } ?: "" }}" +
            (t?.let { "\n" + it.stackTraceToString().lines().take(25).joinToString("\n") { l -> "    $l" } } ?: ""))
        exec.execute { safe { sync(force = true) } }
    }

    private fun append(ctx: Context, line: String) {
        FileOutputStream(currentLogFile(ctx), true).use { it.write((line + "\n").toByteArray()); it.fd.sync() }
        dirty = true
    }

    /** Writes synchronously - used by the crash handler, where there is no time for the background thread. */
    fun appendNow(line: String) {
        val a = app ?: return
        safe { FileOutputStream(currentLogFile(a), true).use { it.write("${stamp.format(Date())} $line\n".toByteArray()); it.fd.sync() } }
    }

    // ------------------------------------------------------------------ task timing

    fun taskStart(name: String, detail: String = "") {
        tasks[name] = System.currentTimeMillis()
        event("TASK", "START $name${if (detail.isNotEmpty()) " - $detail" else ""}")
    }

    fun taskEnd(name: String, outcome: String = "ok") {
        val t0 = tasks.remove(name)
        event("TASK", "END $name ($outcome)${t0?.let { " after ${duration(System.currentTimeMillis() - it)}" } ?: ""}")
    }

    fun runningTasks(): String {
        val now = System.currentTimeMillis()
        return if (tasks.isEmpty()) "tasks: none running"
        else "tasks: " + tasks.entries.sortedBy { it.value }.joinToString("; ") {
            "${it.key} since ${SystemProbe.fmtTime(it.value)} (${duration(now - it.value)})"
        }
    }

    fun duration(ms: Long): String {
        val s = ms / 1000
        return if (s >= 3600) "%dh %02dm %02ds".format(s / 3600, s / 60 % 60, s % 60)
        else if (s >= 60) "%dm %02ds".format(s / 60, s % 60) else "%.1f s".format(Locale.US, ms / 1000.0)
    }

    // ------------------------------------------------------------------ snapshots

    /** Writes a state snapshot (on the diagnostics thread - safe to call from anywhere). */
    fun snapshot(reason: String) = exec.execute { safe { snapshotNow(reason) } }

    private fun snapshotNow(reason: String) {
        val a = app ?: return
        val st = JobRepository.state.value
        val job = "job: ${st.phase}${if (st.progress >= 0) " ${(st.progress * 100).toInt()}%" else ""}" +
            "${if (st.userPaused) " PAUSED by user" else ""}${if (st.thermalPaused) " PAUSED (heat)" else ""} - ${st.status.take(160)}"
        event("SNAPSHOT", "($reason)\n  $job\n  ${runningTasks()}\n" + SystemProbe.snapshot(a, ResourceGovernor.activePids()))
    }

    // ------------------------------------------------------------------ system events

    private fun registerSystemEvents(a: Application) {
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(c: Context, i: Intent) {
                val pm = c.getSystemService(PowerManager::class.java)
                val text = when (i.action) {
                    Intent.ACTION_SCREEN_ON -> "screen on"
                    Intent.ACTION_SCREEN_OFF -> "screen off"
                    Intent.ACTION_USER_PRESENT -> "phone unlocked"
                    Intent.ACTION_POWER_CONNECTED -> "charger connected"
                    Intent.ACTION_POWER_DISCONNECTED -> "charger disconnected"
                    Intent.ACTION_BATTERY_LOW -> "battery low"
                    Intent.ACTION_BATTERY_OKAY -> "battery okay"
                    PowerManager.ACTION_DEVICE_IDLE_MODE_CHANGED -> "doze (deep idle) ${if (pm?.isDeviceIdleMode == true) "STARTED" else "ended"}"
                    PowerManager.ACTION_POWER_SAVE_MODE_CHANGED -> "battery saver ${if (pm?.isPowerSaveMode == true) "ON" else "off"}"
                    else -> i.action ?: "?"
                }
                event("SYSTEM", text)
                if (i.action == PowerManager.ACTION_DEVICE_IDLE_MODE_CHANGED || i.action == PowerManager.ACTION_POWER_SAVE_MODE_CHANGED) {
                    snapshot(text)
                }
            }
        }
        val filter = IntentFilter().apply {
            listOf(Intent.ACTION_SCREEN_ON, Intent.ACTION_SCREEN_OFF, Intent.ACTION_USER_PRESENT, Intent.ACTION_POWER_CONNECTED,
                Intent.ACTION_POWER_DISCONNECTED, Intent.ACTION_BATTERY_LOW, Intent.ACTION_BATTERY_OKAY,
                PowerManager.ACTION_DEVICE_IDLE_MODE_CHANGED, PowerManager.ACTION_POWER_SAVE_MODE_CHANGED).forEach(::addAction)
        }
        if (Build.VERSION.SDK_INT >= 33) a.registerReceiver(receiver, filter, Context.RECEIVER_NOT_EXPORTED)
        else a.registerReceiver(receiver, filter)

        a.getSystemService(PowerManager::class.java)?.addThermalStatusListener(a.mainExecutor) { s ->
            event("THERMAL", "system thermal status changed to ${SystemProbe.thermalStatusName(s)}")
            snapshot("thermal status ${SystemProbe.thermalStatusName(s)}")
        }

        a.registerComponentCallbacks(object : ComponentCallbacks2 {
            override fun onTrimMemory(level: Int) {
                event("MEMORY", "Android asks the app to free memory: ${SystemProbe.trimLevelName(level)}")
                // 15 = RUNNING_CRITICAL, 80 = COMPLETE (named constants are deprecated in API 35 but still delivered)
                if (level == 15 || level >= 80) {
                    snapshot("memory warning ${SystemProbe.trimLevelName(level)}")
                    pauseEvent("critical memory warning ${SystemProbe.trimLevelName(level)}")
                }
            }
            override fun onLowMemory() = event("MEMORY", "Android reports very low memory (onLowMemory)")
            override fun onConfigurationChanged(newConfig: Configuration) {}
        })
    }

    /** Called when the work is paused by heat / memory, or Android sends a critical memory warning. */
    fun pauseEvent(reason: String) {
        val s = settings() ?: return
        val now = System.currentTimeMillis()
        if (s.dumpType == com.acemusicgen.data.DumpType.NONE || !s.dumpOnPause || now - lastPauseDump < 15 * 60_000) return
        lastPauseDump = now
        StateDump.requestAsync(app!!, "pause", reason)
    }

    // ------------------------------------------------------------------ start of the app process

    private fun startupReport(a: Application) {
        val prefs = a.getSharedPreferences("diag", Context.MODE_PRIVATE)
        append(a, "${stamp.format(Date())} [START] ===== app process started: ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE}), " +
            "${Build.MANUFACTURER} ${Build.MODEL}, Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT}), pid ${android.os.Process.myPid()} =====")

        // why did the previous process end? (Android 11+)
        val lastSeen = prefs.getLong("lastExitTs", 0)
        val exits = SystemProbe.exitInfos(a).filter { it.timestamp > lastSeen }.sortedBy { it.timestamp }
        exits.forEach { e -> append(a, "${stamp.format(Date())} [EXIT] previous process ended: ${SystemProbe.describeExit(e)}") }
        exits.maxOfOrNull { it.timestamp }?.let { prefs.edit().putLong("lastExitTs", it).apply() }

        // engine processes left behind by a killed app process keep memory (and may be frozen by a pause)
        SystemProbe.engineProcesses(a).forEach { (pid, exe) ->
            append(a, "${stamp.format(Date())} [ORPHAN] engine process $pid ($exe, ${SystemProbe.procState(pid)}) " +
                "survived the previous app process - stopping it to free its memory")
            runCatching { android.os.Process.sendSignal(pid, 18) }   // SIGCONT, in case it was paused
            runCatching { android.os.Process.killProcess(pid) }
        }

        // a job was running when the process died
        val interrupted = SessionStore.interrupted(a)
        if (interrupted != null) {
            val why = exits.lastOrNull()?.let { SystemProbe.exitReasonName(it.reason) } ?: "unknown (Android 10 does not report it)"
            append(a, "${stamp.format(Date())} [INTERRUPTED] the job started ${SystemProbe.fmtTime(interrupted.startedAt)} did not finish; " +
                "last status \"${interrupted.lastStatus}\"; reason: $why")
            val s = settings()
            if (s != null && s.dumpType != com.acemusicgen.data.DumpType.NONE && s.dumpOnUnexpectedEnd) {
                StateDump.write(a, "unexpected_end", "job interrupted - previous process ended: $why", exits)
            }
        } else if (exits.any { it.reason == 4 || it.reason == 5 || it.reason == 6 }) {
            val s = settings()
            if (s != null && s.dumpType != com.acemusicgen.data.DumpType.NONE && s.dumpOnUnexpectedEnd) {
                StateDump.write(a, "crash", "previous process crashed: ${SystemProbe.exitReasonName(exits.last().reason)}", exits)
            }
        }
        snapshotNow("app start")
        prune(a)
        sync(force = true, all = true)
    }

    // ------------------------------------------------------------------ copy to the user's "app logs" folder

    fun syncNow() = exec.execute { safe { sync(force = true, all = true) } }

    private fun sync(force: Boolean, all: Boolean = false) {
        val a = app ?: return
        val s = settings() ?: return
        if (!s.diagLogs || (!dirty && !force)) return
        dirty = false
        val today = currentLogFile(a)
        val files = if (all) logDir(a).listFiles()?.filter { it.name.startsWith("ace_log_") }?.sortedBy { it.name }.orEmpty()
        else listOfNotNull(syncedDay?.takeIf { it != today.name }?.let { File(logDir(a), it) }?.takeIf { it.exists() }, today)
        files.forEach { f -> if (f.exists()) runCatching { DiagExport.put(a, s.outputFolders, DiagFolder.LOGS, f) } }
        syncedDay = today.name
    }

    private fun prune(ctx: Context) {
        val files = logDir(ctx).listFiles()?.sortedByDescending { it.name } ?: return
        val cutoff = System.currentTimeMillis() - KEEP_DAYS * 24L * 3600 * 1000
        var total = 0L
        files.forEach { f ->
            total += f.length()
            if (f.lastModified() < cutoff || total > MAX_TOTAL_BYTES) f.delete()
        }
    }

    /** Last [n] lines of the private log (for dumps). */
    fun tail(ctx: Context, n: Int): String {
        val files = logDir(ctx).listFiles()?.filter { it.name.startsWith("ace_log_") }?.sortedBy { it.name } ?: return ""
        val lines = ArrayDeque<String>()
        files.takeLast(2).forEach { f -> f.forEachLine { l -> lines.addLast(l); if (lines.size > n) lines.removeFirst() } }
        return lines.joinToString("\n")
    }
}
