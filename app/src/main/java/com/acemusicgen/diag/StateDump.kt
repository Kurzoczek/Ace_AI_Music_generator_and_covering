package com.acemusicgen.diag

import android.app.ApplicationExitInfo
import android.content.Context
import android.os.Build
import android.os.Debug
import com.acemusicgen.AceApp
import com.acemusicgen.BuildConfig
import com.acemusicgen.data.AppSettings
import com.acemusicgen.data.DumpType
import com.acemusicgen.engine.GenerationService
import com.acemusicgen.engine.JobRepository
import com.acemusicgen.engine.ResourceGovernor
import com.chaquo.python.Python
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/**
 * State dumps ("memory dumps" in Windows terms): one ZIP file ACE_dump_<date>_<time>_<trigger>.zip in the
 * "state dumps" folder, with the newest DumpType-dependent set of files:
 *
 *   summary.txt          trigger, reason, app/phone info, job state, running tasks, settings, state snapshot
 *   log_tail.txt         last 3000 lines of the diagnostic log + the Log tab
 *   java_threads.txt     stack of every Java/Kotlin thread
 *   python_threads.txt   stack of every Python thread                     (EXTENDED, FULL)
 *   proc.txt             /proc memory maps of the app and the engine, meminfo, pressure, sensors, CPU (EXTENDED, FULL)
 *   exits.txt + traces/  why earlier processes ended + system crash/ANR traces (EXTENDED, FULL)
 *   work_files.txt       work folder listing (decoded inputs, checkpoints)  (EXTENDED, FULL)
 *   heap.hprof           Java heap dump, opens in Android Studio / Eclipse MAT (FULL)
 */
