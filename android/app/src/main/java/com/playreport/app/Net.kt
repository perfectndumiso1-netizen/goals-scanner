package com.playreport.app

import java.io.BufferedReader
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

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

    data class Response(val code: Int, val body: String)

    fun get(url: String, userAgent: String = UA, accept: String = "application/json, text/plain, */*"): Response {
        return try {
            val conn = open(url, userAgent, accept)
            val code = conn.responseCode
            val stream = if (code < 400) conn.inputStream else conn.errorStream
            val body = stream?.bufferedReader(Charsets.UTF_8)?.use(BufferedReader::readText) ?: ""
            conn.disconnect()
            Response(code, body)
        } catch (e: Exception) {
            Response(0, e.message ?: "network error")
        }
    }

    fun download(url: String, target: File): Boolean {
        return try {
            var conn = open(url, UA, "*/*")
            // GitHub release assets redirect to a different host; HttpURLConnection does not follow cross-host redirects
            var hops = 0
            while (conn.responseCode in 300..399 && hops < 5) {
                val loc = conn.getHeaderField("Location") ?: break
                conn.disconnect()
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
