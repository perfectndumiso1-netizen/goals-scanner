package com.playreport.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.graphics.Color
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewClientCompat
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * PlayReport — native shell around the bundled UI (assets/www). The bridge lets the page fetch data,
 * post notifications, open WhatsApp / e-mail, check for and install updates.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private lateinit var swipe: SwipeRefreshLayout
    private val pool = Executors.newFixedThreadPool(4)
    private var pendingTab: String? = null

    companion object {
        const val HOST = "appassets.androidplatform.net"
        const val START = "https://$HOST/assets/www/index.html"
    }

    private val askNotifications = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        js("window.app && window.app.onPermission && window.app.onPermission($granted);")
    }

    /** "Save as" for CSV exports: the page hands over the text, the user picks a location (Downloads, Drive, ...). */
    private var pendingSave: Pair<String, String>? = null
    private val saveDocument = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val pending = pendingSave
        pendingSave = null
        val uri = result.data?.data
        if (pending == null || uri == null) {
            js("window.__saveDone && window.__saveDone(false);")
            return@registerForActivityResult
        }
        pool.execute {
            val ok = try {
                contentResolver.openOutputStream(uri, "wt")?.use { it.write(pending.second.toByteArray(Charsets.UTF_8)) } != null
            } catch (e: Exception) { false }
            js("window.__saveDone && window.__saveDone($ok);")
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Notifier.createChannels(this)
        scheduleChecks()

        swipe = SwipeRefreshLayout(this)
        web = WebView(this)
        applyTheme(getSharedPreferences(Notifier.PREFS, MODE_PRIVATE).getBoolean("dark", true))
        web.layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        swipe.addView(web)
        setContentView(swipe)
        // Targeting API 36 means modern Android draws the app edge to edge whether it asks to or not, and the
        // system no longer resizes the window for the keyboard. Both are handled here, in one place: the page
        // gets the space between the status bar and the navigation bar, and the keyboard pushes it up rather
        // than covering the search box. On older releases the same listener simply receives no insets.
        ViewCompat.setOnApplyWindowInsetsListener(swipe) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
            v.setPadding(bars.left, bars.top, bars.right, maxOf(bars.bottom, ime.bottom))
            insets
        }

        with(web.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            textZoom = 100
            // the page is bundled in the APK and fetches its data through the native bridge: it never needs
            // a file:// or content:// origin, and never needs to open another window
            allowFileAccess = false
            allowContentAccess = false
            allowFileAccessFromFileURLs = false
            allowUniversalAccessFromFileURLs = false
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
            mediaPlaybackRequiresUserGesture = true
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            // nothing the page does should be readable from a browser outside the app
            setGeolocationEnabled(false)
            userAgentString = "$userAgentString PlayReport/" + BuildConfig.VERSION_NAME
        }
        web.overScrollMode = WebView.OVER_SCROLL_NEVER

        val loader = WebViewAssetLoader.Builder()
            .setDomain(HOST)
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()

        pendingTab = intent?.getStringExtra("tab")
        web.webViewClient = object : WebViewClientCompat() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                loader.shouldInterceptRequest(request.url)

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url
                if (url.host == HOST) return false
                openExternal(url)
                return true
            }

            override fun onPageFinished(view: WebView, url: String) {
                pendingTab?.let { t -> handleTab(t); pendingTab = null }
            }
        }
        web.addJavascriptInterface(Bridge(), "Android")

        swipe.setColorSchemeResources(R.color.brand)
        swipe.setOnRefreshListener {
            web.evaluateJavascript("window.app && window.app.refresh ? window.app.refresh() : Android.refreshDone();", null)
        }
        web.viewTreeObserver.addOnScrollChangedListener { swipe.isEnabled = web.scrollY == 0 }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                web.evaluateJavascript("window.app && window.app.back ? String(window.app.back()) : 'false'") { handled ->
                    if (handled == null || !handled.contains("true")) {
                        isEnabled = false
                        onBackPressedDispatcher.onBackPressed()
                        isEnabled = true
                    }
                }
            }
        })

        if (savedInstanceState == null) web.loadUrl(START) else web.restoreState(savedInstanceState)
        requestNotificationPermission()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        intent.getStringExtra("tab")?.let { t -> handleTab(t) }
    }

    /**
     * Routes a notification "tab" extra. "install" (the update notification) starts the download and
     * the system installer immediately — the user taps once and waits for nothing. "match|<key>" opens
     * that exact match straight away (key = fixture id or livescore id); anything else is a normal
     * tab switch in the page.
     */
    private fun handleTab(t: String) {
        if (t == "install") startUpdateInstall()
        else if (t.startsWith("match|")) js("window.app && window.app.openNotifMatch && window.app.openNotifMatch(${JSONObject.quote(t)});")
        else if (t.startsWith("tennis|")) js("window.app && window.app.openNotifTennis && window.app.openNotifTennis(${JSONObject.quote(t)});")
        else js("window.app && window.app.setTab && window.app.setTab(${JSONObject.quote(t)});")
    }

    /** Update notification tapped: check the release, download the APK, hand it to the installer. */
    private fun startUpdateInstall() {
        pool.execute {
            val info = Updater.check()?.takeIf { Updater.isNewer(it.version, BuildConfig.VERSION_NAME) }
            val payload = if (info != null)
                JSONObject().put("version", info.version).put("url", info.url).put("notes", info.notes).toString()
            else "null"
            js("window.__updateInfo && window.__updateInfo($payload);")
            if (info == null) return@execute
            // the browser downloads it and Android shows its install screen (see Updater.handOff)
            runOnUiThread {
                val ok = Updater.handOff(this@MainActivity, info)
                js("window.__updateProgress && window.__updateProgress('${if (ok) "browser" else "failed"}');")
            }
        }
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && !Notifier.canNotify(this)) {
            askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    private fun scheduleChecks() {
        val req = PeriodicWorkRequestBuilder<CheckWorker>(15, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork("playreport-check", ExistingPeriodicWorkPolicy.UPDATE, req)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    override fun onResume() {
        super.onResume()
        web.onResume()
        js("window.app && window.app.onResume && window.app.onResume();")
    }

    override fun onPause() {
        web.onPause()
        super.onPause()
    }

    override fun onDestroy() {
        pool.shutdownNow()
        super.onDestroy()
    }

    /**
     * Open a link outside the app. Only https is handed to another app: the page can pass any URL through the
     * bridge, and a custom scheme or a file:// URI is how a link turns into an unwanted action.
     */
    private fun openExternal(uri: Uri) {
        if (!uri.scheme.equals("https", ignoreCase = true)) return
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
        } catch (_: Exception) {
        }
    }

    private fun js(code: String) = runOnUiThread { web.evaluateJavascript(code, null) }

    /** Keep the system bars and the WebView backdrop in step with the page theme (no white flashes). */
    private fun applyTheme(dark: Boolean) {
        val bg = if (dark) Color.parseColor("#0B0F14") else Color.parseColor("#F2F4F8")
        val nav = if (dark) Color.parseColor("#0E131A") else Color.WHITE
        web.setBackgroundColor(bg)
        swipe.setBackgroundColor(bg)          // also paints the strips the insets leave either side of the page
        window.navigationBarColor = nav       // ignored from API 35 (edge to edge); the background above is what shows
        val ctl = WindowInsetsControllerCompat(window, web)
        ctl.isAppearanceLightNavigationBars = !dark
        ctl.isAppearanceLightStatusBars = false
        val prefs = getSharedPreferences(Notifier.PREFS, MODE_PRIVATE)
        prefs.edit().putBoolean("dark", dark).apply()
    }

    inner class Bridge {
        @JavascriptInterface
        fun fetch(id: Int, url: String, userAgent: String?) {
            // the page may only reach the hosts it actually needs; anything else comes straight back as an
            // error, so a compromised data file cannot use the app as an open proxy
            if (!Security.webAllowed(url)) {
                js("window.__fetchDone && window.__fetchDone($id, 0, ${JSONObject.quote("blocked host")});")
                return
            }
            pool.execute {
                val r = Net.get(url, userAgent ?: Net.UA)
                js("window.__fetchDone && window.__fetchDone($id, ${r.code}, ${JSONObject.quote(r.body)});")
            }
        }

        @JavascriptInterface
        fun refreshDone() = runOnUiThread { swipe.isRefreshing = false }

        @JavascriptInterface
        fun openUrl(url: String) = openExternal(Uri.parse(url))

        @JavascriptInterface
        fun share(text: String) {
            val send = Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(Intent.EXTRA_TEXT, text)
            }
            startActivity(Intent.createChooser(send, "Share"))
        }

        @JavascriptInterface
        fun version(): String = BuildConfig.VERSION_NAME

        @JavascriptInterface
        fun dataUrl(): String = Net.LATEST_JSON

        @JavascriptInterface
        fun rawBase(): String = "https://raw.githubusercontent.com/${Net.REPO}/${Net.BRANCH}/"

        /** Notification preferences shared with the background checker. */
        @JavascriptInterface
        fun setPref(key: String, value: Boolean) {
            getSharedPreferences(Notifier.PREFS, MODE_PRIVATE).edit().putBoolean("pref_$key", value).apply()
        }

        /** Small JSON blobs shared with the background checker (pending tickets). */
        @JavascriptInterface
        fun setString(key: String, value: String) {
            getSharedPreferences(Notifier.PREFS, MODE_PRIVATE).edit().putString("str_$key", value).apply()
        }

        /** Read back what the page stored natively (tickets, favourites, settings survive re-installs / WebView resets). */
        @JavascriptInterface
        fun getString(key: String): String? =
            getSharedPreferences(Notifier.PREFS, MODE_PRIVATE).getString("str_$key", null)

        /** Save a text file (CSV) through the system file picker; the result comes back via window.__saveDone. */
        @JavascriptInterface
        fun saveText(name: String, mime: String, text: String) {
            runOnUiThread {
                pendingSave = Pair(name, text)
                val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = mime
                    putExtra(Intent.EXTRA_TITLE, name)
                }
                try {
                    saveDocument.launch(intent)
                } catch (e: Exception) {
                    pendingSave = null
                    js("window.__saveDone && window.__saveDone(false);")
                }
            }
        }

        /** Called by the page whenever its theme resolves (system / light / dark). */
        @JavascriptInterface
        fun setTheme(dark: Boolean) = runOnUiThread { applyTheme(dark) }

        @JavascriptInterface
        fun notificationsAllowed(): Boolean = Notifier.canNotify(this@MainActivity)

        @JavascriptInterface
        fun requestNotifications() = runOnUiThread { requestNotificationPermission() }

        @JavascriptInterface
        fun notify(channel: String, id: Int, title: String, text: String, tab: String?) {
            // the page uses short channel names; map them onto the current (versioned) channel ids
            val ch = when (channel) {
                "bets", Notifier.CH_BETS -> Notifier.CH_BETS
                "match", Notifier.CH_MATCH -> Notifier.CH_MATCH
                "goals", Notifier.CH_GOALS -> Notifier.CH_GOALS
                "kickoff", Notifier.CH_KICKOFF -> Notifier.CH_KICKOFF
                "reports", Notifier.CH_REPORTS -> Notifier.CH_REPORTS
                else -> Notifier.CH_REPORTS
            }
            Notifier.notify(this@MainActivity, ch, id, title, text, tab ?: "today")
        }

        /** Opens the system settings of one notification channel (sound, vibration, importance). */
        @JavascriptInterface
        fun openChannelSettings(channel: String) = runOnUiThread {
            try {
                val ch = when (channel) {
                    "goals" -> Notifier.CH_GOALS; "bets" -> Notifier.CH_BETS; "match" -> Notifier.CH_MATCH
                    "kickoff" -> Notifier.CH_KICKOFF; "reports" -> Notifier.CH_REPORTS
                    "tennis" -> Notifier.CH_TENNIS; "tickets" -> Notifier.CH_TICKETS; else -> channel
                }
                startActivity(android.content.Intent(android.provider.Settings.ACTION_CHANNEL_NOTIFICATION_SETTINGS).apply {
                    putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, packageName)
                    putExtra(android.provider.Settings.EXTRA_CHANNEL_ID, ch)
                })
            } catch (e: Exception) {
                try {
                    startActivity(android.content.Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS).apply {
                        putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, packageName)
                    })
                } catch (e2: Exception) { /* no settings screen available */ }
            }
        }

        /** Goal alert from the open app; ignored if the background checker already announced this score. */
        @JavascriptInterface
        fun notifyGoal(eid: String, score: String, title: String, text: String) {
            if (!Notifier.goalSeen(this@MainActivity, eid, score)) {
                Notifier.notify(this@MainActivity, Notifier.CH_GOALS, eid.hashCode(), title, text, "live")
            }
        }

        @JavascriptInterface
        fun markScore(eid: String, score: String) { Notifier.goalSeen(this@MainActivity, eid, score) }

        @JavascriptInterface
        fun checkUpdate() {
            pool.execute {
                val info = Updater.check()?.takeIf { Updater.isNewer(it.version, BuildConfig.VERSION_NAME) }
                // newer release: announce once per version — the notification's tap installs directly
                if (info != null) Notifier.notifyUpdateOnce(this@MainActivity, info.version, info.notes)
                val payload = if (info != null)
                    JSONObject().put("version", info.version).put("url", info.url).put("notes", info.notes).toString()
                else "null"
                js("window.__updateInfo && window.__updateInfo($payload);")
            }
        }

        @JavascriptInterface
        fun installUpdate(url: String) {
            pool.execute {
                // the URL comes from the page, so it is resolved against the release feed and allowlisted
                // first — the page cannot point the app (or the browser) at an arbitrary file
                val info = Updater.check()?.takeIf { it.url == url }
                runOnUiThread {
                    val ok = info != null && Updater.handOff(this@MainActivity, info)
                    js("window.__updateProgress && window.__updateProgress('${if (ok) "browser" else "failed"}');")
                }
            }
        }
    }
}
