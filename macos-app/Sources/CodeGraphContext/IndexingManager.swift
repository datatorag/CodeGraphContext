import Foundation
import os

/// Communicates with the CGC MCP server over HTTP JSON-RPC to index repositories and query state.
@MainActor
final class IndexingManager: ObservableObject {
    @Published var isIndexing = false
    @Published var indexingRepoName: String?
    @Published var indexingPhase: String?
    @Published var indexingElapsed: String?
    @Published var indexingJobId: String?
    @Published var indexedRepositories: [IndexedRepository] = []
    @Published var watchedPaths: Set<String> = []
    @Published var graphStats: GraphStats?
    @Published var activityLog: [ActivityEntry] = []

    private let logger = Logger(subsystem: "com.codegraphcontext.mac", category: "IndexingManager")

    var mcpPort: Int = 47321

    private var mcpURL: URL {
        URL(string: "http://localhost:\(mcpPort)/mcp")!
    }

    // MARK: - Index a Repository

    func indexRepository(at path: String) async {
        let repoName = URL(fileURLWithPath: path).lastPathComponent
        isIndexing = true
        indexingRepoName = repoName
        indexingPhase = "starting"
        indexingElapsed = nil
        logger.info("Starting indexing of \(repoName) at \(path)")
        addActivity("Indexing started for \(repoName)")

        do {
            let result = try await callTool("add_code_to_graph", arguments: ["path": path])
            // Extract job_id for progress tracking
            if let jobId = extractJobId(from: result) {
                indexingJobId = jobId
            }
            logger.info("Indexing complete for \(repoName)")
            addActivity("Indexing complete for \(repoName)")

            // Auto-watch the repo so the graph stays in sync as files change
            await watchRepository(at: path)

            // Refresh stats
            await refreshAll()
        } catch {
            logger.error("Indexing failed for \(repoName): \(error)")
            addActivity("Indexing failed for \(repoName)")
        }

        isIndexing = false
        indexingRepoName = nil
        indexingPhase = nil
        indexingElapsed = nil
        indexingJobId = nil
    }

    // MARK: - Job Progress Polling

    func pollJobProgress() async {
        guard let jobId = indexingJobId else { return }
        do {
            let result = try await callTool("check_job_status", arguments: ["job_id": jobId])
            if let text = extractText(from: result),
               let data = text.data(using: .utf8),
               let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
               let job = json["job"] as? [String: Any] {
                indexingPhase = job["phase"] as? String
                indexingElapsed = job["elapsed_time_human"] as? String
            }
        } catch {
            // Silently ignore polling errors
        }
    }

    // MARK: - File Watching

    func watchRepository(at path: String) async {
        do {
            _ = try await callTool("watch_directory", arguments: ["path": path])
            watchedPaths.insert(path)
            let name = URL(fileURLWithPath: path).lastPathComponent
            addActivity("Watch started for \(name)")
            logger.info("Auto-watching \(path) for changes")
        } catch {
            logger.error("Failed to watch \(path): \(error)")
        }
    }

    func unwatchRepository(at path: String) async {
        do {
            _ = try await callTool("unwatch_directory", arguments: ["path": path])
            watchedPaths.remove(path)
            let name = URL(fileURLWithPath: path).lastPathComponent
            addActivity("Watch stopped for \(name)")
            logger.info("Stopped watching \(path)")
        } catch {
            logger.error("Failed to unwatch \(path): \(error)")
        }
    }

    func unwatchAll() async {
        for path in watchedPaths {
            do {
                _ = try await callTool("unwatch_directory", arguments: ["path": path])
            } catch {
                logger.warning("Failed to unwatch \(path) on shutdown: \(error)")
            }
        }
        watchedPaths.removeAll()
    }

    // MARK: - Refresh All Data

    func refreshAll() async {
        await refreshRepositories()
        await refreshGraphStats()
    }

    func refreshRepositories() async {
        do {
            let result = try await callTool("list_indexed_repositories", arguments: [:])
            if let repos = parseRepoList(from: result) {
                indexedRepositories = repos
            }
        } catch {
            logger.error("Failed to list repos: \(error)")
        }
    }

