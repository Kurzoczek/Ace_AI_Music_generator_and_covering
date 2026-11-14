package com.acemusicgen.engine

import android.content.Context
import com.acemusicgen.R
import com.acemusicgen.data.AppSettings
import com.acemusicgen.data.DeviceInfo
import com.acemusicgen.data.MemoryPlanner

/**
 * Object handed to Python (ace_android.run). Python calls these methods by name, so they must stay public
 * and keep their signatures (see the docstring of ace_android.py and proguard-rules.pro).
 */
class PythonBridge(
    private val context: Context,
    private val settings: AppSettings,
    private val governor: ResourceGovernor,
    private val planner: MemoryPlanner,
    private val ramLimitMb: Long,
) {
    fun onLog(line: String) = JobRepository.log(line)

    fun onProgress(fraction: Double, text: String) {
        JobRepository.update { it.copy(progress = fraction.toFloat(), status = text) }
    }

    fun isCancelled(): Boolean = JobRepository.cancelRequested

    fun onNativeStart(pid: Int, stage: String) = governor.register(pid, stage)

    fun onNativeEnd(pid: Int, code: Int, peakRssKb: Long, stage: String, durationSec: Double, threads: Int) {
        governor.unregister(pid)
        val peakMb = peakRssKb / 1024
        if (code == 0) {
            planner.calibrate(settings, stage, peakRssKb, durationSec)
            if (peakMb > ramLimitMb) {
                JobRepository.update { it.copy(memoryNote = context.getString(R.string.note_over_limit, peakMb.toInt(), ramLimitMb.toInt())) }
            }
        }
    }

    fun onLowMemory(stage: String, peakRssKb: Long, attempt: Int, threads: Int): String {
        JobRepository.update { it.copy(memoryNote = context.getString(R.string.note_low_memory, stage, attempt)) }
        return planner.onLowMemory(stage, attempt, threads)
    }

    /** Blocks the Python thread until enough RAM is free or the time is up (or the user cancels). */
    fun waitForMemory(neededMb: Int, maxWaitSec: Int): Boolean {
        val deadline = System.currentTimeMillis() + maxWaitSec * 1000L
        while (true) {
            if (isCancelled()) return false
            System.gc()
            if (DeviceInfo.memory(context).availableMb >= neededMb) return true
            if (System.currentTimeMillis() >= deadline) return false
            Thread.sleep(2_000)
        }
    }
}
