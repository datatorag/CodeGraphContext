import SwiftUI
import Combine

@MainActor
final class AppState: ObservableObject {
    let pythonManager = PythonManager()
    let indexingManager = IndexingManager()

    var serverPort: Int { pythonManager.mcpPort }
    var vizPort: Int { pythonManager.vizPort }

    /// Cached plugin install status (refreshed on menu open, avoids disk I/O in view body)
    @Published var isPluginInstalled = false

    private var cancellables = Set<AnyCancellable>()
    private var isRefreshing = false

    init() {
        pythonManager.objectWillChange
            .throttle(for: .seconds(1), scheduler: RunLoop.main, latest: true)
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &cancellables)

        indexingManager.objectWillChange
            .throttle(for: .seconds(1), scheduler: RunLoop.main, latest: true)
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &cancellables)

        indexingManager.mcpPort = pythonManager.mcpPort
        start()
    }

    func start() {
        pythonManager.startAll()
        Task {
            try? await Task.sleep(for: .seconds(8))
            await indexingManager.refreshAll()
            checkPluginInstalled()
        }
    }

    func stop() {
        Task { await indexingManager.unwatchAll() }
        pythonManager.stopAll()
    }

    /// Called when user opens the menu. Guarded to prevent piling up concurrent refreshes.
    func refreshOnMenuOpen() {
        guard !isRefreshing else { return }
        isRefreshing = true
        Task {
            await indexingManager.refreshAll()
            if indexingManager.isIndexing {
                await indexingManager.pollJobProgress()
            }
            checkPluginInstalled()
            isRefreshing = false
        }
    }

    private func checkPluginInstalled() {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let path = "\(home)/.claude/plugins/installed_plugins.json"
        guard let data = FileManager.default.contents(atPath: path),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let plugins = json["plugins"] as? [String: Any] else {
            isPluginInstalled = false
            return
        }
        isPluginInstalled = plugins.keys.contains { $0.contains("codegraphcontext") }
    }
}

struct IndexedRepository: Identifiable {
    let id = UUID()
    let name: String
    let path: String
}
