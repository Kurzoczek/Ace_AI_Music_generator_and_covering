package com.acemusicgen.engine

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.acemusicgen.AceApp
import com.acemusicgen.MainActivity
import com.acemusicgen.R
import com.acemusicgen.audio.AudioDecoder
import com.acemusicgen.audio.ResultExporter
import com.acemusicgen.data.DeviceInfo
import com.acemusicgen.data.MemoryPlanner
import com.acemusicgen.data.ModelCatalog
import com.acemusicgen.data.ModelDownloader
import com.acemusicgen.data.Preflight
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

/**
 * Foreground service that does the whole job: decode inputs -> download missing models (only what the user
 * confirmed) -> generate (Python + native engine) -> save the results to Music/ and Download/.
 * Not exported; controlled only by the app's own UI and its notification actions.
 */
class GenerationService : LifecycleService() {

    companion object {
        const val ACTION_START = "com.acemusicgen.START"
        const val ACTION_STOP = "com.acemusicgen.STOP"
        const val ACTION_PAUSE = "com.acemusicgen.PAUSE"
        const val ACTION_RESUME = "com.acemusicgen.RESUME"
        private const val NOTIF_ID = 1
        private const val NOTIF_DONE_ID = 2

        fun start(context: Context) = context.startForegroundService(Intent(context, GenerationService::class.java).setAction(ACTION_START))
        fun send(context: Context, action: String) = context.startService(Intent(context, GenerationService::class.java).setAction(action))

        fun modelsDir(context: Context): File = File(context.getExternalFilesDir(null) ?: context.filesDir, "models")
        fun workDir(context: Context): File = File(context.filesDir, "work")
    }

