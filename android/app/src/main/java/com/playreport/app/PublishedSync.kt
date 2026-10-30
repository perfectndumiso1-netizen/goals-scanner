package com.playreport.app

import android.content.Context
import org.json.JSONObject

/** Warm the very same SQLite snapshot used by the UI, within the existing connected 15-minute worker.
 * The tiny heartbeat is the publication version check; no extra scheduler or background service.
 */
object PublishedSync {
    fun heartbeat(context: Context): Net.Response {
        val cache = JsonCache.shared(context)
        val prefs = context.getSharedPreferences(Notifier.PREFS, Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        if (now < prefs.getLong("cache_meta_after", 0)) return Net.Response(0, "cooldown")
        val saved = try { cache.read(Net.META_JSON) } catch (_: Exception) { null }
        val response = Net.get(Net.META_JSON, etag = saved?.optString("etag"), modified = saved?.optString("modified"))
        if (response.code == 304 && saved != null) return Net.Response(200, saved.getString("body"))
        if (response.code == 200) {
            val meta = try { JSONObject(response.body) } catch (_: Exception) { null }
            if (meta != null && meta.optString("generated").isNotBlank()) {
                try {
                    if (saved?.optString("body") == response.body) cache.touch(Net.META_JSON, now, response.etag, response.modified)
                    else cache.put(Net.META_JSON, JSONObject().put("body", response.body).put("etag", response.etag)
                        .put("modified", response.modified).put("checkedAt", now).put("updatedAt", now))
                } catch (_: Exception) { /* heartbeat/notifications do not require successful persistence */ }
            }
        } else if (response.code == 403 || response.code == 429) {
            prefs.edit().putLong("cache_meta_after", now + maxOf(15 * 60000L, response.retryAfter).coerceAtMost(24 * 3600000L)).apply()
        }
        return response
    }

    fun refresh(context: Context, meta: JSONObject) {
        val version = meta.optString("generated")
        if (version.isBlank()) return
        val prefs = context.getSharedPreferences(Notifier.PREFS, Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        if (now < prefs.getLong("cache_sync_after", 0)) return
        val cache = JsonCache.shared(context)
        run {
            val saved = cache.read(Net.LATEST_JSON)
            if ((saved?.optLong("retryAt") ?: 0) > now) return
            if (saved != null && saved.optString("published") == version) {
                cache.touch(Net.LATEST_JSON, now); cache.failure(Net.LATEST_JSON, null); return
            }
            val result = Net.get(Net.LATEST_JSON, etag = saved?.optString("etag"), modified = saved?.optString("modified"))
            if (result.code == 304 && saved != null) { cache.touch(Net.LATEST_JSON, now); cache.failure(Net.LATEST_JSON, null); return }
            if (result.code == 200) {
                val data = try { JSONObject(result.body) } catch (_: Exception) { null }
                if (data != null && JsonCache.validLatest(data)) {
                    if (saved?.optString("body") == result.body) cache.touch(Net.LATEST_JSON, now, result.etag, result.modified)
                    else cache.put(Net.LATEST_JSON, JSONObject().put("body", result.body).put("etag", result.etag)
                        .put("modified", result.modified).put("checkedAt", now).put("updatedAt", now))
                    cache.failure(Net.LATEST_JSON, null)
                    return
                }
            }
            // Persist cooldown across worker/process restarts; never erase the good snapshot on failure.
            val delay = maxOf(15 * 60000L, result.retryAfter).coerceAtMost(24 * 3600000L)
            cache.failure(Net.LATEST_JSON, JSONObject().put("until", now + delay).put("code", result.code).put("count", 1))
            prefs.edit().putLong("cache_sync_after", now + delay).apply()
        }
    }
}
