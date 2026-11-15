package com.acemusicgen.data

import android.content.Context
import android.net.Uri
import com.acemusicgen.engine.InputTrack
import com.acemusicgen.engine.JobRequest
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Keeps the picked tracks and the running job on disk, so nothing is lost when Android kills the app process
 * (low memory, overheating, battery saving, the app frozen in the background...). Before, the lists lived only in
 * memory and were gone after such a kill. The read permission of each track is persisted by the system picker.
 */
object SessionStore {
    private const val FILE = "session.json"

    data class Interrupted(
        val request: JobRequest,
        val startedAt: Long,
        val lastStatus: String,
    )

    private fun file(ctx: Context) = File(ctx.filesDir, FILE)

    @Synchronized
    private fun read(ctx: Context): JSONObject =
        runCatching { JSONObject(file(ctx).readText()) }.getOrElse { JSONObject() }

    @Synchronized
    private fun write(ctx: Context, o: JSONObject) {
        val f = file(ctx)
        val tmp = File(f.path + ".tmp")
        tmp.writeText(o.toString())
        if (!tmp.renameTo(f)) { f.delete(); tmp.renameTo(f) }
    }

    private fun tracksToJson(list: List<InputTrack>) = JSONArray().apply {
        list.forEach { put(JSONObject().put("uri", it.uri.toString()).put("name", it.name).put("dur", it.durationSec)) }
    }

    private fun tracksFromJson(a: JSONArray?): List<InputTrack> {
        if (a == null) return emptyList()
        return (0 until a.length()).mapNotNull { i ->
            val o = a.optJSONObject(i) ?: return@mapNotNull null
            InputTrack(Uri.parse(o.getString("uri")), o.optString("name", "track"), o.optDouble("dur", 0.0))
        }
    }

    // ---------- picked tracks (Generate screen)
    fun saveLists(ctx: Context, inputs: List<InputTrack>, templates: List<InputTrack>) {
        val o = read(ctx)
        o.put("inputs", tracksToJson(inputs)).put("templates", tracksToJson(templates))
        write(ctx, o)
    }

    fun loadInputs(ctx: Context): List<InputTrack> = tracksFromJson(read(ctx).optJSONArray("inputs"))
    fun loadTemplates(ctx: Context): List<InputTrack> = tracksFromJson(read(ctx).optJSONArray("templates"))

    // ---------- running job
    fun markRunning(ctx: Context, r: JobRequest) {
        val o = read(ctx)
        o.put("job", JSONObject()
            .put("inputs", tracksToJson(r.inputs))
            .put("templates", tracksToJson(r.templates))
            .put("settings", r.settings.toJson())
            .put("confirmed", r.confirmedDownloadBytes)
            .put("startedAt", System.currentTimeMillis())
            .put("status", ""))
        write(ctx, o)
    }

    /** Last known status line, so the "interrupted" card can say where the job was. Cheap, called rarely. */
    fun updateStatus(ctx: Context, status: String) {
        val o = read(ctx)
        val job = o.optJSONObject("job") ?: return
        job.put("status", status).put("statusAt", System.currentTimeMillis())
        write(ctx, o)
    }

    /** The job ended in a way the app saw (done, failed, stopped, time limit) - nothing to resume. */
    fun markEnded(ctx: Context) {
        val o = read(ctx)
        o.remove("job")
        write(ctx, o)
    }

    /** A job that was running when the process died, or null. */
    fun interrupted(ctx: Context): Interrupted? {
        val job = read(ctx).optJSONObject("job") ?: return null
        return runCatching {
            Interrupted(
                JobRequest(tracksFromJson(job.optJSONArray("inputs")), tracksFromJson(job.optJSONArray("templates")),
                    AppSettings.fromJson(job.getJSONObject("settings")), job.optLong("confirmed", 0)),
                job.optLong("startedAt", 0), job.optString("status", ""),
            )
        }.getOrNull()
    }
}
