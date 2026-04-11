import SwiftUI
import AppKit

private let pluginsJsonPath: String = {
    FileManager.default.homeDirectoryForCurrentUser.path + "/.claude/plugins/installed_plugins.json"
}()

private func activateApp() {
    NSApp.setActivationPolicy(.regular)
    NSApp.activate(ignoringOtherApps: true)
}

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
        // Refresh immediately on open + every 10s while menu is visible
        TimelineView(.periodic(from: .now, by: 10)) { _ in
            Color.clear.frame(height: 0)
                .onAppear { appState.refreshOnMenuOpen() }
        }

        Button("Setup Guide...") {
            activateApp()
            openWindow(id: "setup-guide")
        }
        Divider()

        reposSection
        Divider()

        statusSection
        Divider()

        Button("Quit CodeGraphContext") {
            appState.stop()
            NSApplication.shared.terminate(nil)
        }
    }

    // MARK: - Repositories

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
            activateApp()
            // Deferred to let SwiftUI dismiss the menu before showing the modal
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
        .disabled(!pm.isMCPServerRunning)
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
                activateApp()
                // Deferred to let SwiftUI dismiss the menu before showing the modal
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

    // MARK: - Status

    @ViewBuilder
    private var statusSection: some View {
        Text("Status")
            .foregroundColor(.secondary)

        if appState.isPluginInstalled {
            Text("\u{2705} Claude Code Plugin Installed")
        } else {
            Button("\u{26A0}\u{FE0F} Plugin Not Installed \u{2014} Install...") {
                activateApp()
                openWindow(id: "setup-guide")
            }
        }

        let allUp = pm.isFalkorDBRunning && pm.isMCPServerRunning && pm.isVizServerRunning
        if allUp {
            Text("\u{1F7E2} All Services Running")
        } else {
            svcLine("FalkorDB", port: pm.falkorDBPort, up: pm.isFalkorDBRunning)
            svcLine("MCP Server", port: pm.mcpPort, up: pm.isMCPServerRunning)
            svcLine("Visualization", port: pm.vizPort, up: pm.isVizServerRunning)
        }

        if let s = im.graphStats {
            Text("\u{1F4CA} \(fmt(s.totalNodes)) nodes \u{00B7} \(fmt(s.files)) files \u{00B7} \(fmt(s.functions)) functions")
        }
    }

    private func svcLine(_ name: String, port: Int, up: Bool) -> some View {
        let dot = up ? "\u{1F7E2}" : "\u{1F534}"
        let status = up ? ":\(port)" : "Stopped"
        return Text("\(dot) \(name) \(status)")
    }

    // MARK: - Helpers

    private func fmt(_ n: Int) -> String {
        if n >= 1000 {
            let k = Double(n) / 1000.0
            return k >= 100 ? "\(Int(k))K" : String(format: "%.1fK", k)
        }
        return "\(n)"
    }
}
