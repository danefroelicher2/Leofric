import SwiftUI

struct RootTabView: View {
    @StateObject private var settings = AppSettings()
    @State private var selection = Tab.live

    private enum Tab: Hashable {
        case live, nodes
    }

    var body: some View {
        TabView(selection: $selection) {
            LiveFeedView()
                .environmentObject(settings)
                .tabItem { Label("Live", systemImage: "video.fill") }
                .tag(Tab.live)

            NodesView()
                .environmentObject(settings)
                .tabItem { Label("Nodes", systemImage: "server.rack") }
                .tag(Tab.nodes)
        }
        .onAppear {
            // Lets headless verification (xcodebuild + simctl screenshot) jump
            // straight to a tab without GUI scripting. No-op for real users —
            // this env var is only ever set by Task 6's launch command.
            if ProcessInfo.processInfo.environment["LEOFRIC_INITIAL_TAB"] == "nodes" {
                selection = .nodes
            }
        }
    }
}

#Preview {
    RootTabView()
}
