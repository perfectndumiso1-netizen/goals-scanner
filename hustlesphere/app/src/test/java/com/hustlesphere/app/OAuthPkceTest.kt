package com.hustlesphere.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OAuthPkceTest {
    @Test
    fun verifierUsesRfc7636AllowedLengthAndCharacters() {
        val verifier = OAuthPkce.newVerifier()
        assertTrue(verifier.length in 43..128)
        assertTrue(verifier.all { it.isLetterOrDigit() || it in "-._~" })
    }

    @Test
    fun challengeIsBase64UrlEncodedSha256() {
        val verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        assertEquals("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM", OAuthPkce.challenge(verifier))
    }

    @Test
    fun generatedVerifiersAreNotReused() {
        assertNotEquals(OAuthPkce.newVerifier(), OAuthPkce.newVerifier())
    }
}
