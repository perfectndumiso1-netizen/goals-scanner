package com.playreport.app

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

/** Notification channels: new analysis, goals in tracked matches, app updates. */
object Notifier {
    const val CH_REPORTS = "reports"
    const val CH_GOALS = "goals"
    const val CH_UPDATES = "updates"
    const val CH_BETS = "bets"
    const val CH_MATCH = "match"
    const val PREFS = "playreport"

    fun createChannels(ctx: Context) {
        val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.createNotificationChannel(NotificationChannel(CH_REPORTS, "New analysis", NotificationManager.IMPORTANCE_DEFAULT).apply {
            description = "A new PlayReport analysis has been published"
        })
        nm.createNotificationChannel(NotificationChannel(CH_GOALS, "Goals in tracked matches", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Score changes in tracked and shortlisted matches"
        })
        nm.createNotificationChannel(NotificationChannel(CH_BETS, "New selections & tickets", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "A new bet met the safety rules; one of your tickets was settled"
        })
        nm.createNotificationChannel(NotificationChannel(CH_MATCH, "Half-time & full-time", NotificationManager.IMPORTANCE_DEFAULT).apply {
            description = "Half-time and full-time scores of tracked matches"
        })
        nm.createNotificationChannel(NotificationChannel(CH_UPDATES, "App updates", NotificationManager.IMPORTANCE_LOW).apply {
            description = "A newer PlayReport version is available"
        })
    }

    fun canNotify(ctx: Context): Boolean =
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    fun notify(ctx: Context, channel: String, id: Int, title: String, text: String, tab: String = "today") {
        if (!canNotify(ctx)) return
        try {
            val open = Intent(ctx, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra("tab", tab)
            }
            val pi = PendingIntent.getActivity(ctx, id, open, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val n = NotificationCompat.Builder(ctx, channel)
                .setSmallIcon(R.drawable.ic_stat_ball)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(NotificationCompat.BigTextStyle().bigText(text))
                .setContentIntent(pi)
                .setAutoCancel(true)
                .setPriority(if (channel == CH_GOALS || channel == CH_BETS) NotificationCompat.PRIORITY_HIGH else NotificationCompat.PRIORITY_DEFAULT)
                .build()
            NotificationManagerCompat.from(ctx).notify(id, n)
        } catch (_: SecurityException) {
        } catch (_: Exception) {
        }
    }

    /** Remember a (match, score) pair so the same goal is never announced twice (app open or background). */
    fun goalSeen(ctx: Context, eid: String, score: String): Boolean {
        val p = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val key = "score_$eid"
        val prev = p.getString(key, null)
        if (prev == score) return true
        p.edit().putString(key, score).apply()
        return false
    }
}
