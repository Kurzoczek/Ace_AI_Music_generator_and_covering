package com.acemusicgen.data

import android.content.Context
import android.media.MediaMetadataRetriever
import android.net.Uri
import java.io.File

/** Everything the user is told (and must confirm) before processing starts. */
data class PreflightReport(
    val toDownload: List<ModelFile>,
    val downloadBytes: Long,
    val sizesExact: Boolean,
    val source: String,
    val host: String,
    val modelsOnDiskBytes: Long,        // space all models of this configuration occupy after download
    val outputEstimateBytes: Long,      // results + temporary files
    val freeBytes: Long,                // free space where the models go
    val workFreeBytes: Long,            // free space for results / temporary files (internal storage)
    val enoughSpace: Boolean,
    val modelsDir: String,              // where the models are / will be stored
    val network: DeviceInfo.Network,
    val wifiOnlyBlocked: Boolean,
    val deviceRamMb: Long,
    val availableRamMb: Long,
    val plan: MemoryPlanner.Plan,
    val durationSec: Double,
    val thermalStatus: Int,
    val modelLabel: String,
)

object Preflight {
    private const val SECTION_SEC = 14.1          // 32 beats at ~140 BPM + crossfade (as in the scripts)

    fun audioDurationSec(context: Context, uri: Uri): Double = try {
        MediaMetadataRetriever().use { r ->
            r.setDataSource(context, uri)
            (r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L) / 1000.0
        }
    } catch (e: Exception) {
        0.0
    }

    /** Length of audio the model has to generate in one go (before any splitting into passes). */
    fun generatedDurationSec(s: AppSettings, inputDurations: List<Double>): Double {
        val longest = inputDurations.maxOrNull() ?: 0.0
        return if (s.mode == "cover") {
            val fr = s.parsedFragments()
            when {
                !s.coverWholeFile && fr.isNotEmpty() ->
                    if (s.coverFragmentsMode == "separate") fr.sumOf { it.second - it.first } else fr.maxOf { it.second - it.first }
                else -> minOf(longest.takeIf { it > 0 } ?: 180.0, (s.coverMaxSec ?: Float.MAX_VALUE).toDouble())
            }
        } else {
            if (s.wholeTrack) s.numSections * SECTION_SEC + 0.4 else SECTION_SEC + 12.0
        }
    }

    fun build(context: Context, s: AppSettings, modelsDir: File, inputDurations: List<Double>): PreflightReport {
        ModelCatalog.refreshFromServer()                 // exact sizes + checksums; falls back to the built-in table offline
        val required = ModelCatalog.requiredFiles(s)
        val missing = required.filter { !ModelCatalog.isDownloaded(modelsDir, it) }
        val partial = missing.sumOf { File(modelsDir, it.name + ".part").takeIf { f -> f.exists() }?.length() ?: 0L }
        val downloadBytes = (missing.sumOf { it.sizeBytes } - partial).coerceAtLeast(0L)
        val duration = generatedDurationSec(s, inputDurations)
        val totalAudio = if (s.mode == "cover") inputDurations.sum().coerceAtLeast(duration) else duration * maxOf(1, inputDurations.size)
        // results: every channel format of the final track + parts, 16-bit 48 kHz; temporary: decoded input + checkpoints
        val channels = s.channelFormats().map { when (it) { "mono" -> 1; "stereo" -> 2; else -> 6 } }.sum()
        val outputBytes = (totalAudio * 48_000 * 2 * channels * 2.2 + totalAudio * 48_000 * 2 * 2 * 3).toLong()
        val free = DeviceInfo.freeBytes(modelsDir)
        val workFree = DeviceInfo.freeBytes(context.filesDir)
        val reserve = 200L * 1024 * 1024
        val enough = if (DeviceInfo.sameVolume(modelsDir, context.filesDir)) free > downloadBytes + outputBytes + reserve
                     else free > downloadBytes + reserve && workFree > outputBytes + reserve
        val net = DeviceInfo.network(context)
        val mem = DeviceInfo.memory(context)
        val plan = MemoryPlanner(context).plan(s, duration)
        return PreflightReport(
            toDownload = missing, downloadBytes = downloadBytes, sizesExact = ModelCatalog.hasExactSizes,
            source = ModelCatalog.SOURCE_DESCRIPTION, host = ModelCatalog.HOST,
            modelsOnDiskBytes = required.sumOf { it.sizeBytes }, outputEstimateBytes = outputBytes,
            freeBytes = free, workFreeBytes = workFree, enoughSpace = enough, modelsDir = modelsDir.path,
            network = net, wifiOnlyBlocked = downloadBytes > 0 && s.wifiOnly && (net.metered || !net.connected),
            deviceRamMb = mem.totalMb, availableRamMb = mem.availableMb, plan = plan, durationSec = duration,
            thermalStatus = DeviceInfo.thermalStatus(context),
            modelLabel = "${s.model.removePrefix("acestep-v15-")} ${s.quant}" + if (s.mode == "text" && s.lm.isNotEmpty()) " + LM ${s.lm}" else "",
        )
    }
}
