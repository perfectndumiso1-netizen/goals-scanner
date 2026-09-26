package com.playreport.app

import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File

/** Checks the release feed for a newer build, downloads it and hands it to the system installer. */
object Updater {
    data class Info(val version: String, val url: String, val notes: String)

    fun check(): Info? {
        val r = Net.get(Net.RELEASES_LATEST, accept = "application/vnd.github+json")
        if (r.code != 200) return null
        return try {
            val o = JSONObject(r.body)
            val tag = o.optString("tag_name")
            val version = tag.removePrefix("app-v").removePrefix("v")
            var url = ""
            val assets = o.optJSONArray("assets")
            if (assets != null) for (i in 0 until assets.length()) {
                val a = assets.getJSONObject(i)
                if (a.optString("name").endsWith(".apk")) { url = a.optString("browser_download_url"); break }
            }
            if (url.isEmpty() || version.isEmpty()) null else Info(version, url, o.optString("body"))
        } catch (e: Exception) {
            null
        }
    }

    fun isNewer(candidate: String, current: String): Boolean {
        val a = candidate.split(".").map { it.filter(Char::isDigit).toIntOrNull() ?: 0 }
        val b = current.split(".").map { it.filter(Char::isDigit).toIntOrNull() ?: 0 }
        for (i in 0 until maxOf(a.size, b.size)) {
            val x = a.getOrElse(i) { 0 }
            val y = b.getOrElse(i) { 0 }
            if (x != y) return x > y
        }
        return false
    }

    fun apkFile(ctx: Context) = File(ctx.cacheDir, "updates/PlayReport.apk")

    fun download(ctx: Context, url: String): File? {
        val f = apkFile(ctx)
        if (f.exists()) f.delete()
        return if (Net.download(url, f)) f else null
    }

    fun install(ctx: Context, file: File) {
        val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", file)
        val i = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION
        }
        ctx.startActivity(i)
    }
}