    func refreshGraphStats() async {
        do {
            let result = try await callTool("get_repository_stats", arguments: ["path": "."])
            if let text = extractText(from: result),
               let data = text.data(using: .utf8),
               let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
               let stats = json["stats"] as? [String: Any] {
                graphStats = GraphStats(
                    files: stats["files"] as? Int ?? 0,
                    functions: stats["functions"] as? Int ?? 0,
                    classes: stats["classes"] as? Int ?? 0,
                    modules: stats["modules"] as? Int ?? 0
                )
            }
        } catch {
            // Stats not critical — silently ignore
        }
    }

    // MARK: - Activity Log

    private func addActivity(_ message: String) {
        let entry = ActivityEntry(message: message, timestamp: Date())
        activityLog.insert(entry, at: 0)
        // Keep last 10 entries
        if activityLog.count > 10 {
            activityLog = Array(activityLog.prefix(10))
        }
    }

    // MARK: - MCP JSON-RPC Communication

    private func callTool(_ name: String, arguments: [String: String]) async throws -> JSONRPCResponse {
        let request = JSONRPCRequest(
            jsonrpc: "2.0",
            id: Int.random(in: 1...999999),
            method: "tools/call",
            params: ToolCallParams(name: name, arguments: arguments)
        )

        var urlRequest = URLRequest(url: mcpURL)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = try JSONEncoder().encode(request)
        urlRequest.timeoutInterval = 600

        let (data, response) = try await URLSession.shared.data(for: urlRequest)

        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? -1
            throw IndexingError.serverError(statusCode: statusCode)
        }

        return try JSONDecoder().decode(JSONRPCResponse.self, from: data)
    }

    // MARK: - Response Parsing

    private func extractText(from response: JSONRPCResponse) -> String? {
        guard let content = response.result?["content"],
              case .array(let items) = content else { return nil }
        for item in items {
            if case .object(let obj) = item,
               case .string(let text)? = obj["text"] {
                return text
            }
        }
        return nil
    }

    private func extractJobId(from response: JSONRPCResponse) -> String? {
        guard let text = extractText(from: response),
              let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return json["job_id"] as? String
    }

    private func parseRepoList(from response: JSONRPCResponse) -> [IndexedRepository]? {
        guard let text = extractText(from: response),
              let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let repos = json["repositories"] as? [[String: Any]] else { return nil }

        let result = repos.map { repo in
            let path = repo["path"] as? String ?? ""
            let name = repo["name"] as? String ?? URL(fileURLWithPath: path).lastPathComponent
            return IndexedRepository(name: name, path: path)
        }
        return result.isEmpty ? nil : result
    }
}

// MARK: - Data Types

struct GraphStats {
    let files: Int
    let functions: Int
    let classes: Int
    let modules: Int

    var totalNodes: Int { files + functions + classes + modules }
}

struct ActivityEntry: Identifiable {
    let id = UUID()
    let message: String
    let timestamp: Date

    var relativeTime: String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: timestamp, relativeTo: Date())
    }
}

// MARK: - JSON-RPC Types

struct JSONRPCRequest: Encodable {
    let jsonrpc: String
    let id: Int
    let method: String
    let params: ToolCallParams
}

struct ToolCallParams: Encodable {
    let name: String
    let arguments: [String: String]
}

struct JSONRPCResponse: Decodable {
    let jsonrpc: String
    let id: Int?
    let result: [String: JSONValue]?
    let error: JSONRPCError?
}

struct JSONRPCError: Decodable {
    let code: Int
    let message: String
}

/// Lightweight JSON value type for decoding arbitrary MCP responses.
enum JSONValue: Decodable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let v = try? container.decode(String.self) { self = .string(v) }
        else if let v = try? container.decode(Int.self) { self = .int(v) }
        else if let v = try? container.decode(Double.self) { self = .double(v) }
        else if let v = try? container.decode(Bool.self) { self = .bool(v) }
        else if let v = try? container.decode([String: JSONValue].self) { self = .object(v) }
        else if let v = try? container.decode([JSONValue].self) { self = .array(v) }
        else if container.decodeNil() { self = .null }
        else { throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value") }
    }
}

enum IndexingError: LocalizedError {
    case serverError(statusCode: Int)

    var errorDescription: String? {
        switch self {
        case .serverError(let code): return "MCP server returned HTTP \(code)"
        }
    }
}
