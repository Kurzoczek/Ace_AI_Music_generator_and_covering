package com.acemusicgen.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudDownload
import androidx.compose.material.icons.filled.Memory
import androidx.compose.material.icons.filled.SdStorage
import androidx.compose.material.icons.filled.Thermostat
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.acemusicgen.R
import com.acemusicgen.data.PreflightReport

/**
 * Warning shown before any processing: how much data is downloaded and from where, how much phone storage
 * the models take, how much RAM the selected model needs (and what the app does if the limit is lower),
 * and the risk of overheating. Nothing is downloaded or started until the user ticks the box and confirms.
 */
@Composable
fun PreflightDialog(r: PreflightReport, thermalProtection: Boolean, onConfirm: () -> Unit, onDismiss: () -> Unit) {
    var accepted by remember { mutableStateOf(false) }
    val blocked = r.wifiOnlyBlocked || !r.enoughSpace
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.pf_title)) },
        text = {
            Column(Modifier.heightIn(max = 520.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Block(Icons.Default.CloudDownload, stringResource(R.string.pf_download_title)) {
                    if (r.toDownload.isEmpty()) {
                        Text(stringResource(R.string.pf_download_none))
                    } else {
                        Text(stringResource(R.string.pf_download_body, formatBytes(r.downloadBytes), r.toDownload.size, r.source, r.host))
                        r.toDownload.forEach { Text(stringResource(R.string.pf_download_item, it.name, formatBytes(it.sizeBytes)), style = MaterialTheme.typography.bodySmall) }
                        Text(stringResource(if (r.sizesExact) R.string.pf_sizes_exact else R.string.pf_sizes_approx), style = MaterialTheme.typography.bodySmall)
                        if (r.network.metered) Warn(stringResource(R.string.pf_metered))
                        if (r.wifiOnlyBlocked) Warn(stringResource(R.string.pf_wifi_blocked))
                    }
                }
                Block(Icons.Default.SdStorage, stringResource(R.string.pf_storage_title)) {
                    Text(stringResource(R.string.pf_storage_body, formatBytes(r.modelsOnDiskBytes), formatBytes(r.outputEstimateBytes), formatBytes(r.freeBytes)))
                    Text(stringResource(R.string.pf_models_where, r.modelsDir), style = MaterialTheme.typography.bodySmall)
                    if (r.workFreeBytes != r.freeBytes) Text(stringResource(R.string.pf_work_free, formatBytes(r.workFreeBytes)), style = MaterialTheme.typography.bodySmall)
                    if (!r.enoughSpace) Warn(stringResource(R.string.pf_storage_low))
                }
                Block(Icons.Default.Memory, stringResource(R.string.pf_ram_title)) {
                    val e = r.plan.estimate
                    Text(stringResource(R.string.pf_ram_body, r.modelLabel, e.peakGb, e.weightsGb, r.durationSec,
                        r.deviceRamMb / 1024.0, r.availableRamMb / 1024.0, r.plan.limitMb / 1024.0))
                    if (e.lmPeakGb > 0) Text(stringResource(R.string.pf_ram_lm, e.lmPeakGb))
                    Text(stringResource(if (e.calibrated) R.string.pf_ram_calibrated else R.string.pf_ram_estimated), style = MaterialTheme.typography.bodySmall)
                    when {
                        r.plan.belowMinimum -> Warn(stringResource(R.string.pf_ram_below))
                        r.plan.maxPassSec > 0 -> Warn(stringResource(R.string.pf_ram_split, r.plan.maxPassSec, r.plan.threads))
                        else -> Text(stringResource(R.string.pf_ram_fits))
                    }
                    if (e.lmPeakGb > 0 && !r.plan.lmEnabled) Warn(stringResource(R.string.pf_ram_no_lm))
                }
                Block(Icons.Default.Thermostat, stringResource(R.string.pf_heat_title)) {
                    Text(stringResource(R.string.pf_heat_body, stringResource(if (thermalProtection) R.string.pf_heat_on else R.string.pf_heat_off)))
                    if (r.thermalStatus >= 2) Warn(stringResource(R.string.pf_heat_now, r.thermalStatus))
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = accepted, onCheckedChange = { accepted = it }, enabled = !blocked)
                    Text(stringResource(R.string.pf_confirm), style = MaterialTheme.typography.bodyMedium)
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onConfirm, enabled = accepted && !blocked) {
                Text(stringResource(if (r.toDownload.isEmpty()) R.string.pf_go_no_download else R.string.pf_go))
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) } },
    )
}

@Composable
private fun Block(icon: ImageVector, title: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(icon, contentDescription = null)
            Text(title, fontWeight = FontWeight.SemiBold)
        }
        content()
    }
}

@Composable
private fun Warn(text: String) {
    Text(text, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.fillMaxWidth())
}
