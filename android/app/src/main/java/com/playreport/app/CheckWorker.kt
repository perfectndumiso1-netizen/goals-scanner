package com.playreport.app

import android.content.Context
import androidx.work.Worker
import androidx.work.WorkerParameters
import org.json.JSONObject
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter

/**
 * Runs every ~15 minutes in the background (WorkManager):
 *  1. new analysis published  -> notification
 *  2. goals in tracked matches (parlay legs, shortlisted picks) -> notification with the scorer
 *  3. newer app version       -> notification (every 6 h at most)
 */
class CheckWorker(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {

    private val zone: ZoneId = ZoneId.of("Africa/Johannesburg")
    private val fmt: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")

    override fun doWork(): Result {
        val ctx = applicationContext
        val prefs = ctx.getSharedPreferences(Notifier.PREFS, Context.MODE_PRIVATE)
        val r = Net.get(Net.LATEST_JSON + "?t=" + System.currentTimeMillis())
        if (r.code != 200) return Result.success()
        val data = try { JSONObject(r.body) } catch (e: Exception) { return Result.success() }

        // 1. new analysis
        val meta = data.optJSONObject("meta") ?: JSONObject()
        val generated = meta.optString("generated")
        val lastGen = prefs.getString("last_generated", null)
        if (generated.isNotEmpty() && generated != lastGen) {
            prefs.edit().putString("last_generated", generated).apply()
            if (lastGen != null) {
                val parlays = data.optJSONArray("parlays")?.length() ?: 0
                val picks = data.optJSONObject("picks")
                val n15 = picks?.optJSONArray("O15")?.length() ?: 0
                val n25 = picks?.optJSONArray("O25")?.length() ?: 0
                val nb = picks?.optJSONArray("BTTS")?.length() ?: 0
                val run = meta.optString("run").let { if (it.startsWith("manual")) "update" else "$it run" }
                Notifier.notify(ctx, Notifier.CH_REPORTS, 1001, "New PlayReport analysis ($run)",
                    "$parlays parlays · picks: Over 1.5 $n15 · Over 2.5 $n25 · BTTS $nb · ${meta.optInt("fixtures")} fixtures analysed", "today")
            }
        }

        // 2. goals in tracked matches
        try { checkGoals(ctx, data) } catch (_: Exception) { }

        // 3. app update (at most every 6 hours)
        val lastUpd = prefs.getLong("last_update_check", 0L)
        if (System.currentTimeMillis() - lastUpd > 6 * 3600 * 1000L) {
            prefs.edit().putLong("last_update_check", System.currentTimeMillis()).apply()
            val info = Updater.check()
            if (info != null && Updater.isNewer(info.version, BuildConfig.VERSION_NAME) &&
                prefs.getString("update_notified", "") != info.version) {
                prefs.edit().putString("update_notified", info.version).apply()
                Notifier.notify(ctx, Notifier.CH_UPDATES, 1002, "PlayReport ${info.version} is available",
                    "Open the app to install the update.", "today")
            }
        }
        return Result.success()
    }

    private fun checkGoals(ctx: Context, data: JSONObject) {
        val tracked = HashSet<String>()
        data.optJSONArray("tracked")?.let { for (i in 0 until it.length()) tracked.add(it.getString(i)) }
        if (tracked.isEmpty()) return
        val now = ZonedDateTime.now(zone).toLocalDateTime()
        // fixtures worth checking: tracked, with a live id, kicked off in the last 3 h (or starting within 10 min)
        val watch = HashMap<String, JSONObject>()   // livescore id -> fixture
        val fixtures = data.optJSONArray("fixtures") ?: return
        for (i in 0 until fixtures.length()) {
            val f = fixtures.getJSONObject(i)
            if (!tracked.contains(f.optString("id"))) continue
            val eid = f.optString("livescore_id")
            if (eid.isEmpty() || eid == "null") continue
            val ko = try { LocalDateTime.parse(f.optString("kickoff"), fmt) } catch (e: Exception) { continue }
            if (ko.isAfter(now.plusMinutes(10)) || ko.isBefore(now.minusHours(3))) continue
            watch[eid] = f
        }
        if (watch.isEmpty()) return
        val days = watch.values.map { it.optString("kickoff").substring(0, 10).replace("-", "") }.toSet()
        for (day in days) {
            val r = Net.get("https://prod-public-api.livescore.com/v1/api/app/date/soccer/$day/2?MD=1")
            if (r.code != 200) continue
            val stages = JSONObject(r.body).optJSONArray("Stages") ?: continue
            for (s in 0 until stages.length()) {
                val events = stages.getJSONObject(s).optJSONArray("Events") ?: continue
                for (e in 0 until events.length()) {
                    val ev = events.getJSONObject(e)
                    val eid = ev.optString("Eid")
                    val f = watch[eid] ?: continue
                    val hg = ev.optString("Tr1").toIntOrNull() ?: continue
                    val ag = ev.optString("Tr2").toIntOrNull() ?: continue
                    val status = ev.optString("Eps")
                    val score = "$hg-$ag"
                    val prev = ctx.getSharedPreferences(Notifier.PREFS, Context.MODE_PRIVATE).getString("score_$eid", null)
                    if (Notifier.goalSeen(ctx, eid, score)) continue          // unchanged
                    if (prev == null || hg + ag == 0) continue                 // first sighting: just remember it
                    val home = f.optString("home_long", f.optString("home"))
                    val away = f.optString("away_long", f.optString("away"))
                    val scorer = latestScorer(eid)
                    val title = "⚽ GOAL  $home $hg – $ag $away"
                    val body = (if (scorer.isNotEmpty()) "$scorer · " else "") + "$status · ${f.optString("competition")}"
                    Notifier.notify(ctx, Notifier.CH_GOALS, eid.hashCode(), title, body, "live")
                }
            }
        }
    }

    private fun latestScorer(eid: String): String {
        return try {
            val r = Net.get("https://prod-public-api.livescore.com/v1/api/app/incidents/soccer/$eid")
            if (r.code != 200) return ""
            val incs = JSONObject(r.body).optJSONObject("Incs") ?: return ""
            var best: JSONObject? = null
            for (period in incs.keys()) {
                val lst = incs.optJSONArray(period) ?: continue
                for (i in 0 until lst.length()) {
                    val x = lst.getJSONObject(i)
                    val all = ArrayList<JSONObject>().apply { add(x); x.optJSONArray("Incs")?.let { sub -> for (j in 0 until sub.length()) add(sub.getJSONObject(j)) } }
                    for (y in all) {
                        val t = y.optInt("IT")
                        if (t == 36 || t == 37 || t == 39) {
                            if (best == null || y.optInt("Min") >= best!!.optInt("Min")) best = y
                        }
                    }
                }
            }
            val b = best ?: return ""
            val name = b.optString("Pn").ifEmpty { listOf(b.optString("Fn"), b.optString("Ln")).filter { it.isNotEmpty() }.joinToString(" ") }
            val kind = when (b.optInt("IT")) { 37 -> " (own goal)"; 39 -> " (penalty)"; else -> "" }
            "$name ${b.optInt("Min")}'$kind".trim()
        } catch (e: Exception) {
            ""
        }
    }
}
