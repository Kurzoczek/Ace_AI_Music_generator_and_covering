package com.acemusicgen.ui

import android.os.PowerManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.LibraryMusic
import androidx.compose.material.icons.automirrored.filled.Notes
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Storage
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.acemusicgen.R
import com.acemusicgen.data.AppLanguage
import com.acemusicgen.data.AppSettings
import com.acemusicgen.data.CoreSet
import com.acemusicgen.data.Priority
import com.acemusicgen.data.ModelFiles
import com.acemusicgen.data.ModelLocation
import com.acemusicgen.data.ModelPlace
import com.acemusicgen.data.OutputCategory
import com.acemusicgen.data.OutputRouting
import com.acemusicgen.data.DeviceInfo
import com.acemusicgen.data.MemoryPlanner
import com.acemusicgen.data.ModelCatalog
import com.acemusicgen.data.Preflight
import com.acemusicgen.engine.Phase
import java.io.File

@Composable
fun AppRoot(vm: MainViewModel) {
    val colors = if (isSystemInDarkTheme()) darkColorScheme() else lightColorScheme()
    MaterialTheme(colorScheme = colors) {
        var tab by rememberSaveable { mutableIntStateOf(0) }
        val tabs = listOf(
            Triple(R.string.tab_generate, Icons.Default.LibraryMusic, 0),
            Triple(R.string.tab_settings, Icons.Default.Settings, 1),
            Triple(R.string.tab_models, Icons.Default.Storage, 2),
            Triple(R.string.tab_log, Icons.AutoMirrored.Filled.Notes, 3),
        )
        Scaffold(bottomBar = {
            NavigationBar {
                tabs.forEach { (label, icon, i) ->
                    NavigationBarItem(selected = tab == i, onClick = { tab = i }, icon = { Icon(icon, null) }, label = { Text(stringResource(label)) })
                }
            }
        }) { pad ->
            Column(Modifier.padding(pad).fillMaxSize()) {
                when (tab) {
                    0 -> GenerateScreen(vm)
                    1 -> SettingsScreen(vm)
                    2 -> ModelsScreen(vm)
                    else -> LogScreen(vm)
                }
            }
        }
    }
}

