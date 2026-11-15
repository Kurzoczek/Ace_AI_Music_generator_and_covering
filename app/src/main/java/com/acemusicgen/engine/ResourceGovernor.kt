package com.acemusicgen.engine

import android.content.Context
import android.os.Build
import android.os.PowerManager
import android.os.Process
import com.acemusicgen.data.AppSettings
import com.acemusicgen.data.DeviceInfo
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.util.concurrent.ConcurrentHashMap

/**
 * Controls the native acestep.cpp processes while they run:
 *  - CPU limit: duty cycle with SIGSTOP / SIGCONT (e.g. 50 % = runs 100 ms, sleeps 100 ms), on top of the thread
 *    count, core selection (affinity) and low priority (nice) applied when the process starts;
 *  - overheating protection: pauses the process when the phone reports a high thermal status / no thermal headroom
 *    and resumes after it cools down;
 *  - user pause / resume.
 * Pausing never loses work: the process is frozen, not killed.
 */
class ResourceGovernor(
    private val context: Context,
    private val settings: AppSettings,
    private val scope: CoroutineScope,
    private val onThermalChange: (paused: Boolean, status: Int) -> Unit,
) {
    private val pids = ConcurrentHashMap<Int, String>()
    @Volatile var userPaused = false
    @Volatile var thermalPaused = false
        private set
    private var loop: Job? = null
    private val power = context.getSystemService(PowerManager::class.java)!!
    private val thermalListener = PowerManager.OnThermalStatusChangedListener { status -> evaluateThermal(status) }

    companion object {
        private const val SIGCONT = 18
        private const val SIGSTOP = 19
        private const val PERIOD_MS = 200L

        /** The governor of the running job (for diagnostics), or null. */
        @Volatile var current: ResourceGovernor? = null
            private set

        /** Engine processes of the running job: pid -> stage. */
        fun activePids(): Map<Int, String> = current?.pids?.toMap() ?: emptyMap()
    }

    private var thermalPausedAt = 0L

    fun register(pid: Int, stage: String) { pids[pid] = stage }
    fun unregister(pid: Int) { pids.remove(pid) }

    fun start() {
        current = this
        if (settings.thermalProtection) {
            power.addThermalStatusListener(context.mainExecutor, thermalListener)
            evaluateThermal(power.currentThermalStatus)
        }
        loop = scope.launch {
            var lastHeadroomCheck = 0L
            while (isActive) {
                if (settings.thermalProtection && Build.VERSION.SDK_INT >= Build.VERSION_CODES.R &&
                    System.currentTimeMillis() - lastHeadroomCheck > 5_000) {
                    lastHeadroomCheck = System.currentTimeMillis()
                    evaluateThermal(power.currentThermalStatus)
                }
                val pct = settings.cpuMaxPercent.coerceIn(10, 100)
                when {
                    userPaused || thermalPaused -> { signalAll(SIGSTOP); delay(500) }
                    pct >= 100 -> { signalAll(SIGCONT); delay(500) }
                    else -> {
                        signalAll(SIGCONT)
                        delay(PERIOD_MS * pct / 100)
                        if (!userPaused && !thermalPaused) signalAll(SIGSTOP)
                        delay(PERIOD_MS * (100 - pct) / 100)
                    }
                }
            }
        }
    }

    private fun evaluateThermal(status: Int) {
        if (!settings.thermalProtection) return
        val headroom = DeviceInfo.thermalHeadroom(context)
        val hot = status >= settings.thermalPauseLevel || (!headroom.isNaN() && headroom >= 1.0f)
        val cool = status < maxOf(PowerManager.THERMAL_STATUS_LIGHT, settings.thermalPauseLevel - 1) &&
            (headroom.isNaN() || headroom < 0.85f)
        if (!thermalPaused && hot) {
            thermalPaused = true
            thermalPausedAt = System.currentTimeMillis()
            signalAll(SIGSTOP)
            val why = "status ${com.acemusicgen.diag.SystemProbe.thermalStatusName(status)} (pause level ${settings.thermalPauseLevel}), " +
                "headroom ${if (headroom.isNaN()) "n/a" else "%.2f".format(java.util.Locale.US, headroom)} (pause at >= 1.00)"
            com.acemusicgen.diag.Diagnostics.event("GOVERNOR", "overheating protection PAUSED the engine: $why")
            com.acemusicgen.diag.Diagnostics.snapshot("overheating pause")
            com.acemusicgen.diag.Diagnostics.pauseEvent("overheating pause: $why")
            onThermalChange(true, status)
        } else if (thermalPaused && cool) {
            thermalPaused = false
            com.acemusicgen.diag.Diagnostics.event("GOVERNOR", "cooled down - engine RESUMED after " +
                com.acemusicgen.diag.Diagnostics.duration(System.currentTimeMillis() - thermalPausedAt) +
                " (status ${com.acemusicgen.diag.SystemProbe.thermalStatusName(status)}, headroom " +
                "${if (headroom.isNaN()) "n/a" else "%.2f".format(java.util.Locale.US, headroom)})")
            onThermalChange(false, status)
        }
    }

    private fun signalAll(sig: Int) {
        for (pid in pids.keys) runCatching { Process.sendSignal(pid, sig) }
    }

    fun stop() {
        if (current === this) current = null
        loop?.cancel()
        signalAll(SIGCONT)
        if (settings.thermalProtection) runCatching { power.removeThermalStatusListener(thermalListener) }
    }
}
