package com.acemusicgen.audio

import android.content.ContentResolver
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import android.provider.MediaStore
import com.acemusicgen.data.OutputCategory
import com.acemusicgen.data.OutputRouting
import java.io.File
import java.io.IOException

/**
 * Publishes the results. For every category of files (final track, parts, samples, stems, used slices, MIDI,
 * notation, metadata) either:
 *   - the default location through MediaStore (no permission needed on Android 10+):
 *       audio -> Music/ACE_music_gen/<session>/<subfolder>, others -> Download/ACE_music_gen/<session>/<subfolder>
 *   - or a folder the user picked in Settings (Storage Access Framework, persisted permission): <folder>/<session>/
 * If a picked folder is no longer accessible (deleted, card removed, permission revoked), the default is used
 * and this is reported, so no result is ever lost. App-private copies are deleted afterwards.
 */
object ResultExporter {

    data class Exported(val locations: List<String>, val fallbacks: List<String>)

    fun export(context: Context, root: File, session: String, folders: Map<String, String>, deleteAfter: Boolean = true): Exported {
        val resolver = context.contentResolver
        val usable = folders.filterValues { hasWriteAccess(context, it) }
        val fallbacks = (folders.keys - usable.keys).toMutableList()
        val locations = linkedSetOf<String>()
        val dirCache = HashMap<String, Uri>()
        root.walkTopDown().filter { it.isFile }.sortedBy { it.path }.forEach { f ->
            val rel = f.relativeTo(root).path
            val cat = OutputRouting.categoryOf(rel)
            val tree = usable[cat.key]
            var written = false
            if (tree != null) {
                try {
                    val treeUri = Uri.parse(tree)
                    val dir = treeDir(resolver, treeUri, OutputRouting.customSegments(rel, session), dirCache)
                    val doc = DocumentsContract.createDocument(resolver, dir, OutputRouting.mimeOf(f.name), f.name)
                        ?: throw IOException("cannot create ${f.name}")
                    copy(resolver, f, doc)
                    locations += describeTree(treeUri) + "/" + OutputRouting.customSegments(rel, session).joinToString("/")
                    written = true
                } catch (e: Exception) {
                    if (cat.key !in fallbacks) fallbacks += cat.key
                }
            }
            if (!written) {
                val relDir = OutputRouting.defaultRelativeDir(cat, session)
                insertMediaStore(resolver, f, relDir, cat)
                locations += relDir.substringBeforeLast("/$session") + "/$session"
            }
        }
        if (deleteAfter) root.deleteRecursively()
        return Exported(locations.toList(), fallbacks)
    }

    fun hasWriteAccess(context: Context, treeUri: String): Boolean =
        context.contentResolver.persistedUriPermissions.any { it.uri.toString() == treeUri && it.isWritePermission }

    /** Human readable name of a picked folder, e.g. "Music/Beats" or "SD card 1A2B-3C4D/Songs". */
    fun describeTree(treeUri: Uri): String =
        runCatching { OutputRouting.describeTreeDocumentId(DocumentsContract.getTreeDocumentId(treeUri)) }.getOrDefault(treeUri.toString())

    fun takePermission(context: Context, uri: Uri) {
        context.contentResolver.takePersistableUriPermission(uri,
            Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
    }

    fun releasePermission(context: Context, treeUri: String) {
        runCatching {
            context.contentResolver.releasePersistableUriPermission(Uri.parse(treeUri),
                Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        }
    }

    private fun treeDir(resolver: ContentResolver, treeUri: Uri, segments: List<String>, cache: HashMap<String, Uri>): Uri {
        var dir = DocumentsContract.buildDocumentUriUsingTree(treeUri, DocumentsContract.getTreeDocumentId(treeUri))
        var key = treeUri.toString()
        for (seg in segments) {
            key += "/$seg"
            dir = cache.getOrPut(key) {
                findChildDir(resolver, treeUri, dir, seg)
                    ?: DocumentsContract.createDocument(resolver, dir, DocumentsContract.Document.MIME_TYPE_DIR, seg)
                    ?: throw IOException("cannot create folder $seg")
            }
        }
        return dir
    }

    private fun findChildDir(resolver: ContentResolver, treeUri: Uri, parent: Uri, name: String): Uri? {
        val children = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, DocumentsContract.getDocumentId(parent))
        resolver.query(children, arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE), null, null, null)?.use { c ->
            while (c.moveToNext()) {
                if (c.getString(1) == name && c.getString(2) == DocumentsContract.Document.MIME_TYPE_DIR) {
                    return DocumentsContract.buildDocumentUriUsingTree(treeUri, c.getString(0))
                }
            }
        }
        return null
    }

    private fun insertMediaStore(resolver: ContentResolver, f: File, relDir: String, cat: OutputCategory) {
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, f.name)
            put(MediaStore.MediaColumns.MIME_TYPE, OutputRouting.mimeOf(f.name))
            put(MediaStore.MediaColumns.RELATIVE_PATH, relDir)
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val collection = if (cat.audio) MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        else MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val uri = resolver.insert(collection, values) ?: throw IOException("MediaStore refused ${f.name}")
        copy(resolver, f, uri)
        resolver.update(uri, ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }, null, null)
    }

    private fun copy(resolver: ContentResolver, f: File, target: Uri) {
        (resolver.openOutputStream(target, "w") ?: throw IOException("cannot write $target")).use { out ->
            f.inputStream().use { it.copyTo(out, 1 shl 20) }
        }
    }
}
