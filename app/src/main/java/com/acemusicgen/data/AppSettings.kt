package com.acemusicgen.data

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONArray
import org.json.JSONObject

/** Which cores the native engine may run on. */
enum class CoreSet { ALL, EFFICIENCY, PERFORMANCE }

/**
 * Process priority of the native engine, named like the Windows Task Manager levels. Mapped to the Linux nice value
 * (-20 = highest, 19 = lowest). Android lets an app lower its own processes freely; raising above normal works on most
 * phones (the system allows nice down to -20 for app processes) but may be refused, then the engine runs at normal.
 * True real-time scheduling (SCHED_FIFO) is reserved for the system on Android, so REALTIME = the highest nice value.
 */
/**
 * What a state dump contains, named after the Windows "Write debugging information" options.
 * Android does not let an app dump the kernel or other processes, so the levels are the closest equivalents:
 *  SMALL     - like a Windows small memory dump: app/job state, settings, device state, log, Java thread stacks;
 *  EXTENDED  - like a kernel memory dump: SMALL + Python thread stacks, /proc memory maps of the app and the engine,
 *              system memory/pressure, all thermal sensors, exit reasons with system crash/ANR traces, work files;
 *  FULL      - like a complete memory dump: EXTENDED + Java heap dump (.hprof). The engine's model memory (GBs of
 *              weights) is not dumped - it is the model file itself;
 *  AUTOMATIC - EXTENDED for crashes, unexpected ends and manual dumps, SMALL for errors and pauses.
 */
enum class DumpType { NONE, SMALL, EXTENDED, FULL, AUTOMATIC }

enum class Priority(val nice: Int) {
    LOW(19), BELOW_NORMAL(10), NORMAL(0), ABOVE_NORMAL(-5), HIGH(-10), REALTIME(-20);
    val raised: Boolean get() = nice < 0
}

