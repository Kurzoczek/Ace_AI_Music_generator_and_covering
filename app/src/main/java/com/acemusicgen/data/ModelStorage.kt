package com.acemusicgen.data

import android.content.Context
import android.os.Environment
import android.os.storage.StorageManager
import java.io.File

/** Where model files can live. Only the app's own folders: the native engine needs real file paths, and those are
 *  the only places an app may use directly without the broad "all files access" permission. */
enum class ModelPlace { APP_PRIVATE, PHONE, SD_CARD }

data class ModelLocation(
    val id: String,          // "app", "phone" or "sd:<volume uuid>"
    val place: ModelPlace,
    val dir: File,
    val name: String,        // volume description for SD cards (e.g. "SanDisk SD card"), empty otherwise
    val free: Long,
    val total: Long,
)

object ModelStorage {
    const val APP = "app"
    const val PHONE = "phone"
    const val DEFAULT = PHONE
    private const val SD_PREFIX = "sd:"

    /** All locations usable right now (an SD card appears only while it is inserted and mounted). */
    fun locations(context: Context): List<ModelLocation> {
        val sm = context.getSystemService(StorageManager::class.java)!!
        val out = ArrayList<ModelLocation>()
        fun add(id: String, place: ModelPlace, base: File, name: String) {
            val dir = File(base, "models")
            val probe = if (base.exists()) base else context.filesDir
            out += ModelLocation(id, place, dir, name, probe.usableSpace, probe.totalSpace)
        }
        add(APP, ModelPlace.APP_PRIVATE, context.filesDir, "")
        val ext = context.getExternalFilesDirs(null)
        ext.getOrNull(0)?.let { if (Environment.getExternalStorageState(it) == Environment.MEDIA_MOUNTED) add(PHONE, ModelPlace.PHONE, it, "") }
        ext.drop(1).filterNotNull().forEach { dir ->
            if (Environment.getExternalStorageState(dir) != Environment.MEDIA_MOUNTED) return@forEach
            val vol = sm.getStorageVolume(dir) ?: return@forEach
            if (!vol.isRemovable) return@forEach
            val uuid = vol.uuid ?: return@forEach
            add(SD_PREFIX + uuid, ModelPlace.SD_CARD, dir, vol.getDescription(context) ?: "")
        }
        return out
    }

    /** The folder for [id], or null when it is not available now (SD card removed, settings restored on another phone). */
    fun dirFor(context: Context, id: String): File? = locations(context).firstOrNull { it.id == id }?.dir

    /** Folder that the current settings point to; throws a readable error when that storage is missing. */
    fun current(context: Context, s: AppSettings): File =
        dirFor(context, s.modelsLocation) ?: throw MissingStorage(s.modelsLocation)

    fun isSd(id: String) = id.startsWith(SD_PREFIX)

    class MissingStorage(val id: String) : IllegalStateException(
        if (id.startsWith(SD_PREFIX)) "The SD card chosen for the models is not available. Insert it or choose another location on the Models tab."
        else "The model location '$id' is not available. Choose another location on the Models tab."
    )
}
