package com.hustlesphere.app

import android.content.Context
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.URLEncoder
import java.net.URL
import java.net.URI
import java.time.Instant
import javax.net.ssl.HttpsURLConnection

internal data class AuthSession(
    val accessToken: String,
    val refreshToken: String,
    val userId: String,
    val email: String?,
    val expiresAtSeconds: Long
)

internal data class MemberProfile(
    val id: String,
    val username: String,
    val displayName: String,
    val bio: String,
    val visibility: String,
    val updatedAt: String = ""
)

internal data class FeedPost(
    val id: String,
    val authorId: String,
    val username: String,
    val displayName: String,
    val category: String,
    val body: String,
    val createdAt: String,
    val likeCount: Int,
    val commentCount: Int,
    val likedByMe: Boolean
)

internal data class CommentItem(
    val id: String,
    val postId: String,
    val authorId: String,
    val username: String,
    val displayName: String,
    val body: String,
    val createdAt: String
)

internal data class MemberSummary(
    val id: String,
    val username: String,
    val displayName: String,
    val bio: String = ""
)

internal data class MessageRequestItem(
    val id: String,
    val senderId: String,
    val recipientId: String,
    val status: String,
    val createdAt: String,
    val sender: MemberSummary?,
    val recipient: MemberSummary?
)

internal data class ConversationItem(
    val id: String,
    val userA: String,
    val userB: String,
    val otherMember: MemberSummary?,
    val createdAt: String
)

internal data class ChatMessage(
    val id: String,
    val conversationId: String,
    val senderId: String,
    val body: String,
    val createdAt: String
)

internal data class AppNotification(
    val id: String,
    val kind: String,
    val body: String,
    val actorName: String,
    val readAt: String?,
    val createdAt: String
)

internal data class AuthResult(val session: AuthSession?, val emailConfirmationRequired: Boolean)

internal class SupabaseApiException(val status: Int?, message: String) : Exception(message)

/** Minimal HTTPS REST/Auth client. All authorization is enforced by Supabase Auth + RLS. */
internal class SupabaseRepository(context: Context) {
    private val store = SecureSessionStore(context.applicationContext)
    private val baseUrl = BuildConfig.SUPABASE_URL.trim().trimEnd('/')
    private val anonKey = BuildConfig.SUPABASE_ANON_KEY.trim()

    val isConfigured: Boolean
        get() = runCatching {
            val uri = URI(baseUrl)
            uri.scheme.equals("https", ignoreCase = true) &&
                !uri.host.isNullOrBlank() &&
                uri.userInfo == null &&
                uri.rawQuery == null &&
                uri.rawFragment == null &&
                (uri.path.isNullOrEmpty() || uri.path == "/") &&
                anonKey.matches(Regex("^[A-Za-z0-9._-]+$"))
        }.getOrDefault(false)

    suspend fun restoreSession(): AuthSession? = withContext(Dispatchers.IO) {
        refreshSessionIfNeeded()
    }

    suspend fun signUp(email: String, password: String, displayName: String): AuthResult {
        validateConfiguration()
        val body = JSONObject()
            .put("email", email.trim())
            .put("password", password)
            .put("data", JSONObject().put("name", displayName.trim()))
        val raw = publicAuthRequest("auth/v1/signup", body)
        val session = parseSession(raw, null)
        if (session != null) store.saveSession(session)
        return AuthResult(session, session == null)
    }

    suspend fun signIn(email: String, password: String): AuthSession {
        validateConfiguration()
        val raw = publicAuthRequest(
            "auth/v1/token?grant_type=password",
            JSONObject().put("email", email.trim()).put("password", password)
        )
        val session = parseSession(raw, null)
            ?: throw SupabaseApiException(null, "Sign-in did not return a session. Check your email confirmation status.")
        store.saveSession(session)
        return session
    }

    suspend fun signOut() {
        runCatching { authenticatedRequest("auth/v1/logout", "POST", JSONObject()) }
        store.clearSession()
        store.clearPendingOAuth()
    }

    suspend fun createGoogleOAuthUri(): Uri = withContext(Dispatchers.IO) {
        validateConfiguration()
        val verifier = OAuthPkce.newVerifier()
        val challenge = OAuthPkce.challenge(verifier)
        store.savePendingOAuth(verifier)
        val redirect = URLEncoder.encode(OAUTH_REDIRECT_URI, Charsets.UTF_8.name())
        val url = "$baseUrl/auth/v1/authorize?provider=google" +
            "&redirect_to=$redirect" +
            "&code_challenge=$challenge" +
            "&code_challenge_method=s256"
        Uri.parse(url)
    }