    private var job: Job? = null
    private var governor: ResourceGovernor? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var notificationCollector = false

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        when (intent?.action) {
            ACTION_START -> startJob()
            ACTION_STOP -> {
                JobRepository.cancelRequested = true
                governor?.userPaused = false
                JobRepository.update { it.copy(status = getString(R.string.status_stopping), userPaused = false) }
            }
            ACTION_PAUSE -> {
                governor?.userPaused = true
                JobRepository.update { it.copy(userPaused = true) }
                updateNotification()
            }
            ACTION_RESUME -> {
                governor?.userPaused = false
                JobRepository.update { it.copy(userPaused = false) }
                updateNotification()
            }
        }
        return START_NOT_STICKY
    }

    private fun goForeground(processing: Boolean) {
        val type = when {
            processing && Build.VERSION.SDK_INT >= 35 -> ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROCESSING
            else -> ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
        }
        ServiceCompat.startForeground(this, NOTIF_ID, buildNotification(), type)
    }

    private fun startJob() {
        if (job?.isActive == true) return
        val request = JobRepository.pending ?: run { stopSelf(); return }
        JobRepository.reset()
        JobRepository.update { it.copy(phase = Phase.PREPARING, status = getString(R.string.status_preparing)) }
        goForeground(processing = false)
        if (!notificationCollector) {
            notificationCollector = true
            lifecycleScope.launch { JobRepository.state.collect { updateNotification() } }
        }
        job = lifecycleScope.launch(Dispatchers.IO) {
            try {
                run(request)
            } catch (e: ModelDownloader.CancelledException) {
                JobRepository.update { it.copy(phase = Phase.CANCELLED, status = getString(R.string.status_cancelled)) }
            } catch (e: Exception) {
                JobRepository.log("[ERROR] ${e.javaClass.simpleName}: ${e.message}")
                JobRepository.update { it.copy(phase = Phase.FAILED, error = e.message ?: e.javaClass.simpleName) }
            } finally {
                governor?.stop()
                wakeLock?.let { if (it.isHeld) it.release() }
                withContext(Dispatchers.Main) { finish() }
            }
        }
    }

    private suspend fun run(request: JobRequest) {
        val s = request.settings
        val models = modelsDir(this).apply { mkdirs() }
        val work = workDir(this)
        val dirs = listOf("inputs", "templates", "out", "tmp", "ckpt", "logs", "stems").associateWith { File(work, it).apply { mkdirs() } }

        // 1. decode the picked tracks (content:// URIs from the system picker) to WAV
        val inputs = JSONArray()
        request.inputs.forEachIndexed { i, t ->
            check()
            JobRepository.update { it.copy(status = getString(R.string.status_decoding, i + 1, request.inputs.size, t.name), progress = -1f) }
            val wav = File(dirs.getValue("inputs"), "in_${hash(t.uri.toString())}.wav")
            if (!wav.exists()) {
                val tmp = File(wav.path + ".tmp")
                AudioDecoder.decodeToWav(this, t.uri, tmp) { JobRepository.cancelRequested }
                tmp.renameTo(wav)
            }
            inputs.put(JSONObject().put("wav", wav.path).put("name", t.name))
        }
        val templates = JSONArray()
        request.templates.forEach { t ->
            check()
            val wav = File(dirs.getValue("templates"), "tpl_${hash(t.uri.toString())}.wav")
            if (!wav.exists()) AudioDecoder.decodeToWav(this, t.uri, wav) { JobRepository.cancelRequested }
            templates.put(wav.path)
        }

        // 2. download what is missing - never more than the user confirmed
        ModelCatalog.refreshFromServer()
        val missing = ModelCatalog.requiredFiles(s).filter { !ModelCatalog.isDownloaded(models, it) }
        if (missing.isNotEmpty()) {
            val bytes = missing.sumOf { it.sizeBytes }
            if (bytes > request.confirmedDownloadBytes * 1.05 + 50_000_000) {
                throw IllegalStateException(getString(R.string.error_download_grew))
            }
            val net = DeviceInfo.network(this)
            if (!net.connected) throw IllegalStateException(getString(R.string.error_offline))
            if (s.wifiOnly && net.metered) throw IllegalStateException(getString(R.string.error_wifi_only))
            JobRepository.update { it.copy(phase = Phase.DOWNLOADING) }
            val downloader = ModelDownloader(models)
            var doneBefore = 0L
            missing.forEach { f ->
                downloader.download(f, { JobRepository.cancelRequested }) { done, total ->
                    val all = doneBefore + done
                    JobRepository.update {
                        it.copy(progress = (all.toDouble() / bytes).toFloat().coerceIn(0f, 1f),
                            status = getString(R.string.status_downloading, f.name, mb(done), mb(total.coerceAtLeast(f.sizeBytes))))
                    }
                    updateNotification()
                }
                doneBefore += f.sizeBytes
                JobRepository.log("[DOWNLOAD] ${f.name}: OK")
            }
        }

        // 3. generate
        check()
        JobRepository.update { it.copy(phase = Phase.GENERATING, progress = -1f, status = getString(R.string.status_generating)) }
        withContext(Dispatchers.Main) { goForeground(processing = true) }
        val planner = MemoryPlanner(this)
        val duration = Preflight.generatedDurationSec(s, request.inputs.map { it.durationSec })
        val plan = planner.plan(s, duration)
        JobRepository.log("[PLAN] RAM limit ${plan.limitMb} MB, estimated peak ${"%.1f".format(plan.estimate.peakGb)} GB, " +
            "threads ${plan.threads}, max pass ${if (plan.maxPassSec > 0) "%.0f s".format(plan.maxPassSec) else "whole"}, " +
            "language model ${if (plan.lmEnabled) "on" else "off"}")
        val gov = ResourceGovernor(this, s, lifecycleScope) { paused, status ->
            JobRepository.update { it.copy(thermalPaused = paused) }
            JobRepository.log(if (paused) "[THERMAL] Phone too hot (status $status) - generation paused until it cools down."
                              else "[THERMAL] Cooled down - generation continues.")
            notifyThermal(paused)
            updateNotification()
        }
        governor = gov
        gov.start()
        wakeLock = getSystemService(PowerManager::class.java)!!
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AceMusicGen:generation").apply { acquire(24 * 3600 * 1000L) }

        val settingsJson = s.toPythonSettings().put("ACE_STYLE_TEMPLATES", templates)
        val config = JSONObject().apply {
            put("paths", JSONObject().apply {
                put("workspace", work.path); put("output", dirs.getValue("out").path); put("temp", dirs.getValue("tmp").path)
                put("templates", dirs.getValue("templates").path); put("checkpoints", dirs.getValue("ckpt").path)
                put("logs", dirs.getValue("logs").path); put("input", dirs.getValue("inputs").path)
                put("native", applicationInfo.nativeLibraryDir); put("models", models.path)
            })
            put("settings", settingsJson)
            put("resources", JSONObject().apply {
                put("threads", plan.threads)
                put("nice", if (s.lowPriority) 10 else 0)
                put("cores", JSONArray(DeviceInfo.coresFor(s.coreSet)))
                put("lm_enabled", plan.lmEnabled)
                put("max_pass_sec", plan.maxPassSec)
                put("vae_chunk", plan.vaeChunk)
            })
            put("prompt", s.prompt)
            put("inputs", inputs)
            put("subdir", "android")
        }
        if (!Python.isStarted()) Python.start(AndroidPlatform(this))
        val bridge = PythonBridge(this, s, gov, planner, plan.limitMb)
        val result = JSONObject(Python.getInstance().getModule("ace_android").callAttr("run", config.toString(), bridge).toString())
        gov.stop()

        if (result.optBoolean("cancelled")) {
            JobRepository.update {
                it.copy(phase = if (it.phase == Phase.TIMED_OUT) Phase.TIMED_OUT else Phase.CANCELLED,
                    status = getString(R.string.status_cancelled_kept))
            }
            return
        }
        if (!result.optBoolean("ok")) throw IllegalStateException(result.optString("error"))

        // 4. publish the results (MediaStore: Music/ and Download/)
        JobRepository.update { it.copy(phase = Phase.EXPORTING, status = getString(R.string.status_saving), progress = -1f) }
        val locations = mutableListOf<String>()
        val results = result.getJSONArray("results")
        for (i in 0 until results.length()) {
            val r = results.getJSONObject(i)
            val exported = ResultExporter.export(this, File(r.getString("root")), r.getString("session"), s.outputFolders)
            locations += exported.locations
            if (exported.fallbacks.isNotEmpty()) {
                val msg = getString(R.string.out_fallback, exported.fallbacks.joinToString(", "))
                locations += msg
                JobRepository.log("[SAVE] $msg")
            }
            exported.locations.forEach { JobRepository.log("[SAVE] $it") }
        }
        JobRepository.update { it.copy(phase = Phase.DONE, progress = 1f, status = getString(R.string.status_done), results = locations) }
    }

    private fun check() {
        if (JobRepository.cancelRequested) throw ModelDownloader.CancelledException()
    }

    private fun hash(s: String) = MessageDigest.getInstance("SHA-1").digest(s.toByteArray()).take(8).joinToString("") { "%02x".format(it) }
    private fun mb(b: Long) = (b / 1_000_000).toInt()

    /** Android 15+: the system ends long foreground services. Progress is checkpointed - the user can start again. */
    override fun onTimeout(startId: Int, fgsType: Int) {
        JobRepository.cancelRequested = true
        JobRepository.update { it.copy(phase = Phase.TIMED_OUT, status = getString(R.string.status_timeout)) }
        governor?.stop()
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
    }

    private fun finish() {
        val st = JobRepository.state.value
        val nm = getSystemService(NotificationManager::class.java)!!
        val text = when (st.phase) {
            Phase.DONE -> getString(R.string.notif_done)
            Phase.FAILED -> getString(R.string.notif_failed, st.error ?: "")
            Phase.TIMED_OUT -> getString(R.string.status_timeout)
            else -> getString(R.string.status_cancelled_kept)
        }
        nm.notify(NOTIF_DONE_ID, NotificationCompat.Builder(this, AceApp.CHANNEL_DONE)
            .setSmallIcon(R.drawable.ic_notification).setContentTitle(getString(R.string.app_name)).setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(openApp()).setAutoCancel(true).build())
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun openApp(): PendingIntent = PendingIntent.getActivity(this, 0,
        Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE)

    private fun action(action: String, code: Int): PendingIntent = PendingIntent.getService(this, code,
        Intent(this, GenerationService::class.java).setAction(action), PendingIntent.FLAG_IMMUTABLE)

    private fun buildNotification(): Notification {
        val st = JobRepository.state.value
        val text = when {
            st.thermalPaused -> getString(R.string.notif_thermal)
            st.userPaused -> getString(R.string.notif_paused)
            else -> st.status
        }
        val b = NotificationCompat.Builder(this, AceApp.CHANNEL_PROGRESS)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(openApp())
            .setProgress(100, (st.progress.coerceIn(0f, 1f) * 100).toInt(), st.progress < 0)
            .addAction(0, getString(R.string.action_stop), action(ACTION_STOP, 1))
        if (st.phase == Phase.GENERATING) {
            if (st.userPaused) b.addAction(0, getString(R.string.action_resume), action(ACTION_RESUME, 2))
            else b.addAction(0, getString(R.string.action_pause), action(ACTION_PAUSE, 3))
        }
        return b.build()
    }

    private var lastNotify = 0L
    private fun updateNotification() {
        val now = System.currentTimeMillis()
        if (now - lastNotify < 1000) return
        lastNotify = now
        getSystemService(NotificationManager::class.java)!!.notify(NOTIF_ID, buildNotification())
    }

    private fun notifyThermal(paused: Boolean) {
        if (!paused) return
        getSystemService(NotificationManager::class.java)!!.notify(3, NotificationCompat.Builder(this, AceApp.CHANNEL_DONE)
            .setSmallIcon(R.drawable.ic_notification).setContentTitle(getString(R.string.app_name))
            .setContentText(getString(R.string.notif_thermal)).setContentIntent(openApp()).setAutoCancel(true).build())
    }
}
