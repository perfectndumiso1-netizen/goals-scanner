package com.hustlesphere.app

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Encrypts Supabase refresh/access tokens with a non-exportable Android Keystore AES key. */
internal class SecureSessionStore(context: Context) {
    private val preferences = context.getSharedPreferences("hustlesphere_secure_state", Context.MODE_PRIVATE)

    @Synchronized
    fun saveSession(session: AuthSession) {
        val value = JSONObject()
            .put("access_token", session.accessToken)
            .put("refresh_token", session.refreshToken)
            .put("user_id", session.userId)
            .put("email", session.email)
            .put("expires_at", session.expiresAtSeconds)
        preferences.edit().putString(SESSION_KEY, encrypt(value.toString())).commit()
    }

    @Synchronized
    fun readSession(): AuthSession? {
        val encrypted = preferences.getString(SESSION_KEY, null) ?: return null
        return try {
            val value = JSONObject(decrypt(encrypted))
            AuthSession(
                accessToken = value.getString("access_token"),
                refreshToken = value.optString("refresh_token"),
                userId = value.getString("user_id"),
                email = if (value.isNull("email")) null else value.optString("email"),
                expiresAtSeconds = value.optLong("expires_at")
            )
        } catch (_: Exception) {
            clearAll()
            null
        }
    }

    @Synchronized
    fun clearSession() {
        preferences.edit().remove(SESSION_KEY).commit()
    }

    @Synchronized
    fun savePendingOAuth(verifier: String) {
        preferences.edit().putString(OAUTH_KEY, encrypt(verifier)).commit()
    }

    @Synchronized
    fun readPendingOAuth(): String? {
        val encrypted = preferences.getString(OAUTH_KEY, null) ?: return null
        return try {
            decrypt(encrypted)
        } catch (_: Exception) {
            clearAll()
            null
        }
    }

    @Synchronized
    fun clearPendingOAuth() {
        preferences.edit().remove(OAUTH_KEY).commit()
    }

    @Synchronized
    private fun clearAll() {
        preferences.edit().clear().commit()
        runCatching {
            val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
            if (keyStore.containsAlias(KEY_ALIAS)) keyStore.deleteEntry(KEY_ALIAS)
        }
    }

    private fun encrypt(plainText: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        cipher.updateAAD(AAD)
        val encrypted = cipher.doFinal(plainText.toByteArray(Charsets.UTF_8))
        val iv = cipher.iv
        return Base64.encodeToString(iv + encrypted, Base64.NO_WRAP)
    }

    private fun decrypt(encoded: String): String {
        val combined = Base64.decode(encoded, Base64.NO_WRAP)
        require(combined.size > GCM_IV_LENGTH) { "Encrypted state is incomplete." }
        val iv = combined.copyOfRange(0, GCM_IV_LENGTH)
        val cipherText = combined.copyOfRange(GCM_IV_LENGTH, combined.size)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(GCM_TAG_BITS, iv))
        cipher.updateAAD(AAD)
        return cipher.doFinal(cipherText).toString(Charsets.UTF_8)
    }

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        val existing = keyStore.getKey(KEY_ALIAS, null) as? SecretKey
        if (existing != null) return existing

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build()
        )
        return generator.generateKey()
    }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val KEY_ALIAS = "com.hustlesphere.app.secure-state.v1"
        const val SESSION_KEY = "encrypted_session"
        const val OAUTH_KEY = "encrypted_oauth_verifier"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val GCM_IV_LENGTH = 12
        const val GCM_TAG_BITS = 128
        val AAD = "hustlesphere-session-v1".toByteArray(Charsets.UTF_8)
    }
}