    suspend fun finishGoogleOAuth(callback: Uri): AuthSession {
        validateConfiguration()
        if (callback.scheme != "hustlesphere" || callback.host != "auth-callback") {
            throw SupabaseApiException(null, "Unexpected sign-in callback.")
        }
        val oauthError = callback.getQueryParameter("error_description")
            ?: callback.getQueryParameter("error")
        if (!oauthError.isNullOrBlank()) {
            store.clearPendingOAuth()
            throw SupabaseApiException(null, oauthError)
        }
        val code = callback.getQueryParameter("code")
            ?: throw SupabaseApiException(null, "Google sign-in did not return an authorization code.")
        val verifier = store.readPendingOAuth()
            ?: throw SupabaseApiException(null, "The sign-in session expired. Please try Google sign-in again.")
        val raw = publicAuthRequest(
            "auth/v1/token?grant_type=pkce",
            JSONObject().put("auth_code", code).put("code_verifier", verifier)
        )
        val session = parseSession(raw, null)
            ?: throw SupabaseApiException(null, "Google sign-in did not return a session.")
        store.saveSession(session)
        store.clearPendingOAuth()
        return session
    }

    suspend fun loadMyProfile(): MemberProfile {
        val userId = requireUserId()
        val raw = authenticatedRequest(
            "rest/v1/profiles?select=id,username,display_name,bio,visibility,updated_at&id=eq.$userId&limit=1"
        )
        val row = JSONArray(raw).optJSONObject(0)
            ?: throw SupabaseApiException(null, "Your profile is not ready yet. Try refreshing in a moment.")
        return row.toProfile()
    }

    suspend fun saveProfile(username: String, displayName: String, bio: String, visibility: String) {
        val userId = requireUserId()
        val payload = JSONObject()
            .put("username", username.trim().lowercase())
            .put("display_name", displayName.trim())
            .put("bio", bio.trim())
            .put("visibility", visibility)
        authenticatedRequest(
            "rest/v1/profiles?id=eq.$userId",
            "PATCH",
            payload,
            mapOf("Prefer" to "return=minimal")
        )
    }

    suspend fun discoverMembers(): List<MemberSummary> {
        val raw = authenticatedRequest(
            "rest/v1/profiles?select=id,username,display_name,bio&visibility=eq.public&order=display_name.asc&limit=200"
        )
        return JSONArray(raw).toMemberList()
    }

    suspend fun loadFeed(category: String = "All"): List<FeedPost> {
        val filter = if (category == "All") "" else "&category=eq.${queryValue(category)}"
        val raw = authenticatedRequest(
            "rest/v1/post_feed?select=id,author_id,username,display_name,category,body,created_at,like_count,comment_count,liked_by_me" +
                "$filter&order=created_at.desc&limit=100"
        )
        val rows = JSONArray(raw)
        return List(rows.length()) { index -> rows.getJSONObject(index).toFeedPost() }
    }

    suspend fun createPost(authorId: String, category: String, body: String) {
        authenticatedRequest(
            "rest/v1/posts",
            "POST",
            JSONObject().put("author_id", authorId).put("category", category).put("body", body.trim()),
            mapOf("Prefer" to "return=minimal")
        )
    }

    suspend fun deletePost(postId: String) {
        authenticatedRequest("rest/v1/posts?id=eq.$postId", "DELETE")
    }

    suspend fun toggleLike(post: FeedPost, userId: String) {
        if (post.likedByMe) {
            authenticatedRequest(
                "rest/v1/post_likes?post_id=eq.${post.id}&user_id=eq.$userId",
                "DELETE"
            )
        } else {
            authenticatedRequest(
                "rest/v1/post_likes?on_conflict=post_id,user_id",
                "POST",
                JSONObject().put("post_id", post.id).put("user_id", userId),
                mapOf("Prefer" to "resolution=ignore-duplicates,return=minimal")
            )
        }
    }

