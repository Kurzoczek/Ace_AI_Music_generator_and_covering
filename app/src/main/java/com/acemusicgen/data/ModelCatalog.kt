package com.acemusicgen.data

import org.json.JSONArray
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/** One GGUF file of the model repository. sizeBytes is exact when [exact] (read from the Hugging Face API). */
data class ModelFile(
    val name: String,
    val role: String,               // "dit" | "text_encoder" | "vae" | "lm"
    val sizeBytes: Long,
    val exact: Boolean,
    val sha256: String? = null,
)

/**
 * The models come from ONE place: the public Hugging Face repository Serveurperso/ACE-Step-1.5-GGUF
 * (GGUF conversions of ACE-Step 1.5 for acestep.cpp, MIT license), downloaded over HTTPS from huggingface.co
 * and its download CDN (Hugging Face redirects the file requests to its storage servers).
 */
object ModelCatalog {
    const val REPO = "Serveurperso/ACE-Step-1.5-GGUF"
    const val HOST = "huggingface.co"
    const val SOURCE_DESCRIPTION = "https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF"
    private const val RESOLVE = "https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF/resolve/main/"
    private const val API_TREE = "https://huggingface.co/api/models/Serveurperso/ACE-Step-1.5-GGUF/tree/main"

    val DIT_MODELS = listOf("acestep-v15-turbo", "acestep-v15-sft", "acestep-v15-base",
        "acestep-v15-xl-turbo", "acestep-v15-xl-sft", "acestep-v15-xl-base")
    val QUANTS = listOf("Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "BF16")
    val LMS = listOf("", "0.6B", "1.7B", "4B")

    private const val GB = 1_000_000_000L
    private const val MB = 1_000_000L

    /** Approximate sizes used until the exact sizes are read from the server (values from the repository listing). */
    private val DIT_APPROX = mapOf(
        "Q8_0" to (2_400 * MB to 5_000 * MB), "Q6_K" to (1_900 * MB to 3_900 * MB), "Q5_K_M" to (1_600 * MB to 3_300 * MB),
        "Q4_K_M" to (1_450 * MB to 2_800 * MB), "BF16" to (4_500 * MB to 9_300 * MB))
    private val LM_APPROX = mapOf("0.6B" to 700 * MB, "1.7B" to 1_900 * MB, "4B" to 4_200 * MB)
    private val LM4B_APPROX = mapOf("Q8_0" to 4_200 * MB, "Q6_K" to 3_300 * MB, "Q5_K_M" to 3_030 * MB, "BF16" to 8_000 * MB)
    private const val VAE_APPROX = 337 * MB
    private const val TE_Q8_APPROX = 784 * MB
    private const val TE_BF16_APPROX = 1_200 * MB

    @Volatile private var remote: Map<String, Pair<Long, String?>> = emptyMap()
    val hasExactSizes: Boolean get() = remote.isNotEmpty()

    fun url(file: String) = RESOLVE + file

    fun ditFile(model: String, quant: String) = "$model-$quant.gguf"
    fun textEncoderFile(quant: String) = "Qwen3-Embedding-0.6B-${if (quant == "BF16") "BF16" else "Q8_0"}.gguf"
    const val VAE_FILE = "vae-BF16.gguf"

    /** Same rule as gguf_lm_name() in the Python scripts. */
    fun lmFile(size: String, quant: String): String? = when (size) {
        "" -> null
        "4B" -> "acestep-5Hz-lm-4B-${if (quant in listOf("Q8_0", "Q6_K", "Q5_K_M", "BF16")) quant else "Q5_K_M"}.gguf"
        else -> "acestep-5Hz-lm-$size-${if (quant == "BF16") "BF16" else "Q8_0"}.gguf"
    }

    private fun approx(name: String): Long = when {
        name == VAE_FILE -> VAE_APPROX
        name.startsWith("Qwen3-Embedding") -> if ("BF16" in name) TE_BF16_APPROX else TE_Q8_APPROX
        name.startsWith("acestep-5Hz-lm-4B") -> LM4B_APPROX[name.substringAfter("4B-").removeSuffix(".gguf")] ?: 4_200 * MB
        name.startsWith("acestep-5Hz-lm-") -> {
            val size = name.removePrefix("acestep-5Hz-lm-").substringBefore("-")
            val base = LM_APPROX[size] ?: 1_000 * MB
            if (name.endsWith("BF16.gguf")) base * 2 else base
        }
        else -> {
            val quant = QUANTS.firstOrNull { name.endsWith("-$it.gguf") } ?: "Q8_0"
            val (small, xl) = DIT_APPROX.getValue(quant)
            if ("-xl-" in name) xl else small
        }
    }

    fun file(name: String, role: String): ModelFile {
        val r = remote[name]
        return if (r != null) ModelFile(name, role, r.first, true, r.second) else ModelFile(name, role, approx(name), false)
    }

    /** Files needed for the given settings (text encoder and VAE are always needed by ace-synth). */
    fun requiredFiles(s: AppSettings): List<ModelFile> = buildList {
        add(file(ditFile(s.model, s.quant), "dit"))
        add(file(textEncoderFile(s.quant), "text_encoder"))
        add(file(VAE_FILE, "vae"))
        if (s.mode == "text") lmFile(s.lm, s.quant)?.let { add(file(it, "lm")) }
    }

    /**
     * Reads the exact file sizes and SHA-256 checksums from the Hugging Face API (no download of the files).
     * Returns false when offline - the approximate sizes are used then.
     */
    fun refreshFromServer(): Boolean = try {
        val c = URL(API_TREE).openConnection() as HttpURLConnection
        c.connectTimeout = 15_000
        c.readTimeout = 30_000
        c.setRequestProperty("User-Agent", "AceMusicGen-Android")
        val body = c.inputStream.bufferedReader().use { it.readText() }
        c.disconnect()
        val arr = JSONArray(body)
        val map = HashMap<String, Pair<Long, String?>>()
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            val path = o.optString("path")
            if (!path.endsWith(".gguf")) continue
            val lfs = o.optJSONObject("lfs")
            val size = lfs?.optLong("size") ?: o.optLong("size")
            map[path] = size to lfs?.optString("oid")?.takeIf { it.length == 64 }
        }
        if (map.isNotEmpty()) remote = map
        map.isNotEmpty()
    } catch (e: Exception) {
        false
    }

    fun isDownloaded(dir: File, f: ModelFile): Boolean {
        val file = File(dir, f.name)
        return file.isFile && (!f.exact || file.length() == f.sizeBytes)
    }
}
