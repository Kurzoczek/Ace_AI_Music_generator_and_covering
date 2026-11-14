package com.acemusicgen.data

import android.content.Context
import org.json.JSONObject
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

/**
 * RAM estimates and the low-memory plan.
 *
 * acestep.cpp keeps the quantized weights in RAM: DiT + text encoder + VAE (the language model runs as a separate,
 * earlier step, so it is never in memory together with the DiT). On top of that come the activations, which grow
 * with the length of the generated audio. The per-second figure starts from a conservative default and is calibrated
 * from the real peak memory (VmHWM) measured after every run on this phone.
 *
 * There is NO fixed upper RAM cap: the user's limit can be anything up to the RAM of the phone. When the limit is
 * smaller than the model needs, the plan does not refuse to run - it uses shorter passes, fewer threads and no
 * language model, and the engine waits for memory / retries instead of failing (see ace_android.py).
 */
class MemoryPlanner(context: Context) {
    private val prefs = context.getSharedPreferences("memory_calibration", Context.MODE_PRIVATE)
    private val appContext = context.applicationContext

    companion object {
        const val GB = 1024.0 * 1024.0 * 1024.0
        const val BASE_ACTIVATIONS_GB = 0.35          // buffers that do not depend on the audio length
        const val DEFAULT_GB_PER_SEC = 0.012           // conservative start value, replaced by calibration
        const val LM_OVERHEAD_GB = 0.35                // KV cache + buffers of the language model step
        const val PYTHON_APP_GB = 0.45                 // the app itself (analysis in Python/numpy) while the model runs
        const val MIN_PASS_SEC = 24.0                  // shortest pass (10 s of music + margins)
        const val SYSTEM_RESERVE_MB = 1536L            // left for Android and other apps in "Auto" mode
    }

    data class Estimate(
        val weightsGb: Double,          // DiT + text encoder + VAE
        val synthPeakGb: Double,        // weights + activations for the planned pass length
        val lmPeakGb: Double,           // language model step (0 when not used)
        val peakGb: Double,             // max of both steps + the app itself
        val gbPerSec: Double,
        val calibrated: Boolean,
    )

    data class Plan(
        val limitMb: Long,
        val maxPassSec: Double,         // 0 = no limit (whole track in one pass)
        val lmEnabled: Boolean,
        val threads: Int,
        val belowMinimum: Boolean,      // the limit is lower than the weights alone -> relies on system compressed memory
        val estimate: Estimate,
        val vaeChunk: Int = 0,          // ace-synth --vae-chunk (0 = default 1024); smaller tiles = less RAM when decoding
    )

    private fun key(s: AppSettings) = "${s.model}|${s.quant}"

    private fun gbPerSec(s: AppSettings): Pair<Double, Boolean> {
        val v = prefs.getFloat("gbps|${key(s)}", -1f)
        return if (v > 0) v.toDouble() to true else DEFAULT_GB_PER_SEC to false
    }

    fun estimate(s: AppSettings, durationSec: Double): Estimate {
        val files = ModelCatalog.requiredFiles(s)
        val weights = files.filter { it.role != "lm" }.sumOf { it.sizeBytes } / GB * 1.05
        val lmFile = files.firstOrNull { it.role == "lm" }
        val lmPeak = if (lmFile != null) lmFile.sizeBytes / GB * 1.05 + LM_OVERHEAD_GB else 0.0
        val (perSec, calibrated) = gbPerSec(s)
        val synth = weights + BASE_ACTIVATIONS_GB + perSec * max(10.0, durationSec)
        return Estimate(weights, synth, lmPeak, max(synth, lmPeak) + PYTHON_APP_GB, perSec, calibrated)
    }

    /** RAM the generation may use: the user's limit, or (Auto) the phone RAM minus a reserve for the system. */
    fun limitMb(s: AppSettings): Long {
        val total = DeviceInfo.memory(appContext).totalMb
        return if (s.ramAuto) max(512L, total - SYSTEM_RESERVE_MB) else s.ramLimitMb.toLong().coerceAtLeast(256L)
    }

    fun plan(s: AppSettings, durationSec: Double): Plan {
        val limitMb = limitMb(s)
        val limitGb = limitMb / 1024.0
        val est = estimate(s, durationSec)
        val budgetForModel = limitGb - PYTHON_APP_GB
        val free = budgetForModel - est.weightsGb - BASE_ACTIVATIONS_GB
        val maxPass = when {
            free <= 0 -> MIN_PASS_SEC
            free / est.gbPerSec >= durationSec -> 0.0
            else -> max(MIN_PASS_SEC, free / est.gbPerSec)
        }
        val lmEnabled = est.lmPeakGb == 0.0 || est.lmPeakGb <= budgetForModel
        val userThreads = if (s.threads > 0) s.threads else DeviceInfo.defaultThreads()
        val coreLimit = DeviceInfo.coreCount(s.coreSet)
        var threads = min(userThreads, coreLimit)
        if (free <= 0) threads = min(threads, 2)          // every thread has its own scratch buffers
        val vaeChunk = when {
            free <= 0 -> 128
            maxPass > 0 -> 256
            else -> 0
        }
        return Plan(limitMb, maxPass, lmEnabled, max(1, threads), free <= 0, est, vaeChunk)
    }

    /** Called after a successful native run: refines GB-per-second of audio from the measured peak. */
    fun calibrate(s: AppSettings, stage: String, peakRssKb: Long, durationSec: Double) {
        if (stage != "synth" || peakRssKb <= 0 || durationSec < 10) return
        val peakGb = peakRssKb * 1024.0 / GB
        val weights = estimate(s, durationSec).weightsGb
        val measured = (peakGb - weights - BASE_ACTIVATIONS_GB) / durationSec
        if (measured <= 0) return
        val (old, had) = gbPerSec(s)
        val next = if (had) old * 0.5 + measured * 0.5 else measured
        prefs.edit().putFloat("gbps|${key(s)}", next.toFloat()).apply()
    }

    /** Response to an out-of-memory kill of the native process (JSON for ace_android.py). */
    fun onLowMemory(stage: String, attempt: Int, threads: Int): String = JSONObject().apply {
        put("threads", max(1, threads / 2))
        put("lm_enabled", false)
        put("wait_sec", min(600.0, 20.0 * 2.0.pow((attempt - 1).coerceIn(0, 5))).toInt())
    }.toString()
}
