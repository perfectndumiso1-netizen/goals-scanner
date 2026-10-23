package com.hustlesphere.app

import java.util.Base64
import java.security.MessageDigest
import java.security.SecureRandom

/** RFC 7636 S256 PKCE helper used for Supabase's browser-based Google OAuth flow. */
internal object OAuthPkce {
    private val secureRandom = SecureRandom()

    fun newVerifier(): String {
        val randomBytes = ByteArray(32)
        secureRandom.nextBytes(randomBytes)
        return Base64.getUrlEncoder().withoutPadding().encodeToString(randomBytes)
    }

    fun challenge(verifier: String): String {
        require(verifier.length in 43..128) { "PKCE verifier must contain 43 to 128 characters." }
        require(verifier.all { it.isLetterOrDigit() || it in "-._~" }) { "PKCE verifier contains an invalid character." }
        val digest = MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII))
        return Base64.getUrlEncoder().withoutPadding().encodeToString(digest)
    }
}
