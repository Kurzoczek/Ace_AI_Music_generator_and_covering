package com.acemusicgen.diag

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import android.provider.MediaStore
import com.acemusicgen.R
import com.acemusicgen.audio.ResultExporter
import com.acemusicgen.data.OutputRouting
import java.io.File
import java.io.IOException

/** The two diagnostic folders. The user can point each of them to any folder (system folder picker). */
enum class DiagFolder(val key: String, val nameRes: Int) {
    LOGS("diag_logs", R.string.diag_folder_logs),       // "app logs" / "logi aplikacji"
    DUMPS("diag_dumps", R.string.diag_folder_dumps),    // "state dumps" / "zrzuty stanu"
}

/**
 * Writes diagnostic files (logs, dumps) to the folder the user picked, or by default to
 * Download/ACE_music_gen/<folder name>/ through MediaStore - no storage permission in both cases.
 * Files with the same name are overwritten, so a growing log can be copied again and again.
 */
object DiagExport {

    fun defaultRelDir(ctx: Context, folder: DiagFolder) =
        "${OutputRouting.DOWNLOAD_DIR}/${OutputRouting.FOLDER}/${ctx.getString(folder.nameRes)}"

    /** Picked folder for [folder] if it is still writable, otherwise null (= default location). */
    private fun tree(ctx: Context, folders: Map<String, String>, folder: DiagFolder): Uri? =
        folders[folder.key]?.takeIf { ResultExporter.hasWriteAccess(ctx, it) }?.let(Uri::parse)

    /** Human readable target, e.g. "Download/ACE_music_gen/app logs" or "SD card 1A2B-3C4D/Logs". */
    fun describe(ctx: Context, folders: Map<String, String>, folder: DiagFolder): String =
        tree(ctx, folders, folder)?.let { ResultExporter.describeTree(it) } ?: defaultRelDir(ctx, folder)

    /** Copies [src] as [name] into the folder, replacing an older file of that name. Returns a description. */
    fun put(ctx: Context, folders: Map<String, String>, folder: DiagFolder, src: File, name: String = src.name): String {
        val resolver = ctx.contentResolver
        val mime = OutputRouting.mimeOf(name)
        val treeUri = tree(ctx, folders, folder)
        if (treeUri != null) {
            val dir = ResultExporter.treeDir(resolver, treeUri, emptyList(), HashMap())
            val existing = findChild(ctx, treeUri, dir, name)
            val target = existing ?: DocumentsContract.createDocument(resolver, dir, mime, name)
                ?: throw IOException("cannot create $name")
            copy(ctx, src, target)
            return "${ResultExporter.describeTree(treeUri)}/$name"
        }
        val rel = defaultRelDir(ctx, folder) + "/"
        val collection = MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val existing = resolver.query(collection, arrayOf(MediaStore.MediaColumns._ID),
            "${MediaStore.MediaColumns.RELATIVE_PATH}=? AND ${MediaStore.MediaColumns.DISPLAY_NAME}=?", arrayOf(rel, name), null)
            ?.use { c -> if (c.moveToFirst()) Uri.withAppendedPath(collection, c.getLong(0).toString()) else null }
        if (existing != null) {
            copy(ctx, src, existing)
        } else {
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, name)
                put(MediaStore.MediaColumns.MIME_TYPE, mime)
                put(MediaStore.MediaColumns.RELATIVE_PATH, rel)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
            val uri = resolver.insert(collection, values) ?: throw IOException("MediaStore refused $name")
            copy(ctx, src, uri)
            resolver.update(uri, ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }, null, null)
        }
        return rel + name
    }

    /** Keeps only the newest [keep] files whose name starts with [prefix] (names contain a sortable time stamp). */
    fun prune(ctx: Context, folders: Map<String, String>, folder: DiagFolder, prefix: String, keep: Int) {
        val resolver = ctx.contentResolver
        val treeUri = tree(ctx, folders, folder)
        if (treeUri != null) {
            val dir = ResultExporter.treeDir(resolver, treeUri, emptyList(), HashMap())
            val children = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, DocumentsContract.getDocumentId(dir))
            val files = ArrayList<Pair<String, Uri>>()
            resolver.query(children, arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME),
                null, null, null)?.use { c ->
                while (c.moveToNext()) {
                    val n = c.getString(1) ?: continue
                    if (n.startsWith(prefix)) files += n to DocumentsContract.buildDocumentUriUsingTree(treeUri, c.getString(0))
                }
            }
            files.sortedByDescending { it.first }.drop(keep).forEach { runCatching { DocumentsContract.deleteDocument(resolver, it.second) } }
            return
        }
        val collection = MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val rows = ArrayList<Pair<String, Long>>()
        resolver.query(collection, arrayOf(MediaStore.MediaColumns._ID, MediaStore.MediaColumns.DISPLAY_NAME),
            "${MediaStore.MediaColumns.RELATIVE_PATH}=?", arrayOf(defaultRelDir(ctx, folder) + "/"), null)?.use { c ->
            while (c.moveToNext()) {
                val n = c.getString(1) ?: continue
                if (n.startsWith(prefix)) rows += n to c.getLong(0)
            }
        }
        rows.sortedByDescending { it.first }.drop(keep).forEach {
            runCatching { resolver.delete(Uri.withAppendedPath(collection, it.second.toString()), null, null) }
        }
    }

    private fun findChild(ctx: Context, treeUri: Uri, dir: Uri, name: String): Uri? {
        val children = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, DocumentsContract.getDocumentId(dir))
        ctx.contentResolver.query(children, arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME),
            null, null, null)?.use { c ->
            while (c.moveToNext()) if (c.getString(1) == name) return DocumentsContract.buildDocumentUriUsingTree(treeUri, c.getString(0))
        }
        return null
    }

    private fun copy(ctx: Context, src: File, target: Uri) {
        (ctx.contentResolver.openOutputStream(target, "wt") ?: throw IOException("cannot write $target")).use { out ->
            src.inputStream().use { it.copyTo(out, 1 shl 16) }
        }
    }
}
