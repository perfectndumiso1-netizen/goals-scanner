package com.playreport.app

/**
 * What the app is allowed to talk to, in one place.
 *
 * The app is a native shell around a bundled page, so every request is made by the shell on the page's
 * behalf. Without an allowlist that bridge is an open proxy: anything that can get script into the page
 * (a compromised data file, a future web view bug) could fetch arbitrary URLs through the app. Play Protect
 * also judges an app by what it can reach — an app that will fetch "anywhere from the internet" looks like a
 * downloader.
 *
 * Every entry is a host the bundled page genuinely uses. Nothing else resolves, at any layer.
 */
object Security {

    /** Hosts the page may fetch through the native bridge (data + live scores + crest images). */
    val WEB_HOSTS = setOf(
        "raw.githubusercontent.com",        // the published analysis (data branch)
        "api.github.com",                   // release check for the update banner
        "prod-public-api.livescore.com",    // live scores
        "lsm-static-prod.livescore.com",    // crest / badge images
    )

    /** Hosts the app itself may download from (the update flow). */
    val NATIVE_HOSTS = WEB_HOSTS + setOf("github.com", "objects.githubusercontent.com")

    /**
     * True when [url] is an https URL on one of [hosts].
     *
     * Deliberately strict: https only, no userinfo (`https://evil.com@raw.githubusercontent.com/…`), and the
     * host must match exactly — `raw.githubusercontent.com.evil.com` and `evilgithub.com` are both rejected.
     */
    fun allowed(url: String?, hosts: Set<String>): Boolean {
        val u = url?.trim() ?: return false
        if (!u.startsWith("https://", ignoreCase = true)) return false
        val rest = u.substring(8)
        if (rest.isEmpty() || rest.startsWith("/")) return false
        val authority = rest.substringBefore('/').substringBefore('?').substringBefore('#')
        if (authority.isEmpty() || authority.contains('@')) return false          // no credentials trickery
        if (authority.contains('\\')) return false
        val host = authority.substringBefore(':').lowercase()
        val port = authority.substringAfter(':', "")
        if (port.isNotEmpty() && port != "443") return false                      // https on a non-standard port
        return hosts.contains(host)
    }

    fun webAllowed(url: String?) = allowed(url, WEB_HOSTS)
    fun nativeAllowed(url: String?) = allowed(url, NATIVE_HOSTS)

    /**
     * SHA-256 of a file, or null when it cannot be read. GitHub publishes a digest for every release asset;
     * an APK that does not match it is not installed.
     */
    fun sha256(file: java.io.File): String? = try {
        val md = java.security.MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buf = ByteArray(64 * 1024)
            while (true) {
                val n = input.read(buf)
                if (n <= 0) break
                md.update(buf, 0, n)
            }
        }
        md.digest().joinToString("") { "%02x".format(it) }
    } catch (e: Exception) {
        null
    }
}
