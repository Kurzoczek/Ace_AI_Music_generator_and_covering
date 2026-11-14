package com.acemusicgen.engine

import android.net.Uri
import com.acemusicgen.data.AppSettings
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update

enum class Phase { IDLE, PREPARING, DOWNLOADING, GENERATING, EXPORTING, DONE, FAILED, CANCELLED, TIMED_OUT }

data class InputTrack(val uri: Uri, val name: String, val durationSec: Double)

/** What the user confirmed in the warning dialog. The service refuses to download more than this. */
data class JobRequest(
    val inputs: List<InputTrack>,
    val templates: List<InputTrack>,
    val settings: AppSettings,
    val confirmedDownloadBytes: Long,
)

data class JobState(
    val phase: Phase = Phase.IDLE,
    val progress: Float = -1f,                 // 0..1, or -1 when unknown
    val status: String = "",
    val log: List<String> = emptyList(),
    val userPaused: Boolean = false,
    val thermalPaused: Boolean = false,
    val memoryNote: String? = null,
    val results: List<String> = emptyList(),   // human readable result locations
    val error: String? = null,
) {
    val running: Boolean get() = phase in setOf(Phase.PREPARING, Phase.DOWNLOADING, Phase.GENERATING, Phase.EXPORTING)
}

/** Shared state between the foreground service and the UI (same process). */
object JobRepository {
    private const val MAX_LOG = 600
    private val _state = MutableStateFlow(JobState())
    val state: StateFlow<JobState> = _state

    @Volatile var pending: JobRequest? = null
    @Volatile var cancelRequested = false

    fun update(transform: (JobState) -> JobState) = _state.update(transform)

    fun log(line: String) = _state.update { s -> s.copy(log = (s.log + line).takeLast(MAX_LOG)) }

    fun reset() {
        cancelRequested = false
        _state.value = JobState()
    }
}
