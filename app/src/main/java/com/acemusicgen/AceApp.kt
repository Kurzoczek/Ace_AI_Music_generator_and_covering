package com.acemusicgen

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import com.acemusicgen.data.SettingsStore

class AceApp : Application() {
    lateinit var settings: SettingsStore
        private set

    override fun attachBaseContext(base: android.content.Context) {
        super.attachBaseContext(com.acemusicgen.data.AppLanguage.wrap(base))
    }

    override fun onCreate() {
        super.onCreate()
        settings = SettingsStore(this)
        com.acemusicgen.diag.Diagnostics.init(this)
        val nm = getSystemService(NotificationManager::class.java)!!
        nm.createNotificationChannel(NotificationChannel(CHANNEL_PROGRESS, getString(R.string.channel_progress), NotificationManager.IMPORTANCE_LOW))
        nm.createNotificationChannel(NotificationChannel(CHANNEL_DONE, getString(R.string.channel_done), NotificationManager.IMPORTANCE_DEFAULT))
    }

    companion object {
        const val CHANNEL_PROGRESS = "progress"
        const val CHANNEL_DONE = "done"
    }
}
