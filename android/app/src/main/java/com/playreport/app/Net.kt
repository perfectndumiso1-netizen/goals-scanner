package com.playreport.app

import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CompletableFuture
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

/** Minimal HTTP helpers shared by the WebView bridge, the background checker and the updater. */
object Net {
    const val UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

    /** Where the published analysis lives. Not shown anywhere in the UI. */
    val REPO: String = BuildConfig.REPO
    const val BRANCH = "data"
    val LATEST_JSON get() = "https://raw.githubusercontent.com/$REPO/$BRANCH/data/app/latest.json"
    val META_JSON get() = "https://raw.githubusercontent.com/$REPO/$BRANCH/data/app/meta.json"
    val ALERTS_JSON get() = "https://raw.githubusercontent.com/$REPO/$BRANCH/data/app/alerts.json"
    val RELEASES_LATEST get() = "https://api.github.com/repos/$REPO/releases/latest"

    data class Response(val code: Int, val body: String, val etag: String = "", val modified: String = "", val retryAfter: Long = 0)

    private val pending = ConcurrentHashMap<String, CompletableFuture<Response>>()

    fun get(url: String, userAgent: String = UA, accept: String = "application/json, text/plain, */*", etag: String? = null, modified: String? = null): Response {
        val key = listOf(url, userAgent, accept, etag ?: "", modified ?: "").joinToString("\n")
        val mine = CompletableFuture<Response>()
        val existing = pending.putIfAbsent(key, mine)
        if (existing != null) return try { existing.get(50, TimeUnit.SECONDS) } catch (_: Exception) { Response(0, "request timeout") }
        return try {
            val result = request(url, userAgent, accept, etag, modified)
            mine.complete(result); result
        } catch (_: Exception) {
            val result = Response(0, "network error"); mine.complete(result); result
        } finally { pending.remove(key, mine) }
    }

    private fun request(url: String, userAgent: String, accept: String, etag: String?, modified: String?): Response {
        if (!Security.nativeAllowed(url)) return Response(0, "blocked host")
        var conn: HttpURLConnection? = null
        return try {
            val connection = open(url, userAgent, accept)
            conn = connection
            if (!etag.isNullOrBlank()) connection.setRequestProperty("If-None-Match", etag)
            else if (!modified.isNullOrBlank()) connection.setRequestProperty("If-Modified-Since", modified)
            val code = connection.responseCode
            val stream = if (code == 304) null else if (code < 400) connection.inputStream else connection.errorStream
            val body = stream?.bufferedReader(Charsets.UTF_8)?.use { reader ->
                val text = StringBuilder(); val buffer = CharArray(8192)
                while (true) {
                    val count = reader.read(buffer); if (count < 0) break
                    if (text.length + count > 8 * 1024 * 1024) throw IllegalStateException("response too large")
                    text.append(buffer, 0, count)
                }
                text.toString()
            } ?: ""
            val retry = connection.getHeaderField("Retry-After")?.let { value ->
                value.toLongOrNull()?.times(1000) ?: try {
                    java.text.SimpleDateFormat("EEE, dd MMM yyyy HH:mm:ss zzz", java.util.Locale.US).parse(value)?.time?.minus(System.currentTimeMillis())
                } catch (_: Exception) { null }
            } ?: 0L
            val reset = connection.getHeaderField("X-RateLimit-Reset")?.toLongOrNull()?.times(1000)?.minus(System.currentTimeMillis()) ?: 0L
            val result = Response(code, body, connection.getHeaderField("ETag") ?: "", connection.getHeaderField("Last-Modified") ?: "", maxOf(0L, retry, if (code == 403 || code == 429) reset else 0L))
            result
        } catch (e: Exception) {
            Response(0, "network error")
        } finally { conn?.disconnect() }
    }

    fun download(url: String, target: File): Boolean {
        if (!Security.nativeAllowed(url)) return false
        return try {
            var conn = open(url, UA, "*/*")
            // GitHub release assets redirect to a different host; HttpURLConnection does not follow cross-host
            // redirects, so each hop is followed by hand — and each hop is allowlisted like the first, so a
            // redirect cannot walk the app off to somewhere the allowlist does not cover.
            var hops = 0
            while (conn.responseCode in 300..399 && hops < 5) {
                val loc = conn.getHeaderField("Location") ?: break
                conn.disconnect()
                if (!Security.nativeAllowed(loc)) return false
                conn = open(loc, UA, "*/*")
                hops++
            }
            if (conn.responseCode != 200) return false
            target.parentFile?.mkdirs()
            conn.inputStream.use { input -> target.outputStream().use { out -> input.copyTo(out) } }
            conn.disconnect()
            target.length() > 100_000
        } catch (e: Exception) {
            false
        }
    }

    private fun open(url: String, userAgent: String, accept: String): HttpURLConnection {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 15000
        conn.readTimeout = 30000
        conn.instanceFollowRedirects = true
        conn.setRequestProperty("User-Agent", userAgent)
        conn.setRequestProperty("Accept", accept)
        conn.setRequestProperty("Accept-Language", "en")
        return conn
    }
}