    suspend fun loadComments(postId: String): List<CommentItem> {
        val raw = authenticatedRequest(
            "rest/v1/comments?select=id,post_id,author_id,body,created_at,author:profiles!comments_author_id_fkey(username,display_name)" +
                "&post_id=eq.$postId&order=created_at.asc&limit=100"
        )
        val rows = JSONArray(raw)
        return List(rows.length()) { index ->
            val row = rows.getJSONObject(index)
            val author = row.optJSONObject("author")
            CommentItem(
                id = row.optString("id"),
                postId = row.optString("post_id"),
                authorId = row.optString("author_id"),
                username = author?.optString("username").orEmpty(),
                displayName = author?.optString("display_name").orEmpty(),
                body = row.optString("body"),
                createdAt = row.optString("created_at")
            )
        }
    }

    suspend fun addComment(postId: String, authorId: String, body: String) {
        authenticatedRequest(
            "rest/v1/comments",
            "POST",
            JSONObject().put("post_id", postId).put("author_id", authorId).put("body", body.trim()),
            mapOf("Prefer" to "return=minimal")
        )
    }

    suspend fun sendMessageRequest(recipientId: String): String {
        val raw = authenticatedRequest(
            "rest/v1/rpc/hustlesphere_send_message_request",
            "POST",
            JSONObject().put("p_recipient_id", recipientId)
        )
        return raw.trim().trim('"')
    }

    suspend fun loadMessageRequests(userId: String): List<MessageRequestItem> {
        val select = "id,sender_id,recipient_id,status,created_at," +
            "sender:profiles!message_requests_sender_id_fkey(id,username,display_name)," +
            "recipient:profiles!message_requests_recipient_id_fkey(id,username,display_name)"
        val raw = authenticatedRequest(
            "rest/v1/message_requests?select=$select&or=(sender_id.eq.$userId,recipient_id.eq.$userId)&order=created_at.desc&limit=100"
        )
        val rows = JSONArray(raw)
        return List(rows.length()) { index ->
            val row = rows.getJSONObject(index)
            MessageRequestItem(
                id = row.optString("id"),
                senderId = row.optString("sender_id"),
                recipientId = row.optString("recipient_id"),
                status = row.optString("status"),
                createdAt = row.optString("created_at"),
                sender = row.optJSONObject("sender")?.toMemberSummary(),
                recipient = row.optJSONObject("recipient")?.toMemberSummary()
            )
        }
    }

    suspend fun acceptMessageRequest(requestId: String) {
        authenticatedRequest(
            "rest/v1/rpc/hustlesphere_accept_message_request",
            "POST",
            JSONObject().put("p_request_id", requestId)
        )
    }

    suspend fun declineMessageRequest(requestId: String) {
        authenticatedRequest(
            "rest/v1/rpc/hustlesphere_decline_message_request",
            "POST",
            JSONObject().put("p_request_id", requestId)
        )
    }

    suspend fun loadConversations(userId: String): List<ConversationItem> {
        val select = "id,user_a,user_b,created_at," +
            "profile_a:profiles!conversations_user_a_fkey(id,username,display_name)," +
            "profile_b:profiles!conversations_user_b_fkey(id,username,display_name)"
        val raw = authenticatedRequest(
            "rest/v1/conversations?select=$select&or=(user_a.eq.$userId,user_b.eq.$userId)&order=created_at.desc&limit=100"
        )
        val rows = JSONArray(raw)
        return List(rows.length()) { index ->
            val row = rows.getJSONObject(index)
            val userA = row.optString("user_a")
            val userB = row.optString("user_b")
            val profileA = row.optJSONObject("profile_a")?.toMemberSummary()
            val profileB = row.optJSONObject("profile_b")?.toMemberSummary()
            ConversationItem(
                id = row.optString("id"),
                userA = userA,
                userB = userB,
                otherMember = if (userA == userId) profileB else profileA,
                createdAt = row.optString("created_at")
            )
        }
    }

    suspend fun loadMessages(conversationId: String): List<ChatMessage> {
        val raw = authenticatedRequest(
            "rest/v1/messages?select=id,conversation_id,sender_id,body,created_at" +
                "&conversation_id=eq.$conversationId&order=created_at.asc&limit=200"
        )
        val rows = JSONArray(raw)
        return List(rows.length()) { index ->
            val row = rows.getJSONObject(index)
            ChatMessage(
                id = row.optString("id"),
                conversationId = row.optString("conversation_id"),
                senderId = row.optString("sender_id"),
                body = row.optString("body"),
                createdAt = row.optString("created_at")
            )
        }
    }

    suspend fun sendMessage(conversationId: String, senderId: String, body: String) {
        authenticatedRequest(
            "rest/v1/messages",
            "POST",
            JSONObject().put("conversation_id", conversationId).put("sender_id", senderId).put("body", body.trim()),
            mapOf("Prefer" to "return=minimal")
        )
    }

