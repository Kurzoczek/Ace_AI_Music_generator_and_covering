package com.acemusicgen.ui

import java.util.Locale

fun formatBytes(b: Long): String = when {
    b >= 1_000_000_000L -> String.format(Locale.getDefault(), "%.2f GB", b / 1e9)
    b >= 1_000_000L -> String.format(Locale.getDefault(), "%.0f MB", b / 1e6)
    else -> String.format(Locale.getDefault(), "%.0f kB", b / 1e3)
}
