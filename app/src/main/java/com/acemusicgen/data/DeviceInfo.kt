package com.acemusicgen.data

import android.app.ActivityManager
import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.os.PowerManager
import android.os.StatFs
import java.io.File

/** Read-only facts about the phone used for planning and warnings. */
object DeviceInfo {

    data class Memory(val totalMb: Long, val availableMb: Long, val lowMemory: Boolean)

    fun memory(context: Context): Memory {
        val am = context.getSystemService(ActivityManager::class.java)!!
        val mi = ActivityManager.MemoryInfo()
        am.getMemoryInfo(mi)
        return Memory(mi.totalMem / MB, mi.availMem / MB, mi.lowMemory)
    }

    fun freeBytes(dir: File): Long {
        var d: File? = dir
        while (d != null && !d.exists()) d = d.parentFile
        return if (d == null) 0L else StatFs(d.path).availableBytes
    }

    /** True when both paths are on the same filesystem (so their free space is shared). */
    fun sameVolume(a: File, b: File): Boolean = try {
        fun existing(f: File): File { var d: File? = f; while (d != null && !d.exists()) d = d.parentFile; return d ?: File("/") }
        android.system.Os.stat(existing(a).path).st_dev == android.system.Os.stat(existing(b).path).st_dev
    } catch (e: Exception) {
        true
    }

    /** Max frequency (kHz) of every core; used to tell "big" (performance) and "little" (efficiency) cores apart. */
    fun coreMaxFreqs(): List<Pair<Int, Long>> {
        val n = Runtime.getRuntime().availableProcessors()
        return (0 until n).map { i ->
            val f = runCatching {
                File("/sys/devices/system/cpu/cpu$i/cpufreq/cpuinfo_max_freq").readText().trim().toLong()
            }.getOrDefault(0L)
            i to f
        }
    }

    fun coresFor(set: CoreSet): List<Int> {
        val cores = coreMaxFreqs()
        val freqs = cores.map { it.second }.filter { it > 0 }.distinct().sorted()
        if (freqs.size < 2 || set == CoreSet.ALL) return emptyList()      // empty = no affinity restriction
        val lowest = freqs.first()
        return when (set) {
            CoreSet.EFFICIENCY -> cores.filter { it.second == lowest }.map { it.first }
            CoreSet.PERFORMANCE -> cores.filter { it.second > lowest }.map { it.first }
            CoreSet.ALL -> emptyList()
        }
    }

    fun coreCount(set: CoreSet): Int =
        coresFor(set).size.takeIf { it > 0 } ?: Runtime.getRuntime().availableProcessors()

    /** Default thread count: the big cores (little cores slow ggml down when mixed in). */
    fun defaultThreads(): Int {
        val perf = coresFor(CoreSet.PERFORMANCE).size
        return if (perf > 0) perf else maxOf(1, Runtime.getRuntime().availableProcessors() / 2)
    }

    fun thermalStatus(context: Context): Int =
        context.getSystemService(PowerManager::class.java)!!.currentThermalStatus

    /** 0..1+ (1 = throttling expected), or NaN when the phone does not report it. */
    fun thermalHeadroom(context: Context): Float =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R)
            context.getSystemService(PowerManager::class.java)!!.getThermalHeadroom(10)
        else Float.NaN

    data class Network(val connected: Boolean, val metered: Boolean)

    fun network(context: Context): Network {
        val cm = context.getSystemService(ConnectivityManager::class.java)!!
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return Network(false, false)
        val connected = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
        val metered = !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
        return Network(connected, metered)
    }

    const val MB = 1024L * 1024L
}
