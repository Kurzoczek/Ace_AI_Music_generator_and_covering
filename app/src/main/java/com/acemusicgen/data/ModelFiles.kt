package com.acemusicgen.data

import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream
import java.security.MessageDigest

/**
 * Plain-file helpers for the model folder (no Android APIs, so they are unit-testable on a desktop JVM):
 * listing, moving between storage locations, and copying an imported file in with verification.
 */
object ModelFiles {
    /** Space kept free on the target so the phone does not run completely out of storage. */
    const val RESERVE_BYTES = 200_000_000L
    private const val BUF = 1 shl 20

    class Cancelled : IOException("cancelled")

    /** Model files (finished .gguf and partial .gguf.part downloads) in [dir]. */
    fun list(dir: File): List<File> =
        dir.listFiles()?.filter { it.isFile && (it.name.endsWith(".gguf") || it.name.endsWith(".gguf.part")) }?.sortedBy { it.name }
            ?: emptyList()

    fun totalBytes(dir: File): Long = list(dir).sumOf { it.length() }

    /** Bytes that must be copied to move [from] into [to] (files already present there with the same size are skipped). */
    fun bytesToMove(from: File, to: File): Long = list(from).filter { f ->
        val t = File(to, f.name)
        !(t.isFile && t.length() == f.length())
    }.sumOf { it.length() }

    /**
     * Moves every model file from [from] to [to]. Same-filesystem moves are instant renames; otherwise each file is
     * copied to "<name>.moving", flushed, renamed into place and only then deleted from the source, so an interruption
     * never loses a model. [freeBytes] reports free space of the target.
     */
    fun move(
        from: File, to: File, freeBytes: (File) -> Long,
        isCancelled: () -> Boolean = { false }, onProgress: (done: Long, total: Long, name: String) -> Unit = { _, _, _ -> },
    ) {
        if (from.canonicalPath == to.canonicalPath) return
        to.mkdirs()
        val total = bytesToMove(from, to)
        if (total > 0 && total + RESERVE_BYTES > freeBytes(to)) throw NotEnoughSpace(total + RESERVE_BYTES, freeBytes(to))
        var done = 0L
        for (f in list(from)) {
            if (isCancelled()) throw Cancelled()
            val target = File(to, f.name)
            if (target.isFile && target.length() == f.length()) { f.delete(); continue }
            if (f.renameTo(target)) { done += target.length(); onProgress(done, total, f.name); continue }
            val tmp = File(to, f.name + ".moving")
            val base = done
            FileInputStream(f).use { input ->
                copy(input, tmp, isCancelled) { n -> onProgress(base + n, total, f.name) }
            }
            if (tmp.length() != f.length()) { tmp.delete(); throw IOException("copy of ${f.name} is incomplete") }
            target.delete()
            if (!tmp.renameTo(target)) { tmp.delete(); throw IOException("cannot rename ${tmp.name}") }
            done += f.length()
            f.delete()
        }
        from.listFiles()?.filter { it.name.endsWith(".moving") }?.forEach { it.delete() }
    }

    /**
     * Copies an imported model ([input], named [name]) into [dir]. When the expected size / SHA-256 are known (from the
     * Hugging Face file list) the copy is verified and rejected on mismatch. Returns the final file.
     */
    fun importStream(
        input: InputStream, name: String, dir: File, expectedSize: Long?, expectedSha: String?,
        isCancelled: () -> Boolean = { false }, onProgress: (Long) -> Unit = {},
    ): File {
        require(name.endsWith(".gguf") && '/' !in name && '\\' !in name && !name.startsWith(".")) { "not a model file: $name" }
        dir.mkdirs()
        val tmp = File(dir, "$name.importing")
        val digest = if (expectedSha != null) MessageDigest.getInstance("SHA-256") else null
        input.use { copy(it, tmp, isCancelled, digest, onProgress) }
        if (expectedSize != null && tmp.length() != expectedSize) {
            val got = tmp.length(); tmp.delete()
            throw IOException("$name: size $got B, expected $expectedSize B - the file is incomplete or a different version")
        }
        if (digest != null && expectedSha != null) {
            val sha = digest.digest().joinToString("") { "%02x".format(it) }
            if (!sha.equals(expectedSha, ignoreCase = true)) { tmp.delete(); throw IOException("$name: checksum mismatch - the file is damaged") }
        }
        val target = File(dir, name)
        target.delete()
        File(dir, "$name.part").delete()
        if (!tmp.renameTo(target)) { tmp.delete(); throw IOException("cannot rename ${tmp.name}") }
        return target
    }

    /** Removes leftovers of interrupted moves/imports. */
    fun cleanTemp(dir: File) {
        dir.listFiles()?.filter { it.name.endsWith(".moving") || it.name.endsWith(".importing") }?.forEach { it.delete() }
    }

    private fun copy(input: InputStream, out: File, isCancelled: () -> Boolean, digest: MessageDigest? = null, onProgress: (Long) -> Unit) {
        try {
            FileOutputStream(out).use { o ->
                val buf = ByteArray(BUF)
                var n = 0L
                var lastReport = 0L
                while (true) {
                    if (isCancelled()) throw Cancelled()
                    val r = input.read(buf)
                    if (r < 0) break
                    o.write(buf, 0, r)
                    digest?.update(buf, 0, r)
                    n += r
                    if (n - lastReport >= 8 * BUF) { onProgress(n); lastReport = n }
                }
                o.fd.sync()
                onProgress(n)
            }
        } catch (e: Exception) {
            out.delete()
            throw e
        }
    }

    class NotEnoughSpace(val needed: Long, val free: Long) : IOException("not enough space: need $needed B, free $free B")
}
