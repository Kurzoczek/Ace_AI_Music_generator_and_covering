package com.acemusicgen.diag

import android.app.ActivityManager
import android.app.ApplicationExitInfo
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Reads the state of the phone and of the app's processes as plain text, for the 10-minute log snapshots and
 * for state dumps. Everything is best-effort: some files are hidden by Android (SELinux) on some phones, which
 * is then written as "not readable" instead of failing.
 */
object SystemProbe {
    private val time = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US)

    fun fmtTime(ms: Long): String = if (ms <= 0) "-" else time.format(Date(ms))

    fun thermalStatusName(s: Int) = when (s) {
        PowerManager.THERMAL_STATUS_NONE -> "NONE"
        PowerManager.THERMAL_STATUS_LIGHT -> "LIGHT"
        PowerManager.THERMAL_STATUS_MODERATE -> "MODERATE"
        PowerManager.THERMAL_STATUS_SEVERE -> "SEVERE"
        PowerManager.THERMAL_STATUS_CRITICAL -> "CRITICAL"
        PowerManager.THERMAL_STATUS_EMERGENCY -> "EMERGENCY"
        PowerManager.THERMAL_STATUS_SHUTDOWN -> "SHUTDOWN"
        else -> "?"
    } + "($s)"

    fun trimLevelName(level: Int) = when (level) {
        5 -> "RUNNING_MODERATE"; 10 -> "RUNNING_LOW"; 15 -> "RUNNING_CRITICAL"; 20 -> "UI_HIDDEN"
        40 -> "BACKGROUND"; 60 -> "MODERATE"; 80 -> "COMPLETE"; else -> "?"
    } + "($level)"

    private fun importanceName(i: Int) = when (i) {
        100 -> "FOREGROUND"; 125 -> "FOREGROUND_SERVICE"; 150 -> "TOP_SLEEPING"; 200 -> "VISIBLE"; 230 -> "PERCEPTIBLE"
        250 -> "CANT_SAVE_STATE"; 300 -> "SERVICE"; 325 -> "TOP_SLEEPING_PRE_28"; 350 -> "CANT_SAVE_STATE_PRE_26"
        400 -> "CACHED"; 1000 -> "GONE"; else -> "?"
    } + "($i)"

    private fun bucketName(b: Int) = when (b) {
        5 -> "EXEMPTED"; 10 -> "ACTIVE"; 20 -> "WORKING_SET"; 30 -> "FREQUENT"; 40 -> "RARE"; 45 -> "RESTRICTED"; 50 -> "NEVER"
        else -> "?"
    } + "($b)"

    fun exitReasonName(r: Int) = when (r) {
        0 -> "UNKNOWN"; 1 -> "EXIT_SELF"; 2 -> "SIGNALED"; 3 -> "LOW_MEMORY"; 4 -> "CRASH"; 5 -> "CRASH_NATIVE"; 6 -> "ANR"
        7 -> "INITIALIZATION_FAILURE"; 8 -> "PERMISSION_CHANGE"; 9 -> "EXCESSIVE_RESOURCE_USAGE"; 10 -> "USER_REQUESTED"
        11 -> "USER_STOPPED"; 12 -> "DEPENDENCY_DIED"; 13 -> "OTHER"; 14 -> "FREEZER"; 15 -> "PACKAGE_STATE_CHANGE"
        16 -> "PACKAGE_UPDATED"; else -> "?"
    } + "($r)"

    /** Linux signal name for an engine exit code (Python returns -N when the process was killed by signal N). */
    fun signalName(code: Int): String = when (-code) {
        9 -> "SIGKILL (killed - by Android's memory/process killer or the app)"
        15 -> "SIGTERM (asked to stop)"; 6 -> "SIGABRT (engine aborted)"; 11 -> "SIGSEGV (engine crashed)"
        7 -> "SIGBUS"; 4 -> "SIGILL (CPU does not support the instruction set)"; else -> "signal ${-code}"
    }

    private fun read(path: String, max: Int = 64 * 1024): String? =
        runCatching { File(path).readText().take(max) }.getOrNull()

    private fun battery(ctx: Context): String {
        val i: Intent = ctx.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED)) ?: return "battery: ?"
        val temp = i.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
        val level = i.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) * 100 / i.getIntExtra(BatteryManager.EXTRA_SCALE, 100).coerceAtLeast(1)
        val status = when (i.getIntExtra(BatteryManager.EXTRA_STATUS, -1)) {
            BatteryManager.BATTERY_STATUS_CHARGING -> "charging"; BatteryManager.BATTERY_STATUS_DISCHARGING -> "discharging"
            BatteryManager.BATTERY_STATUS_FULL -> "full"; BatteryManager.BATTERY_STATUS_NOT_CHARGING -> "not charging"; else -> "?"
        }
        val plugged = when (i.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0)) {
            BatteryManager.BATTERY_PLUGGED_AC -> "AC"; BatteryManager.BATTERY_PLUGGED_USB -> "USB"
            BatteryManager.BATTERY_PLUGGED_WIRELESS -> "wireless"; 0 -> "unplugged"; else -> "plugged"
        }
        val mv = i.getIntExtra(BatteryManager.EXTRA_VOLTAGE, -1)
        return "battery: ${if (temp != Int.MIN_VALUE) "%.1f°C".format(Locale.US, temp / 10.0) else "?"}, $level%, $status, $plugged, ${mv} mV"
    }

    /** Thermal sensors exposed in /sys/class/thermal (hottest first). */
    fun thermalZones(limit: Int = 12): String {
        val zones = File("/sys/class/thermal").listFiles { f -> f.name.startsWith("thermal_zone") } ?: return "sensors: not readable"
        val list = zones.mapNotNull { z ->
            val t = read("${z.path}/temp")?.trim()?.toLongOrNull() ?: return@mapNotNull null
            val type = read("${z.path}/type")?.trim() ?: z.name
            val c = if (t > 1000 || t < -1000) t / 1000.0 else t.toDouble()
            if (c < -40 || c > 150) null else type to c
        }.sortedByDescending { it.second }
        if (list.isEmpty()) return "sensors: not readable on this phone (Android hides them)"
        return "sensors: " + list.take(limit).joinToString(", ") { "%s=%.1f°C".format(Locale.US, it.first, it.second) } +
            if (list.size > limit) " (+${list.size - limit} more)" else ""
    }

    private fun cpuFreqs(): String {
        val cpus = File("/sys/devices/system/cpu").listFiles { f -> f.name.matches(Regex("cpu\\d+")) }?.sortedBy { it.name.drop(3).toInt() }
            ?: return "cpu: ?"
        val parts = cpus.map { c ->
            val cur = read("${c.path}/cpufreq/scaling_cur_freq")?.trim()?.toLongOrNull()
            val max = read("${c.path}/cpufreq/scaling_max_freq")?.trim()?.toLongOrNull()
            val online = read("${c.path}/online")?.trim() != "0"
            "${c.name}=" + when {
                !online -> "off"
                cur == null -> "?"
                else -> "${cur / 1000}${if (max != null) "/${max / 1000}" else ""}"
            }
        }
        return "cpu MHz (current/max allowed): " + parts.joinToString(" ")
    }

    fun memory(ctx: Context): String {
        val am = ctx.getSystemService(ActivityManager::class.java)!!
        val mi = ActivityManager.MemoryInfo().also { am.getMemoryInfo(it) }
        val st = procStatus("/proc/self/status")
        return "memory: available ${mi.availMem / 1_048_576} MB of ${mi.totalMem / 1_048_576} MB, low=${mi.lowMemory} " +
            "(threshold ${mi.threshold / 1_048_576} MB); app RSS ${st["VmRSS"]?.let { it / 1024 } ?: "?"} MB, " +
            "app peak ${st["VmHWM"]?.let { it / 1024 } ?: "?"} MB"
    }

    fun power(ctx: Context): String {
        val pm = ctx.getSystemService(PowerManager::class.java)!!
        val am = ctx.getSystemService(ActivityManager::class.java)!!
        val usm = ctx.getSystemService(UsageStatsManager::class.java)
        val me = ActivityManager.RunningAppProcessInfo().also { ActivityManager.getMyMemoryState(it) }
        val headroom = if (Build.VERSION.SDK_INT >= 30) runCatching { "%.2f".format(Locale.US, pm.getThermalHeadroom(10)) }.getOrDefault("?") else "n/a"
        return "thermal: status ${thermalStatusName(pm.currentThermalStatus)}, headroom(10 s) $headroom (1.0 = throttling starts)\n" +
            "  power: screen ${if (pm.isInteractive) "on" else "off"}, doze=${pm.isDeviceIdleMode}, battery saver=${pm.isPowerSaveMode}, " +
            "battery optimization ${if (pm.isIgnoringBatteryOptimizations(ctx.packageName)) "OFF (unrestricted)" else "ON (optimized)"}, " +
            "background restricted=${am.isBackgroundRestricted}, standby bucket ${usm?.appStandbyBucket?.let(::bucketName) ?: "?"}\n" +
            "  process: importance ${importanceName(me.importance)}, last trim ${trimLevelName(me.lastTrimLevel)}, pid ${android.os.Process.myPid()}"
    }

    fun procStatus(path: String): Map<String, Long> {
        val text = read(path) ?: return emptyMap()
        return text.lines().mapNotNull { l ->
            val k = l.substringBefore(':', "")
            if (k !in setOf("VmRSS", "VmHWM", "VmSwap", "Threads", "voluntary_ctxt_switches", "nonvoluntary_ctxt_switches")) return@mapNotNull null
            l.substringAfter(':').trim().split(Regex("\\s+")).firstOrNull()?.toLongOrNull()?.let { k to it }
        }.toMap()
    }

    /** Process state letter from /proc/<pid>/stat: R running, S sleeping, D disk wait, T stopped (paused), Z zombie. */
    fun procState(pid: Int): String {
        val stat = read("/proc/$pid/stat") ?: return "gone"
        val after = stat.substringAfterLast(')').trim()
        return when (after.firstOrNull()) {
            'R' -> "R running"; 'S' -> "S sleeping"; 'D' -> "D waiting for disk"; 'T' -> "T stopped (paused)"; 't' -> "t traced"
            'Z' -> "Z zombie"; 'X' -> "X dead"; else -> after.take(1)
        }
    }

    /** Native engine processes of this app (also orphans left behind by an earlier, killed app process). */
    fun engineProcesses(ctx: Context): List<Pair<Int, String>> {
        val libDir = ctx.applicationInfo.nativeLibraryDir
        val me = android.os.Process.myPid()
        return (File("/proc").listFiles { f -> f.name.all(Char::isDigit) } ?: emptyArray()).mapNotNull { p ->
            val pid = p.name.toInt()
            if (pid == me) return@mapNotNull null
            val cmd = read("/proc/$pid/cmdline", 4096)?.replace('\u0000', ' ')?.trim() ?: return@mapNotNull null
            if (cmd.startsWith(libDir) && "libace" in cmd) pid to cmd.substringAfterLast('/').substringBefore(' ') else null
        }
    }

    fun engines(ctx: Context, known: Map<Int, String>): String {
        val list = engineProcesses(ctx)
        if (list.isEmpty()) return "engine: not running"
        return list.joinToString("\n  ", prefix = "engine: ") { (pid, exe) ->
            val st = procStatus("/proc/$pid/status")
            "pid $pid $exe [${known[pid] ?: "unknown stage"}] ${procState(pid)}, RSS ${st["VmRSS"]?.let { it / 1024 } ?: "?"} MB, " +
                "peak ${st["VmHWM"]?.let { it / 1024 } ?: "?"} MB, threads ${st["Threads"] ?: "?"}" +
                if (pid !in known) " - ORPHAN (left from an earlier app process)" else ""
        }
    }

    fun pressure(): String {
        val parts = listOf("cpu", "memory", "io").mapNotNull { k ->
            read("/proc/pressure/$k")?.lines()?.firstOrNull()?.let { "$k: ${it.removePrefix("some ").trim()}" }
        }
        return if (parts.isEmpty()) "pressure (PSI): not readable" else "pressure (PSI, % of time stalled): " + parts.joinToString(" | ")
    }

    /** Compact multi-line state used every 10 minutes and at important events. */
    fun snapshot(ctx: Context, known: Map<Int, String>): String = listOf(
        power(ctx), battery(ctx), thermalZones(), cpuFreqs(), memory(ctx), engines(ctx, known), pressure(),
    ).joinToString("\n  ", prefix = "  ")

    /** Why earlier app processes ended (Android 11+), newest first. */
    fun exitInfos(ctx: Context, max: Int = 8): List<ApplicationExitInfo> =
        if (Build.VERSION.SDK_INT < 30) emptyList()
        else runCatching { ctx.getSystemService(ActivityManager::class.java)!!.getHistoricalProcessExitReasons(ctx.packageName, 0, max) }
            .getOrDefault(emptyList())

    fun describeExit(e: ApplicationExitInfo): String =
        "${fmtTime(e.timestamp)} ${e.processName}: ${exitReasonName(e.reason)}, status ${e.status}, " +
            "importance ${importanceName(e.importance)}, PSS ${e.pss / 1024} MB, RSS ${e.rss / 1024} MB" +
            (e.description?.let { ", \"$it\"" } ?: "")

    /** Full /proc details for extended dumps. */
    fun procDetails(ctx: Context, known: Map<Int, String>): String = buildString {
        fun section(title: String, body: String?) { append("===== $title =====\n").append(body ?: "(not readable)").append("\n\n") }
        section("/proc/self/status", read("/proc/self/status"))
        section("/proc/self/smaps_rollup", read("/proc/self/smaps_rollup"))
        engineProcesses(ctx).forEach { (pid, exe) ->
            section("engine pid $pid ($exe, ${known[pid] ?: "unknown"}) /proc/$pid/status", read("/proc/$pid/status"))
            section("engine pid $pid /proc/$pid/smaps_rollup", read("/proc/$pid/smaps_rollup"))
            section("engine pid $pid /proc/$pid/stat", read("/proc/$pid/stat"))
            section("engine pid $pid /proc/$pid/wchan (what it waits for)", read("/proc/$pid/wchan"))
        }
        section("/proc/meminfo", read("/proc/meminfo"))
        listOf("cpu", "memory", "io").forEach { section("/proc/pressure/$it", read("/proc/pressure/$it")) }
        section("thermal sensors (all)", thermalZones(limit = 200))
        section("cpu frequencies", cpuFreqs())
    }
}