@Composable
fun GenerateScreen(vm: MainViewModel) {
    val s by vm.settings.collectAsState()
    val job by vm.job.collectAsState()
    val inputs by vm.inputs.collectAsState()
    val templates by vm.templates.collectAsState()
    val checking by vm.checking.collectAsState()
    val preflight by vm.preflight.collectAsState()
    var showReport by rememberSaveable { mutableStateOf(false) }
    val interrupted by vm.interrupted.collectAsState()
    // System file picker (Storage Access Framework): no storage permission, the user chooses exactly which files
    val pickTracks = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { vm.addInputs(it) }
    val pickTemplates = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { vm.addTemplates(it) }
    val audioTypes = arrayOf("audio/*")

    Column(Modifier.verticalScroll(rememberScrollState()).padding(12.dp)) {
        if (!job.running) interrupted?.let { InterruptedCard(vm, it) }
        SectionCard(stringResource(R.string.tracks_title)) {
            if (inputs.isEmpty()) Text(stringResource(R.string.tracks_none), style = MaterialTheme.typography.bodySmall)
            inputs.forEach { t ->
                val sec = t.durationSec.toInt()
                Text(stringResource(R.string.duration_fmt, t.name, sec / 60, sec % 60), style = MaterialTheme.typography.bodyMedium)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { pickTracks.launch(audioTypes) }, enabled = !job.running) { Text(stringResource(R.string.pick_tracks)) }
                if (inputs.isNotEmpty()) OutlinedButton(onClick = vm::clearInputs, enabled = !job.running) { Text(stringResource(R.string.clear)) }
            }
        }
        SectionCard(stringResource(R.string.templates_title)) {
            if (templates.isEmpty()) Text(stringResource(R.string.templates_none), style = MaterialTheme.typography.bodySmall)
            templates.forEach { Text(it.name, style = MaterialTheme.typography.bodyMedium) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { pickTemplates.launch(audioTypes) }, enabled = !job.running) { Text(stringResource(R.string.pick_templates)) }
                if (templates.isNotEmpty()) TextButton(onClick = vm::clearTemplates, enabled = !job.running) { Text(stringResource(R.string.clear)) }
            }
        }
        SectionCard(stringResource(R.string.set_model)) {
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                listOf("cover" to R.string.mode_cover, "text" to R.string.mode_text).forEachIndexed { i, (m, label) ->
                    SegmentedButton(selected = s.mode == m, onClick = { vm.update { it.copy(mode = m) } },
                        shape = SegmentedButtonDefaults.itemShape(i, 2)) { Text(stringResource(label), fontSize = 12.sp) }
                }
            }
            OutlinedTextField(value = s.prompt, onValueChange = { p -> vm.update { it.copy(prompt = p) } },
                label = { Text(stringResource(R.string.prompt_label)) }, placeholder = { Text(stringResource(R.string.prompt_hint)) },
                modifier = Modifier.fillMaxWidth(), minLines = 2)
        }

        if (job.running) {
            SectionCard(job.status) {
                if (job.progress < 0) LinearProgressIndicator(Modifier.fillMaxWidth())
                else LinearProgressIndicator(progress = { job.progress }, modifier = Modifier.fillMaxWidth())
                if (job.thermalPaused) Text(stringResource(R.string.paused_thermal), color = MaterialTheme.colorScheme.error)
                if (job.userPaused) Text(stringResource(R.string.paused_user))
                job.memoryNote?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                job.log.lastOrNull()?.let { Text(it, style = MaterialTheme.typography.bodySmall, maxLines = 2) }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (job.phase == Phase.GENERATING) {
                        if (job.userPaused) OutlinedButton(onClick = vm::resume) { Text(stringResource(R.string.resume)) }
                        else OutlinedButton(onClick = vm::pause) { Text(stringResource(R.string.pause)) }
                    }
                    Button(onClick = vm::stop) { Text(stringResource(R.string.stop)) }
                }
            }
        } else {
            when (job.phase) {
                Phase.DONE -> SectionCard(stringResource(R.string.results_title)) {
                    job.results.forEach { Text(it) }
                    TextButton(onClick = { showReport = true }) { Text(stringResource(R.string.report_button)) }
                }
                Phase.FAILED -> SectionCard(stringResource(R.string.error_title)) { Text(job.error ?: "", color = MaterialTheme.colorScheme.error) }
                Phase.CANCELLED, Phase.TIMED_OUT -> SectionCard(job.status) { }
                else -> {}
            }
            if (checking) {
                Text(stringResource(R.string.checking))
                LinearProgressIndicator(Modifier.fillMaxWidth())
            }
            Button(onClick = vm::prepareStart, enabled = inputs.isNotEmpty() && !checking, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
                Text(stringResource(R.string.start))
            }
            if (inputs.isEmpty()) Text(stringResource(R.string.need_track), style = MaterialTheme.typography.bodySmall)
            val customOut = s.outputFolders.keys.count { k -> OutputCategory.entries.any { it.key == k } }
            Text(if (customOut == 0) stringResource(R.string.out_where_default)
                 else stringResource(R.string.out_where_custom, customOut),
                style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 8.dp))
        }
    }
    preflight?.let { r ->
        PreflightDialog(r, s.thermalProtection, onConfirm = { vm.confirmStart(r) }, onDismiss = vm::dismissPreflight)
    }
    if (showReport) ReportDialog(s, job.results, onDismiss = { showReport = false })
}

