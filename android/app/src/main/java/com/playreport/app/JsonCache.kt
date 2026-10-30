package com.playreport.app

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicLong

/** Public downloaded data only. Preferences/tickets remain in their existing stores.
 * All callers run on a bridge executor or WorkManager, never on the Android UI thread.
 * SQLite transactions atomically replace a whole resource; no cross-date row merges.
 */
class JsonCache(context: Context) : SQLiteOpenHelper(context, "published-cache.db", null, 1) {
    private val generation = AtomicLong(0)
    fun epoch(): Long = generation.get()
    fun invalidate(): Long = generation.incrementAndGet()

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE failures (url TEXT PRIMARY KEY, until_time INTEGER NOT NULL, code TEXT NOT NULL, count INTEGER NOT NULL)")
        db.execSQL("CREATE TABLE resources (url TEXT PRIMARY KEY, body TEXT NOT NULL, etag TEXT NOT NULL, modified TEXT NOT NULL, checked INTEGER NOT NULL, updated INTEGER NOT NULL, published TEXT NOT NULL, bytes INTEGER NOT NULL)")
    }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

    companion object {
        @Volatile private var instance: JsonCache? = null
        fun shared(context: Context): JsonCache = instance ?: synchronized(this) {
            instance ?: JsonCache(context.applicationContext).also { instance = it }
        }
        const val MAX_BYTES = 32L * 1024 * 1024
        const val MAX_ENTRY = 8 * 1024 * 1024
        fun validLatest(data: JSONObject): Boolean {
            val generated = data.optJSONObject("meta")?.optString("generated") ?: return false
            if (!generated.matches(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}.*")) || data.optInt("version") < 3) return false
            if (data.optJSONObject("safe") == null || data.optJSONObject("picks") == null ||
                data.optJSONObject("history") == null || data.optJSONArray("tracked") == null) return false
            val safe = data.getJSONObject("safe")
            if (safe.has("bets") && safe.optJSONArray("bets") == null) return false
            val bets = safe.optJSONArray("bets")
            if (bets != null) {
                val predictions = HashSet<String>()
                for (i in 0 until bets.length()) {
                    val id = bets.optJSONObject(i)?.optString("id") ?: return false
                    if (id.isBlank() || !predictions.add(id)) return false
                }
            }
            val fixtures = data.optJSONArray("fixtures") ?: return false
            if (fixtures.length() == 0) return false
            val ids = HashSet<String>()
            for (i in 0 until fixtures.length()) {
                val row = fixtures.optJSONObject(i) ?: return false
                val id = row.optString("id")
                if (id.isBlank() || !ids.add(id)) return false
                val sels = row.optJSONArray("sels")
                if (row.has("sels") && sels == null) return false
                if (sels != null) {
                    val markets = HashSet<String>()
                    for (s in 0 until sels.length()) {
                        val selection = sels.optJSONArray(s)?.optString(0) ?: sels.optJSONObject(s)?.optString("sel") ?: return false
                        if (selection.isBlank() || !markets.add(selection)) return false
                    }
                }
                val kickoff = row.optString("kickoff")
                if (kickoff.isNotBlank() && id.take(10) != kickoff.take(10)) return false
            }
            return true
        }
        fun allowed(url: String): Boolean = Security.webAllowed(url) &&
            (url.startsWith("https://raw.githubusercontent.com/${Net.REPO}/${Net.BRANCH}/data/app/") && url.endsWith(".json") ||
             url.startsWith("https://prod-public-api.livescore.com/v1/api/app/") ||
             url.matches(Regex("https://raw\\.githubusercontent\\.com/${Regex.escape(Net.REPO)}/${Net.BRANCH}/reports/[0-9]{4}-[0-9]{2}-[0-9]{2}\\.md")))
    }

    fun read(url: String): JSONObject? {
        if (!allowed(url)) return null
        val entry = readableDatabase.rawQuery("SELECT body,etag,modified,checked,updated,published FROM resources WHERE url=?", arrayOf(url)).use { c ->
            if (!c.moveToFirst()) null else JSONObject().put("body", c.getString(0)).put("etag", c.getString(1))
                .put("modified", c.getString(2)).put("checkedAt", c.getLong(3)).put("updatedAt", c.getLong(4)).put("published", c.getString(5))
        }
        return readableDatabase.rawQuery("SELECT until_time,code,count FROM failures WHERE url=?", arrayOf(url)).use { c ->
            if (!c.moveToFirst()) entry else (entry ?: JSONObject()).put("retryAt", c.getLong(0))
                .put("errorCode", c.getString(1).let { if (it == "invalid") it else it.toIntOrNull() ?: 0 }).put("failureCount", c.getInt(2))
        }
    }

    fun failure(url: String, value: JSONObject?) {
        if (!allowed(url)) return
        val db = writableDatabase
        if (value == null) { db.delete("failures", "url=?", arrayOf(url)); return }
        val row = ContentValues().apply {
            put("url", url); put("until_time", value.optLong("until")); put("code", value.optString("code")); put("count", value.optInt("count"))
        }
        db.insertWithOnConflict("failures", null, row, SQLiteDatabase.CONFLICT_REPLACE)
        // Failure-only URLs cannot grow an unbounded negative-cache database.
        db.execSQL("DELETE FROM failures WHERE url NOT IN (SELECT url FROM failures ORDER BY until_time DESC LIMIT 300)")
    }

    fun put(url: String, entry: JSONObject, expectedEpoch: Long = epoch()): Boolean {
        if (!allowed(url)) return false
        val body = entry.optString("body")
        val bytes = body.toByteArray(Charsets.UTF_8).size
        if (body.isBlank() || bytes > MAX_ENTRY || entry.optLong("checkedAt") <= 0) return false
        // Store JSON only, never an HTML error page. Domain-specific checks also run before this call.
        val data = try { JSONObject(body) } catch (_: Exception) { return false }
        if (url == Net.LATEST_JSON && !validLatest(data)) return false
        val published = data.optJSONObject("meta")?.optString("generated") ?: data.optString("generated")
        val db = writableDatabase
        db.beginTransaction()
        try {
            if (expectedEpoch != epoch()) return false
            val old = db.rawQuery("SELECT published FROM resources WHERE url=?", arrayOf(url)).use { if (it.moveToFirst()) it.getString(0) else "" }
            if (published.isNotBlank() && old.isNotBlank() && published < old) return false
            val values = ContentValues().apply {
                put("url", url); put("body", body); put("etag", entry.optString("etag")); put("modified", entry.optString("modified"))
                put("published", published); put("checked", entry.getLong("checkedAt")); put("updated", entry.getLong("updatedAt")); put("bytes", bytes)
            }
            if (db.insertWithOnConflict("resources", null, values, SQLiteDatabase.CONFLICT_REPLACE) == -1L) return false
            var total = db.rawQuery("SELECT COALESCE(SUM(bytes),0) FROM resources", null).use { it.moveToFirst(); it.getLong(0) }
            db.rawQuery("SELECT url,bytes FROM resources WHERE url<>? AND url<>? ORDER BY checked ASC", arrayOf(url, Net.LATEST_JSON)).use { c ->
                while (total > MAX_BYTES && c.moveToNext()) {
                    db.delete("resources", "url=?", arrayOf(c.getString(0))); total -= c.getLong(1)
                }
            }
            db.setTransactionSuccessful(); return true
        } finally { db.endTransaction() }
    }

    fun touch(url: String, checked: Long, etag: String? = null, modified: String? = null): Boolean {
        val values = ContentValues().apply {
            put("checked", checked)
            if (etag != null) put("etag", etag)
            if (modified != null) put("modified", modified)
        }
        return writableDatabase.update("resources", values, "url=?", arrayOf(url)) > 0
    }
    fun clear(expectedEpoch: Long = invalidate()) {
        val db = writableDatabase
        db.beginTransaction()
        try {
            if (expectedEpoch != epoch()) return
            db.delete("resources", null, null); db.delete("failures", null, null)
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
    }
}
