package com.acemusicgen.ui

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import com.acemusicgen.BuildConfig
import com.acemusicgen.R
import com.acemusicgen.data.AppSettings

/**
 * "Report content" form (Google Play AI-Generated Content policy): the user flags an offensive / harmful / infringing
 * result inside the app. The report (reason, comment, model and prompt - never the audio or the user's files) is then
 * handed to the e-mail app, or to a new GitHub issue when no report address is configured.
 */
@Composable
fun ReportDialog(settings: AppSettings, results: List<String>, onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    val reasons = listOf(
        R.string.report_reason_offensive, R.string.report_reason_harmful, R.string.report_reason_copyright,
        R.string.report_reason_person, R.string.report_reason_other,
    )
    var reason by remember { mutableStateOf(reasons.first()) }
    var comment by remember { mutableStateOf("") }
    var sent by remember { mutableStateOf<Boolean?>(null) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.report_title)) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                if (sent == null) {
                    Text(stringResource(R.string.report_info), style = MaterialTheme.typography.bodySmall)
                    reasons.forEach { r ->
                        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                            RadioButton(selected = reason == r, onClick = { reason = r })
                            Text(stringResource(r), style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                    OutlinedTextField(value = comment, onValueChange = { comment = it.take(2000) },
                        label = { Text(stringResource(R.string.report_comment)) }, modifier = Modifier.fillMaxWidth(), minLines = 2)
                } else {
                    Text(stringResource(if (sent == true) R.string.report_handed_over else R.string.report_no_app))
                }
            }
        },
        confirmButton = {
            if (sent == null) {
                val reasonText = stringResource(reason)
                TextButton(onClick = { sent = sendReport(ctx, settings, results, reasonText, comment) }) { Text(stringResource(R.string.report_send)) }
            } else {
                TextButton(onClick = onDismiss) { Text(stringResource(R.string.ok)) }
            }
        },
        dismissButton = { if (sent == null) TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) } },
    )
}

private fun reportBody(settings: AppSettings, results: List<String>, reason: String, comment: String): String = buildString {
    appendLine("Reason: $reason")
    if (comment.isNotBlank()) appendLine("Comment: ${comment.trim()}")
    appendLine()
    appendLine("App: ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
    appendLine("Android: ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})")
    appendLine("Mode: ${settings.mode}, model: ${settings.model} ${settings.quant}, seed: ${settings.seed}")
    if (settings.prompt.isNotBlank()) appendLine("Prompt: ${settings.prompt.take(500)}")
    if (results.isNotEmpty()) appendLine("Result: ${results.first().substringAfterLast('/').take(200)}")
}

/** Returns true when an app accepted the report, false when there is no e-mail app / browser. */
private fun sendReport(ctx: Context, settings: AppSettings, results: List<String>, reason: String, comment: String): Boolean {
    val subject = "[${ctx.getString(R.string.app_name)}] Content report: $reason"
    val body = reportBody(settings, results, reason, comment)
    val intent = if (BuildConfig.REPORT_EMAIL.isNotEmpty()) {
        Intent(Intent.ACTION_SENDTO, Uri.parse("mailto:")).apply {
            putExtra(Intent.EXTRA_EMAIL, arrayOf(BuildConfig.REPORT_EMAIL))
            putExtra(Intent.EXTRA_SUBJECT, subject)
            putExtra(Intent.EXTRA_TEXT, body)
        }
    } else {
        val uri = Uri.parse(BuildConfig.REPORT_URL).buildUpon()
            .appendQueryParameter("title", subject).appendQueryParameter("body", body).appendQueryParameter("labels", "content-report")
            .build()
        Intent(Intent.ACTION_VIEW, uri)
    }
    return try {
        ctx.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        true
    } catch (e: ActivityNotFoundException) {
        false
    }
}