@Composable
fun SettingsScreen(vm: MainViewModel) {
    val s by vm.settings.collectAsState()
    val ctx = LocalContext.current
    val ramTotalMb = remember { vm.deviceRamMb() }
    val cores = remember { Runtime.getRuntime().availableProcessors() }
    val planner = remember { MemoryPlanner(ctx) }
    fun f(v: Float?) = v?.toString() ?: ""

    Column(Modifier.verticalScroll(rememberScrollState()).padding(12.dp)) {
        SectionCard(stringResource(R.string.set_language)) {
            val lang = remember { AppLanguage.get(ctx) }
            // language names are written in their own language, so they can be found whatever the current UI language is
            ChoiceRow(stringResource(R.string.set_language_label), listOf(
                AppLanguage.SYSTEM to stringResource(R.string.lang_system),
                "en" to "English",
                "pl" to "Polski"), lang) { t ->
                (ctx as? android.app.Activity)?.let { AppLanguage.set(it, t) }
            }
        }

        SectionCard(stringResource(R.string.set_model)) {
            ChoiceRow(stringResource(R.string.set_dit), ModelCatalog.DIT_MODELS.map { it to it.removePrefix("acestep-v15-") }, s.model) { m -> vm.update { it.copy(model = m) } }
            ChoiceRow(stringResource(R.string.set_quant), ModelCatalog.QUANTS.map { it to it }, s.quant) { q -> vm.update { it.copy(quant = q) } }
            ChoiceRow(stringResource(R.string.set_lm), ModelCatalog.LMS.map { it to (it.ifEmpty { stringResource(R.string.set_lm_none) }) }, s.lm) { l -> vm.update { it.copy(lm = l) } }
            ModelDescriptions(s)
        }

        SectionCard(stringResource(R.string.set_memory)) {
            val autoGb = (ramTotalMb - MemoryPlanner.SYSTEM_RESERVE_MB).coerceAtLeast(512) / 1024f
            SwitchRow(stringResource(R.string.set_ram_auto, autoGb), s.ramAuto) { v -> vm.update { it.copy(ramAuto = v) } }
            if (!s.ramAuto) {
                // No fixed cap: anything from 0.5 GB up to the RAM of this phone.
                val maxMb = ramTotalMb.toFloat().coerceAtLeast(1024f)
                SliderRow(stringResource(R.string.set_ram_limit, s.ramLimitMb / 1024f, ramTotalMb / 1024f),
                    s.ramLimitMb.toFloat(), 512f..maxMb) { v -> vm.update { it.copy(ramLimitMb = ((v / 128).toInt() * 128).coerceAtLeast(512)) } }
            }
            val duration = Preflight.generatedDurationSec(s, listOf(180.0))
            val plan = remember(s) { planner.plan(s, duration) }
            Text(stringResource(R.string.set_ram_info, plan.estimate.peakGb,
                stringResource(if (plan.maxPassSec == 0.0 && !plan.belowMinimum) R.string.set_ram_ok else R.string.set_ram_adapt)),
                style = MaterialTheme.typography.bodySmall)
        }

        SectionCard(stringResource(R.string.set_cpu)) {
            SliderRow(stringResource(R.string.set_threads, if (s.threads == 0) stringResource(R.string.set_threads_auto) else s.threads.toString(), cores),
                s.threads.toFloat(), 0f..cores.toFloat(), steps = (cores - 1).coerceAtLeast(0)) { v -> vm.update { it.copy(threads = v.toInt()) } }
            SliderRow(stringResource(R.string.set_cpu_pct, s.cpuMaxPercent), s.cpuMaxPercent.toFloat(), 10f..100f, steps = 8) { v ->
                vm.update { it.copy(cpuMaxPercent = ((v / 10).toInt() * 10).coerceIn(10, 100)) }
            }
            ChoiceRow(stringResource(R.string.set_cores), listOf(CoreSet.ALL to stringResource(R.string.set_cores_all),
                CoreSet.EFFICIENCY to stringResource(R.string.set_cores_eff), CoreSet.PERFORMANCE to stringResource(R.string.set_cores_perf)), s.coreSet) { c ->
                vm.update { it.copy(coreSet = c) }
            }
            ChoiceRow(stringResource(R.string.set_priority), listOf(
                Priority.LOW to stringResource(R.string.prio_low),
                Priority.BELOW_NORMAL to stringResource(R.string.prio_below_normal),
                Priority.NORMAL to stringResource(R.string.prio_normal),
                Priority.ABOVE_NORMAL to stringResource(R.string.prio_above_normal),
                Priority.HIGH to stringResource(R.string.prio_high),
                Priority.REALTIME to stringResource(R.string.prio_realtime)), s.priority) { p ->
                vm.update { it.copy(priority = p) }
            }
            Text(stringResource(when (s.priority) {
                Priority.LOW -> R.string.prio_low_info
                Priority.BELOW_NORMAL -> R.string.prio_below_normal_info
                Priority.NORMAL -> R.string.prio_normal_info
                Priority.ABOVE_NORMAL, Priority.HIGH -> R.string.prio_raised_info
                Priority.REALTIME -> R.string.prio_realtime_info
            }), style = MaterialTheme.typography.bodySmall,
                color = if (s.priority == Priority.REALTIME) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
            SwitchRow(stringResource(R.string.set_thermal), s.thermalProtection) { v -> vm.update { it.copy(thermalProtection = v) } }
            if (s.thermalProtection) {
                ChoiceRow(stringResource(R.string.set_thermal_level), listOf(
                    PowerManager.THERMAL_STATUS_MODERATE to stringResource(R.string.set_thermal_moderate),
                    PowerManager.THERMAL_STATUS_SEVERE to stringResource(R.string.set_thermal_severe),
                    PowerManager.THERMAL_STATUS_CRITICAL to stringResource(R.string.set_thermal_critical)), s.thermalPauseLevel) { l ->
                    vm.update { it.copy(thermalPauseLevel = l) }
                }
            }
        }

        SectionCard(stringResource(R.string.set_generation)) {
            NumberField(stringResource(R.string.set_steps), s.steps?.toString() ?: "") { t -> vm.update { it.copy(steps = t.toIntOrNull()?.coerceAtLeast(1)) } }
            NumberField(stringResource(R.string.set_seed), s.seed.toString()) { t -> vm.update { it.copy(seed = t.toIntOrNull() ?: -1) } }
            NumberField(stringResource(R.string.set_guidance), f(s.guidance), decimal = true) { t -> vm.update { it.copy(guidance = t.replace(',', '.').toFloatOrNull()) } }
            SliderRow(stringResource(R.string.set_sections) + ": ${s.numSections}", s.numSections.toFloat(), 1f..24f, steps = 22) { v -> vm.update { it.copy(numSections = v.toInt()) } }
            SwitchRow(stringResource(R.string.set_whole), s.wholeTrack) { v -> vm.update { it.copy(wholeTrack = v) } }
            if (!s.wholeTrack) NumberField(stringResource(R.string.set_passes), s.numPasses.toString()) { t -> vm.update { it.copy(numPasses = t.toIntOrNull()?.coerceAtLeast(0) ?: 0) } }
            SwitchRow(stringResource(R.string.set_instrumental), s.instrumental) { v -> vm.update { it.copy(instrumental = v) } }
            if (!s.instrumental) OutlinedTextField(value = s.lyrics, onValueChange = { t -> vm.update { it.copy(lyrics = t) } },
                label = { Text(stringResource(R.string.set_lyrics)) }, modifier = Modifier.fillMaxWidth(), minLines = 3)
            SwitchRow(stringResource(R.string.set_reference), s.useReference) { v -> vm.update { it.copy(useReference = v) } }
            if (s.useReference && s.mode == "text" && !s.wholeTrack) {
                SwitchRow(stringResource(R.string.set_reference_previous), s.referenceMode == "previous") { v ->
                    vm.update { it.copy(referenceMode = if (v) "previous" else "input") }
                }
            }
        }

        if (s.mode == "cover") SectionCard(stringResource(R.string.set_cover)) {
            SliderRow(stringResource(R.string.set_strength, s.coverStrength), s.coverStrength, 0f..1f) { v -> vm.update { it.copy(coverStrength = (v * 20).toInt() / 20f) } }
            SliderRow(stringResource(R.string.set_noise, s.coverNoise), s.coverNoise, 0f..1f) { v -> vm.update { it.copy(coverNoise = (v * 20).toInt() / 20f) } }
            SwitchRow(stringResource(R.string.set_whole_file), s.coverWholeFile) { v -> vm.update { it.copy(coverWholeFile = v) } }
            if (s.coverWholeFile) {
                NumberField(stringResource(R.string.set_max_sec), f(s.coverMaxSec), decimal = true) { t ->
                    vm.update { it.copy(coverMaxSec = t.replace(',', '.').toFloatOrNull()?.coerceAtLeast(10f)) }
                }
            } else {
                OutlinedTextField(value = s.coverFragments, onValueChange = { t -> vm.update { it.copy(coverFragments = t) } },
                    label = { Text(stringResource(R.string.set_fragments)) }, modifier = Modifier.fillMaxWidth())
                ChoiceRow(stringResource(R.string.set_fragments_mode), listOf("insert" to stringResource(R.string.set_frag_insert),
                    "separate" to stringResource(R.string.set_frag_separate)), s.coverFragmentsMode) { m -> vm.update { it.copy(coverFragmentsMode = m) } }
            }
        }

        SectionCard(stringResource(R.string.set_export)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    SwitchRow(stringResource(R.string.set_mono), s.formatMono) { v -> vm.update { it.copy(formatMono = v) } }
                    SwitchRow(stringResource(R.string.set_stereo), s.formatStereo) { v -> vm.update { it.copy(formatStereo = v) } }
                    SwitchRow(stringResource(R.string.set_surround), s.formatSurround) { v -> vm.update { it.copy(formatSurround = v) } }
                }
            }
            SwitchRow(stringResource(R.string.set_notation), s.exportNotation) { v -> vm.update { it.copy(exportNotation = v) } }
            SwitchRow(stringResource(R.string.set_samples), s.exportSamples) { v -> vm.update { it.copy(exportSamples = v) } }
            SwitchRow(stringResource(R.string.set_used), s.exportUsedSounds) { v -> vm.update { it.copy(exportUsedSounds = v) } }
            SwitchRow(stringResource(R.string.set_stems), s.stemAnalysis) { v -> vm.update { it.copy(stemAnalysis = v) } }
            if (s.stemAnalysis) SwitchRow(stringResource(R.string.set_stems_export), s.exportStems) { v -> vm.update { it.copy(exportStems = v) } }
        }

        SaveLocationsCard(vm, s)

        SectionCard(stringResource(R.string.set_network)) {
            SwitchRow(stringResource(R.string.set_wifi_only), s.wifiOnly) { v -> vm.update { it.copy(wifiOnly = v) } }
        }

        DiagnosticsCard(vm, s)
    }
}

