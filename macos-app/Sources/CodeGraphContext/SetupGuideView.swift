import SwiftUI
import AppKit

struct SetupGuideView: View {
    @ObservedObject var appState: AppState
    @Environment(\.dismiss) private var dismiss
    @State private var step = 0
    @State private var indexPath: String?
    @State private var indexStats: String?
    @State private var isIndexing = false
    @State private var copied = false

    private let totalSteps = 4

    var body: some View {
        VStack(spacing: 0) {
            // Progress bar
            ProgressView(value: Double(step), total: Double(totalSteps - 1))
                .padding(.horizontal, 24)
                .padding(.top, 16)

            // Step content
            Group {
                switch step {
                case 0: welcomeStep
                case 1: pluginStep
                case 2: indexStep
                case 3: tryItStep
                default: EmptyView()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(24)
        }
        .frame(width: 520, height: 440)
    }

    // MARK: - Step 0: Welcome

    private var welcomeStep: some View {
        VStack(spacing: 16) {
            Text("Welcome to CodeGraphContext")
                .font(.title2.bold())

            Text("CodeGraphContext gives Claude Code structural understanding of your codebase. It parses your code into a graph database, then exposes query tools so Claude can answer questions like \"who calls this function?\" or \"find dead code\" in milliseconds.")
                .multilineTextAlignment(.center)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Spacer()

            VStack(spacing: 8) {
                HStack(spacing: 24) {
                    statBox("16", "Languages")
                    statBox("21", "MCP Tools")
                    statBox("6", "Node Types")
                }
                Text("Functions, Classes, Imports, Calls, Inheritance, Parameters")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer()

            navButtons(backLabel: nil, nextLabel: "Get Started")
        }
    }

    // MARK: - Step 1: Plugin

    private var pluginStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Connect to Claude Code")
                .font(.title2.bold())
                .frame(maxWidth: .infinity, alignment: .center)

            Text("Install the plugin so Claude Code can use the graph tools.")
                .foregroundColor(.secondary)
                .frame(maxWidth: .infinity, alignment: .center)

            Spacer()

            Group {
                Text("Option A: Plugin install")
                    .font(.headline)
                copiableCode("claude plugin install codegraphcontext")

                Text("Option B: Manual config")
                    .font(.headline)
                    .padding(.top, 8)
                Text("Add to your project's .mcp.json:")
                    .foregroundColor(.secondary)
                copiableCode("""
                {"mcpServers":{"codegraphcontext":{"type":"http","url":"http://localhost:47321/mcp"}}}
                """)
            }

            Spacer()

            navButtons(backLabel: "Back", nextLabel: "Next")
        }
    }

    // MARK: - Step 2: Index

    private var indexStep: some View {
        VStack(spacing: 16) {
            Text("Index Your First Repository")
                .font(.title2.bold())

            Text("Select a git repository to index. This builds the code graph.")
                .foregroundColor(.secondary)

            Spacer()

            if isIndexing {
                VStack(spacing: 8) {
                    ProgressView()
                    Text("Indexing \(indexPath?.components(separatedBy: "/").last ?? "")...")
                        .foregroundColor(.secondary)
                    if let phase = appState.indexingManager.indexingPhase {
                        Text(phase.replacingOccurrences(of: "_", with: " "))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            } else if let stats = indexStats {
                VStack(spacing: 8) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 32))
                        .foregroundColor(.green)
                    Text(stats)
                        .foregroundColor(.secondary)
                }
            } else {
                Button("Select Repository...") {
                    selectAndIndex()
                }
                .controlSize(.large)
            }

            Spacer()

            navButtons(
                backLabel: "Back",
                nextLabel: indexStats != nil ? "Next" : "Skip",
                nextDisabled: isIndexing
            )
        }
    }

    // MARK: - Step 3: Try It

    private var tryItStep: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Try It Out")
                .font(.title2.bold())
                .frame(maxWidth: .infinity, alignment: .center)

            Text("Copy these prompts into Claude Code:")
                .foregroundColor(.secondary)
                .frame(maxWidth: .infinity, alignment: .center)

            Spacer()

            let prompts = [
                "Who calls the authenticate function?",
                "Find dead code in this project",
                "What would break if I changed the User model?",
                "Show me circular dependencies",
                "What are the most complex functions?",
            ]

            ForEach(prompts, id: \.self) { prompt in
                promptRow(prompt)
            }

            Spacer()

            Button("Done") {
                dismiss()
            }
            .controlSize(.large)
            .keyboardShortcut(.defaultAction)
            .frame(maxWidth: .infinity, alignment: .center)
        }
    }

    // MARK: - Components

    private func statBox(_ value: String, _ label: String) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.system(size: 28, weight: .bold, design: .rounded))
            Text(label)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .frame(width: 100)
    }

    private func copiableCode(_ text: String) -> some View {
        HStack {
            Text(text.trimmingCharacters(in: .whitespacesAndNewlines))
                .font(.system(.caption, design: .monospaced))
                .lineLimit(2)
                .truncationMode(.middle)
            Spacer()
            Button {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(text.trimmingCharacters(in: .whitespacesAndNewlines), forType: .string)
            } label: {
                Image(systemName: "doc.on.doc")
            }
            .buttonStyle(.borderless)
            .help("Copy to clipboard")
        }
        .padding(8)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(6)
    }

    private func promptRow(_ prompt: String) -> some View {
        HStack {
            Text(prompt)
                .font(.system(.body, design: .monospaced))
                .lineLimit(1)
            Spacer()
            Button {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(prompt, forType: .string)
            } label: {
                Image(systemName: "doc.on.doc")
            }
            .buttonStyle(.borderless)
            .help("Copy to clipboard")
        }
        .padding(.vertical, 4)
    }

    private func navButtons(
        backLabel: String?,
        nextLabel: String,
        nextDisabled: Bool = false
    ) -> some View {
        HStack {
            if let back = backLabel {
                Button(back) { step -= 1 }
                    .controlSize(.large)
            }
            Spacer()
            Button(nextLabel) { step += 1 }
                .controlSize(.large)
                .keyboardShortcut(.defaultAction)
                .disabled(nextDisabled)
        }
    }

    // MARK: - Actions

    private func selectAndIndex() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.message = "Select a git repository to index"
        panel.prompt = "Index"

        guard panel.runModal() == .OK, let url = panel.url else { return }

        if let error = IndexingManager.validateRepoPath(url.path) {
            let alert = NSAlert()
            alert.messageText = "Cannot Index Directory"
            alert.informativeText = error
            alert.alertStyle = .warning
            alert.addButton(withTitle: "OK")
            alert.runModal()
            return
        }

        indexPath = url.path
        isIndexing = true

        Task { @MainActor in
            await appState.indexingManager.indexRepository(at: url.path)
            isIndexing = false

            // Fetch stats
            if let stats = appState.indexingManager.graphStats {
                indexStats = "\(stats.files) files, \(stats.functions) functions, \(stats.classes) classes"
            } else {
                indexStats = "Indexing complete"
            }
        }
    }
}
