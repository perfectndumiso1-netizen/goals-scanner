package za.goalsscanner

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewClientCompat
import org.json.JSONObject
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * Thin native shell: a WebView showing the bundled UI (assets/www) plus a small bridge so the page can
 * fetch JSON from GitHub / Livescore / Sportybet without browser cross-origin limits, open links in the
 * browser and support pull-to-refresh and the system back button.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private lateinit var swipe: SwipeRefreshLayout
    private val pool = Executors.newFixedThreadPool(4)

    companion object {
        const val HOST = "appassets.androidplatform.net"
        const val START = "https://$HOST/assets/www/index.html"
        const val UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        swipe = SwipeRefreshLayout(this)
        web = WebView(this)
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
            mediaPlaybackRequiresUserGesture = true
        }
        web.overScrollMode = WebView.OVER_SCROLL_NEVER

        val loader = WebViewAssetLoader.Builder()
            .setDomain(HOST)
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()

        web.webViewClient = object : WebViewClientCompat() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                loader.shouldInterceptRequest(request.url)

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url
                if (url.host == HOST) return false
                openExternal(url)
                return true
            }
        }
        web.addJavascriptInterface(Bridge(), "Android")

        swipe.setColorSchemeResources(R.color.brand)
        swipe.setOnRefreshListener {
            web.evaluateJavascript("window.app && window.app.refresh ? window.app.refresh() : Android.refreshDone();", null)
        }
        // only let the pull-to-refresh gesture win when the page is scrolled to the top
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
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    override fun onResume() {
        super.onResume()
        web.onResume()
        web.evaluateJavascript("window.app && window.app.onResume && window.app.onResume();", null)
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

    inner class Bridge {
        /** Asynchronous GET; the result is delivered to window.__fetchDone(id, status, body). */
        @JavascriptInterface
        fun fetch(id: Int, url: String, userAgent: String?) {
            pool.execute {
                var status = 0
                var body = ""
                try {
                    val conn = URL(url).openConnection() as HttpURLConnection
                    conn.connectTimeout = 15000
                    conn.readTimeout = 25000
                    conn.instanceFollowRedirects = true
                    conn.setRequestProperty("User-Agent", userAgent ?: UA)
                    conn.setRequestProperty("Accept", "application/json, text/plain, */*")
                    conn.setRequestProperty("Accept-Language", "en")
                    status = conn.responseCode
                    val stream = if (status < 400) conn.inputStream else conn.errorStream
                    body = stream?.bufferedReader(Charsets.UTF_8)?.use(BufferedReader::readText) ?: ""
                    conn.disconnect()
                } catch (e: Exception) {
                    status = 0
                    body = e.message ?: "network error"
                }
                js("window.__fetchDone && window.__fetchDone($id, $status, ${JSONObject.quote(body)});")
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
        fun repo(): String = BuildConfig.REPO
    }
}
