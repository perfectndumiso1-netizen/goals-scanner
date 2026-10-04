package com.playreport.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The allowlist is what stops the WebView bridge from being an open proxy, so it is tested the way an
 * attacker would probe it: lookalike hosts, credentials in the URL, scheme downgrades, odd ports.
 */
class SecurityTest {

    @Test
    fun `allows exactly the hosts the app uses`() {
        assertTrue(Security.webAllowed("https://raw.githubusercontent.com/o/r/data/data/app/latest.json"))
        assertTrue(Security.webAllowed("https://api.github.com/repos/o/r/releases/latest"))
        assertTrue(Security.webAllowed("https://prod-public-api.livescore.com/v1/api/app/date/soccer/20261003/2?MD=1"))
        assertTrue(Security.webAllowed("https://lsm-static-prod.livescore.com/medium/enet/8699.png"))
        assertTrue(Security.nativeAllowed("https://github.com/o/r/releases/download/app-v1/PlayReport.apk"))
        assertTrue(Security.nativeAllowed("https://objects.githubusercontent.com/github-production-release-asset/x"))
    }

    @Test
    fun `rejects lookalike and unrelated hosts`() {
        assertFalse(Security.webAllowed("https://raw.githubusercontent.com.evil.com/x"))
        assertFalse(Security.webAllowed("https://evilraw.githubusercontent.com/x"))
        assertFalse(Security.webAllowed("https://gist.githubusercontent.com/x"))
        assertFalse(Security.webAllowed("https://raw.githubusercontent.com.attacker.net/logo.png"))
        assertFalse(Security.nativeAllowed("https://notgithub.com/o/r/releases/download/x.apk"))
    }

    @Test
    fun `rejects credentials in the url`() {
        assertFalse(Security.webAllowed("https://raw.githubusercontent.com@evil.com/x"))
        assertFalse(Security.webAllowed("https://user:pass@raw.githubusercontent.com/x"))
    }

    @Test
    fun `rejects non-https schemes and odd ports`() {
        assertFalse(Security.webAllowed("http://raw.githubusercontent.com/x"))
        assertFalse(Security.webAllowed("file:///etc/hosts"))
        assertFalse(Security.webAllowed("content://com.android.contacts/data"))
        assertFalse(Security.webAllowed("javascript:alert(1)"))
        assertFalse(Security.webAllowed("https://raw.githubusercontent.com:8443/x"))
        assertFalse(Security.webAllowed("https://raw.githubusercontent.com:80/x"))
        assertTrue(Security.webAllowed("https://raw.githubusercontent.com:443/x"))
    }

    @Test
    fun `rejects nonsense input`() {
        assertFalse(Security.webAllowed(null))
        assertFalse(Security.webAllowed(""))
        assertFalse(Security.webAllowed("   "))
        assertFalse(Security.webAllowed("https://"))
        assertFalse(Security.webAllowed("https:///path-only"))
    }

    @Test
    fun `sha256 matches the published digest of a file`() {
        val f = File.createTempFile("digest", ".bin")
        try {
            f.writeText("abc")
            assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", Security.sha256(f))
            f.writeText("abcd")
            assertFalse("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad".equals(Security.sha256(f), true))
        } finally {
            f.delete()
        }
        assertNull(Security.sha256(File("/does/not/exist/anywhere")))
    }
}
