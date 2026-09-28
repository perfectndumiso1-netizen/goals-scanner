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
 *  2. new high-probability selections found by any run                          -> notification per bet (max 4, then a summary)
 *  3. tracked matches (high-probability selections, bets of the day, shortlist, the user's tickets):
 *     goals with the scorer, half-time and full-time scores       -> notifications (each switchable in Settings)
 *  4. the user's pending tickets settled from the final scores   -> notification
 *  5. newer app version                                          -> notification (every 6 h at most)
 */
class CheckWorker(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {

    override fun doWork(): Result {
        val ctx = applicationContext
        val prefs = ctx.getSharedPreferences(Notifier.PREFS, Context.MODE_PRIVATE)
        val r = Net.get(Net.META_JSON + "?t=" + System.currentTimeMillis())
        val meta = if (r.code == 200) (try { JSONObject(r.body) } catch (e: Exception) { JSONObject() }) else JSONObject()

        // 1. full analysis published
        val generated = meta.optString("generated")
        val reportRun = meta.optBoolean("report_run", false)
        val lastGen = prefs.getString("last_generated", null)
        if (generated.isNotEmpty() && generated != lastGen && reportRun) {
            prefs.edit().putString("last_generated", generated).apply()
            if (lastGen != null && prefs.getBoolean("pref_reports", true)) {
                val run = meta.optString("run").let { if (it.startsWith("manual") || it.startsWith("auto")) "update" else "$it run" }
                Notifier.notify(ctx, Notifier.CH_REPORTS, 1001, "New PlayReport analysis ($run)",
                    "${meta.optInt("safe_bets")} high-probability selections · ${meta.optJSONArray("botd")?.length() ?: 0} bets of the day · ${meta.optInt("fixtures")} fixtures worldwide", "home")
            }
        } else if (lastGen == null && generated.isNotEmpty()) {
            prefs.edit().putString("last_generated", generated).apply()
        }

        // 2. new high-probability selections
        try { checkAlerts(ctx, meta) } catch (_: Exception) { }

        // 3 + 4. tracked matches and tickets
        try { checkMatches(ctx, meta) } catch (_: Exception) { }

        // 5. app update (at most every 6 hours)
        val lastUpd = prefs.getLong("last_update_check", 0L)
        if (System.currentTimeMillis() - lastUpd > 6 * 3600 * 1000L) {
            prefs.edit().putLong("last_update_check", System.currentTimeMillis()).apply()
            val info = Updater.check()
            if (info != null && Updater.isNewer(info.version, BuildConfig.VERSION_NAME) &&
                prefs.getString("update_notified", "") != info.version) {
                prefs.edit().putString("update_notified", info.version).apply()
                val whatsNew = info.notes.lines().map { it.trim().trimStart('-', '*', '•', ' ') }
                    .filter { it.isNotBlank() && !it.startsWith("#") && !it.startsWith("Download") }.take(3)
                val text = if (whatsNew.isEmpty()) "Open the app to install the update."
                    else "New: " + whatsNew.joinToString(" · ") + " — open the app to install."
                Notifier.notify(ctx, Notifier.CH_UPDATES, 1002, "PlayReport ${info.version} is available", text, "home")
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
                a.optString("title", "New high-probability selection"), a.optString("text"), "bets")
        } else {
            val body = items.take(6).joinToString("\n") { "• " + it.optString("text") } + if (items.size > 6) "\n…and ${items.size - 6} more" else ""
            Notifier.notify(ctx, Notifier.CH_BETS, 2001, "${items.size} new high-probability selections", body, "bets")
        }
    }

    private data class Ev(val eid: String, val status: String, val hg: Int?, val ag: Int?, val home: String, val away: String, val comp: String)

    private fun isFinished(st: String) = st == "FT" || st == "AET" || st == "AP" || st == "Awarded"
    private fun isVoid(st: String) = st == "Postp." || st == "Canc." || st == "Aband."

    private fun checkMatches(ctx: Context, meta: JSONObject) {
        val prefs = ctx.getSharedPreferences(Notifier.PREFS, Context.MODE_PRIVATE)
        val wantGoals = prefs.getBoolean("pref_goals", true)
        val wantHt = prefs.getBoolean("pref_ht", false)
        val wantFt = prefs.getBoolean("pref_ft", true)
        val tickets = try { JSONArray(prefs.getString("str_tickets", "[]") ?: "[]") } catch (e: Exception) { JSONArray() }
        val favs = try { JSONArray(prefs.getString("str_favs", "[]") ?: "[]") } catch (e: Exception) { JSONArray() }
        val want = HashSet<String>()
        meta.optJSONArray("tracked_eids")?.let { for (i in 0 until it.length()) want.add(it.getString(i)) }
        val mine = ArrayList<JSONObject>()      // favourites + ticket legs: kick-off reminders
        for (i in 0 until tickets.length()) {
            val legs = tickets.getJSONObject(i).optJSONArray("legs") ?: continue
            for (j in 0 until legs.length()) { val l = legs.getJSONObject(j); val e = l.optString("eid"); if (e.isNotEmpty() && e != "null") { want.add(e); mine.add(l) } }
        }
        for (i in 0 until favs.length()) { val f = favs.getJSONObject(i); val e = f.optString("eid"); if (e.isNotEmpty() && e != "null") { want.add(e); mine.add(f) } }
        val zone = java.time.ZoneId.of("Africa/Johannesburg")
        val today = java.time.LocalDate.now(zone)
        // kick-off reminders (15-20 min before) for the user's own matches
        if (prefs.getBoolean("pref_ko", true)) {
            val now = java.time.LocalDateTime.now(zone)
            val fmt = java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")
            for (m in mine) {
                val eid = m.optString("eid"); if (eid.isEmpty() || prefs.getBoolean("ko_$eid", false)) continue
                val ko = try { java.time.LocalDateTime.parse(m.optString("kickoff"), fmt) } catch (e: Exception) { continue }
                val mins = java.time.Duration.between(now, ko).toMinutes()
                if (mins in 0..20) {
                    prefs.edit().putBoolean("ko_$eid", true).apply()
                    Notifier.notify(ctx, Notifier.CH_MATCH, 7000 + (eid.hashCode() and 0xfff), "⏰ Kick-off in $mins min · ${m.optString("home")} v ${m.optString("away")}",
                        (if (m.has("label")) m.optString("label") + " · " else "") + m.optString("competition", ""), "live")
                }
            }
        }
        if (want.isEmpty()) return
        val found = HashMap<String, Ev>()
        for (day in listOf(today, today.minusDays(1))) {
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
                    if (!want.contains(eid) || found.containsKey(eid)) continue
                    val home = ev.optJSONArray("T1")?.optJSONObject(0)?.optString("Nm") ?: "Home"
                    val away = ev.optJSONArray("T2")?.optJSONObject(0)?.optString("Nm") ?: "Away"
                    val comp = listOf(st.optString("Cnm"), st.optString("Snm")).filter { it.isNotEmpty() }.joinToString(" · ")
                    found[eid] = Ev(eid, ev.optString("Eps"), ev.optString("Tr1").toIntOrNull(), ev.optString("Tr2").toIntOrNull(), home, away, comp)
                }
            }
        }
        // goals / HT / FT
        for (ev in found.values) {
            if (ev.status == "NS" || ev.status.isEmpty() || ev.hg == null || ev.ag == null) continue
            val score = "${ev.hg}-${ev.ag}"
            val prev = prefs.getString("score_${ev.eid}", null)
            val changed = !Notifier.goalSeen(ctx, ev.eid, score)
            if (changed && prev != null && ev.hg + ev.ag > 0 && !isFinished(ev.status) && wantGoals) {
                val scorer = latestScorer(ev.eid)
                Notifier.notify(ctx, Notifier.CH_GOALS, ev.eid.hashCode(), "⚽ GOAL  ${ev.home} ${ev.hg} – ${ev.ag} ${ev.away}",
                    (if (scorer.isNotEmpty()) "$scorer · " else "") + "${ev.status} · ${ev.comp}", "live")
            }
            if (ev.status == "HT" && wantHt && !prefs.getBoolean("ht_${ev.eid}", false)) {
                prefs.edit().putBoolean("ht_${ev.eid}", true).apply()
                Notifier.notify(ctx, Notifier.CH_MATCH, 5000 + (ev.eid.hashCode() and 0xfff), "⏸ Half-time  ${ev.home} ${ev.hg} – ${ev.ag} ${ev.away}", ev.comp, "live")
            }
            if (isFinished(ev.status) && wantFt && !prefs.getBoolean("ft_${ev.eid}", false)) {
                prefs.edit().putBoolean("ft_${ev.eid}", true).apply()
                if (prev != null || prefs.getBoolean("ht_${ev.eid}", false))   // only for matches we were actually following
                    Notifier.notify(ctx, Notifier.CH_MATCH, 6000 + (ev.eid.hashCode() and 0xfff), "🏁 Full-time  ${ev.home} ${ev.hg} – ${ev.ag} ${ev.away}", ev.comp, "live")
            }
        }
        // tickets (goals markets only here; corners / cards are graded in the app from the match statistics)
        if (!wantFt) return
        for (i in 0 until tickets.length()) {
            val t = tickets.getJSONObject(i)
            val id = t.optString("id")
            if (id.isEmpty() || prefs.getBoolean("tk_$id", false)) continue
            val legs = t.optJSONArray("legs") ?: continue
            var lost = false; var allWon = legs.length() > 0
            val lines = ArrayList<String>()
            for (j in 0 until legs.length()) {
                val l = legs.getJSONObject(j)
                val ev = found[l.optString("eid")]
                val sel = l.optString("sel")
                val res: Boolean? = if (ev != null && isFinished(ev.status) && ev.hg != null && ev.ag != null) settle(sel, ev.hg, ev.ag) else if (ev != null && isVoid(ev.status)) true else null
                if (res == null) allWon = false else if (!res) { lost = true }
                lines.add((if (res == true) "✅ " else if (res == false) "❌ " else "⏳ ") + l.optString("label") + " (" + l.optString("home") + " v " + l.optString("away") + ")")
            }
            if (lost || allWon) {
                prefs.edit().putBoolean("tk_$id", true).apply()
                val odds = t.optDouble("odds", 0.0)
                val stake = t.optDouble("stake", 0.0)
                val title = if (lost) "❌ Ticket lost" else "🎉 Ticket won · odds ${"%.2f".format(odds)}" + if (stake > 0) " · return ${"%.2f".format(stake * odds)}" else ""
                Notifier.notify(ctx, Notifier.CH_BETS, 3000 + (id.hashCode() and 0xfff), title, lines.joinToString("\n"), "bets")
            }
        }
    }

    /** true / false, or null when the selection cannot be graded from goals alone. */
    private fun settle(sel: String, hg: Int, ag: Int): Boolean? {
        val tot = hg + ag
        fun line(s: String) = s.filter { it.isDigit() }.toInt() / 10.0
        return when {
            sel == "H" -> hg > ag; sel == "D" -> hg == ag; sel == "A" -> ag > hg
            sel == "1X" -> hg >= ag; sel == "12" -> hg != ag; sel == "X2" -> ag >= hg
            sel == "BTTS" -> hg > 0 && ag > 0; sel == "NBTTS" -> !(hg > 0 && ag > 0)
            Regex("^[OU]\\d+$").matches(sel) -> if (sel[0] == 'O') tot > line(sel) else tot < line(sel)
            Regex("^[HA][OU]\\d+$").matches(sel) -> { val g = if (sel[0] == 'H') hg else ag; if (sel[1] == 'O') g > line(sel) else g < line(sel) }
            else -> null
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
