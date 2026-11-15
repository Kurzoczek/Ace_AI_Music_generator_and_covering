package com.acemusicgen.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.acemusicgen.R
import com.acemusicgen.data.AppSettings
import com.acemusicgen.data.DumpType
import com.acemusicgen.diag.DiagFolder
import com.acemusicgen.diag.SystemProbe

/** Shown on the Generate screen when Android ended the app while a job was running. */
@Composable
fun InterruptedCard(vm: MainViewModel, job: MainViewModel.InterruptedJob) {
    SectionCard(stringResource(R.string.interrupted_title)) {
        Text(stringResource(R.string.interrupted_info, SystemProbe.fmtTime(job.info.startedAt),
            job.info.request.inputs.joinToString { it.name }), style = MaterialTheme.typography.bodySmall)
        if (job.info.lastStatus.isNotEmpty()) {
            Text(stringResource(R.string.interrupted_status, job.info.lastStatus), style = MaterialTheme.typography.bodySmall)
        }
        Text(if (job.reason.isNotEmpty()) stringResource(R.string.interrupted_reason, job.reason)
             else stringResource(R.string.interrupted_reason_unknown), style = MaterialTheme.typography.bodySmall)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = vm::resumeInterrupted) { Text(stringResource(R.string.interrupted_resume)) }
            TextButton(onClick = vm::discardInterrupted) { Text(stringResource(R.string.interrupted_discard)) }
        }
    }
}

/** Settings > Diagnostics: file log, state dumps, their folders. */
@Composable
fun DiagnosticsCard(vm: MainViewModel, s: AppSettings) {
    var picking by remember { mutableStateOf<DiagFolder?>(null) }
    val pickFolder = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        val f = picking
        if (uri != null && f != null) vm.setDiagFolder(f, uri)
        picking = null
    }

    @Composable
    fun FolderRow(folder: DiagFolder) {
        val custom = s.outputFolders[folder.key]
        Text(stringResource(R.string.diag_folder_now, vm.diagFolderDescription(folder)), style = MaterialTheme.typography.bodySmall)
        if (custom != null && !vm.hasFolderAccess(custom)) {
            Text(stringResource(R.string.out_no_access), color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextButton(onClick = { picking = folder; pickFolder.launch(null) }) { Text(stringResource(R.string.out_change)) }
            if (custom != null) TextButton(onClick = { vm.resetDiagFolder(folder) }) { Text(stringResource(R.string.out_reset)) }
        }
    }

    SectionCard(stringResource(R.string.diag_title)) {
        Text(stringResource(R.string.diag_info), style = MaterialTheme.typography.bodySmall)

        // --- log file
        Text(stringResource(R.string.diag_logs_title), fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp))
        SwitchRow(stringResource(R.string.diag_logs_switch), s.diagLogs) { vm.setDiagLogs(it) }
        Text(stringResource(R.string.diag_logs_info), style = MaterialTheme.typography.bodySmall)
        FolderRow(DiagFolder.LOGS)

        // --- dumps
        Text(stringResource(R.string.dump_title), fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp))
        ChoiceRow(stringResource(R.string.dump_type), listOf(
            DumpType.NONE to stringResource(R.string.dump_none),
            DumpType.SMALL to stringResource(R.string.dump_small),
            DumpType.EXTENDED to stringResource(R.string.dump_extended),
            DumpType.FULL to stringResource(R.string.dump_full),
            DumpType.AUTOMATIC to stringResource(R.string.dump_auto)), s.dumpType) { t -> vm.update { it.copy(dumpType = t) } }
        Text(stringResource(when (s.dumpType) {
            DumpType.NONE -> R.string.dump_none_info
            DumpType.SMALL -> R.string.dump_small_info
            DumpType.EXTENDED -> R.string.dump_extended_info
            DumpType.FULL -> R.string.dump_full_info
            DumpType.AUTOMATIC -> R.string.dump_auto_info
        }), style = MaterialTheme.typography.bodySmall)
        if (s.dumpType != DumpType.NONE) {
            Text(stringResource(R.string.dump_when), style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 4.dp))
            SwitchRow(stringResource(R.string.dump_on_unexpected), s.dumpOnUnexpectedEnd) { v -> vm.update { it.copy(dumpOnUnexpectedEnd = v) } }
            SwitchRow(stringResource(R.string.dump_on_error), s.dumpOnError) { v -> vm.update { it.copy(dumpOnError = v) } }
            SwitchRow(stringResource(R.string.dump_on_pause), s.dumpOnPause) { v -> vm.update { it.copy(dumpOnPause = v) } }
            ChoiceRow(stringResource(R.string.dump_keep), listOf(1, 3, 5, 10, 20).map {
                it to if (it == 1) stringResource(R.string.dump_keep_overwrite) else it.toString()
            }, s.dumpKeep) { k -> vm.update { it.copy(dumpKeep = k) } }
        }
        FolderRow(DiagFolder.DUMPS)
        Column {
            OutlinedButton(onClick = vm::dumpNow) { Text(stringResource(R.string.dump_now)) }
            Text(stringResource(R.string.dump_now_info), style = MaterialTheme.typography.bodySmall)
        }
    }
}

/** Description of the selected model / quantization / language model, under the choice rows. */
@Composable
fun ModelDescriptions(s: AppSettings) {
    val dit = when (s.model.removePrefix("acestep-v15-")) {
        "turbo" -> R.string.mdesc_turbo
        "sft" -> R.string.mdesc_sft
        "base" -> R.string.mdesc_base
        "xl-turbo" -> R.string.mdesc_xl_turbo
        "xl-sft" -> R.string.mdesc_xl_sft
        "xl-base" -> R.string.mdesc_xl_base
        else -> null
    }
    val quant = when (s.quant) {
        "Q4_K_M" -> R.string.qdesc_q4
        "Q5_K_M" -> R.string.qdesc_q5
        "Q6_K" -> R.string.qdesc_q6
        "Q8_0" -> R.string.qdesc_q8
        "BF16" -> R.string.qdesc_bf16
        else -> null
    }
    val lm = when (s.lm) {
        "" -> R.string.lmdesc_none
        "0.6B" -> R.string.lmdesc_06
        "1.7B" -> R.string.lmdesc_17
        "4B" -> R.string.lmdesc_4
        else -> null
    }
    Column(Modifier.padding(top = 4.dp)) {
        listOfNotNull(dit, quant, lm).forEach {
            Text(stringResource(it), style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 4.dp))
        }
        Text(stringResource(R.string.mdesc_howto), style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 6.dp))
    }
}