    suspend fun loadNotifications(userId: String): List<AppNotification> {
        val raw = authenticatedRequest(
            "rest/v1/notifications?select=id,kind,body,read_at,created_at,actor:profiles!notifications_actor_id_fkey(username,display_name)" +
                "&recipient_id=eq.$userId&order=created_at.desc&limit=100"
        )
        val rows = JSONArray(raw)
        return List(rows.length()) { index ->
            val row = rows.getJSONObject(index)
            val actor = row.optJSONObject("actor")
            val actorName = actor?.optString("display_name")?.takeIf { it.isNotBlank() }
                ?: actor?.optString("username")?.takeIf { it.isNotBlank() }
                ?: "A member"
            AppNotification(
                id = row.optString("id"),
                kind = row.optString("kind"),
                body = row.optString("body"),
                actorName = actorName,
                readAt = row.nullableString("read_at"),
                createdAt = row.optString("created_at")
            )
        }
    }

    suspend fun markNotificationRead(notificationId: String) {
        authenticatedRequest(
            "rest/v1/notifications?id=eq.$notificationId",
            "PATCH",
            JSONObject().put("read_at", Instant.now().toString()),
            mapOf("Prefer" to "return=minimal")
        )
    }

    suspend fun loadBlockedIds(userId: String): Set<String> {
        val raw = authenticatedRequest(
            "rest/v1/blocks?select=blocked_id&blocker_id=eq.$userId&limit=500"
        )
        val rows = JSONArray(raw)
        return buildSet { for (index in 0 until rows.length()) add(rows.getJSONObject(index).optString("blocked_id")) }
    }

    suspend fun blockMember(memberId: String, userId: String) {
        authenticatedRequest(
            "rest/v1/blocks?on_conflict=blocker_id,blocked_id",
            "POST",
            JSONObject().put("blocker_id", userId).put("blocked_id", memberId),
            mapOf("Prefer" to "resolution=ignore-duplicates,return=minimal")
        )
    }

    suspend fun unblockMember(memberId: String, userId: String) {
        authenticatedRequest(
            "rest/v1/blocks?blocker_id=eq.$userId&blocked_id=eq.$memberId",
            "DELETE"
        )
    }

    suspend fun submitReport(
        reporterId: String,
        reason: String,
        targetUserId: String? = null,
        postId: String? = null,
        commentId: String? = null
    ) {
        val payload = JSONObject().put("reporter_id", reporterId).put("reason", reason.trim())
        targetUserId?.let { payload.put("target_user_id", it) }
        postId?.let { payload.put("post_id", it) }
        commentId?.let { payload.put("comment_id", it) }
        authenticatedRequest("rest/v1/reports", "POST", payload, mapOf("Prefer" to "return=minimal"))
    }

    suspend fun deleteMyAccount() {
        authenticatedRequest("functions/v1/delete-account", "POST", JSONObject())
        store.clearSession()
        store.clearPendingOAuth()
    }

    private fun requireUserId(): String = store.readSession()?.userId
        ?: throw SupabaseApiException(401, "Please sign in again.")

    private suspend fun publicAuthRequest(path: String, payload: JSONObject): String {
        validateConfiguration()
        return withContext(Dispatchers.IO) {
            executeBlocking(path, "POST", payload, null, emptyMap())
        }
    }

    private suspend fun authenticatedRequest(
        path: String,
        method: String = "GET",
        payload: JSONObject? = null,
        headers: Map<String, String> = emptyMap()
    ): String {
        validateConfiguration()
        return withContext(Dispatchers.IO) {
            val session = refreshSessionIfNeeded()
                ?: throw SupabaseApiException(401, "Please sign in again.")
            executeBlocking(path, method, payload, session.accessToken, headers)
        }
    }

    private fun refreshSessionIfNeeded(): AuthSession? {
        val current = store.readSession() ?: return null
        if (current.expiresAtSeconds > Instant.now().epochSecond + 60) return current
        if (current.refreshToken.isBlank()) {
            store.clearSession()
            return null
        }
        return try {
            val raw = executeBlocking(
                "auth/v1/token?grant_type=refresh_token",
                "POST",
                JSONObject().put("refresh_token", current.refreshToken),
                null,
                emptyMap()
            )
            val refreshed = parseSession(raw, current)
                ?: throw SupabaseApiException(null, "Session refresh returned no access token.")
            store.saveSession(refreshed)
            refreshed
        } catch (error: SupabaseApiException) {
            if (error.status != null && error.status in 400..499) store.clearSession()
            if (error.status == null || error.status >= 500) current else null
        } catch (_: Exception) {
            // A transient network failure should not erase a still-usable local session.
            current
        }
    }