@Composable
fun ModelsScreen(vm: MainViewModel) {
    val s by vm.settings.collectAsState()
    val version by vm.modelsVersion.collectAsState()
    val job by vm.job.collectAsState()
    val task by vm.storageTask.collectAsState()
    val dir = vm.modelsDir
    LaunchedEffect(Unit) { vm.refreshSizes() }
    val required = remember(s, version) { ModelCatalog.requiredFiles(s) }
    val onPhone = remember(version, s.modelsLocation) { dir?.let { ModelFiles.list(it) } ?: emptyList() }
    val locations = remember(version, s.modelsLocation) { vm.modelLocations() }
    var pendingSwitch by remember { mutableStateOf<ModelLocation?>(null) }
    val importLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        if (uris.isNotEmpty()) vm.importModels(uris)
    }
    val busy = job.running || task?.finished == false

    Column(Modifier.verticalScroll(rememberScrollState()).padding(12.dp)) {
        Text(stringResource(R.string.models_source, ModelCatalog.SOURCE_DESCRIPTION), style = MaterialTheme.typography.bodySmall)
        if (dir != null) {
            Text(stringResource(R.string.models_used_space, formatBytes(onPhone.sumOf { it.length() }), formatBytes(DeviceInfo.freeBytes(dir))),
                style = MaterialTheme.typography.bodySmall)
        }

        SectionCard(stringResource(R.string.models_location_title)) {
            Text(stringResource(R.string.models_location_info), style = MaterialTheme.typography.bodySmall)
            if (dir == null) Text(stringResource(R.string.models_location_missing), color = MaterialTheme.colorScheme.error)
            locations.forEach { loc ->
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                    RadioButton(selected = loc.id == s.modelsLocation, enabled = !busy,
                        onClick = { if (loc.id != s.modelsLocation) pendingSwitch = loc })
                    Column(Modifier.weight(1f)) {
                        Text(locationLabel(loc), style = MaterialTheme.typography.bodyMedium)
                        Text(stringResource(R.string.models_location_free, formatBytes(loc.free), formatBytes(loc.total)),
                            style = MaterialTheme.typography.bodySmall)
                        Text(loc.dir.path, style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace, fontSize = 10.sp)
                    }
                }
            }
            if (locations.none { it.place == ModelPlace.SD_CARD }) {
                Text(stringResource(R.string.models_location_no_sd), style = MaterialTheme.typography.bodySmall)
            }
            Text(stringResource(R.string.models_location_uninstall), style = MaterialTheme.typography.bodySmall)
            if (busy && job.running) Text(stringResource(R.string.models_location_busy), style = MaterialTheme.typography.bodySmall)
        }

        SectionCard(stringResource(R.string.models_import_title)) {
            Text(stringResource(R.string.models_import_info), style = MaterialTheme.typography.bodySmall)
            OutlinedButton(enabled = !busy && dir != null, onClick = { importLauncher.launch(arrayOf("*/*")) }) {
                Text(stringResource(R.string.models_import_button))
            }
        }

        SectionCard(stringResource(R.string.models_required)) {
            required.forEach { m ->
                val ok = dir != null && ModelCatalog.isDownloaded(dir, m)
                Text("${m.name} - ${formatBytes(m.sizeBytes)} - ${stringResource(if (ok) R.string.model_ok else R.string.model_missing)}",
                    style = MaterialTheme.typography.bodyMedium)
            }
            TextButton(onClick = { vm.refreshSizes() }) { Text(stringResource(R.string.refresh_sizes)) }
        }
        SectionCard(stringResource(R.string.models_on_phone)) {
            onPhone.forEach { f ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("${f.name} (${formatBytes(f.length())})", Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
                    TextButton(enabled = !busy, onClick = { vm.deleteModel(f.name.removeSuffix(".part")) }) { Text(stringResource(R.string.delete)) }
                }
            }
        }
    }

    pendingSwitch?.let { target ->
        val toMove = remember(target.id) { vm.bytesToMove(target.id) }
        AlertDialog(
            onDismissRequest = { pendingSwitch = null },
            title = { Text(stringResource(R.string.models_switch_title, locationLabel(target))) },
            text = {
                Text(if (onPhone.isEmpty()) stringResource(R.string.models_switch_empty)
                     else stringResource(R.string.models_switch_body, formatBytes(toMove), formatBytes(target.free)))
            },
            confirmButton = {
                TextButton(onClick = { vm.setModelsLocation(target.id, move = onPhone.isNotEmpty()); pendingSwitch = null }) {
                    Text(stringResource(if (onPhone.isEmpty()) R.string.models_switch_ok else R.string.models_switch_move))
                }
            },
            dismissButton = {
                Row {
                    if (onPhone.isNotEmpty()) TextButton(onClick = { vm.setModelsLocation(target.id, move = false); pendingSwitch = null }) {
                        Text(stringResource(R.string.models_switch_keep))
                    }
                    TextButton(onClick = { pendingSwitch = null }) { Text(stringResource(R.string.cancel)) }
                }
            },
        )
    }

    task?.let { t ->
        AlertDialog(
            onDismissRequest = { vm.dismissStorageTask() },
            title = { Text(t.title) },
            text = {
                Column {
                    if (!t.finished) {
                        if (t.file.isNotEmpty()) Text(t.file, style = MaterialTheme.typography.bodySmall)
                        if (t.total > 0) {
                            LinearProgressIndicator(progress = { (t.done.toDouble() / t.total).toFloat().coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp))
                            Text("${formatBytes(t.done)} / ${formatBytes(t.total)}", style = MaterialTheme.typography.bodySmall)
                        } else {
                            LinearProgressIndicator(modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp))
                        }
                    }
                    if (!t.error.isNullOrEmpty()) Text(t.error, color = MaterialTheme.colorScheme.error)
                }
            },
            confirmButton = {
                if (t.finished) TextButton(onClick = { vm.dismissStorageTask() }) { Text(stringResource(R.string.ok)) }
                else TextButton(onClick = { vm.cancelStorageTask() }) { Text(stringResource(R.string.cancel)) }
            },
        )
    }
}

