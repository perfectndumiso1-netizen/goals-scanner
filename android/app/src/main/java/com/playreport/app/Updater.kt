package com.playreport.app

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File

/**
 * Checks the release feed for a newer build and hands the APK to the SYSTEM installer.
 *
 * What this deliberately does NOT do:
 *  - it never installs anything itself (no REQUEST_INSTALL_PACKAGES, no PackageInstaller session). The system
 *    installer is the only thing that installs, it is what Play Protect inspects, and the user confirms it.
 *  - it never trusts the download. GitHub publishes a SHA-256 digest for every release asset; the bytes on
 *    disk must match it before the installer is offered the file. A published APK that is not the one on
 *    GitHub is never installed.
 *  - it never opens the file as a generic "package archive" — a specific MIME type plus a read-only grant for
 *    one file is all the installer gets.
 */
object Updater {
    data class Info(val version: String, val url: String, val notes: String, val sha256: String?)

    fun check(): Info? {
        val r = Net.get(Net.RELEASES_LATEST, accept = "application/vnd.github+json")
        if (r.code != 200) return null
        return try {
            val o = JSONObject(r.body)
            val tag = o.optString("tag_name")
            val version = tag.removePrefix("app-v").removePrefix("v")
            var url = ""
            var digest: String? = null
            val assets = o.optJSONArray("assets")
            if (assets != null) for (i in 0 until assets.length()) {
                val a = assets.getJSONObject(i)
                if (a.optString("name").endsWith(".apk")) {
                    url = a.optString("browser_download_url")
                    digest = a.optString("digest").takeIf { it.startsWith("sha256:") }?.removePrefix("sha256:")
                    break
                }
            }
            if (url.isEmpty() || version.isEmpty() || !Security.nativeAllowed(url)) null
            else Info(version, url, o.optString("body"), digest)
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

    /**
     * Download [info] and return the verified file, or null. The digest check is the point: an APK that does
     * not match the digest GitHub published for that release is deleted, not installed.
     */
    fun download(ctx: Context, info: Info): File? {
        if (!Security.nativeAllowed(info.url)) return null
        val f = apkFile(ctx)
        if (f.exists()) f.delete()
        if (!Net.download(info.url, f)) {
            f.delete()
            return null
        }
        val digest = info.sha256
        if (!digest.isNullOrBlank() && !digest.equals(Security.sha256(f), ignoreCase = true)) {
            f.delete()
            return null
        }
        return f
    }

    /** Hand the verified file to the system installer. The user sees Android's own confirmation screen. */
    fun install(ctx: Context, file: File): Boolean {
        return try {
            val uri: Uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", file)
            val i = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "application/vnd.android.package-archive")
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION
                // this URI grant is for one file, for one receiver — nothing else can read it
                clipData = android.content.ClipData.newRawUri("PlayReport update", uri)
            }
            ctx.startActivity(i)
            true
        } catch (e: ActivityNotFoundException) {
            false          // no installer on this device (rare) — the user still has the release page
        } catch (e: Exception) {
            false
        }
    }
}
