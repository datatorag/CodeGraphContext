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
        // Refresh graph stats and repo list every 30 seconds
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self else { return }
                if self.pythonManager.isMCPServerRunning {
                    await self.indexingManager.refreshAll()
                    // Poll job progress if indexing
                    if self.indexingManager.isIndexing {
                        await self.indexingManager.pollJobProgress()
                    }
                }
            }
        }
        // Also do an initial fetch after services have had time to start
        Task {
            try? await Task.sleep(for: .seconds(10))
            if pythonManager.isMCPServerRunning {
                await indexingManager.refreshAll()
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