@Composable
private fun locationLabel(loc: ModelLocation): String = when (loc.place) {
    ModelPlace.APP_PRIVATE -> stringResource(R.string.models_place_app)
    ModelPlace.PHONE -> stringResource(R.string.models_place_phone)
    ModelPlace.SD_CARD -> stringResource(R.string.models_place_sd, loc.name.ifEmpty { "SD" })
}

@Composable
fun LogScreen(vm: MainViewModel) {
    val job by vm.job.collectAsState()
    val s by vm.settings.collectAsState()
    val dumpMessage by vm.dumpMessage.collectAsState()
    val state = rememberLazyListState()
    LaunchedEffect(job.log.size) { if (job.log.isNotEmpty()) state.scrollToItem(job.log.size - 1) }
    Column(Modifier.fillMaxSize().padding(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = vm::dumpNow) { Text(stringResource(R.string.dump_now)) }
            Text(stringResource(if (s.diagLogs) R.string.log_saving_on else R.string.log_saving_off),
                style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
        }
        dumpMessage?.let { msg ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(msg, style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                TextButton(onClick = vm::clearDumpMessage) { Text(stringResource(R.string.ok)) }
            }
        }
        LazyColumn(Modifier.fillMaxSize(), state = state) {
            items(job.log) { line -> Text(line, fontFamily = FontFamily.Monospace, fontSize = 11.sp) }
        }
    }
}

