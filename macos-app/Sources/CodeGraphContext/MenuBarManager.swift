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

        // Bottom actions
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
        serviceRow("FalkorDB", port: appState.pythonManager.falkorDBPort,
                   isRunning: appState.pythonManager.isFalkorDBRunning)
        serviceRow("MCP Server", port: appState.pythonManager.mcpPort,
                   isRunning: appState.pythonManager.isMCPServerRunning)
        serviceRow("Visualization", port: appState.pythonManager.vizPort,
                   isRunning: appState.pythonManager.isVizServerRunning)
    }

    private func serviceRow(_ name: String, port: Int, isRunning: Bool) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "circle.fill")
                .foregroundColor(isRunning ? .green : .red)
                .font(.system(size: 8))
            Text("\(name)")
            Spacer()
            Text(":\(port)")
                .foregroundColor(.secondary)
                .font(.system(.body, design: .monospaced))
        }
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

        return Menu {
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
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "folder.fill")
                    .foregroundColor(.accentColor)
                Text(repo.name)
                Spacer()
                if isWatched {
                    Image(systemName: "eye")
                        .foregroundColor(.green)
                        .font(.system(size: 10))
                }
            }
        }
    }

    // MARK: - Indexing Progress

    @ViewBuilder
    private var indexingProgressSection: some View {
        if let name = appState.indexingManager.indexingRepoName {
            HStack(spacing: 6) {
                ProgressView()
                    .controlSize(.small)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Indexing \(name)")
                        .font(.system(.body, weight: .medium))
                    if let phase = appState.indexingManager.indexingPhase {
                        HStack(spacing: 4) {
                            Text(phase.replacingOccurrences(of: "_", with: " "))
                                .foregroundColor(.secondary)
                            if let elapsed = appState.indexingManager.indexingElapsed {
                                Text("(\(elapsed))")
                                    .foregroundColor(.secondary)
                            }
                        }
                        .font(.system(.caption))
                    }
                }
            }
        }
    }

    // MARK: - Graph Stats

    private func graphStatsSection(_ stats: GraphStats) -> some View {
        Menu {
            Text("\(formatted(stats.files)) files")
            Text("\(formatted(stats.functions)) functions")
            Text("\(formatted(stats.classes)) classes")
            Text("\(formatted(stats.modules)) modules")
        } label: {
            HStack {
                Image(systemName: "chart.bar.fill")
                Text("Graph: \(formatted(stats.totalNodes)) nodes")
                    .foregroundColor(.secondary)
            }
        }
    }

    // MARK: - Activity Feed

    @ViewBuilder
    private var activitySection: some View {
        Menu {
            ForEach(appState.indexingManager.activityLog.prefix(5)) { entry in
                Text("\(entry.message) \(entry.relativeTime)")
            }
        } label: {
            HStack {
                Image(systemName: "clock")
                Text("Recent Activity")
                    .foregroundColor(.secondary)
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
