import SwiftUI
import AppKit

struct MenuBarView: View {
    @ObservedObject var appState: AppState
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        servicesSection

        Divider()

        repositoriesSection

        Divider()

        if appState.indexingManager.isIndexing {
            indexingProgressSection
            Divider()
        }

        if let stats = appState.indexingManager.graphStats {
            graphStatsSection(stats)
            Divider()
        }

        if !appState.indexingManager.activityLog.isEmpty {
            activitySection
            Divider()
        }

        Button("Open Visualization") {
            if appState.pythonManager.isVizServerRunning {
                NSWorkspace.shared.open(URL(string: "http://localhost:\(appState.pythonManager.vizPort)/explore")!)
            }
        }
        .disabled(!appState.pythonManager.isVizServerRunning)

        Button("Index Repository...") {
            // Activate app so NSOpenPanel appears in front
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
                    Task { @MainActor in
                        await appState.indexingManager.indexRepository(at: url.path)
                    }
                }

                // Return to accessory mode after dialog closes
                NSApp.setActivationPolicy(.accessory)
            }
        }
        .disabled(!appState.pythonManager.isMCPServerRunning || appState.indexingManager.isIndexing)

        Divider()

        Button("Settings...") {
            NSApp.setActivationPolicy(.regular)
            NSApp.activate(ignoringOtherApps: true)
            if #available(macOS 14, *) {
                NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
            } else {
                NSApp.sendAction(Selector(("showPreferencesWindow:")), to: nil, from: nil)
            }
        }

        Button("Quit") {
            appState.stop()
            NSApplication.shared.terminate(nil)
        }
        .keyboardShortcut("q", modifiers: [.command])
    }

    // MARK: - Services

    @ViewBuilder
    private var servicesSection: some View {
        serviceItem("FalkorDB", port: appState.pythonManager.falkorDBPort,
                    isRunning: appState.pythonManager.isFalkorDBRunning)
        serviceItem("MCP Server", port: appState.pythonManager.mcpPort,
                    isRunning: appState.pythonManager.isMCPServerRunning)
        serviceItem("Visualization", port: appState.pythonManager.vizPort,
                    isRunning: appState.pythonManager.isVizServerRunning)
    }

    private func serviceItem(_ name: String, port: Int, isRunning: Bool) -> some View {
        let dot = isRunning ? "\u{1F7E2}" : "\u{1F534}"
        let status = isRunning ? "Running on :\(port)" : "Stopped"
        return Text("\(dot) \(name) \u{2014} \(status)")
    }

    // MARK: - Repositories

    @ViewBuilder
    private var repositoriesSection: some View {
        if appState.indexingManager.indexedRepositories.isEmpty {
            Text("No repositories indexed")
                .foregroundColor(.secondary)
        } else {
            ForEach(appState.indexingManager.indexedRepositories) { repo in
                repoMenu(repo)
            }
        }
    }

    private func repoMenu(_ repo: IndexedRepository) -> some View {
        let isWatched = appState.indexingManager.watchedPaths.contains(repo.path)
        let watchBadge = isWatched ? " \u{1F441}" : ""

        return Menu("\u{1F4C1} \(repo.name)\(watchBadge)") {
            Text(repo.path)

            Divider()

            Button("Reindex") {
                Task { @MainActor in
                    await appState.indexingManager.indexRepository(at: repo.path)
                }
            }
            .disabled(appState.indexingManager.isIndexing)

            if isWatched {
                Button("Stop Watching") {
                    Task { @MainActor in
                        await appState.indexingManager.unwatchRepository(at: repo.path)
                    }
                }
            } else {
                Button("Start Watching") {
                    Task { @MainActor in
                        await appState.indexingManager.watchRepository(at: repo.path)
                    }
                }
            }

            Button("Open in Finder") {
                NSWorkspace.shared.selectFile(nil, inFileViewerRootedAtPath: repo.path)
            }
        }
    }

    // MARK: - Indexing Progress

    @ViewBuilder
    private var indexingProgressSection: some View {
        if let name = appState.indexingManager.indexingRepoName {
            let phase = appState.indexingManager.indexingPhase?
                .replacingOccurrences(of: "_", with: " ") ?? "starting"
            let elapsed = appState.indexingManager.indexingElapsed.map { " (\($0))" } ?? ""
            Text("\u{23F3} Indexing \(name) \u{2014} \(phase)\(elapsed)")
        }
    }

    // MARK: - Graph Stats

    private func graphStatsSection(_ stats: GraphStats) -> some View {
        Menu("\u{1F4CA} Graph: \(formatted(stats.totalNodes)) nodes") {
            Text("\(formatted(stats.files)) files")
            Text("\(formatted(stats.functions)) functions")
            Text("\(formatted(stats.classes)) classes")
            Text("\(formatted(stats.modules)) modules")
        }
    }

    // MARK: - Activity Feed

    @ViewBuilder
    private var activitySection: some View {
        Menu("\u{1F552} Recent Activity") {
            ForEach(appState.indexingManager.activityLog.prefix(5)) { entry in
                Text("\(entry.message) \u{2014} \(entry.relativeTime)")
            }
        }
    }

    // MARK: - Helpers

    private func formatted(_ n: Int) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        return formatter.string(from: NSNumber(value: n)) ?? "\(n)"
    }
}
