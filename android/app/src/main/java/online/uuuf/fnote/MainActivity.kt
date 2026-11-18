package online.uuuf.fnote

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.webkit.*
import android.widget.*

class MainActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var status: LinearLayout
    private lateinit var message: TextView
    private lateinit var retry: Button
    private var failed = false
    private val home = "https://uuuf.online/"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = FrameLayout(this)
        root.setBackgroundColor(Color.rgb(248, 249, 251))
        // Android 15 draws edge to edge. Apply system and keyboard insets once.
        root.setOnApplyWindowInsetsListener { view, insets ->
            view.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop,
                insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
            insets
        }
        web = WebView(this)
        root.addView(web, FrameLayout.LayoutParams(-1, -1))
        status = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.rgb(248, 249, 251))
            setPadding(32, 32, 32, 32)
        }
        status.addView(ImageView(this).apply { setImageResource(online.uuuf.fnote.R.drawable.fnote) },
            LinearLayout.LayoutParams(108, 108))
        message = TextView(this).apply { textSize = 17f; gravity = Gravity.CENTER }
        status.addView(message)
        retry = Button(this).apply {
            text = "重试"
            setOnClickListener { web.loadUrl(home) }
        }
        status.addView(retry)
        root.addView(status, FrameLayout.LayoutParams(-1, -1))
        setContentView(root)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            setSupportMultipleWindows(true)
        }
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false)
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                if (internal(request.url)) return false
                if (request.isForMainFrame) external(request.url)
                return true
            }
            override fun onPageStarted(view: WebView, url: String?, favicon: android.graphics.Bitmap?) {
                failed = false
                message.text = "正在加载 FNote…"
                retry.visibility = View.GONE
                status.visibility = View.VISIBLE
            }
            override fun onPageFinished(view: WebView, url: String?) {
                CookieManager.getInstance().flush()
                if (!failed) status.visibility = View.GONE
            }
            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) showError()
            }
            override fun onReceivedHttpError(view: WebView, request: WebResourceRequest, response: WebResourceResponse) {
                if (request.isForMainFrame && response.statusCode >= 400) showError()
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onCreateWindow(view: WebView, dialog: Boolean, gesture: Boolean, result: android.os.Message): Boolean {
                if (!gesture) return false
                val popup = WebView(this@MainActivity)
                popup.webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                        if (internal(request.url)) web.loadUrl(request.url.toString()) else external(request.url)
                        popup.destroy()
                        return true
                    }
                }
                (result.obj as WebView.WebViewTransport).webView = popup
                result.sendToTarget()
                return true
            }
        }
        if (savedInstanceState == null || web.restoreState(savedInstanceState) == null) web.loadUrl(home)
        else status.visibility = View.GONE
    }

    private fun internal(uri: Uri) = uri.scheme == "https" && uri.host == "uuuf.online" &&
        (uri.port == -1 || uri.port == 443) && uri.userInfo == null

    private fun external(uri: Uri) {
        if (uri.scheme != "https") return
        try { startActivity(Intent(Intent.ACTION_VIEW, uri).addCategory(Intent.CATEGORY_BROWSABLE)) }
        catch (_: ActivityNotFoundException) { Toast.makeText(this, "未找到可用的浏览器", Toast.LENGTH_SHORT).show() }
    }

    private fun showError() {
        failed = true
        message.text = "暂时无法连接，请检查网络后重试"
        retry.visibility = View.VISIBLE
        status.visibility = View.VISIBLE
    }

    @Deprecated("Legacy back dispatch for WebView")
    override fun onBackPressed() {
        // Ant Design handles Escape for its dialogs and drawers.
        web.evaluateJavascript("""
            (function() {
                const dialog = document.querySelector('.ant-modal-wrap:not([style*="display: none"]), .ant-drawer-open');
                if (!dialog) return false;
                const close = dialog.querySelector('.ant-modal-close, .ant-drawer-close');
                if (close) { close.click(); return true; }
                return false;
            })()
        """.trimIndent()) { handled ->
            if (handled != "true") {
                if (web.canGoBack()) web.goBack() else finish()
            }
        }
    }

    override fun onSaveInstanceState(outState: Bundle) { web.saveState(outState); super.onSaveInstanceState(outState) }
    override fun onPause() { CookieManager.getInstance().flush(); web.onPause(); super.onPause() }
    override fun onResume() { super.onResume(); if (::web.isInitialized) web.onResume() }
    override fun onDestroy() { web.destroy(); super.onDestroy() }
}
