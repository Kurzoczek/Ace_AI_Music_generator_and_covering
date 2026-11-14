package com.acemusicgen.data

import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * Downloads GGUF model files over HTTPS with resume (.part files) and SHA-256 verification
 * (checksums published by Hugging Face for every file). Only data files are downloaded - never code.
 */
class ModelDownloader(private val modelsDir: File) {

    class CancelledException : IOException("cancelled")

    fun download(
        file: ModelFile,
        isCancelled: () -> Boolean,
        onProgress: (done: Long, total: Long) -> Unit,
    ) {
        modelsDir.mkdirs()
        val target = File(modelsDir, file.name)
        if (ModelCatalog.isDownloaded(modelsDir, file)) return
        val part = File(modelsDir, file.name + ".part")
        var attempt = 0
        while (true) {
            attempt++
            try {
                fetch(file, part, isCancelled, onProgress)
                break
            } catch (e: CancelledException) {
                throw e
            } catch (e: IOException) {
                if (attempt >= 8) throw IOException("download of ${file.name} failed: ${e.message}", e)
                Thread.sleep(minOf(60_000L, 2_000L * attempt * attempt))
            }
        }
        file.sha256?.let { expected ->
            val actual = sha256(part)
            if (!actual.equals(expected, ignoreCase = true)) {
                part.delete()
                throw IOException("checksum mismatch for ${file.name} - the file was deleted, please try again")
            }
        }
        if (target.exists()) target.delete()
        if (!part.renameTo(target)) throw IOException("cannot rename ${part.name}")
    }

    private fun fetch(file: ModelFile, part: File, isCancelled: () -> Boolean, onProgress: (Long, Long) -> Unit) {
        var start = if (part.exists()) part.length() else 0L
        val c = URL(ModelCatalog.url(file.name)).openConnection() as HttpURLConnection
        c.connectTimeout = 20_000
        c.readTimeout = 60_000
        c.instanceFollowRedirects = true
        c.setRequestProperty("User-Agent", "AceMusicGen-Android")
        if (start > 0) c.setRequestProperty("Range", "bytes=$start-")
        try {
            val code = c.responseCode
            if (code == 416 && file.exact && start == file.sizeBytes) return          // already complete
            if (code !in listOf(200, 206)) throw IOException("HTTP $code for ${file.name}")
            if (code == 200) start = 0L                                               // server ignored the range
            val total = if (code == 206) start + c.contentLengthLong else c.contentLengthLong
            c.inputStream.use { input ->
                FileOutputStream(part, start > 0).use { out ->
                    val buf = ByteArray(256 * 1024)
                    var done = start
                    var lastReport = 0L
                    while (true) {
                        if (isCancelled()) throw CancelledException()
                        val n = input.read(buf)
                        if (n < 0) break
                        out.write(buf, 0, n)
                        done += n
                        val now = System.currentTimeMillis()
                        if (now - lastReport > 500) {
                            lastReport = now
                            onProgress(done, total)
                        }
                    }
                    onProgress(done, total)
                    if (total > 0 && done < total) throw IOException("connection closed early")
                }
            }
        } finally {
            c.disconnect()
        }
    }

    private fun sha256(f: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        FileInputStream(f).use { input ->
            val buf = ByteArray(1024 * 1024)
            while (true) {
                val n = input.read(buf)
                if (n < 0) break
                md.update(buf, 0, n)
            }
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }
}