private fun categoryLabel(cat: OutputCategory): Int = when (cat) {
    OutputCategory.FINAL -> R.string.out_cat_final
    OutputCategory.PARTS -> R.string.out_cat_parts
    OutputCategory.SAMPLES -> R.string.out_cat_samples
    OutputCategory.STEMS -> R.string.out_cat_stems
    OutputCategory.USED_SOUNDS -> R.string.out_cat_used_sounds
    OutputCategory.MIDI -> R.string.out_cat_midi
    OutputCategory.NOTATION -> R.string.out_cat_notation
    OutputCategory.METADATA -> R.string.out_cat_metadata
}

/** Default location of every kind of result + optional own folder (system folder picker, no storage permission). */
@Composable
fun SaveLocationsCard(vm: MainViewModel, s: AppSettings) {
    var picking by remember { mutableStateOf<List<OutputCategory>>(emptyList()) }
    val pickFolder = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        if (uri != null && picking.isNotEmpty()) vm.setOutputFolder(picking, uri)
        picking = emptyList()
    }
    val session = stringResource(R.string.out_session)
    SectionCard(stringResource(R.string.out_title)) {
        Text(stringResource(R.string.out_info), style = MaterialTheme.typography.bodySmall)
        OutputCategory.entries.forEach { cat ->
            val custom = s.outputFolders[cat.key]
            Column(Modifier.padding(top = 6.dp)) {
                Text(stringResource(categoryLabel(cat)), fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                if (custom == null) {
                    Text(stringResource(R.string.out_default, OutputRouting.defaultDisplay(cat, session)), style = MaterialTheme.typography.bodySmall)
                } else {
                    Text(stringResource(R.string.out_custom, vm.describeFolder(custom) + "/" + session), style = MaterialTheme.typography.bodySmall)
                    if (!vm.hasFolderAccess(custom)) Text(stringResource(R.string.out_no_access), color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = { picking = listOf(cat); pickFolder.launch(null) }) { Text(stringResource(R.string.out_change)) }
                    if (custom != null) TextButton(onClick = { vm.resetOutputFolder(listOf(cat)) }) { Text(stringResource(R.string.out_reset)) }
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { picking = OutputCategory.entries.toList(); pickFolder.launch(null) }) { Text(stringResource(R.string.out_all)) }
            if (OutputCategory.entries.any { it.key in s.outputFolders }) TextButton(onClick = { vm.resetOutputFolder(OutputCategory.entries.toList()) }) {
                Text(stringResource(R.string.out_all_reset))
            }
        }
    }
}