object StateDump {
    const val PREFIX = "ACE_dump_"
    private val nameTime = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US)
    private val worker = Executors.newSingleThreadExecutor { r -> Thread(r, "ace-dump").apply { isDaemon = true } }

    /** Level actually used for a trigger ("automatic" picks per trigger, like Windows). */
    fun levelFor(type: DumpType, trigger: String): DumpType = when (type) {
        DumpType.AUTOMATIC -> if (trigger in setOf("crash", "unexpected_end", "manual")) DumpType.EXTENDED else DumpType.SMALL
        else -> type
    }

    fun requestAsync(ctx: Context, trigger: String, reason: String, forceLevel: DumpType? = null, onDone: (String) -> Unit = {}) {
        worker.execute {
            onDone(runCatching { write(ctx, trigger, reason, emptyList(), forceLevel = forceLevel) }.getOrElse { "error: ${it.message}" })
        }
    }

    /** Creates the dump and copies it to the folder. Returns where it went. Blocking - call off the main thread. */
    fun write(ctx: Context, trigger: String, reason: String, exits: List<ApplicationExitInfo>, crash: Throwable? = null,
              forceLevel: DumpType? = null): String {
        val s: AppSettings = (ctx.applicationContext as AceApp).settings.state.value
        val level = forceLevel ?: levelFor(s.dumpType, trigger)
        if (level == DumpType.NONE) return "off"
        val extended = level == DumpType.EXTENDED || level == DumpType.FULL
        val dir = File(ctx.filesDir, "diag/dumps").apply { mkdirs() }
        val name = "$PREFIX${nameTime.format(Date())}_$trigger.zip"
        val zipFile = File(dir, name)
        Diagnostics.appendNow("[DUMP] writing ${level.name} dump \"$name\" (trigger: $trigger, $reason)")
        val known = ResourceGovernor.activePids()

        ZipOutputStream(zipFile.outputStream().buffered()).use { zip ->
            fun text(entry: String, body: String) {
                zip.putNextEntry(ZipEntry(entry)); zip.write(body.toByteArray()); zip.closeEntry()
            }
            text("summary.txt", summary(ctx, s, level, trigger, reason, crash, known))
            text("log_tail.txt", "===== diagnostic log (last 3000 lines) =====\n" + Diagnostics.tail(ctx, 3000) +
                "\n\n===== Log tab =====\n" + JobRepository.state.value.log.joinToString("\n"))
            text("java_threads.txt", javaThreads())
            if (extended) {
                text("python_threads.txt", pythonThreads())
                text("proc.txt", SystemProbe.procDetails(ctx, known))
                val allExits = (exits + SystemProbe.exitInfos(ctx)).distinctBy { it.timestamp to it.pid }.sortedByDescending { it.timestamp }
                text("exits.txt", if (allExits.isEmpty()) "No exit history (Android 11+ only).\n"
                    else allExits.joinToString("\n") { SystemProbe.describeExit(it) } + "\n")
                if (Build.VERSION.SDK_INT >= 30) allExits.forEach { e ->
                    runCatching {
                        e.traceInputStream?.use { input ->
                            val ext = if (e.reason == ApplicationExitInfo.REASON_CRASH_NATIVE) "tombstone.pb" else "txt"
                            zip.putNextEntry(ZipEntry("traces/${nameTime.format(Date(e.timestamp))}_${SystemProbe.exitReasonName(e.reason)}.$ext"))
                            input.copyTo(zip); zip.closeEntry()
                        }
                    }
                }
                text("work_files.txt", workListing(ctx))
            }
            if (level == DumpType.FULL) {
                val hprof = File(dir, "heap_tmp.hprof")
                runCatching {
                    Debug.dumpHprofData(hprof.path)
                    zip.putNextEntry(ZipEntry("heap.hprof")); hprof.inputStream().use { it.copyTo(zip) }; zip.closeEntry()
                }.onFailure { text("heap.hprof.error.txt", "Heap dump failed: ${it.message}") }
                hprof.delete()
            }
        }

        // keep at most 3 dumps inside the app; the folder keeps dumpKeep of them
        dir.listFiles()?.filter { it.name.startsWith(PREFIX) }?.sortedByDescending { it.name }?.drop(3)?.forEach { it.delete() }
        val where = runCatching {
            val w = DiagExport.put(ctx, s.outputFolders, DiagFolder.DUMPS, zipFile)
            DiagExport.prune(ctx, s.outputFolders, DiagFolder.DUMPS, PREFIX, s.dumpKeep)
            w
        }.getOrElse { "app storage only (${zipFile.path}) - copying to the folder failed: ${it.message}" }
        Diagnostics.appendNow("[DUMP] ${level.name} dump saved: $where (${zipFile.length() / 1024} kB)")
        return where
    }

    private fun summary(ctx: Context, s: AppSettings, level: DumpType, trigger: String, reason: String, crash: Throwable?,
                        known: Map<Int, String>): String = buildString {
        val st = JobRepository.state.value
        appendLine("AI Music Generator and Cover Maker - state dump")
        appendLine("time:     ${SystemProbe.fmtTime(System.currentTimeMillis())}")
        appendLine("type:     ${level.name} (setting: ${s.dumpType.name})")
        appendLine("trigger:  $trigger")
        appendLine("reason:   $reason")
        appendLine("app:      ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE}), pid ${android.os.Process.myPid()}")
        appendLine("phone:    ${Build.MANUFACTURER} ${Build.MODEL} (${Build.DEVICE}), Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT}), " +
            "security patch ${Build.VERSION.SECURITY_PATCH}, ABI ${Build.SUPPORTED_ABIS.joinToString()}")
        appendLine()
        appendLine("job:      ${st.phase}, progress ${if (st.progress >= 0) "${(st.progress * 100).toInt()}%" else "?"}, " +
            "paused by user=${st.userPaused}, paused by heat=${st.thermalPaused}")
        appendLine("status:   ${st.status}")
        st.memoryNote?.let { appendLine("memory:   $it") }
        st.error?.let { appendLine("error:    $it") }
        appendLine(Diagnostics.runningTasks())
        appendLine()
        appendLine("===== state =====")
        appendLine(SystemProbe.snapshot(ctx, known))
        if (crash != null) {
            appendLine(); appendLine("===== crash =====")
            appendLine(crash.stackTraceToString())
        }
        appendLine(); appendLine("===== settings =====")
        appendLine(s.copy(prompt = s.prompt.take(300), lyrics = s.lyrics.take(300)).toJson().toString(2))
    }

    private fun javaThreads(): String = buildString {
        Thread.getAllStackTraces().entries.sortedBy { it.key.name }.forEach { (t, stack) ->
            appendLine("\"${t.name}\" id=${t.id} state=${t.state} priority=${t.priority}${if (t.isDaemon) " daemon" else ""}")
            stack.forEach { appendLine("    at $it") }
            appendLine()
        }
    }

    /** Stacks of all Python threads; needs the Python lock, so it is given 5 s and skipped if Python is busy. */
    private fun pythonThreads(): String {
        if (!Python.isStarted()) return "Python is not running in this process.\n"
        val ex = Executors.newSingleThreadExecutor()
        return try {
            ex.submit<String> { Python.getInstance().getModule("ace_android").callAttr("dump_threads").toString() }
                .get(5, TimeUnit.SECONDS)
        } catch (e: Exception) {
            "Could not read the Python threads (${e.javaClass.simpleName}: ${e.message}) - Python was busy or stuck.\n"
        } finally {
            ex.shutdownNow()
        }
    }

    private fun workListing(ctx: Context): String = buildString {
        val work = GenerationService.workDir(ctx)
        appendLine("work folder: ${work.path}")
        work.walkTopDown().maxDepth(4).filter { it.isFile }.sortedBy { it.path }.take(2000).forEach { f ->
            appendLine("%10d kB  %s  %s".format(f.length() / 1024, SystemProbe.fmtTime(f.lastModified()), f.path.removePrefix(work.path)))
        }
    }
}
