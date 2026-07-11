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
            } else if let errorMessage {
                Text(errorMessage)
                    .foregroundStyle(.white)
                    .padding()
            } else {
                ProgressView()
                    .tint(.white)
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
