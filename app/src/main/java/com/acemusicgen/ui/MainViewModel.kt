package com.acemusicgen.ui

import android.app.Application
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.acemusicgen.AceApp
import com.acemusicgen.audio.ResultExporter
import com.acemusicgen.data.AppSettings
import com.acemusicgen.data.OutputCategory
import com.acemusicgen.data.DeviceInfo
import com.acemusicgen.data.ModelCatalog
import com.acemusicgen.data.ModelFiles
import com.acemusicgen.data.ModelLocation
import com.acemusicgen.data.ModelStorage
import com.acemusicgen.R
import com.acemusicgen.engine.Phase
import com.acemusicgen.data.Preflight
import com.acemusicgen.data.DumpType
import com.acemusicgen.data.SessionStore
import com.acemusicgen.diag.DiagExport
import com.acemusicgen.diag.DiagFolder
import com.acemusicgen.diag.Diagnostics
import com.acemusicgen.diag.StateDump
import com.acemusicgen.diag.SystemProbe
import com.acemusicgen.data.PreflightReport
import com.acemusicgen.engine.GenerationService
import com.acemusicgen.engine.InputTrack
import com.acemusicgen.engine.JobRepository
import com.acemusicgen.engine.JobRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import java.io.File

class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val store = (app as AceApp).settings
    val settings: StateFlow<AppSettings> = store.state
    val job = JobRepository.state

    private val _inputs = MutableStateFlow<List<InputTrack>>(emptyList())
    val inputs: StateFlow<List<InputTrack>> = _inputs
    private val _templates = MutableStateFlow<List<InputTrack>>(emptyList())
    val templates: StateFlow<List<InputTrack>> = _templates

    private val _preflight = MutableStateFlow<PreflightReport?>(null)
    val preflight: StateFlow<PreflightReport?> = _preflight
    private val _checking = MutableStateFlow(false)
    val checking: StateFlow<Boolean> = _checking

    /** Bumped after model files change, so the models screen recomposes. */
    private val _modelsVersion = MutableStateFlow(0)
    val modelsVersion: StateFlow<Int> = _modelsVersion

    /** Current model folder; null when the chosen storage (SD card) is not available right now. */
    val modelsDir: File? get() = GenerationService.modelsDir(getApplication())

    fun update(transform: (AppSettings) -> AppSettings) = store.update(transform)

    // ---------- picked tracks survive the app being killed (saved in SessionStore)
    private val _interrupted = MutableStateFlow<InterruptedJob?>(null)
    /** A job that was running when Android ended the app, or null. */
    val interrupted: StateFlow<InterruptedJob?> = _interrupted

    data class InterruptedJob(val info: SessionStore.Interrupted, val reason: String)

    init {
        val ctx = getApplication<Application>()
        viewModelScope.launch(Dispatchers.IO) {
            val readable = ctx.contentResolver.persistedUriPermissions.filter { it.isReadPermission }.map { it.uri }.toSet()
            fun keep(t: InputTrack) = t.uri in readable || t.uri.scheme == "file"
            if (_inputs.value.isEmpty()) _inputs.value = SessionStore.loadInputs(ctx).filter(::keep)
            if (_templates.value.isEmpty()) _templates.value = SessionStore.loadTemplates(ctx).filter(::keep)
            val i = SessionStore.interrupted(ctx)
            if (i != null && !JobRepository.state.value.running && JobRepository.pending == null) {
                val exit = SystemProbe.exitInfos(ctx, 1).firstOrNull()
                    ?.takeIf { it.timestamp >= i.startedAt }?.let { SystemProbe.exitReasonName(it.reason) }
                _interrupted.value = InterruptedJob(i, exit ?: "")
            }
        }
    }

    private fun saveLists() {
        val ctx = getApplication<Application>()
        val ins = _inputs.value
        val tpl = _templates.value
        viewModelScope.launch(Dispatchers.IO) { SessionStore.saveLists(ctx, ins, tpl) }
    }

    /** Starts the interrupted job again with the same tracks and settings; finished passes are reused (checkpoints). */
    fun resumeInterrupted() {
        val i = _interrupted.value ?: return
        _interrupted.value = null
        _inputs.value = i.info.request.inputs
        _templates.value = i.info.request.templates
        saveLists()
        Diagnostics.event("USER", "resumes the interrupted job started ${SystemProbe.fmtTime(i.info.startedAt)}")
        JobRepository.pending = i.info.request
        GenerationService.start(getApplication())
    }

    fun discardInterrupted() {
        _interrupted.value = null
        viewModelScope.launch(Dispatchers.IO) { SessionStore.markEnded(getApplication()) }
    }

    // ---------- diagnostics
    private val _dumpMessage = MutableStateFlow<String?>(null)
    val dumpMessage: StateFlow<String?> = _dumpMessage

    /** Manual dump; with dumps switched off it still writes an extended one, since the user asked for it. */
    fun dumpNow() {
        val ctx = getApplication<Application>()
        val type = settings.value.dumpType
        _dumpMessage.value = ctx.getString(R.string.dump_running)
        StateDump.requestAsync(ctx, "manual", "requested by the user",
            forceLevel = if (type == DumpType.NONE) DumpType.EXTENDED else StateDump.levelFor(type, "manual")) { where ->
            _dumpMessage.value = ctx.getString(R.string.dump_done, where)
        }
    }

    fun clearDumpMessage() { _dumpMessage.value = null }

    fun setDiagFolder(folder: DiagFolder, uri: Uri) {
        val ctx = getApplication<Application>()
        runCatching { ResultExporter.takePermission(ctx, uri) }.onFailure { return }
        val old = settings.value.outputFolders
        store.update { s -> s.copy(outputFolders = s.outputFolders + (folder.key to uri.toString())) }
        releaseUnused(old)
        if (folder == DiagFolder.LOGS) Diagnostics.syncNow()
    }

    fun resetDiagFolder(folder: DiagFolder) {
        val old = settings.value.outputFolders
        store.update { s -> s.copy(outputFolders = s.outputFolders - folder.key) }
        releaseUnused(old)
    }

    fun diagFolderDescription(folder: DiagFolder): String =
        DiagExport.describe(getApplication(), settings.value.outputFolders, folder)

    fun setDiagLogs(on: Boolean) {
        store.update { it.copy(diagLogs = on) }
        Diagnostics.event("SETTINGS", "saving logs to the folder ${if (on) "ON" else "off"}")
        if (on) Diagnostics.syncNow()
    }

    private fun describe(uri: Uri): InputTrack {
        val ctx = getApplication<Application>()
        // keep read access across app restarts (Storage Access Framework), no storage permission needed
        runCatching { ctx.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION) }
        val name = ctx.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        } ?: uri.lastPathSegment ?: "track"
        return InputTrack(uri, name, Preflight.audioDurationSec(ctx, uri))
    }

    fun addInputs(uris: List<Uri>) = viewModelScope.launch(Dispatchers.IO) {
        val added = uris.map { describe(it) }
        _inputs.value = (_inputs.value + added).distinctBy { it.uri }
        saveLists()
    }

    fun addTemplates(uris: List<Uri>) = viewModelScope.launch(Dispatchers.IO) {
        val added = uris.map { describe(it) }
        _templates.value = (_templates.value + added).distinctBy { it.uri }.take(10)
        saveLists()
    }

    fun clearInputs() { _inputs.value = emptyList(); saveLists() }
    fun clearTemplates() { _templates.value = emptyList(); saveLists() }

    /** Step 1 of Start: compute downloads, storage, RAM and heat information for the warning dialog. */
    fun prepareStart() {
        if (_checking.value) return
        _checking.value = true
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val dir = modelsDir
                if (dir == null) {
                    JobRepository.update { it.copy(phase = Phase.FAILED, error = getApplication<Application>().getString(R.string.models_location_missing)) }
                    return@launch
                }
                _preflight.value = Preflight.build(getApplication(), settings.value, dir, _inputs.value.map { it.durationSec })
            } finally {
                _checking.value = false
            }
        }
    }

    fun dismissPreflight() { _preflight.value = null }

    /** Step 2 of Start: the user confirmed the dialog. */
    fun confirmStart(report: PreflightReport) {
        _preflight.value = null
        _interrupted.value = null
        JobRepository.pending = JobRequest(_inputs.value, _templates.value, settings.value, report.downloadBytes)
        GenerationService.start(getApplication())
    }

    fun stop() = GenerationService.send(getApplication(), GenerationService.ACTION_STOP)
    fun pause() = GenerationService.send(getApplication(), GenerationService.ACTION_PAUSE)
    fun resume() = GenerationService.send(getApplication(), GenerationService.ACTION_RESUME)

    fun refreshSizes() = viewModelScope.launch(Dispatchers.IO) {
        ModelCatalog.refreshFromServer()
        _modelsVersion.value++
    }

    fun deleteModel(name: String) = viewModelScope.launch(Dispatchers.IO) {
        val dir = modelsDir ?: return@launch
        File(dir, name).delete()
        File(dir, "$name.part").delete()
        _modelsVersion.value++
    }

    // ---------- model storage location (app folders only: the native engine needs real file paths)
    data class StorageTask(val title: String, val file: String = "", val done: Long = 0, val total: Long = 0,
                           val error: String? = null, val finished: Boolean = false)

    private val _storageTask = MutableStateFlow<StorageTask?>(null)
    val storageTask: StateFlow<StorageTask?> = _storageTask
    @Volatile private var storageCancel = false

    fun modelLocations(): List<ModelLocation> = ModelStorage.locations(getApplication())

    /** Bytes that would be copied when switching to [id] with "move models". */
    fun bytesToMove(id: String): Long {
        val from = modelsDir ?: return 0
        val to = ModelStorage.dirFor(getApplication(), id) ?: return 0
        return ModelFiles.bytesToMove(from, to)
    }

    /** Switches the model folder; with [move] the models already downloaded are moved there first. */
    fun setModelsLocation(id: String, move: Boolean) {
        if (job.value.running || _storageTask.value?.finished == false) return
        val ctx = getApplication<Application>()
        val from = modelsDir
        val to = ModelStorage.dirFor(ctx, id) ?: return
        if (!move || from == null || ModelFiles.list(from).isEmpty()) {
            store.update { it.copy(modelsLocation = id) }
            _modelsVersion.value++
            return
        }
        storageCancel = false
        val title = ctx.getString(R.string.models_moving)
        _storageTask.value = StorageTask(title)
        viewModelScope.launch(Dispatchers.IO) {
            try {
                ModelFiles.move(from, to, { DeviceInfo.freeBytes(it) }, { storageCancel }) { done, total, name ->
                    _storageTask.value = StorageTask(title, name, done, total)
                }
                store.update { it.copy(modelsLocation = id) }
                _storageTask.value = StorageTask(ctx.getString(R.string.models_moved), finished = true)
            } catch (e: ModelFiles.NotEnoughSpace) {
                _storageTask.value = StorageTask(title, error = ctx.getString(R.string.models_move_no_space,
                    formatBytes(e.needed), formatBytes(e.free)), finished = true)
            } catch (e: ModelFiles.Cancelled) {
                ModelFiles.cleanTemp(to)
                _storageTask.value = StorageTask(ctx.getString(R.string.models_move_cancelled), finished = true)
            } catch (e: Exception) {
                ModelFiles.cleanTemp(to)
                _storageTask.value = StorageTask(title, error = e.message ?: e.javaClass.simpleName, finished = true)
            } finally {
                _modelsVersion.value++
            }
        }
    }

    /** Copies .gguf files picked by the user (e.g. downloaded on a computer) into the model folder, verified when possible. */
    fun importModels(uris: List<Uri>) {
        if (job.value.running || _storageTask.value?.finished == false) return
        val ctx = getApplication<Application>()
        val dir = modelsDir ?: run {
            _storageTask.value = StorageTask(ctx.getString(R.string.models_importing), error = ctx.getString(R.string.models_location_missing), finished = true)
            return
        }
        storageCancel = false
        val title = ctx.getString(R.string.models_importing)
        _storageTask.value = StorageTask(title)
        viewModelScope.launch(Dispatchers.IO) {
            ModelCatalog.refreshFromServer()
            val ok = ArrayList<String>()
            val failed = ArrayList<String>()
            try {
                for (uri in uris) {
                    if (storageCancel) throw ModelFiles.Cancelled()
                    val name = ctx.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)
                        ?.use { c -> if (c.moveToFirst()) c.getString(0) else null } ?: uri.lastPathSegment ?: "model.gguf"
                    if (!name.endsWith(".gguf")) { failed += ctx.getString(R.string.models_import_not_gguf, name); continue }
                    val known = ModelCatalog.knownFile(name)
                    val size = known?.first ?: ctx.contentResolver.query(uri, arrayOf(OpenableColumns.SIZE), null, null, null)
                        ?.use { c -> if (c.moveToFirst() && !c.isNull(0)) c.getLong(0) else null } ?: 0L
                    if (size > 0 && size + ModelFiles.RESERVE_BYTES > DeviceInfo.freeBytes(dir)) {
                        failed += ctx.getString(R.string.models_move_no_space, formatBytes(size + ModelFiles.RESERVE_BYTES), formatBytes(DeviceInfo.freeBytes(dir)))
                        continue
                    }
                    try {
                        val input = ctx.contentResolver.openInputStream(uri) ?: throw java.io.IOException("cannot open $name")
                        ModelFiles.importStream(input, name, dir, known?.first, known?.second, { storageCancel }) { done ->
                            _storageTask.value = StorageTask(title, name, done, size)
                        }
                        ok += name
                    } catch (e: ModelFiles.Cancelled) {
                        throw e
                    } catch (e: Exception) {
                        failed += e.message ?: name
                    }
                }
                val summary = buildString {
                    append(ctx.getString(R.string.models_imported, ok.size))
                    if (ok.any { ModelCatalog.knownFile(it) == null }) append("\n").append(ctx.getString(R.string.models_import_unknown))
                    failed.forEach { append("\n- ").append(it) }
                }
                _storageTask.value = StorageTask(summary, finished = true, error = if (failed.isNotEmpty() && ok.isEmpty()) "" else null)
            } catch (e: ModelFiles.Cancelled) {
                ModelFiles.cleanTemp(dir)
                _storageTask.value = StorageTask(ctx.getString(R.string.models_import_cancelled), finished = true)
            } finally {
                _modelsVersion.value++
            }
        }
    }

    fun cancelStorageTask() { storageCancel = true }
    fun dismissStorageTask() { if (_storageTask.value?.finished == true) _storageTask.value = null }

    fun deviceRamMb(): Long = DeviceInfo.memory(getApplication()).totalMb

    // ---------- save locations (Storage Access Framework folders, persisted permission)
    fun setOutputFolder(cats: List<OutputCategory>, uri: Uri) {
        val ctx = getApplication<Application>()
        runCatching { ResultExporter.takePermission(ctx, uri) }.onFailure { return }
        val old = settings.value.outputFolders
        store.update { s -> s.copy(outputFolders = s.outputFolders + cats.associate { it.key to uri.toString() }) }
        releaseUnused(old)
    }

    fun resetOutputFolder(cats: List<OutputCategory>) {
        val old = settings.value.outputFolders
        store.update { s -> s.copy(outputFolders = s.outputFolders - cats.map { it.key }.toSet()) }
        releaseUnused(old)
    }

    /** Gives back folder permissions that no category uses any more. */
    private fun releaseUnused(old: Map<String, String>) {
        val inUse = settings.value.outputFolders.values.toSet()
        (old.values.toSet() - inUse).forEach { ResultExporter.releasePermission(getApplication(), it) }
    }

    fun describeFolder(uri: String): String = ResultExporter.describeTree(Uri.parse(uri))
    fun hasFolderAccess(uri: String): Boolean = ResultExporter.hasWriteAccess(getApplication(), uri)
}
