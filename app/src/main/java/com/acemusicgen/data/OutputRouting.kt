package com.acemusicgen.data

/**
 * Where every kind of result goes. Pure Kotlin (no Android types) so it can be unit-tested.
 *
 * Default locations (MediaStore, no permission needed):
 *   audio  -> Music/ACE_music_gen/<track session>/<subfolder>
 *   others -> Download/ACE_music_gen/<track session>/<subfolder>
 * A custom folder picked by the user (Storage Access Framework) replaces the default for that category;
 * files then go to <picked folder>/<track session>/.
 */
enum class OutputCategory(val key: String, val subdir: String, val audio: Boolean) {
    FINAL("final", "final", true),
    PARTS("parts", "parts", true),
    SAMPLES("samples", "samples", true),
    STEMS("stems", "stems", true),
    USED_SOUNDS("used_sounds", "used_sounds", true),
    MIDI("midi", "midi", false),
    NOTATION("notation", "notation", false),
    METADATA("metadata", "", false),
}

object OutputRouting {
    const val FOLDER = "ACE_music_gen"
    const val MUSIC_DIR = "Music"          // = Environment.DIRECTORY_MUSIC
    const val DOWNLOAD_DIR = "Download"    // = Environment.DIRECTORY_DOWNLOADS

    /** Category of a result file from its path relative to the session folder, e.g. "final/track_mono.wav". */
    fun categoryOf(relativePath: String): OutputCategory {
        val parts = relativePath.replace('\\', '/').trim('/').split('/')
        if (parts.size == 1) return OutputCategory.METADATA
        return OutputCategory.entries.firstOrNull { it.subdir.isNotEmpty() && it.subdir == parts[0] } ?: OutputCategory.METADATA
    }

    /** MediaStore RELATIVE_PATH of the default location. */
    fun defaultRelativeDir(cat: OutputCategory, session: String): String =
        "${if (cat.audio) MUSIC_DIR else DOWNLOAD_DIR}/$FOLDER/$session" + if (cat.subdir.isNotEmpty()) "/${cat.subdir}" else ""

    /** Default location as shown to the user (session name replaced by a placeholder). */
    fun defaultDisplay(cat: OutputCategory, sessionPlaceholder: String): String = defaultRelativeDir(cat, sessionPlaceholder)

    /** Folders to create inside a user-picked folder: <session>, plus any nested folders below the category folder. */
    fun customSegments(relativePath: String, session: String): List<String> {
        val parts = relativePath.replace('\\', '/').trim('/').split('/')
        val inner = if (parts.size > 2) parts.subList(1, parts.size - 1) else emptyList()
        return listOf(session) + inner
    }

    /** "primary:Music/Beats" -> "Music/Beats"; "1A2B-3C4D:Songs" -> "SD card 1A2B-3C4D/Songs"; "primary:" -> "/". */
    fun describeTreeDocumentId(docId: String): String {
        val volume = docId.substringBefore(':', "")
        val path = docId.substringAfter(':', docId)
        return when {
            volume == "primary" || volume.isEmpty() -> path.ifEmpty { "/" }
            else -> "SD card $volume" + if (path.isNotEmpty()) "/$path" else ""
        }
    }

    /** MIME type that keeps the file name unchanged in every document provider. */
    fun mimeOf(fileName: String): String = when (fileName.substringAfterLast('.', "").lowercase()) {
        "wav" -> "audio/x-wav"
        "mid", "midi" -> "audio/midi"
        "json" -> "application/json"
        "txt" -> "text/plain"
        else -> "application/octet-stream"          // .musicxml, .ly - unknown types would get an extra extension
    }
}
