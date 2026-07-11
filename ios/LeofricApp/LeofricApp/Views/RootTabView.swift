import SwiftUI

struct RootTabView: View {
    @StateObject private var settings = AppSettings()
    @StateObject private var store: LeofricStore
    @State private var selection = Tab.live

    private enum Tab: Hashable {
        case live, nodes
    }

    init() {
        let settings = AppSettings()
        _settings = StateObject(wrappedValue: settings)
        _store = StateObject(wrappedValue: LeofricStore(settings: settings))
    }

    var body: some View {
        TabView(selection: $selection) {
            LiveFeedView()
                .tabItem { Label("Live", systemImage: "video.fill") }
                .tag(Tab.live)

            NodesView()
                .tabItem { Label("Nodes", systemImage: "server.rack") }
                .tag(Tab.nodes)
        }
        .environmentObject(settings)
        .environmentObject(store)
        .onAppear {
            // Lets headless verification (xcodebuild + simctl screenshot) jump
            // straight to a tab without GUI scripting. No-op for real users.
            if ProcessInfo.processInfo.environment["LEOFRIC_INITIAL_TAB"] == "nodes" {
                selection = .nodes
            }
        }
    }
}

#Preview {
    RootTabView()
}
