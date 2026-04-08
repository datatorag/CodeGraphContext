import SwiftUI
import WebKit

struct VisualizationWindow: View {
    let port: Int

    var body: some View {
        WebViewWrapper(url: URL(string: "http://localhost:\(port)/explore?backend=http%3A%2F%2Flocalhost%3A\(port)")!)
            .frame(minWidth: 800, minHeight: 600)
    }
}

struct WebViewWrapper: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        // Reload if URL changed
        if webView.url != url {
            webView.load(URLRequest(url: url))
        }
    }
}
