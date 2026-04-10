import SwiftUI

@main
struct CodeGraphContextApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var appState = AppState()

    var body: some Scene {
        MenuBarExtra {
            MenuBarView(appState: appState)
        } label: {
            HStack(spacing: 2) {
                Image(systemName: "arrow.triangle.branch")
                Image(systemName: "circle.fill")
                    .font(.system(size: 6))
                    .foregroundColor(menuBarDotColor)
            }
        }
        .menuBarExtraStyle(.menu)

        Window("CodeGraphContext - Visualization", id: "visualization") {
            VisualizationWindow(port: appState.vizPort)
        }
        .defaultSize(width: 1200, height: 800)

        Settings {
            SettingsView()
        }
    }

    /// Green: all services healthy. Yellow: indexing. Red: FalkorDB or MCP down.
    private var menuBarDotColor: Color {
        if appState.indexingManager.isIndexing {
            return .yellow
        }
        let pm = appState.pythonManager
        if pm.isFalkorDBRunning && pm.isMCPServerRunning {
            return .green
        }
        return .red
    }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Hide from dock — menu bar only app
        NSApp.setActivationPolicy(.accessory)
    }

    func applicationWillTerminate(_ notification: Notification) {
        // Subprocesses are cleaned up via AppState.stop() called from Quit button
    }
}
