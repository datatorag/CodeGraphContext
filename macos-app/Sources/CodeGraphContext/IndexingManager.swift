import Foundation
import os

/// Communicates with the CGC MCP server over HTTP JSON-RPC to index repositories and query state.
@MainActor
final class IndexingManager: ObservableObject {
    @Published var isIndexing = false
    @Published var indexingRepoName: String?
    @Published var indexedRepositories: [IndexedRepository] = []

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
        logger.info("Starting indexing of \(repoName) at \(path)")

        do {
            _ = try await callTool("add_code_to_graph", arguments: [
                "repo_path": path
            ])
            logger.info("Indexing complete for \(repoName)")

            // Refresh the repository list
            await refreshRepositories()
        } catch {
            logger.error("Indexing failed for \(repoName): \(error)")
        }

        isIndexing = false
        indexingRepoName = nil
    }

    // MARK: - List Repositories

    func refreshRepositories() async {
        do {
            let result = try await callTool("list_repos", arguments: [:])
            // Parse the response — the tool returns content with repo information
            if let repos = parseRepoList(from: result) {
                indexedRepositories = repos
            }
            logger.info("Refreshed repo list: \(self.indexedRepositories.count) repositories")
        } catch {
            logger.error("Failed to list repos: \(error)")
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
        // Indexing can take a long time for large repos
        urlRequest.timeoutInterval = 600

        let (data, response) = try await URLSession.shared.data(for: urlRequest)

        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? -1
            throw IndexingError.serverError(statusCode: statusCode)
        }

        return try JSONDecoder().decode(JSONRPCResponse.self, from: data)
    }

    private func parseRepoList(from response: JSONRPCResponse) -> [IndexedRepository]? {
        guard let content = response.result?["content"] else { return nil }

        // The MCP tool response content is an array of content blocks
        // Try to extract repo names from text content
        if case .array(let items) = content {
            var repos: [IndexedRepository] = []
            for item in items {
                if case .object(let obj) = item,
                   case .string(let text)? = obj["text"] {
                    // Parse repo entries from the text response
                    for line in text.components(separatedBy: "\n") {
                        let trimmed = line.trimmingCharacters(in: .whitespaces)
                        if !trimmed.isEmpty && !trimmed.hasPrefix("#") {
                            let name = URL(fileURLWithPath: trimmed).lastPathComponent
                            repos.append(IndexedRepository(name: name.isEmpty ? trimmed : name, path: trimmed))
                        }
                    }
                }
            }
            return repos.isEmpty ? nil : repos
        }

        return nil
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
