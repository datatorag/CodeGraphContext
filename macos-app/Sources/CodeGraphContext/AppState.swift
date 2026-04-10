import SwiftUI
import Combine

@MainActor
final class AppState: ObservableObject {
    let pythonManager = PythonManager()
    let indexingManager = IndexingManager()

    var serverPort: Int { pythonManager.mcpPort }
    var vizPort: Int { pythonManager.vizPort }

    private var cancellables = Set<AnyCancellable>()
    private var refreshTimer: Timer?

    init() {
        // Forward child ObservableObject changes so SwiftUI views update
        pythonManager.objectWillChange
            .receive(on: RunLoop.main)
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &cancellables)

        indexingManager.objectWillChange
            .receive(on: RunLoop.main)
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &cancellables)

        // Keep indexing manager's port in sync
        indexingManager.mcpPort = pythonManager.mcpPort

        // Auto-start servers on launch
        start()
    }

    func start() {
        pythonManager.startAll()
        startPeriodicRefresh()
    }

    func stop() {
        stopPeriodicRefresh()
        Task { await indexingManager.unwatchAll() }
        pythonManager.stopAll()
    }

    // MARK: - Periodic Data Refresh

    private func startPeriodicRefresh() {
        // Refresh every 10 seconds — calls are cheap HTTP GETs and fail silently
        // when MCP isn't ready yet
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self else { return }
                await self.indexingManager.refreshAll()
                if self.indexingManager.isIndexing {
                    await self.indexingManager.pollJobProgress()
                }
            }
        }
        // Initial fetch — retry a few times in case MCP is still starting
        Task {
            for delay in [5, 10, 20] {
                try? await Task.sleep(for: .seconds(delay))
                await indexingManager.refreshAll()
                if !indexingManager.indexedRepositories.isEmpty { break }
            }
        }
    }

    private func stopPeriodicRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
    }
}

struct IndexedRepository: Identifiable {
    let id = UUID()
    let name: String
    let path: String
}
