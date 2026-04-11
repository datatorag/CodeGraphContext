import SwiftUI
import AppKit

struct MenuBarView: View {
    @ObservedObject var appState: AppState
    @Environment(\.openWindow) private var openWindow

    private let pm: PythonManager
    private let im: IndexingManager

    init(appState: AppState) {
        self.appState = appState
        self.pm = appState.pythonManager
        self.im = appState.indexingManager
    }

    var body: some View {
        // ── Section 1: Plugin & Setup ──
        pluginSection
        Divider()

        // ── Section 2: Repositories ──
        reposSection
        Divider()

        // ── Section 3: Status ──
        statusSection
        Divider()

        // ── Section 4: App ──
        Button("Settings...") {
            NSApp.setActivationPolicy(.regular)
            NSApp.activate(ignoringOtherApps: true)
            if #available(macOS 14, *) {
                NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
            } else {
                NSApp.sendAction(Selector(("showPreferencesWindow:")), to: nil, from: nil)
            }
        }
        .keyboardShortcut(",", modifiers: [.command])

        Button("Quit") {
            appState.stop()
            NSApplication.shared.terminate(nil)
        }
        .keyboardShortcut("q", modifiers: [.command])
    }

    // ═══════════════════════════════════════════════════
    // MARK: - Section 1: Plugin & Setup
    // ═══════════════════════════════════════════════════

    @ViewBuilder
    private var pluginSection: some View {
        let installed = Self.isPluginInstalled()
        if installed {
            Text("\u{2705} Claude Code Plugin Installed")
        } else {
            Button("\u{26A0}\u{FE0F} Plugin Not Installed \u{2014} Install...") {
                NSApp.setActivationPolicy(.regular)
                NSApp.activate(ignoringOtherApps: true)
                openWindow(id: "setup-guide")
            }
            Button("Setup Guide...") {
                NSApp.setActivationPolicy(.regular)
                NSApp.activate(ignoringOtherApps: true)
                openWindow(id: "setup-guide")
            }
        }
    }

    private static func isPluginInstalled() -> Bool {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let path = "\(home)/.claude/plugins/installed_plugins.json"
        guard let data = FileManager.default.contents(atPath: path),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let plugins = json["plugins"] as? [String: Any] else {
            return false
        }
        return plugins.keys.contains { $0.contains("codegraphcontext") }
    }

    // ═══════════════════════════════════════════════════
    // MARK: - Section 2: Repositories
    // ═══════════════════════════════════════════════════

    @ViewBuilder
    private var reposSection: some View {
        Text("Repositories")
            .foregroundColor(.secondary)

        if im.indexedRepositories.isEmpty {
            Text("  No repositories indexed")
                .foregroundColor(.secondary)
        } else {
            ForEach(im.indexedRepositories) { repo in
                repoSubmenu(repo)
            }
        }

        if im.isIndexing, let name = im.indexingRepoName {
            let phase = im.indexingPhase?.replacingOccurrences(of: "_", with: " ") ?? "starting"
            let elapsed = im.indexingElapsed.map { " (\($0))" } ?? ""
            Text("\u{23F3} Indexing \(name) \u{2014} \(phase)\(elapsed)")
        }

        Button("Index Repository...") {
            NSApp.setActivationPolicy(.regular)
            NSApp.activate(ignoringOtherApps: true)
            DispatchQueue.main.async {
                let panel = NSOpenPanel()
                panel.canChooseDirectories = true
                panel.canChooseFiles = false
                panel.allowsMultipleSelection = false
                panel.message = "Select a repository to index"
                panel.prompt = "Index"
                if panel.runModal() == .OK, let url = panel.url {
                    if let error = IndexingManager.validateRepoPath(url.path) {
                        let alert = NSAlert()
                        alert.messageText = "Cannot Index Directory"
                        alert.informativeText = error
                        alert.alertStyle = .warning
                        alert.addButton(withTitle: "OK")
                        alert.runModal()
                    } else {
                        Task { @MainActor in
                            await im.indexRepository(at: url.path)
                        }
                    }
                }
                NSApp.setActivationPolicy(.accessory)
            }
        }
        .keyboardShortcut("i", modifiers: [.command])
        .disabled(!pm.isMCPServerRunning || im.isIndexing)
    }

    private func repoSubmenu(_ repo: IndexedRepository) -> some View {
        let isWatched = im.watchedPaths.contains(repo.path)
        let badge = isWatched ? " \u{1F441}" : ""

        return Menu("\u{1F4C1} \(repo.name)\(badge)") {
            Button("Open Visualization") {
                let port = pm.vizPort
                let enc = repo.path.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? repo.path
                if let url = URL(string: "http://localhost:\(port)/explore?backend=http%3A%2F%2Flocalhost%3A\(port)&repo_path=\(enc)") {
                    NSWorkspace.shared.open(url)
                }
            }
            .disabled(!pm.isVizServerRunning)

            Button("Reindex") {
                Task { @MainActor in await im.indexRepository(at: repo.path) }
            }
            .disabled(im.isIndexing)

            if isWatched {
                Button("Stop Watching") {
                    Task { @MainActor in await im.unwatchRepository(at: repo.path) }
                }
            } else {
                Button("Start Watching") {
                    Task { @MainActor in await im.watchRepository(at: repo.path) }
                }
            }

            Divider()

            Button("Remove from Index") {
                NSApp.setActivationPolicy(.regular)
                NSApp.activate(ignoringOtherApps: true)
                DispatchQueue.main.async {
                    let alert = NSAlert()
                    alert.messageText = "Remove \(repo.name)?"
                    alert.informativeText = "This will delete all indexed data for \(repo.name) from the graph. The source files are not affected."
                    alert.alertStyle = .warning
                    alert.addButton(withTitle: "Remove")
                    alert.addButton(withTitle: "Cancel")
                    if alert.runModal() == .alertFirstButtonReturn {
                        Task { @MainActor in await im.removeRepository(at: repo.path) }
                    }
                    NSApp.setActivationPolicy(.accessory)
                }
            }
        }
    }

    // ═══════════════════════════════════════════════════
    // MARK: - Section 3: Status
    // ═══════════════════════════════════════════════════

    @ViewBuilder
    private var statusSection: some View {
        Text("Status")
            .foregroundColor(.secondary)

        // Services: condensed if all healthy, expanded if any down
        let allUp = pm.isFalkorDBRunning && pm.isMCPServerRunning && pm.isVizServerRunning
        if allUp {
            Text("\u{1F7E2} All Services Running")
        } else {
            svcLine("FalkorDB", port: pm.falkorDBPort, up: pm.isFalkorDBRunning)
            svcLine("MCP Server", port: pm.mcpPort, up: pm.isMCPServerRunning)
            svcLine("Visualization", port: pm.vizPort, up: pm.isVizServerRunning)
        }

        // Graph stats: single line
        if let s = im.graphStats {
            Text("\u{1F4CA} \(fmt(s.totalNodes)) nodes \u{00B7} \(fmt(s.files)) files \u{00B7} \(fmt(s.functions)) functions")
        }
    }

    private func svcLine(_ name: String, port: Int, up: Bool) -> some View {
        let dot = up ? "\u{1F7E2}" : "\u{1F534}"
        let status = up ? ":\(port)" : "Stopped"
        return Text("\(dot) \(name) \(status)")
    }

    // ═══════════════════════════════════════════════════
    // MARK: - Helpers
    // ═══════════════════════════════════════════════════

    private func fmt(_ n: Int) -> String {
        if n >= 1000 {
            let k = Double(n) / 1000.0
            return k >= 100 ? "\(Int(k))K" : String(format: "%.1fK", k)
        }
        return "\(n)"
    }
}
