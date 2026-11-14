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
import com.acemusicgen.data.Preflight
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

    val modelsDir: File get() = GenerationService.modelsDir(getApplication())

    fun update(transform: (AppSettings) -> AppSettings) = store.update(transform)

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
    }

    fun addTemplates(uris: List<Uri>) = viewModelScope.launch(Dispatchers.IO) {
        val added = uris.map { describe(it) }
        _templates.value = (_templates.value + added).distinctBy { it.uri }.take(10)
    }

    fun clearInputs() { _inputs.value = emptyList() }
    fun clearTemplates() { _templates.value = emptyList() }

    /** Step 1 of Start: compute downloads, storage, RAM and heat information for the warning dialog. */
    fun prepareStart() {
        if (_checking.value) return
        _checking.value = true
        viewModelScope.launch(Dispatchers.IO) {
            try {
                _preflight.value = Preflight.build(getApplication(), settings.value, modelsDir, _inputs.value.map { it.durationSec })
            } finally {
                _checking.value = false
            }
        }
    }

    fun dismissPreflight() { _preflight.value = null }

    /** Step 2 of Start: the user confirmed the dialog. */
    fun confirmStart(report: PreflightReport) {
        _preflight.value = null
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
        File(modelsDir, name).delete()
        File(modelsDir, "$name.part").delete()
        _modelsVersion.value++
    }

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
