import SwiftUI

/// Health board (per-node online/offline/role) plus the one setting the app
/// needs: the Mac's address.
struct NodesView: View {
    @EnvironmentObject private var settings: AppSettings
    @EnvironmentObject private var store: LeofricStore
    @State private var nodes: [NodeStatus] = []
    @State private var brainHealthy: Bool?

    var body: some View {
        NavigationStack {
            List {
                Section("Brain") {
                    HStack {
                        Circle()
                            .fill(brainHealthy == true ? .green : (brainHealthy == false ? .red : .gray))
                            .frame(width: 10, height: 10)
                        Text(brainHealthy == true ? "Online" : (brainHealthy == false ? "Unreachable" : "Checking…"))
                    }
                }

                Section("Nodes") {
                    if nodes.isEmpty {
                        Text("No nodes seen yet.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(nodes) { node in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Circle()
                                    .fill(node.online ? .green : .red)
                                    .frame(width: 8, height: 8)
                                Text(node.name).font(.headline)
                                if let role = node.role {
                                    Text(role.capitalized)
                                        .font(.caption)
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 2)
                                        .background(.secondary.opacity(0.2), in: Capsule())
                                }
                            }
                            Text(node.streaming ? "Streaming" : "Not streaming")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Section("Settings") {
                    TextField("Mac address", text: $settings.baseURLString)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .font(.system(.body, design: .monospaced))
                }
            }
            .navigationTitle("Nodes")
            .refreshable { await refresh() }
            .task { await refresh() }
        }
    }

    private func refresh() async {
        guard settings.baseURL != nil else {
            brainHealthy = false
            return
        }
        let api = store.api
        brainHealthy = try? await api.health()
        nodes = (try? await api.fetchNodes()) ?? nodes
    }
}

#Preview {
    NodesView()
        .environmentObject(AppSettings())
}
