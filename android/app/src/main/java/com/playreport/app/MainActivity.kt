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
        applyTheme(getSharedPreferences(Notifier.PREFS, MODE_PRIVATE).getBoolean("dark", false))
        web.layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        swipe.addView(web)
        setContentView(swipe)

        with(web.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            textZoom = 100
            allowFileAccess = false
            allowContentAccess = false
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
                pendingTab?.let { t -> js("window.app && window.app.setTab && window.app.setTab(${JSONObject.quote(t)});"); pendingTab = null }
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
        intent.getStringExtra("tab")?.let { t -> js("window.app && window.app.setTab && window.app.setTab(${JSONObject.quote(t)});") }
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

    private fun openExternal(uri: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
        } catch (_: Exception) {
        }
    }

    private fun js(code: String) = runOnUiThread { web.evaluateJavascript(code, null) }

    /** Keep the system bars and the WebView backdrop in step with the page theme (no white flashes). */
    private fun applyTheme(dark: Boolean) {
        val bg = if (dark) Color.parseColor("#0B0F14") else Color.parseColor("#F2F4F8")
        val nav = if (dark) Color.parseColor("#131A22") else Color.WHITE
        web.setBackgroundColor(bg)
        swipe.setBackgroundColor(bg)
        window.navigationBarColor = nav
        val ctl = WindowInsetsControllerCompat(window, web)
        ctl.isAppearanceLightNavigationBars = !dark
        ctl.isAppearanceLightStatusBars = false
        val prefs = getSharedPreferences(Notifier.PREFS, MODE_PRIVATE)
        prefs.edit().putBoolean("dark", dark).apply()
    }

    inner class Bridge {
        @JavascriptInterface
        fun fetch(id: Int, url: String, userAgent: String?) {
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
        fun notify(channel: String, id: Int, title: String, text: String, tab: String?) =
            Notifier.notify(this@MainActivity, channel, id, title, text, tab ?: "today")

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
                val info = Updater.check()
                val payload = if (info != null && Updater.isNewer(info.version, BuildConfig.VERSION_NAME))
                    JSONObject().put("version", info.version).put("url", info.url).put("notes", info.notes).toString()
                else "null"
                js("window.__updateInfo && window.__updateInfo($payload);")
            }
        }

        @JavascriptInterface
        fun installUpdate(url: String) {
            pool.execute {
                js("window.__updateProgress && window.__updateProgress('downloading');")
                val f = Updater.download(this@MainActivity, url)
                if (f == null) {
                    js("window.__updateProgress && window.__updateProgress('failed');")
                } else {
                    js("window.__updateProgress && window.__updateProgress('installing');")
                    runOnUiThread { Updater.install(this@MainActivity, f) }
                }
            }
        }
    }
}
