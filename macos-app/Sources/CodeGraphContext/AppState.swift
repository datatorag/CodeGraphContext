import SwiftUI
import Combine

@MainActor
final class AppState: ObservableObject {
    let pythonManager = PythonManager()
    let indexingManager = IndexingManager()

    var serverPort: Int { pythonManager.mcpPort }
    var vizPort: Int { pythonManager.vizPort }

    private var cancellables = Set<AnyCancellable>()

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
    }

    func stop() {
        pythonManager.stopAll()
    }
}

struct IndexedRepository: Identifiable {
    let id = UUID()
    let name: String
    let path: String
}
