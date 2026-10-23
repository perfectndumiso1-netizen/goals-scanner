package com.hustlesphere.app

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.text.format.DateUtils
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Block
import androidx.compose.material.icons.filled.ChatBubbleOutline
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Explore
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.Mail
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Report
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Divider
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.Instant

private val postCategories = listOf("Sports", "Betting", "AI Tools", "Technology", "Online Income", "General")
private val feedCategories = listOf("All") + postCategories

private data class ReportTarget(
    val targetUserId: String? = null,
    val postId: String? = null,
    val commentId: String? = null,
    val label: String
)

private data class BlockTarget(val memberId: String, val label: String)

class MainActivity : ComponentActivity() {
    private var callbackUri by mutableStateOf<Uri?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        callbackUri = intent?.data
        setContent {
            HustleSphereApp(
                callbackUri = callbackUri,
                onCallbackHandled = { callbackUri = null }
            )
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        callbackUri = intent.data
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun HustleSphereApp(callbackUri: Uri?, onCallbackHandled: () -> Unit) {
    val context = LocalContext.current
    val repository = remember(context) { SupabaseRepository(context) }
    val scope = rememberCoroutineScope()

    var session by remember { mutableStateOf<AuthSession?>(null) }
    var profile by remember { mutableStateOf<MemberProfile?>(null) }
    var posts by remember { mutableStateOf<List<FeedPost>>(emptyList()) }
    var members by remember { mutableStateOf<List<MemberSummary>>(emptyList()) }
    var messageRequests by remember { mutableStateOf<List<MessageRequestItem>>(emptyList()) }
    var conversations by remember { mutableStateOf<List<ConversationItem>>(emptyList()) }
    var notifications by remember { mutableStateOf<List<AppNotification>>(emptyList()) }
    var blockedIds by remember { mutableStateOf<Set<String>>(emptySet()) }
    var chatMessages by remember { mutableStateOf<List<ChatMessage>>(emptyList()) }

    var selectedTab by remember { mutableStateOf("Home") }
    var selectedCategory by remember { mutableStateOf("All") }
    var selectedConversation by remember { mutableStateOf<ConversationItem?>(null) }
    var commentsForPost by remember { mutableStateOf<FeedPost?>(null) }
    var comments by remember { mutableStateOf<List<CommentItem>>(emptyList()) }
    var reportTarget by remember { mutableStateOf<ReportTarget?>(null) }
    var blockTarget by remember { mutableStateOf<BlockTarget?>(null) }
    var showComposer by remember { mutableStateOf(false) }
    var showDeleteAccountDialog by remember { mutableStateOf(false) }
    var isBusy by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var infoMessage by remember { mutableStateOf<String?>(null) }

    fun runTask(block: suspend () -> Unit) {
        scope.launch {
            isBusy = true
            errorMessage = null
            infoMessage = null
            try {
                block()
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                errorMessage = error.message ?: "Something went wrong. Please try again."
            } finally {
                isBusy = false
            }
        }
    }

    suspend fun reloadFeed() {
        posts = repository.loadFeed(selectedCategory)
    }

    suspend fun reloadRequests(userId: String) {
        messageRequests = repository.loadMessageRequests(userId)
        conversations = repository.loadConversations(userId)
    }

    suspend fun reloadNotifications(userId: String) {
        notifications = repository.loadNotifications(userId)
    }

    LaunchedEffect(Unit) {
        if (repository.isConfigured) {
            isBusy = true
            try {
                session = repository.restoreSession()
            } catch (error: Exception) {
                errorMessage = error.message
            } finally {
                isBusy = false
            }
        }
    }

    LaunchedEffect(session?.userId) {
        val userId = session?.userId
        if (userId == null) {
            profile = null
            posts = emptyList()
            members = emptyList()
            messageRequests = emptyList()
            conversations = emptyList()
            notifications = emptyList()
            blockedIds = emptySet()
            selectedConversation = null
            return@LaunchedEffect
        }
        isBusy = true
        errorMessage = null
        try {
            profile = repository.loadMyProfile()
            posts = repository.loadFeed(selectedCategory)
            members = repository.discoverMembers()
            messageRequests = repository.loadMessageRequests(userId)
            conversations = repository.loadConversations(userId)
            notifications = repository.loadNotifications(userId)
            blockedIds = repository.loadBlockedIds(userId)
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            errorMessage = error.message ?: "Could not load your account data."
        } finally {
            isBusy = false
        }
    }

    LaunchedEffect(callbackUri) {
        val callback = callbackUri ?: return@LaunchedEffect
        try {
            session = repository.finishGoogleOAuth(callback)
            infoMessage = "Google sign-in complete."
        } catch (error: Exception) {
            errorMessage = error.message ?: "Google sign-in failed."
        } finally {
            onCallbackHandled()
        }
    }

    LaunchedEffect(session?.userId) {
        val userId = session?.userId ?: return@LaunchedEffect
        while (true) {
            delay(30_000)
            try {
                reloadNotifications(userId)
            } catch (_: Exception) {
                // Keep the current screen usable during a temporary network failure.
            }
        }
    }

    LaunchedEffect(session?.userId, selectedConversation?.id) {
        val conversationId = selectedConversation?.id ?: return@LaunchedEffect
        if (session?.userId == null) return@LaunchedEffect
        while (true) {
            try {
                chatMessages = repository.loadMessages(conversationId)
            } catch (_: Exception) {
                // The next poll or an explicit refresh can recover.
            }
            delay(6_000)
        }
    }

    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Color(0xFF285B4B),
            onPrimary = Color.White,
            secondary = Color(0xFFB77935),
            background = Color(0xFFF6F7F4),
            surface = Color.White,
            surfaceVariant = Color(0xFFE8EEE9),
            error = Color(0xFFB3261E)
        )
    ) {
        val signedInUserId = session?.userId
        if (session == null) {
            AuthScreen(
                configured = repository.isConfigured,
                loading = isBusy,
                errorMessage = errorMessage,
                infoMessage = infoMessage,
                onSignIn = { email, password ->
                    runTask { session = repository.signIn(email, password) }
                },
                onSignUp = { email, password, displayName ->
                    runTask {
                        val result = repository.signUp(email, password, displayName)
                        if (result.session != null) {
                            session = result.session
                        } else if (result.emailConfirmationRequired) {
                            infoMessage = "Account created. Check your email to confirm it, then sign in."
                        }
                    }
                },
                onGoogleSignIn = {
                    runTask {
                        val activity = context as? ComponentActivity
                            ?: throw IllegalStateException("Could not open the sign-in browser.")
                        val uri = repository.createGoogleOAuthUri()
                        activity.startActivity(Intent(Intent.ACTION_VIEW, uri))
                    }
                }
            )
        } else {
            val currentTitle = when {
                selectedTab == "Messages" && selectedConversation != null -> {
                    selectedConversation?.otherMember?.displayName?.takeIf { it.isNotBlank() }
                        ?: selectedConversation?.otherMember?.username?.let { "@$it" }
                        ?: "Private conversation"
                }
                selectedTab == "Home" -> "Community feed"
                selectedTab == "Explore" -> "Discover members"
                selectedTab == "Messages" -> "Messages"
                selectedTab == "Notifications" -> "Notifications"
                else -> "Your profile"
            }
            BackHandler(enabled = selectedTab == "Messages" && selectedConversation != null) {
                selectedConversation = null
                chatMessages = emptyList()
            }
            Scaffold(
                topBar = {
                    TopAppBar(
                        navigationIcon = {
                            if (selectedTab == "Messages" && selectedConversation != null) {
                                IconButton(onClick = {
                                    selectedConversation = null
                                    chatMessages = emptyList()
                                }) {
                                    Icon(Icons.Default.ArrowBack, contentDescription = "Back to messages")
                                }
                            }
                        },
                        title = {
                            Column {
                                Text(currentTitle, fontWeight = FontWeight.Bold)
                                if (selectedConversation == null) {
                                    Text("Connect. Learn. Build.", style = MaterialTheme.typography.labelSmall)
                                }
                            }
                        },
                        actions = {
                            IconButton(onClick = {
                                runTask {
                                    if (signedInUserId != null) {
                                        profile = repository.loadMyProfile()
                                        reloadFeed()
                                        members = repository.discoverMembers()
                                        reloadRequests(signedInUserId)
                                        reloadNotifications(signedInUserId)
                                        blockedIds = repository.loadBlockedIds(signedInUserId)
                                        selectedConversation?.let { chatMessages = repository.loadMessages(it.id) }
                                    }
                                }
                            }) {
                                Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                            }
                            IconButton(onClick = { selectedTab = "Notifications" }) {
                                Icon(
                                    Icons.Default.Notifications,
                                    contentDescription = "Notifications, ${notifications.count { it.readAt == null }} unread"
                                )
                            }
                            IconButton(onClick = { runTask { repository.signOut(); session = null } }) {
                                Icon(Icons.Default.Logout, contentDescription = "Sign out")
                            }
                        }
                    )
                },
                bottomBar = {
                    NavigationBar {
                        NavigationBarItem(
                            selected = selectedTab == "Home",
                            onClick = { selectedTab = "Home"; selectedConversation = null },
                            icon = { Icon(Icons.Default.Home, contentDescription = null) },
                            label = { Text("Home") }
                        )
                        NavigationBarItem(
                            selected = selectedTab == "Explore",
                            onClick = { selectedTab = "Explore"; selectedConversation = null },
                            icon = { Icon(Icons.Default.Explore, contentDescription = null) },
                            label = { Text("Explore") }
                        )
                        NavigationBarItem(
                            selected = selectedTab == "Messages",
                            onClick = { selectedTab = "Messages" },
                            icon = { Icon(Icons.Default.Mail, contentDescription = null) },
                            label = { Text("Messages") }
                        )
                        NavigationBarItem(
                            selected = selectedTab == "Profile",
                            onClick = { selectedTab = "Profile"; selectedConversation = null },
                            icon = { Icon(Icons.Default.Person, contentDescription = null) },
                            label = { Text("Profile") }
                        )
                    }
                },
                floatingActionButton = {
                    if (selectedTab == "Home") {
                        FloatingActionButton(onClick = { showComposer = true }) {
                            Text("+", fontSize = 26.sp, fontWeight = FontWeight.Light)
                        }
                    }
                }
            ) { padding ->
                Column(Modifier.fillMaxSize().padding(padding)) {
                    if (isBusy) LinearProgressIndicatorCompat()
                    StatusBanner(errorMessage, isError = true)
                    StatusBanner(infoMessage, isError = false)
                    when (selectedTab) {
                        "Home" -> HomeScreen(
                            posts = posts,
                            currentUserId = signedInUserId.orEmpty(),
                            selectedCategory = selectedCategory,
                            onCategorySelected = { category ->
                                selectedCategory = category
                                runTask { posts = repository.loadFeed(category) }
                            },
                            onLike = { post ->
                                if (signedInUserId != null) runTask {
                                    repository.toggleLike(post, signedInUserId)
                                    reloadFeed()
                                }
                            },
                            onComment = { post ->
                                commentsForPost = post
                                comments = emptyList()
                                runTask { comments = repository.loadComments(post.id) }
                            },
                            onReport = { post ->
                                reportTarget = ReportTarget(postId = post.id, label = "this post")
                            },
                            onBlock = { post ->
                                blockTarget = BlockTarget(post.authorId, post.displayName.ifBlank { "@${post.username}" })
                            }
                        )
                        "Explore" -> ExploreScreen(
                            members = members.filter { it.id != signedInUserId },
                            blockedIds = blockedIds,
                            onRefresh = {
                                runTask {
                                    members = repository.discoverMembers()
                                    if (signedInUserId != null) blockedIds = repository.loadBlockedIds(signedInUserId)
                                }
                            },
                            onMessageRequest = { member ->
                                runTask {
                                    repository.sendMessageRequest(member.id)
                                    if (signedInUserId != null) reloadRequests(signedInUserId)
                                    infoMessage = "Message request sent to @${member.username}."
                                }
                            },
                            onReport = { member ->
                                reportTarget = ReportTarget(targetUserId = member.id, label = "@${member.username}")
                            },
                            onBlock = { member -> blockTarget = BlockTarget(member.id, "@${member.username}") }
                        )
                        "Messages" -> MessagesScreen(
                            currentUserId = signedInUserId.orEmpty(),
                            requests = messageRequests,
                            conversations = conversations,
                            selectedConversation = selectedConversation,
                            messages = chatMessages,
                            busy = isBusy,
                            onRefresh = {
                                if (signedInUserId != null) runTask {
                                    reloadRequests(signedInUserId)
                                    selectedConversation?.let { chatMessages = repository.loadMessages(it.id) }
                                }
                            },
                            onSelectConversation = { conversation ->
                                selectedConversation = conversation
                                runTask { chatMessages = repository.loadMessages(conversation.id) }
                            },
                            onAccept = { request ->
                                runTask {
                                    repository.acceptMessageRequest(request.id)
                                    if (signedInUserId != null) reloadRequests(signedInUserId)
                                    infoMessage = "Request accepted. You can now message this member."
                                }
                            },
                            onDecline = { request ->
                                runTask {
                                    repository.declineMessageRequest(request.id)
                                    if (signedInUserId != null) reloadRequests(signedInUserId)
                                    infoMessage = "Message request declined."
                                }
                            },
                            onSendMessage = { conversation, body ->
                                if (signedInUserId != null) runTask {
                                    repository.sendMessage(conversation.id, signedInUserId, body)
                                    chatMessages = repository.loadMessages(conversation.id)
                                }
                            }
                        )
                        "Notifications" -> NotificationsScreen(
                            notifications = notifications,
                            onMarkRead = { notification ->
                                runTask {
                                    repository.markNotificationRead(notification.id)
                                    notifications = notifications.map {
                                        if (it.id == notification.id) it.copy(readAt = Instant.now().toString()) else it
                                    }
                                }
                            },
                            onRefresh = {
                                if (signedInUserId != null) runTask { reloadNotifications(signedInUserId) }
                            }
                        )
                        else -> ProfileScreen(
                            profile = profile,
                            blockedIds = blockedIds,
                            busy = isBusy,
                            onSave = { username, displayName, bio, visibility ->
                                runTask {
                                    repository.saveProfile(username, displayName, bio, visibility)
                                    profile = repository.loadMyProfile()
                                    members = repository.discoverMembers()
                                    reloadFeed()
                                    infoMessage = "Profile saved."
                                }
                            },
                            onUnblock = { memberId ->
                                if (signedInUserId != null) runTask {
                                    repository.unblockMember(memberId, signedInUserId)
                                    blockedIds = repository.loadBlockedIds(signedInUserId)
                                    members = repository.discoverMembers()
                                    reloadFeed()
                                    infoMessage = "Member unblocked."
                                }
                            },
                            onDeleteAccount = { showDeleteAccountDialog = true }
                        )
                    }
                }
            }

            if (showComposer) {
                CreatePostDialog(
                    busy = isBusy,
                    onDismiss = { showComposer = false },
                    onSubmit = { category, body ->
                        if (signedInUserId != null) runTask {
                            repository.createPost(signedInUserId, category, body)
                            selectedCategory = "All"
                            posts = repository.loadFeed("All")
                            infoMessage = "Your post was published."
                        }
                        showComposer = false
                    }
                )
            }
            commentsForPost?.let { post ->
                CommentsDialog(
                    post = post,
                    comments = comments,
                    currentUserId = signedInUserId.orEmpty(),
                    busy = isBusy,
                    onDismiss = { commentsForPost = null },
                    onSend = { body ->
                        if (signedInUserId != null) runTask {
                            repository.addComment(post.id, signedInUserId, body)
                            comments = repository.loadComments(post.id)
                            reloadFeed()
                        }
                    },
                    onReport = { comment ->
                        reportTarget = ReportTarget(commentId = comment.id, label = "this comment")
                    }
                )
            }
            reportTarget?.let { target ->
                ReportDialog(
                    targetLabel = target.label,
                    busy = isBusy,
                    onDismiss = { reportTarget = null },
                    onSubmit = { reason ->
                        if (signedInUserId != null) runTask {
                            repository.submitReport(
                                reporterId = signedInUserId,
                                reason = reason,
                                targetUserId = target.targetUserId,
                                postId = target.postId,
                                commentId = target.commentId
                            )
                            reportTarget = null
                            infoMessage = "Report submitted for moderator review."
                        }
                    }
                )
            }
            blockTarget?.let { target ->
                AlertDialog(
                    onDismissRequest = { blockTarget = null },
                    title = { Text("Block ${target.label}?") },
                    text = {
                        Text("Their profile and content will be hidden from you, and existing message access will be revoked. You can unblock them from your profile.")
                    },
                    confirmButton = {
                        TextButton(enabled = !isBusy, onClick = {
                            if (signedInUserId != null) runTask {
                                repository.blockMember(target.memberId, signedInUserId)
                                blockedIds = repository.loadBlockedIds(signedInUserId)
                                members = repository.discoverMembers()
                                reloadFeed()
                                reloadRequests(signedInUserId)
                                selectedConversation?.let { conversation ->
                                    if (conversation.otherMember?.id == target.memberId) {
                                        selectedConversation = null
                                        chatMessages = emptyList()
                                    }
                                }
                                blockTarget = null
                                infoMessage = "Member blocked."
                            }
                        }) { Text("Block") }
                    },
                    dismissButton = { TextButton(onClick = { blockTarget = null }) { Text("Cancel") } }
                )
            }
            if (showDeleteAccountDialog) {
                DeleteAccountDialog(
                    busy = isBusy,
                    onDismiss = { showDeleteAccountDialog = false },
                    onConfirm = {
                        runTask {
                            repository.deleteMyAccount()
                            session = null
                            showDeleteAccountDialog = false
                            infoMessage = "Your account was deleted."
                        }
                    }
                )
            }
        }
    }
}

