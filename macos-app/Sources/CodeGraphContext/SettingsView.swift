import SwiftUI
import ServiceManagement

struct SettingsView: View {
    @AppStorage("mcpPort") private var mcpPort: Int = 47321
    @AppStorage("vizPort") private var vizPort: Int = 47322
    @AppStorage("launchAtLogin") private var launchAtLogin: Bool = false
    @AppStorage("autoIndexPaths") private var autoIndexPathsData: Data = Data()

    @State private var autoIndexPaths: [String] = []
    @State private var showAddRepo = false

    var body: some View {
        TabView {
            generalTab
                .tabItem { Label("General", systemImage: "gear") }
            repositoriesTab
                .tabItem { Label("Repositories", systemImage: "folder") }
        }
        .frame(width: 480, height: 320)
        .onAppear { loadAutoIndexPaths() }
    }

    // MARK: - General Tab

    private var generalTab: some View {
        Form {
            Section("Server") {
                HStack {
                    Text("MCP Server Port")
                    Spacer()
                    TextField("Port", value: $mcpPort, format: .number)
                        .frame(width: 80)
                        .textFieldStyle(.roundedBorder)
                }

                HStack {
                    Text("Visualization Port")
                    Spacer()
                    TextField("Port", value: $vizPort, format: .number)
                        .frame(width: 80)
                        .textFieldStyle(.roundedBorder)
                }
            }

            Section("Startup") {
                Toggle("Launch at Login", isOn: $launchAtLogin)
                    .onChange(of: launchAtLogin) { _, newValue in
                        setLaunchAtLogin(newValue)
                    }
            }

            Section("Database") {
                LabeledContent("FalkorDB") {
                    Text("Standalone (bundled redis-server + falkordb.so)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
        .formStyle(.grouped)
        .padding()
    }

    // MARK: - Repositories Tab

    private var repositoriesTab: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Auto-Index on Launch")
                .font(.headline)

            Text("These repositories will be automatically indexed when the app starts.")
                .font(.caption)
                .foregroundColor(.secondary)

            List {
                ForEach(autoIndexPaths, id: \.self) { path in
                    HStack {
                        Image(systemName: "folder.fill")
                            .foregroundColor(.accentColor)
                        VStack(alignment: .leading) {
                            Text(URL(fileURLWithPath: path).lastPathComponent)
                                .font(.body)
                            Text(path)
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        }
                        Spacer()
                        Button(role: .destructive) {
                            removeAutoIndexPath(path)
                        } label: {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.borderless)
                    }
                }
            }
            .frame(minHeight: 120)
            .overlay {
                if autoIndexPaths.isEmpty {
                    Text("No repositories configured")
                        .foregroundColor(.secondary)
                }
            }

            HStack {
                Spacer()
                Button("Add Repository...") {
                    addAutoIndexRepo()
                }
            }
        }
        .padding()
    }

    // MARK: - Launch at Login

    private func setLaunchAtLogin(_ enabled: Bool) {
        do {
            if enabled {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
        } catch {
            // Reset toggle if registration fails
            launchAtLogin = !enabled
        }
    }

    // MARK: - Auto-Index Paths

    private func loadAutoIndexPaths() {
        if let paths = try? JSONDecoder().decode([String].self, from: autoIndexPathsData) {
            autoIndexPaths = paths
        }
    }

    private func saveAutoIndexPaths() {
        if let data = try? JSONEncoder().encode(autoIndexPaths) {
            autoIndexPathsData = data
        }
    }

    private func addAutoIndexRepo() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.message = "Select a repository to auto-index on launch"
        panel.prompt = "Add"

        if panel.runModal() == .OK, let url = panel.url {
            let path = url.path
            if !autoIndexPaths.contains(path) {
                autoIndexPaths.append(path)
                saveAutoIndexPaths()
            }
        }
    }

    private func removeAutoIndexPath(_ path: String) {
        autoIndexPaths.removeAll { $0 == path }
        saveAutoIndexPaths()
    }
}
