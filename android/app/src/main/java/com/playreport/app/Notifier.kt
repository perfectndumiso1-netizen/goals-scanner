package com.playreport.app

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

/** Notification channels: new analysis, goals in tracked matches, app updates. */
object Notifier {
    // v1.6: every channel has PlayReport's own sound (res/raw/pr_*.ogg). Android fixes a channel's sound when the
    // channel is first created, so the ids carry a version suffix and the old channels are deleted.
    const val CH_REPORTS = "reports_v2"
    const val CH_GOALS = "goals_v2"
    const val CH_UPDATES = "updates"
    const val CH_BETS = "bets_v2"
    const val CH_MATCH = "match_v2"
    const val CH_KICKOFF = "kickoff_v2"
    const val PREFS = "playreport"
    private val OLD_CHANNELS = listOf("reports", "goals", "bets", "match")

    private fun sound(ctx: Context, name: String): Uri =
        Uri.parse("android.resource://${ctx.packageName}/raw/$name")

    private val soundAttrs: AudioAttributes = AudioAttributes.Builder()
        .setUsage(AudioAttributes.USAGE_NOTIFICATION_EVENT)
        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
        .build()

    private fun channel(ctx: Context, id: String, name: String, importance: Int, desc: String, soundName: String?,
                        vibrate: Boolean = true): NotificationChannel =
        NotificationChannel(id, name, importance).apply {
            description = desc
            if (soundName != null) setSound(sound(ctx, soundName), soundAttrs)
            enableVibration(vibrate)
            if (vibrate) vibrationPattern = longArrayOf(0, 180, 90, 180)
        }

    fun createChannels(ctx: Context) {
        val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        for (old in OLD_CHANNELS) try { nm.deleteNotificationChannel(old) } catch (e: Exception) { /* not present */ }
        nm.createNotificationChannel(channel(ctx, CH_REPORTS, "New analysis", NotificationManager.IMPORTANCE_DEFAULT,
            "A new PlayReport analysis has been published", "pr_report", vibrate = false))
        nm.createNotificationChannel(channel(ctx, CH_GOALS, "Goals in tracked matches", NotificationManager.IMPORTANCE_HIGH,
            "Score changes in tracked and shortlisted matches", "pr_goal"))
        nm.createNotificationChannel(channel(ctx, CH_BETS, "New selections & tickets", NotificationManager.IMPORTANCE_HIGH,
            "A new high-probability selection was found; one of your tickets was settled", "pr_selection"))
        nm.createNotificationChannel(channel(ctx, CH_KICKOFF, "Kick-off reminders", NotificationManager.IMPORTANCE_DEFAULT,
            "A tracked or favourite match is about to start", "pr_kickoff"))
        nm.createNotificationChannel(channel(ctx, CH_MATCH, "Half-time & full-time", NotificationManager.IMPORTANCE_DEFAULT,
            "Half-time and full-time scores of tracked matches", "pr_fulltime", vibrate = false))
        nm.createNotificationChannel(NotificationChannel(CH_UPDATES, "App updates", NotificationManager.IMPORTANCE_LOW).apply {
            description = "A newer PlayReport version is available"
        })
    }

    /** Sound file (res/raw name) behind each channel — used by the Settings page previews. */
    fun soundFor(channel: String): String? = when (channel) {
        CH_REPORTS -> "pr_report"; CH_GOALS -> "pr_goal"; CH_BETS -> "pr_selection"; CH_KICKOFF -> "pr_kickoff"; CH_MATCH -> "pr_fulltime"
        else -> null
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