@Composable
private fun AuthScreen(
    configured: Boolean,
    loading: Boolean,
    errorMessage: String?,
    infoMessage: String?,
    onSignIn: (String, String) -> Unit,
    onSignUp: (String, String, String) -> Unit,
    onGoogleSignIn: () -> Unit
) {
    var registering by remember { mutableStateOf(false) }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var displayName by remember { mutableStateOf("") }

    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Surface(shape = CircleShape, color = MaterialTheme.colorScheme.primaryContainer, modifier = Modifier.size(76.dp)) {
                Box(contentAlignment = Alignment.Center) {
                    Text("H", fontSize = 36.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
                }
            }
            Spacer(Modifier.height(16.dp))
            Text("HustleSphere", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text("Connect. Learn. Build.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(24.dp))
            StatusBanner(errorMessage, isError = true)
            StatusBanner(infoMessage, isError = false)
            if (!configured) {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                    Text(
                        "Supabase is not configured. Build with SUPABASE_URL and SUPABASE_ANON_KEY. See hustlesphere/README.md. No demo data is shown.",
                        Modifier.padding(16.dp),
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
                Spacer(Modifier.height(16.dp))
            }
            if (registering) {
                OutlinedTextField(
                    value = displayName,
                    onValueChange = { displayName = it.take(80) },
                    label = { Text("Display name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !loading
                )
                Spacer(Modifier.height(10.dp))
            }
            OutlinedTextField(
                value = email,
                onValueChange = { email = it.trim() },
                label = { Text("Email") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                enabled = !loading
            )
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                label = { Text("Password") },
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                enabled = !loading
            )
            Spacer(Modifier.height(16.dp))
            Button(
                onClick = {
                    if (email.isBlank() || password.isBlank()) return@Button
                    if (registering) onSignUp(email, password, displayName) else onSignIn(email, password)
                },
                enabled = configured && !loading && email.isNotBlank() && password.isNotBlank(),
                modifier = Modifier.fillMaxWidth()
            ) {
                if (loading) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                else Text(if (registering) "Create account" else "Sign in")
            }
            TextButton(
                onClick = { registering = !registering },
                enabled = configured && !loading
            ) {
                Text(if (registering) "Already have an account? Sign in" else "New here? Create an account")
            }
            Divider(Modifier.padding(vertical = 8.dp))
            OutlinedButton(
                onClick = onGoogleSignIn,
                enabled = configured && !loading,
                modifier = Modifier.fillMaxWidth()
            ) { Text("Continue with Google") }
            Spacer(Modifier.height(18.dp))
            Text(
                "Use community features responsibly. Private profiles and conversations are protected by database policies.",
                style = MaterialTheme.typography.bodySmall,
                textAlign = TextAlign.Center,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun HomeScreen(
    posts: List<FeedPost>,
    currentUserId: String,
    selectedCategory: String,
    onCategorySelected: (String) -> Unit,
    onLike: (FeedPost) -> Unit,
    onComment: (FeedPost) -> Unit,
    onReport: (FeedPost) -> Unit,
    onBlock: (FeedPost) -> Unit
) {
    Column(Modifier.fillMaxSize()) {
        Text(
            "Share what you're learning across sport, AI, technology and online income.",
            Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        androidx.compose.foundation.lazy.LazyRow(
            contentPadding = PaddingValues(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(feedCategories) { category ->
                FilterChip(
                    selected = selectedCategory == category,
                    onClick = { onCategorySelected(category) },
                    label = { Text(category) }
                )
            }
        }
        if (posts.isEmpty()) {
            EmptyState(
                title = "No posts yet",
                message = "Be the first to start a useful, respectful conversation in this community."
            )
        } else {
            LazyColumn(
                contentPadding = PaddingValues(start = 12.dp, end = 12.dp, top = 8.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                items(posts, key = { it.id }) { post ->
                    PostCard(
                        post = post,
                        currentUserId = currentUserId,
                        onLike = { onLike(post) },
                        onComment = { onComment(post) },
                        onReport = { onReport(post) },
                        onBlock = { onBlock(post) }
                    )
                }
            }
        }
    }
}

@Composable
private fun PostCard(
    post: FeedPost,
    currentUserId: String,
    onLike: () -> Unit,
    onComment: () -> Unit,
    onReport: () -> Unit,
    onBlock: () -> Unit
) {
    var menuExpanded by remember { mutableStateOf(false) }
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    shape = CircleShape,
                    color = MaterialTheme.colorScheme.primaryContainer,
                    modifier = Modifier.size(42.dp)
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(
                            (post.displayName.ifBlank { post.username }).take(1).uppercase(),
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.primary
                        )
                    }
                }
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(post.displayName.ifBlank { "@${post.username}" }, fontWeight = FontWeight.SemiBold)
                    Text("@${post.username} · ${post.category} · ${timeAgo(post.createdAt)}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (post.authorId != currentUserId) {
                    Box {
                        IconButton(onClick = { menuExpanded = true }) {
                            Icon(Icons.Default.MoreVert, contentDescription = "Post actions")
                        }
                        androidx.compose.material3.DropdownMenu(
                            expanded = menuExpanded,
                            onDismissRequest = { menuExpanded = false }
                        ) {
                            androidx.compose.material3.DropdownMenuItem(
                                text = { Text("Report post") },
                                leadingIcon = { Icon(Icons.Default.Report, null) },
                                onClick = { menuExpanded = false; onReport() }
                            )
                            androidx.compose.material3.DropdownMenuItem(
                                text = { Text("Block author") },
                                leadingIcon = { Icon(Icons.Default.Block, null) },
                                onClick = { menuExpanded = false; onBlock() }
                            )
                        }
                    }
                }
            }
            Text(post.body, style = MaterialTheme.typography.bodyLarge)
            Divider()
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = onLike) {
                    Icon(
                        if (post.likedByMe) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                        contentDescription = if (post.likedByMe) "Unlike" else "Like",
                        tint = if (post.likedByMe) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(Modifier.width(6.dp))
                    Text(post.likeCount.toString())
                }
                TextButton(onClick = onComment) {
                    Icon(Icons.Default.ChatBubbleOutline, contentDescription = "Comments")
                    Spacer(Modifier.width(6.dp))
                    Text("${post.commentCount} comments")
                }
            }
        }
    }
}

@Composable
private fun ExploreScreen(
    members: List<MemberSummary>,
    blockedIds: Set<String>,
    onRefresh: () -> Unit,
    onMessageRequest: (MemberSummary) -> Unit,
    onReport: (MemberSummary) -> Unit,
    onBlock: (MemberSummary) -> Unit
) {
    var search by remember { mutableStateOf("") }
    val visibleMembers = members.filter {
        val query = search.trim().lowercase()
        query.isBlank() || listOf(it.username, it.displayName, it.bio).any { value -> value.lowercase().contains(query) }
    }
    Column(Modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
            OutlinedTextField(
                value = search,
                onValueChange = { search = it },
                label = { Text("Search public members") },
                singleLine = true,
                modifier = Modifier.weight(1f)
            )
            IconButton(onClick = onRefresh) { Icon(Icons.Default.Refresh, contentDescription = "Refresh members") }
        }
        if (visibleMembers.isEmpty()) {
            EmptyState("No public members found", "Try another search, or check back later.")
        } else {
            LazyColumn(
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                items(visibleMembers, key = { it.id }) { member ->
                    MemberCard(
                        member = member,
                        isBlocked = member.id in blockedIds,
                        onMessageRequest = { onMessageRequest(member) },
                        onReport = { onReport(member) },
                        onBlock = { onBlock(member) }
                    )
                }
            }
        }
    }
}

@Composable
private fun MemberCard(
    member: MemberSummary,
    isBlocked: Boolean,
    onMessageRequest: () -> Unit,
    onReport: () -> Unit,
    onBlock: () -> Unit
) {
    var expanded by remember { mutableStateOf(false) }
    Card(shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(shape = CircleShape, color = MaterialTheme.colorScheme.secondaryContainer, modifier = Modifier.size(42.dp)) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(member.displayName.ifBlank { member.username }.take(1).uppercase(), fontWeight = FontWeight.Bold)
                    }
                }
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(member.displayName.ifBlank { "@${member.username}" }, fontWeight = FontWeight.SemiBold)
                    Text("@${member.username}", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Box {
                    IconButton(onClick = { expanded = true }) { Icon(Icons.Default.MoreVert, contentDescription = "Member actions") }
                    androidx.compose.material3.DropdownMenu(expanded, { expanded = false }) {
                        androidx.compose.material3.DropdownMenuItem(
                            text = { Text("Report member") },
                            leadingIcon = { Icon(Icons.Default.Report, null) },
                            onClick = { expanded = false; onReport() }
                        )
                        androidx.compose.material3.DropdownMenuItem(
                            text = { Text("Block member") },
                            leadingIcon = { Icon(Icons.Default.Block, null) },
                            onClick = { expanded = false; onBlock() }
                        )
                    }
                }
            }
            if (member.bio.isNotBlank()) Text(member.bio, style = MaterialTheme.typography.bodyMedium)
            FilledTonalButton(onClick = onMessageRequest, enabled = !isBlocked) {
                Icon(Icons.Default.Mail, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text("Request to message")
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MessagesScreen(
    currentUserId: String,
    requests: List<MessageRequestItem>,
    conversations: List<ConversationItem>,
    selectedConversation: ConversationItem?,
    messages: List<ChatMessage>,
    busy: Boolean,
    onRefresh: () -> Unit,
    onSelectConversation: (ConversationItem) -> Unit,
    onAccept: (MessageRequestItem) -> Unit,
    onDecline: (MessageRequestItem) -> Unit,
    onSendMessage: (ConversationItem, String) -> Unit
) {
    if (selectedConversation != null) {
        ConversationPane(
            conversation = selectedConversation,
            currentUserId = currentUserId,
            messages = messages,
            busy = busy,
            onRefresh = onRefresh,
            onSend = { body -> onSendMessage(selectedConversation, body) }
        )
        return
    }

    val incoming = requests.filter { it.recipientId == currentUserId && it.status == "pending" }
    val outgoing = requests.filter { it.senderId == currentUserId && it.status == "pending" }
    LazyColumn(
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Message requests", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Text("Only accepted requests can start a conversation.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                IconButton(onClick = onRefresh) { Icon(Icons.Default.Refresh, contentDescription = "Refresh messages") }
            }
        }
        if (incoming.isEmpty() && outgoing.isEmpty()) {
            item { Text("No pending requests.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
        items(incoming, key = { "incoming-${it.id}" }) { request ->
            val sender = request.sender
            Card(shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("${sender?.displayName?.takeIf { it.isNotBlank() } ?: "A member"} (@${sender?.username ?: request.senderId.take(8)})", fontWeight = FontWeight.SemiBold)
                    Text("Would like to message you.", style = MaterialTheme.typography.bodyMedium)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { onAccept(request) }, enabled = !busy) {
                            Icon(Icons.Default.Check, contentDescription = null)
                            Spacer(Modifier.width(4.dp)); Text("Accept")
                        }
                        OutlinedButton(onClick = { onDecline(request) }, enabled = !busy) {
                            Icon(Icons.Default.Close, contentDescription = null)
                            Spacer(Modifier.width(4.dp)); Text("Decline")
                        }
                    }
                }
            }
        }
        items(outgoing, key = { "outgoing-${it.id}" }) { request ->
            val recipient = request.recipient
            Text("Waiting for ${recipient?.username?.let { "@$it" } ?: "member ${request.recipientId.take(8)}"} to respond.", style = MaterialTheme.typography.bodySmall)
        }
        item {
            Text("Conversations", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 12.dp))
        }
        if (conversations.isEmpty()) {
            item { Text("Accepted conversations will appear here.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
        items(conversations, key = { it.id }) { conversation ->
            val other = conversation.otherMember
            Card(
                onClick = { onSelectConversation(conversation) },
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Surface(shape = CircleShape, color = MaterialTheme.colorScheme.primaryContainer, modifier = Modifier.size(42.dp)) {
                        Box(contentAlignment = Alignment.Center) { Text((other?.displayName ?: other?.username ?: "M").take(1).uppercase(), fontWeight = FontWeight.Bold) }
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(other?.let { it.displayName.ifBlank { "@${it.username}" } } ?: "Member ${if (conversation.userA == currentUserId) conversation.userB.take(8) else conversation.userA.take(8)}", fontWeight = FontWeight.SemiBold)
                        Text("Private conversation · ${timeAgo(conversation.createdAt)}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Icon(Icons.Default.ChatBubbleOutline, contentDescription = "Open conversation")
                }
            }
        }
    }
}

@Composable
private fun ConversationPane(
    conversation: ConversationItem,
    currentUserId: String,
    messages: List<ChatMessage>,
    busy: Boolean,
    onRefresh: () -> Unit,
    onSend: (String) -> Unit
) {
    var draft by remember(conversation.id) { mutableStateOf("") }
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Messages are visible only to conversation members under database RLS.", Modifier.weight(1f), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            IconButton(onClick = onRefresh) { Icon(Icons.Default.Refresh, contentDescription = "Refresh conversation") }
        }
        if (messages.isEmpty()) {
            EmptyState("Start the conversation", "Your messages are stored in Supabase and restricted to the accepted participants.")
        } else {
            LazyColumn(
                modifier = Modifier.weight(1f),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(messages, key = { it.id }) { message ->
                    val mine = message.senderId == currentUserId
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start
                    ) {
                        Surface(
                            color = if (mine) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant,
                            shape = RoundedCornerShape(18.dp),
                            modifier = Modifier.widthIn(max = 320.dp)
                        ) {
                            Column(Modifier.padding(horizontal = 14.dp, vertical = 10.dp)) {
                                Text(message.body)
                                Text(timeAgo(message.createdAt), style = MaterialTheme.typography.labelSmall, modifier = Modifier.align(Alignment.End), color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            }
        }
        Row(
            Modifier.fillMaxWidth().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            OutlinedTextField(
                value = draft,
                onValueChange = { draft = it.take(5000) },
                modifier = Modifier.weight(1f),
                label = { Text("Message") },
                maxLines = 4,
                enabled = !busy
            )
            IconButton(
                onClick = {
                    val body = draft.trim()
                    if (body.isNotEmpty()) {
                        onSend(body)
                        draft = ""
                    }
                },
                enabled = !busy && draft.isNotBlank()
            ) { Icon(Icons.Default.Send, contentDescription = "Send message") }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NotificationsScreen(
    notifications: List<AppNotification>,
    onMarkRead: (AppNotification) -> Unit,
    onRefresh: () -> Unit
) {
    if (notifications.isEmpty()) {
        Column {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                IconButton(onClick = onRefresh) { Icon(Icons.Default.Refresh, contentDescription = "Refresh notifications") }
            }
            EmptyState("No notifications", "Likes, comments, message requests and messages will appear here.")
        }
    } else {
        LazyColumn(
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            item {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("Recent activity", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                    IconButton(onClick = onRefresh) { Icon(Icons.Default.Refresh, contentDescription = "Refresh notifications") }
                }
            }
            items(notifications, key = { it.id }) { notification ->
                Card(
                    onClick = { if (notification.readAt == null) onMarkRead(notification) },
                    colors = CardDefaults.cardColors(
                        containerColor = if (notification.readAt == null) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface
                    ),
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp)
                ) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text("${notification.actorName} ${notification.body}", fontWeight = if (notification.readAt == null) FontWeight.SemiBold else FontWeight.Normal)
                        Text(timeAgo(notification.createdAt), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun ProfileScreen(
    profile: MemberProfile?,
    blockedIds: Set<String>,
    busy: Boolean,
    onSave: (String, String, String, String) -> Unit,
    onUnblock: (String) -> Unit,
    onDeleteAccount: () -> Unit
) {
    var username by remember(profile?.id) { mutableStateOf(profile?.username.orEmpty()) }
    var displayName by remember(profile?.id) { mutableStateOf(profile?.displayName.orEmpty()) }
    var bio by remember(profile?.id) { mutableStateOf(profile?.bio.orEmpty()) }
    var isPublic by remember(profile?.id) { mutableStateOf(profile?.visibility != "private") }

    LaunchedEffect(profile?.updatedAt) {
        if (profile != null) {
            username = profile.username
            displayName = profile.displayName
            bio = profile.bio
            isPublic = profile.visibility != "private"
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Text("Edit profile", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text("Your private profile and posts are hidden from public discovery.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        item {
            OutlinedTextField(
                value = username,
                onValueChange = { username = it.lowercase().filter { c -> c in 'a'..'z' || c in '0'..'9' || c == '_' }.take(24) },
                label = { Text("Username") },
                prefix = { Text("@") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                enabled = !busy
            )
        }
        item {
            OutlinedTextField(
                value = displayName,
                onValueChange = { displayName = it.take(80) },
                label = { Text("Display name") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                enabled = !busy
            )
        }
        item {
            OutlinedTextField(
                value = bio,
                onValueChange = { bio = it.take(500) },
                label = { Text("Bio") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 3,
                maxLines = 5,
                enabled = !busy
            )
        }
        item {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Icon(if (isPublic) Icons.Default.Person else Icons.Default.Lock, contentDescription = null)
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(if (isPublic) "Public profile" else "Private profile", fontWeight = FontWeight.SemiBold)
                    Text(if (isPublic) "Visible to signed-in members." else "Hidden from discovery and public feed content.", style = MaterialTheme.typography.bodySmall)
                }
                Switch(checked = isPublic, onCheckedChange = { isPublic = it }, enabled = !busy)
            }
        }
        item {
            Button(
                onClick = { onSave(username, displayName, bio, if (isPublic) "public" else "private") },
                enabled = !busy && username.length in 3..24,
                modifier = Modifier.fillMaxWidth()
            ) { Text("Save profile") }
        }
        item {
            Divider(Modifier.padding(vertical = 4.dp))
            Text("Blocked members", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Text("Unblocking restores profile visibility. Previously blocked conversations remain closed.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (blockedIds.isEmpty()) {
            item { Text("You haven't blocked anyone.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        } else {
            items(blockedIds.sorted(), key = { it }) { id ->
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("Member ${id.take(8)}", Modifier.weight(1f))
                    TextButton(onClick = { onUnblock(id) }, enabled = !busy) { Text("Unblock") }
                }
            }
        }
        item {
            Divider(Modifier.padding(vertical = 4.dp))
            OutlinedButton(onClick = onDeleteAccount, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                Text("Delete account and data", color = MaterialTheme.colorScheme.error)
            }
            Text("Deletion requires the Supabase delete-account Edge Function to be deployed.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun CreatePostDialog(
    busy: Boolean,
    onDismiss: () -> Unit,
    onSubmit: (String, String) -> Unit
) {
    var category by remember { mutableStateOf("General") }
    var body by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Create a post") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Choose a topic", style = MaterialTheme.typography.labelLarge)
                postCategories.chunked(2).forEach { row ->
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        row.forEach { item ->
                            FilterChip(selected = category == item, onClick = { category = item }, label = { Text(item) })
                        }
                    }
                }
                OutlinedTextField(
                    value = body,
                    onValueChange = { body = it.take(5000) },
                    label = { Text("What would you like to share?") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 3,
                    maxLines = 6,
                    enabled = !busy
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { if (body.isNotBlank()) onSubmit(category, body) }, enabled = !busy && body.isNotBlank()) {
                Text("Publish")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("Cancel") } }
    )
}

@Composable
private fun CommentsDialog(
    post: FeedPost,
    comments: List<CommentItem>,
    currentUserId: String,
    busy: Boolean,
    onDismiss: () -> Unit,
    onSend: (String) -> Unit,
    onReport: (CommentItem) -> Unit
) {
    var draft by remember(post.id) { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Comments") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(post.body.take(120), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (comments.isEmpty()) {
                    Text("No comments yet.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    LazyColumn(Modifier.heightIn(max = 240.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        items(comments, key = { it.id }) { comment ->
                            Row(verticalAlignment = Alignment.Top) {
                                Column(Modifier.weight(1f)) {
                                    Text(comment.displayName.ifBlank { "@${comment.username}" }, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
                                    Text(comment.body, style = MaterialTheme.typography.bodyMedium)
                                }
                                if (comment.authorId != currentUserId) {
                                    IconButton(onClick = { onReport(comment) }) {
                                        Icon(Icons.Default.Report, contentDescription = "Report comment")
                                    }
                                }
                            }
                        }
                    }
                }
                OutlinedTextField(
                    value = draft,
                    onValueChange = { draft = it.take(2000) },
                    label = { Text("Write a comment") },
                    modifier = Modifier.fillMaxWidth(),
                    maxLines = 3,
                    enabled = !busy
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { if (draft.isNotBlank()) { onSend(draft); draft = "" } }, enabled = !busy && draft.isNotBlank()) {
                Text("Comment")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Done") } }
    )
}

@Composable
private fun ReportDialog(
    targetLabel: String,
    busy: Boolean,
    onDismiss: () -> Unit,
    onSubmit: (String) -> Unit
) {
    var reason by remember(targetLabel) { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Report $targetLabel") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Tell moderators why this should be reviewed. Your report is private.")
                OutlinedTextField(
                    value = reason,
                    onValueChange = { reason = it.take(1000) },
                    label = { Text("Reason") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 3,
                    enabled = !busy
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onSubmit(reason) }, enabled = !busy && reason.trim().length >= 3) { Text("Submit report") }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("Cancel") } }
    )
}

@Composable
private fun DeleteAccountDialog(
    busy: Boolean,
    onDismiss: () -> Unit,
    onConfirm: () -> Unit
) {
    var confirmation by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Delete your account permanently?") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Your profile, posts, comments, likes, messages and notifications will be deleted through Supabase. This cannot be undone.")
                OutlinedTextField(
                    value = confirmation,
                    onValueChange = { confirmation = it },
                    label = { Text("Type DELETE to confirm") },
                    singleLine = true,
                    enabled = !busy
                )
            }
        },
        confirmButton = {
            TextButton(onClick = onConfirm, enabled = !busy && confirmation == "DELETE") {
                Text("Delete permanently", color = MaterialTheme.colorScheme.error)
            }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("Cancel") } }
    )
}

@Composable
private fun StatusBanner(message: String?, isError: Boolean) {
    if (message.isNullOrBlank()) return
    val background = if (isError) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.secondaryContainer
    val foreground = if (isError) MaterialTheme.colorScheme.onErrorContainer else MaterialTheme.colorScheme.onSecondaryContainer
    Surface(color = background, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp)) {
        Text(message, Modifier.padding(12.dp), color = foreground, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun LinearProgressIndicatorCompat() {
    androidx.compose.material3.LinearProgressIndicator(Modifier.fillMaxWidth())
}

@Composable
private fun EmptyState(title: String, message: String) {
    Column(
        Modifier.fillMaxWidth().padding(horizontal = 28.dp, vertical = 40.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center)
        Text(message, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
    }
}

private fun timeAgo(isoTime: String): String {
    val millis = runCatching { Instant.parse(isoTime).toEpochMilli() }.getOrNull() ?: return "recently"
    return DateUtils.getRelativeTimeSpanString(
        millis,
        System.currentTimeMillis(),
        DateUtils.MINUTE_IN_MILLIS
    ).toString()
}