    private fun executeBlocking(
        path: String,
        method: String,
        payload: JSONObject?,
        accessToken: String?,
        headers: Map<String, String>
    ): String {
        validateConfiguration()
        if (path.startsWith("/") || path.contains("..")) {
            throw SupabaseApiException(null, "Invalid API route.")
        }
        val connection = (URL("$baseUrl/$path").openConnection() as HttpsURLConnection).apply {
            requestMethod = method
            connectTimeout = 15_000
            readTimeout = 25_000
            instanceFollowRedirects = false
            setRequestProperty("apikey", anonKey)
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            if (!accessToken.isNullOrBlank()) setRequestProperty("Authorization", "Bearer $accessToken")
            headers.forEach { (name, value) -> setRequestProperty(name, value) }
        }
        try {
            if (payload != null) {
                connection.doOutput = true
                connection.outputStream.use { stream -> stream.write(payload.toString().toByteArray(Charsets.UTF_8)) }
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val response = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (status !in 200..299) {
                throw SupabaseApiException(status, parseErrorMessage(response, status))
            }
            return response
        } finally {
            connection.disconnect()
        }
    }

    private fun parseSession(raw: String, previous: AuthSession?): AuthSession? {
        if (raw.isBlank()) return null
        val response = runCatching { JSONObject(raw) }.getOrNull() ?: return null
        val accessToken = response.optString("access_token").takeIf { it.isNotBlank() } ?: return null
        val refreshToken = response.optString("refresh_token").takeIf { it.isNotBlank() }
            ?: previous?.refreshToken.orEmpty()
        val user = response.optJSONObject("user")
        val userId = user?.optString("id")?.takeIf { it.isNotBlank() } ?: previous?.userId ?: return null
        val email = user?.nullableString("email") ?: previous?.email
        val expiresAt = response.optLong("expires_at").takeIf { it > 0 }
            ?: (Instant.now().epochSecond + response.optLong("expires_in", 3600))
        return AuthSession(accessToken, refreshToken, userId, email, expiresAt)
    }

    private fun parseErrorMessage(body: String, status: Int): String {
        val json = runCatching { JSONObject(body) }.getOrNull()
        val message = json?.optString("msg")?.takeIf { it.isNotBlank() }
            ?: json?.optString("message")?.takeIf { it.isNotBlank() }
            ?: json?.optString("error_description")?.takeIf { it.isNotBlank() }
            ?: json?.optString("error")?.takeIf { it.isNotBlank() }
        return message?.take(500) ?: "Supabase request failed (HTTP $status)."
    }

    private fun validateConfiguration() {
        if (!isConfigured) {
            throw SupabaseApiException(
                null,
                "Supabase is not configured. Add SUPABASE_URL and SUPABASE_ANON_KEY at build time."
            )
        }
    }

    private fun queryValue(value: String): String = URLEncoder.encode(value, Charsets.UTF_8.name())

    private fun JSONObject.toProfile() = MemberProfile(
        id = optString("id"),
        username = optString("username"),
        displayName = optString("display_name"),
        bio = optString("bio"),
        visibility = optString("visibility"),
        updatedAt = optString("updated_at")
    )

    private fun JSONObject.toFeedPost() = FeedPost(
        id = optString("id"),
        authorId = optString("author_id"),
        username = optString("username"),
        displayName = optString("display_name"),
        category = optString("category"),
        body = optString("body"),
        createdAt = optString("created_at"),
        likeCount = optInt("like_count"),
        commentCount = optInt("comment_count"),
        likedByMe = optBoolean("liked_by_me")
    )

    private fun JSONArray.toMemberList(): List<MemberSummary> =
        List(length()) { index -> getJSONObject(index).toMemberSummary() }

    private fun JSONObject.toMemberSummary() = MemberSummary(
        id = optString("id"),
        username = optString("username"),
        displayName = optString("display_name"),
        bio = optString("bio")
    )

    private fun JSONObject.nullableString(key: String): String? =
        if (isNull(key)) null else optString(key).takeIf { it.isNotBlank() }

    companion object {
        const val OAUTH_REDIRECT_URI = "hustlesphere://auth-callback"
    }
}
