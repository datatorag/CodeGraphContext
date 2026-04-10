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
            openWindow(id: "visualization")
            NSApp.setActivationPolicy(.regular)
            NSApp.activate(ignoringOtherApps: true)
        }
        .disabled(!appState.pythonManager.isVizServerRunning)

        Button("Index Repository...") {
            indexRepository()
        }
        .keyboardShortcut("i", modifiers: [.command])
        .disabled(!appState.pythonManager.isMCPServerRunning || appState.indexingManager.isIndexing)

        Divider()

        SettingsLink {
            Text("Settings...")
        }
        .keyboardShortcut(",", modifiers: [.command])

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
        let dot = isRunning ? "\u{1F7E2}" : "\u{1F534}"  // green/red circle emoji
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
        let watchBadge = isWatched ? " \u{1F441}" : ""  // eye emoji

        return Menu("\u{1F4C1} \(repo.name)\(watchBadge)") {
            Text(repo.path)
                .foregroundColor(.secondary)

            Divider()

            Button("Reindex") {
                Task { await appState.indexingManager.indexRepository(at: repo.path) }
            }
            .disabled(appState.indexingManager.isIndexing)

            if isWatched {
                Button("Stop Watching") {
                    Task { await appState.indexingManager.unwatchRepository(at: repo.path) }
                }
            } else {
                Button("Start Watching") {
                    Task { await appState.indexingManager.watchRepository(at: repo.path) }
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

    // MARK: - Actions

    private func indexRepository() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.message = "Select a repository to index"
        panel.prompt = "Index"

        panel.begin { response in
            if response == .OK, let url = panel.url {
                Task {
                    await appState.indexingManager.indexRepository(at: url.path)
                }
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
