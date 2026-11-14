package com.acemusicgen.data

import android.app.Activity
import android.app.LocaleManager
import android.content.Context
import android.content.res.Configuration
import android.os.Build
import android.os.LocaleList
import java.util.Locale

/**
 * In-app UI language: "" = follow the phone, "en" = English, "pl" = Polish.
 *
 * Android 13+: uses the system per-app language (LocaleManager), so the choice is also shown and changeable in
 * the phone's Settings > Apps > Language, and applies to every part of the app automatically.
 * Android 10-12: the choice is kept in the app and applied to each component with [wrap] (Activity, Service, Application).
 */
object AppLanguage {
    const val SYSTEM = ""
    val SUPPORTED = listOf("en", "pl")
    private const val PREFS = "ui"
    private const val KEY = "lang"

    fun get(context: Context): String {
        if (Build.VERSION.SDK_INT >= 33) {
            val list = context.getSystemService(LocaleManager::class.java)?.applicationLocales
            return if (list == null || list.isEmpty) SYSTEM else normalize(list[0].language)
        }
        return normalize(context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, SYSTEM) ?: SYSTEM)
    }

    /** Applies [tag]. On Android 13+ the system recreates the screen itself; below that the activity is recreated here. */
    fun set(activity: Activity, tag: String) {
        val t = normalize(tag)
        if (t == get(activity)) return
        if (Build.VERSION.SDK_INT >= 33) {
            activity.getSystemService(LocaleManager::class.java)?.applicationLocales =
                if (t == SYSTEM) LocaleList.getEmptyLocaleList() else LocaleList.forLanguageTags(t)
        } else {
            activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY, t).commit()
            activity.recreate()
        }
    }

    /** Context with the chosen language for Android 10-12 (on 13+ the system already does this). */
    fun wrap(base: Context): Context {
        if (Build.VERSION.SDK_INT >= 33) return base
        val t = normalize(base.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, SYSTEM) ?: SYSTEM)
        if (t == SYSTEM) return base
        val locale = Locale.forLanguageTag(t)
        Locale.setDefault(locale)
        val config = Configuration(base.resources.configuration)
        config.setLocales(LocaleList(locale))
        return base.createConfigurationContext(config)
    }

    private fun normalize(tag: String): String = tag.substringBefore('-').substringBefore('_').lowercase().takeIf { it in SUPPORTED } ?: SYSTEM
}