/** All user settings. Generation settings map 1:1 to the constants of the Python scripts (see toPythonSettings). */
data class AppSettings(
    // --- generation
    val mode: String = "cover",                     // "cover" | "text"
    val model: String = "acestep-v15-turbo",        // DiT model id
    val quant: String = "Q4_K_M",                   // GGUF quantization (Q4_K_M = least RAM, sensible default for phones)
    val lm: String = "",                            // language model for text mode: "" | "0.6B" | "1.7B" | "4B"
    val steps: Int? = null,                         // null = model default (turbo 8, sft/base 32)
    val guidance: Float? = null,
    val seed: Int = -1,
    val numSections: Int = 6,
    val wholeTrack: Boolean = true,
    val numPasses: Int = 0,
    val prompt: String = "",
    val instrumental: Boolean = true,
    val lyrics: String = "[Instrumental]",
    // --- cover
    val coverStrength: Float = 0.5f,
    val coverNoise: Float = 0.0f,
    val coverWholeFile: Boolean = true,
    val coverMaxSec: Float? = null,
    val coverFragments: String = "",                // "0:30-1:15; 2:00-2:45"
    val coverFragmentsMode: String = "insert",      // "insert" | "separate"
    // --- reference
    val useReference: Boolean = true,
    val referenceMode: String = "input",            // "input" | "previous"
    val referenceLenSec: Float = 30f,
    // --- analysis / export
    val stemAnalysis: Boolean = false,              // PRO analysis (HPSS stems on the phone) - slower
    val exportNotation: Boolean = true,
    val exportSamples: Boolean = false,
    val exportUsedSounds: Boolean = false,
    val exportStems: Boolean = false,
    val formatMono: Boolean = true,
    val formatStereo: Boolean = true,
    val formatSurround: Boolean = false,
    // --- resources
    val ramAuto: Boolean = true,                    // true = plan for the RAM the phone actually has
    val ramLimitMb: Int = 4096,                     // used when ramAuto = false; no upper cap other than the device RAM
    val threads: Int = 0,                           // 0 = automatic (all big cores)
    val cpuMaxPercent: Int = 100,                   // duty-cycle limit of the native process (10..100 %)
    val coreSet: CoreSet = CoreSet.ALL,
    val priority: Priority = Priority.BELOW_NORMAL, // nice 10: the phone stays responsive
    val thermalProtection: Boolean = true,          // pause when the phone gets hot
    val thermalPauseLevel: Int = 3,                 // PowerManager.THERMAL_STATUS_SEVERE
    // --- network
    val wifiOnly: Boolean = true,
    // --- save locations: OutputCategory.key -> folder picked by the user (SAF tree URI); missing = default location
    val outputFolders: Map<String, String> = emptyMap(),
    /** Where models are stored: ModelStorage.APP, PHONE (default) or "sd:<uuid>". */
    val modelsLocation: String = ModelStorage.DEFAULT,
    // --- diagnostics (folders are kept in outputFolders under DiagFolders.LOGS / DiagFolders.DUMPS)
    val diagLogs: Boolean = false,                  // copy the diagnostic log to the "app logs" folder
    val dumpType: DumpType = DumpType.NONE,
    val dumpOnError: Boolean = true,                // when a job fails
    val dumpOnUnexpectedEnd: Boolean = true,        // app crash, or the system killed the app during a job
    val dumpOnPause: Boolean = false,               // overheating pause, waiting for memory, critical memory warning
    val dumpKeep: Int = 5,                          // dumps kept in the folder (1 = always overwrite, like Windows)
) {
    fun effectiveSteps(): Int = steps ?: if ("turbo" in model) 8 else 32

    fun channelFormats(): List<String> = buildList {
        if (formatMono) add("mono")
        if (formatStereo) add("stereo")
        if (formatSurround) add("surround")
        if (isEmpty()) add("stereo")
    }

    /** Parses "0:30-1:15; 2:00-2:45" into [[30,75],[120,165]]; invalid parts are skipped. */
    fun parsedFragments(): List<Pair<Double, Double>> {
        fun t(s: String): Double? {
            val p = s.trim().split(":")
            return try {
                when (p.size) {
                    1 -> p[0].toDouble()
                    2 -> p[0].toDouble() * 60 + p[1].toDouble()
                    3 -> p[0].toDouble() * 3600 + p[1].toDouble() * 60 + p[2].toDouble()
                    else -> null
                }
            } catch (e: NumberFormatException) { null }
        }
        return coverFragments.split(";", "\n").mapNotNull { part ->
            val ab = part.trim().split("-")
            if (ab.size != 2) return@mapNotNull null
            val a = t(ab[0]) ?: return@mapNotNull null
            val b = t(ab[1]) ?: return@mapNotNull null
            if (b > a) a to b else null
        }
    }

    /** Settings for ace_core (names identical to the script constants). */
    fun toPythonSettings(): JSONObject = JSONObject().apply {
        put("ACE_MODE", mode)
        put("ACE_MODEL_DIT", model)
        put("ACE_GGUF_QUANT", quant)
        put("ACE_CPP_LM", lm)
        put("ACE_STEPS", effectiveSteps())
        put("ACE_GUIDANCE", guidance ?: JSONObject.NULL)
        put("ACE_SEED", seed)
        put("NUM_SEGMENTS", numSections)
        put("ACE_WHOLE_TRACK", wholeTrack)
        put("ACE_NUM_PASSES", numPasses)
        put("ACE_INSTRUMENTAL", instrumental)
        put("ACE_LYRICS", if (instrumental || lyrics.isBlank()) "[Instrumental]" else lyrics)
        put("ACE_COVER_STRENGTH", coverStrength.toDouble())
        put("ACE_COVER_NOISE", coverNoise.toDouble())
        put("ACE_COVER_WHOLE_FILE", coverWholeFile)
        put("ACE_COVER_MAX_SEC", coverMaxSec?.toDouble() ?: JSONObject.NULL)
        put("ACE_COVER_FRAGMENTS", JSONArray().apply { parsedFragments().forEach { put(JSONArray().put(it.first).put(it.second)) } })
        put("ACE_COVER_FRAGMENTS_MODE", coverFragmentsMode)
        put("ACE_USE_REFERENCE", useReference)
        put("ACE_REFERENCE_MODE", referenceMode)
        put("ACE_REFERENCE_LEN_SEC", referenceLenSec.toDouble())
        put("ACE_LOW_RAM", true)                       // analysis never runs in parallel with the model on a phone
        put("STEM_SEPARATION", stemAnalysis)
        put("EXPORT_STEMS", exportStems && stemAnalysis)
        put("STEMS_ALL_FORMATS", false)
        put("EXPORT_NOTATION", exportNotation)
        put("EXPORT_SAMPLES", exportSamples)
        put("EXPORT_USED_SOUNDS", exportUsedSounds)
        put("CHANNEL_FORMATS", JSONArray(channelFormats()))
        put("WAV_SUBTYPE", "PCM_16")
    }

    fun toJson(): JSONObject = JSONObject().apply {
        put("mode", mode); put("model", model); put("quant", quant); put("lm", lm)
        put("steps", steps ?: JSONObject.NULL); put("guidance", guidance?.toDouble() ?: JSONObject.NULL)
        put("seed", seed); put("numSections", numSections); put("wholeTrack", wholeTrack); put("numPasses", numPasses)
        put("prompt", prompt); put("instrumental", instrumental); put("lyrics", lyrics)
        put("coverStrength", coverStrength.toDouble()); put("coverNoise", coverNoise.toDouble())
        put("coverWholeFile", coverWholeFile); put("coverMaxSec", coverMaxSec?.toDouble() ?: JSONObject.NULL)
        put("coverFragments", coverFragments); put("coverFragmentsMode", coverFragmentsMode)
        put("useReference", useReference); put("referenceMode", referenceMode); put("referenceLenSec", referenceLenSec.toDouble())
        put("stemAnalysis", stemAnalysis); put("exportNotation", exportNotation); put("exportSamples", exportSamples)
        put("exportUsedSounds", exportUsedSounds); put("exportStems", exportStems)
        put("formatMono", formatMono); put("formatStereo", formatStereo); put("formatSurround", formatSurround)
        put("ramAuto", ramAuto); put("ramLimitMb", ramLimitMb); put("threads", threads); put("cpuMaxPercent", cpuMaxPercent)
        put("coreSet", coreSet.name); put("priority", priority.name); put("thermalProtection", thermalProtection)
        put("thermalPauseLevel", thermalPauseLevel); put("wifiOnly", wifiOnly)
        put("outputFolders", JSONObject(outputFolders as Map<*, *>))
        put("modelsLocation", modelsLocation)
        put("diagLogs", diagLogs); put("dumpType", dumpType.name); put("dumpOnError", dumpOnError)
        put("dumpOnUnexpectedEnd", dumpOnUnexpectedEnd); put("dumpOnPause", dumpOnPause); put("dumpKeep", dumpKeep)
    }

    companion object {
        fun fromJson(o: JSONObject): AppSettings {
            val d = AppSettings()
            fun optIntOrNull(k: String): Int? = if (o.isNull(k) || !o.has(k)) null else o.optInt(k)
            fun optFloatOrNull(k: String): Float? = if (o.isNull(k) || !o.has(k)) null else o.optDouble(k).toFloat()
            return AppSettings(
                mode = o.optString("mode", d.mode), model = o.optString("model", d.model), quant = o.optString("quant", d.quant),
                lm = o.optString("lm", d.lm), steps = optIntOrNull("steps"), guidance = optFloatOrNull("guidance"),
                seed = o.optInt("seed", d.seed), numSections = o.optInt("numSections", d.numSections),
                wholeTrack = o.optBoolean("wholeTrack", d.wholeTrack), numPasses = o.optInt("numPasses", d.numPasses),
                prompt = o.optString("prompt", d.prompt), instrumental = o.optBoolean("instrumental", d.instrumental),
                lyrics = o.optString("lyrics", d.lyrics),
                coverStrength = o.optDouble("coverStrength", d.coverStrength.toDouble()).toFloat(),
                coverNoise = o.optDouble("coverNoise", d.coverNoise.toDouble()).toFloat(),
                coverWholeFile = o.optBoolean("coverWholeFile", d.coverWholeFile), coverMaxSec = optFloatOrNull("coverMaxSec"),
                coverFragments = o.optString("coverFragments", d.coverFragments),
                coverFragmentsMode = o.optString("coverFragmentsMode", d.coverFragmentsMode),
                useReference = o.optBoolean("useReference", d.useReference), referenceMode = o.optString("referenceMode", d.referenceMode),
                referenceLenSec = o.optDouble("referenceLenSec", d.referenceLenSec.toDouble()).toFloat(),
                stemAnalysis = o.optBoolean("stemAnalysis", d.stemAnalysis), exportNotation = o.optBoolean("exportNotation", d.exportNotation),
                exportSamples = o.optBoolean("exportSamples", d.exportSamples), exportUsedSounds = o.optBoolean("exportUsedSounds", d.exportUsedSounds),
                exportStems = o.optBoolean("exportStems", d.exportStems), formatMono = o.optBoolean("formatMono", d.formatMono),
                formatStereo = o.optBoolean("formatStereo", d.formatStereo), formatSurround = o.optBoolean("formatSurround", d.formatSurround),
                ramAuto = o.optBoolean("ramAuto", d.ramAuto), ramLimitMb = o.optInt("ramLimitMb", d.ramLimitMb),
                threads = o.optInt("threads", d.threads), cpuMaxPercent = o.optInt("cpuMaxPercent", d.cpuMaxPercent),
                coreSet = runCatching { CoreSet.valueOf(o.optString("coreSet", d.coreSet.name)) }.getOrDefault(d.coreSet),
                priority = runCatching { Priority.valueOf(o.getString("priority")) }.getOrElse {
                    // settings saved by version 1.0 had a single "low priority" switch
                    if (o.optBoolean("lowPriority", true)) Priority.BELOW_NORMAL else Priority.NORMAL
                }, thermalProtection = o.optBoolean("thermalProtection", d.thermalProtection),
                thermalPauseLevel = o.optInt("thermalPauseLevel", d.thermalPauseLevel), wifiOnly = o.optBoolean("wifiOnly", d.wifiOnly),
                outputFolders = o.optJSONObject("outputFolders")?.let { f -> f.keys().asSequence().associateWith { f.getString(it) } } ?: emptyMap(),
                modelsLocation = o.optString("modelsLocation", d.modelsLocation),
                diagLogs = o.optBoolean("diagLogs", d.diagLogs),
                dumpType = runCatching { DumpType.valueOf(o.optString("dumpType", d.dumpType.name)) }.getOrDefault(d.dumpType),
                dumpOnError = o.optBoolean("dumpOnError", d.dumpOnError),
                dumpOnUnexpectedEnd = o.optBoolean("dumpOnUnexpectedEnd", d.dumpOnUnexpectedEnd),
                dumpOnPause = o.optBoolean("dumpOnPause", d.dumpOnPause),
                dumpKeep = o.optInt("dumpKeep", d.dumpKeep).coerceIn(1, 50),
            )
        }
    }
}

/** Persists the settings in SharedPreferences (backed up; models and files are excluded from backup). */
class SettingsStore(context: Context) {
    private val prefs = context.getSharedPreferences("settings", Context.MODE_PRIVATE)
    private val _state = MutableStateFlow(load())
    val state: StateFlow<AppSettings> = _state

    private fun load(): AppSettings = prefs.getString("json", null)?.let {
        runCatching { AppSettings.fromJson(JSONObject(it)) }.getOrNull()
    } ?: AppSettings()

    fun update(transform: (AppSettings) -> AppSettings) {
        val next = transform(_state.value)
        _state.value = next
        prefs.edit().putString("json", next.toJson().toString()).apply()
    }
}
