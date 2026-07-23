import SwiftUI

/// Full-screen live camera feed. Opens straight to the security node so the
/// app can be "a security camera in hand" in under 2 seconds.
struct LiveFeedView: View {
    @EnvironmentObject private var settings: AppSettings
    @EnvironmentObject private var store: LeofricStore
    @StateObject private var reader = MJPEGStreamReader()
    @State private var nodes: [NodeStatus] = []
    @State private var selectedNode = "leofric"
    @State private var errorMessage: String?

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            if let data = reader.currentFrame, let uiImage = UIImage(data: data) {
                Image(uiImage: uiImage)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    // Keep the last frame up during a drop (context beats black),
                    // but say plainly that it's stale and being reconnected.
                    .overlay(alignment: .top) {
                        if case .retrying = reader.status {
                            statusBanner("Connection lost — reconnecting…")
                        } else if reader.status == .connecting {
                            statusBanner("Reconnecting…")
                        }
                    }
            } else if let errorMessage {
                Text(errorMessage)
                    .foregroundStyle(.white)
                    .padding()
            } else if case .retrying(let attempt, let reason) = reader.status {
                VStack(spacing: 12) {
                    Text("Can't reach \(settings.baseURL?.host() ?? "the Mac")")
                        .font(.headline)
                    Text(reason)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Text("Retrying automatically (attempt \(attempt))…")
                        .font(.footnote)
                }
                .foregroundStyle(.white)
                .multilineTextAlignment(.center)
                .padding()
            } else {
                VStack(spacing: 12) {
                    ProgressView()
                        .tint(.white)
                    Text("Connecting to \(settings.baseURL?.host() ?? "the Mac")…")
                        .font(.footnote)
                        .foregroundStyle(.white)
                }
            }

            VStack {
                Spacer()
                if nodes.count > 1 {
                    Picker("Node", selection: $selectedNode) {
                        ForEach(nodes) { node in
                            Text(node.name).tag(node.name)
                        }
                    }
                    .pickerStyle(.segmented)
                    .padding()
                    .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
                    .padding()
                }
            }
        }
        .task { await start() }
        .onChange(of: selectedNode) { _, newNode in
            connect(node: newNode)
        }
        .onDisappear { reader.stop() }
    }

    private func start() async {
        connect(node: selectedNode)
        guard settings.baseURL != nil else { return }
        let api = store.api
        if let fetched = try? await api.fetchNodes(), !fetched.isEmpty {
            nodes = fetched
            if !fetched.contains(where: { $0.name == selectedNode }) {
                selectedNode = fetched[0].name
            }
        }
    }

    private func statusBanner(_ text: String) -> some View {
        Text(text)
            .font(.footnote.weight(.medium))
            .foregroundStyle(.white)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(.black.opacity(0.6), in: Capsule())
            .padding(.top, 8)
    }

    private func connect(node: String) {
        guard settings.baseURL != nil else {
            errorMessage = "Set the Mac's address in the Nodes tab."
            return
        }
        errorMessage = nil
        reader.start(url: store.api.feedURL(node: node))
    }
}

#Preview {
    LiveFeedView()
        .environmentObject(AppSettings())
}
