package com.playreport.app

import android.content.Context
import androidx.work.Worker
import androidx.work.WorkerParameters
import org.json.JSONArray
import org.json.JSONObject

/**
 * Runs every ~15 minutes in the background (WorkManager). Reads the tiny meta.json heartbeat first, so the
 * half-hourly refreshes cost almost no data:
 *  1. a full analysis (07:00 / 12:00 / 17:00 run) was published -> notification
 *  2. new safest bets found by any run                          -> notification per bet (max 4, then a summary)
 *  3. goals in tracked matches (safest bets, bets of the day, shortlist) -> notification with the scorer
 *  4. newer app version                                          -> notification (every 6 h at most)
 */
class CheckWorker(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {

    override fun doWork(): Result {
        val ctx = applicationContext
        val prefs = ctx.getSharedPreferences(Notifier.PREFS, Context.MODE_PRIVATE)
        val r = Net.get(Net.META_JSON + "?t=" + System.currentTimeMillis())
        if (r.code != 200) return Result.success()
        val meta = try { JSONObject(r.body) } catch (e: Exception) { return Result.success() }

        // 1. full analysis published
        val generated = meta.optString("generated")
        val reportRun = meta.optBoolean("report_run", false)
        val lastGen = prefs.getString("last_generated", null)
        if (generated.isNotEmpty() && generated != lastGen && reportRun) {
            prefs.edit().putString("last_generated", generated).apply()
            if (lastGen != null && prefs.getBoolean("pref_reports", true)) {
                val run = meta.optString("run").let { if (it.startsWith("manual") || it.startsWith("auto")) "update" else "$it run" }
                Notifier.notify(ctx, Notifier.CH_REPORTS, 1001, "New PlayReport analysis ($run)",
                    "${meta.optInt("safe_bets")} safest bets · ${meta.optJSONArray("botd")?.length() ?: 0} bets of the day · ${meta.optInt("fixtures")} fixtures worldwide", "home")
            }
        } else if (lastGen == null && generated.isNotEmpty()) {
            prefs.edit().putString("last_generated", generated).apply()
        }

        // 2. new safest bets
        try { checkAlerts(ctx, meta) } catch (_: Exception) { }

        // 3. goals in tracked matches
        try { checkGoals(ctx, meta) } catch (_: Exception) { }

        // 4. app update (at most every 6 hours)
        val lastUpd = prefs.getLong("last_update_check", 0L)
        if (System.currentTimeMillis() - lastUpd > 6 * 3600 * 1000L) {
            prefs.edit().putLong("last_update_check", System.currentTimeMillis()).apply()
            val info = Updater.check()
            if (info != null && Updater.isNewer(info.version, BuildConfig.VERSION_NAME) &&
                prefs.getString("update_notified", "") != info.version) {
                prefs.edit().putString("update_notified", info.version).apply()
                Notifier.notify(ctx, Notifier.CH_UPDATES, 1002, "PlayReport ${info.version} is available",
                    "Open the app to install the update.", "home")
            }
        }
        return Result.success()
    }

    private fun checkAlerts(ctx: Context, meta: JSONObject) {
        val prefs = ctx.getSharedPreferences(Notifier.PREFS, Context.MODE_PRIVATE)
        val ids = meta.optJSONArray("alerts") ?: return
        val seen = (prefs.getString("alerts_seen", "") ?: "").split("\n").filter { it.isNotEmpty() }.toMutableSet()
        val fresh = ArrayList<String>()
        for (i in 0 until ids.length()) { val id = ids.getString(i); if (!seen.contains(id)) fresh.add(id) }
        if (fresh.isEmpty()) return
        val firstSync = seen.isEmpty()
        seen.addAll(fresh)
        prefs.edit().putString("alerts_seen", seen.toList().takeLast(300).joinToString("\n")).apply()
        if (firstSync || !prefs.getBoolean("pref_bets", true)) return   // first run: just remember what exists
        val r = Net.get(Net.ALERTS_JSON + "?t=" + System.currentTimeMillis())
        if (r.code != 200) return
        val all = try { JSONArray(r.body) } catch (e: Exception) { return }
        val byId = HashMap<String, JSONObject>()
        for (i in 0 until all.length()) { val a = all.getJSONObject(i); byId[a.optString("id")] = a }
        val items = fresh.mapNotNull { byId[it] }
        if (items.isEmpty()) return
        if (items.size <= 4) {
            for (a in items) Notifier.notify(ctx, Notifier.CH_BETS, 2000 + (a.optString("id").hashCode() and 0xffff),
                a.optString("title", "New safest bet"), a.optString("text"), "bets")
        } else {
            val body = items.take(6).joinToString("\n") { "• " + it.optString("text") } + if (items.size > 6) "\n…and ${items.size - 6} more" else ""
            Notifier.notify(ctx, Notifier.CH_BETS, 2001, "${items.size} new safest bets found", body, "bets")
        }
    }

    private fun checkGoals(ctx: Context, meta: JSONObject) {
        val prefs = ctx.getSharedPreferences(Notifier.PREFS, Context.MODE_PRIVATE)
        if (!prefs.getBoolean("pref_goals", true)) return
        val want = HashSet<String>()
        meta.optJSONArray("tracked_eids")?.let { for (i in 0 until it.length()) want.add(it.getString(i)) }
        if (want.isEmpty()) return
        val zone = java.time.ZoneId.of("Africa/Johannesburg")
        val today = java.time.LocalDate.now(zone)
        val days = listOf(today, today.minusDays(1))
        for (day in days) {
            val ymd = day.toString().replace("-", "")
            val r = Net.get("https://prod-public-api.livescore.com/v1/api/app/date/soccer/$ymd/2?MD=1")
            if (r.code != 200) continue
            val stages = JSONObject(r.body).optJSONArray("Stages") ?: continue
            for (s in 0 until stages.length()) {
                val st = stages.getJSONObject(s)
                val events = st.optJSONArray("Events") ?: continue
                for (e in 0 until events.length()) {
                    val ev = events.getJSONObject(e)
                    val eid = ev.optString("Eid")
                    if (!want.contains(eid)) continue
                    val status = ev.optString("Eps")
                    if (status == "NS") continue
                    val hg = ev.optString("Tr1").toIntOrNull() ?: continue
                    val ag = ev.optString("Tr2").toIntOrNull() ?: continue
                    val score = "$hg-$ag"
                    val prev = prefs.getString("score_$eid", null)
                    if (Notifier.goalSeen(ctx, eid, score)) continue          // unchanged
                    if (prev == null || hg + ag == 0) continue                 // first sighting: just remember it
                    if (status == "FT" || status == "AET" || status == "AP") continue   // final scores are not goal alerts
                    val home = ev.optJSONArray("T1")?.optJSONObject(0)?.optString("Nm") ?: "Home"
                    val away = ev.optJSONArray("T2")?.optJSONObject(0)?.optString("Nm") ?: "Away"
                    val comp = listOf(st.optString("Cnm"), st.optString("Snm")).filter { it.isNotEmpty() }.joinToString(" · ")
                    val scorer = latestScorer(eid)
                    val title = "⚽ GOAL  $home $hg – $ag $away"
                    val body = (if (scorer.isNotEmpty()) "$scorer · " else "") + "$status · $comp"
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
        } catch (e: Exception) { "" }
    }
}
