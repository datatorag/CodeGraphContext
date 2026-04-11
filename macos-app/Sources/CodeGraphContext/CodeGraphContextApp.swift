import SwiftUI
import AppKit

@main
struct CodeGraphContextApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var appState = AppState()

    var body: some Scene {
        MenuBarExtra {
            MenuBarView(appState: appState)
        } label: {
            HStack(spacing: 2) {
                Image(nsImage: Self.menuBarIcon())
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

        Window("Setup Guide", id: "setup-guide") {
            SetupGuideView(appState: appState)
        }
        .defaultSize(width: 520, height: 440)
        .windowResizability(.contentSize)

        Settings {
            SettingsView()
        }
    }

    /// Hub-and-spoke graph in a circle ring (Life360-inspired).
    private static func menuBarIcon() -> NSImage {
        let size = NSSize(width: 18, height: 18)
        let image = NSImage(size: size, flipped: false) { rect in
            let cx: CGFloat = 9
            let cy: CGFloat = 9

            // Outer ring
            let ringRect = NSRect(x: 1.5, y: 1.5, width: 15, height: 15)
            let ring = NSBezierPath(ovalIn: ringRect)
            ring.lineWidth = 1.5
            NSColor.black.setStroke()
            ring.stroke()

            // Center hub
            let hub = NSPoint(x: cx, y: cy)

            // 3 nodes on perimeter (evenly spaced, like Life360 people)
            let n1 = NSPoint(x: cx, y: cy + 6)           // top
            let n2 = NSPoint(x: cx - 5.2, y: cy - 3)     // bottom-left
            let n3 = NSPoint(x: cx + 5.2, y: cy - 3)     // bottom-right

            // Edges from hub to each node
            let edges = NSBezierPath()
            edges.lineWidth = 1.2
            for n in [n1, n2, n3] {
                edges.move(to: hub); edges.line(to: n)
            }
            NSColor.black.setStroke()
            edges.stroke()

            // Hub node (larger)
            let hr: CGFloat = 2.8
            let hubRect = NSRect(x: hub.x - hr, y: hub.y - hr, width: hr * 2, height: hr * 2)
            NSBezierPath(ovalIn: hubRect).fill()

            // Perimeter nodes
            let r: CGFloat = 2.0
            for n in [n1, n2, n3] {
                let nodeRect = NSRect(x: n.x - r, y: n.y - r, width: r * 2, height: r * 2)
                NSColor.black.setFill()
                NSBezierPath(ovalIn: nodeRect).fill()
            }
            return true
        }
        image.isTemplate = true
        return image
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
