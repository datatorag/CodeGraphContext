import SwiftUI
import AppKit

struct MenuBarView: View {
    @ObservedObject var appState: AppState
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        // Status indicator
        statusSection

        Divider()

        Button("Open Visualization") {
            openWindow(id: "visualization")
            NSApp.setActivationPolicy(.regular)
            NSApp.activate(ignoringOtherApps: true)
        }
        .disabled(!appState.pythonManager.isVizServerRunning)

        repositoriesSection

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

    // MARK: - Status

    @ViewBuilder
    private var statusSection: some View {
        if appState.indexingManager.isIndexing, let name = appState.indexingManager.indexingRepoName {
            HStack(spacing: 6) {
                ProgressView()
                    .controlSize(.small)
                Text("Indexing \(name)...")
            }
        } else {
            HStack(spacing: 6) {
                Image(systemName: "circle.fill")
                    .foregroundColor(appState.pythonManager.isFalkorDBRunning ? .green : .red)
                    .font(.system(size: 8))
                Text("FalkorDB")
            }
            HStack(spacing: 6) {
                Image(systemName: "circle.fill")
                    .foregroundColor(appState.pythonManager.isMCPServerRunning ? .green : .red)
                    .font(.system(size: 8))
                Text("MCP Server")
            }
            HStack(spacing: 6) {
                Image(systemName: "circle.fill")
                    .foregroundColor(appState.pythonManager.isVizServerRunning ? .green : .red)
                    .font(.system(size: 8))
                Text("Visualization")
            }
        }
    }

    // MARK: - Repositories

    @ViewBuilder
    private var repositoriesSection: some View {
        Menu("Indexed Repositories") {
            if appState.indexingManager.indexedRepositories.isEmpty {
                Text("No repositories indexed")
                    .foregroundColor(.secondary)
            } else {
                ForEach(appState.indexingManager.indexedRepositories) { repo in
                    Button {
                        // Could reveal in Finder or show details
                    } label: {
                        Label(repo.name, systemImage: "folder")
                    }
                }
            }

            Divider()

            Button("Refresh") {
                Task { await appState.indexingManager.refreshRepositories() }
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
}
