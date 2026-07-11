import SwiftUI

struct RootTabView: View {
    @StateObject private var settings = AppSettings()
    @StateObject private var store: LeofricStore
    @State private var selection = Tab.live

    private enum Tab: Hashable {
        case live, alerts, chats, nodes
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

            AlertsView()
                .tabItem { Label("Alerts", systemImage: "bell.fill") }
                .tag(Tab.alerts)

            ChatsListView()
                .tabItem { Label("Chats", systemImage: "message.fill") }
                .tag(Tab.chats)

            NodesView()
                .tabItem { Label("Nodes", systemImage: "server.rack") }
                .tag(Tab.nodes)
        }
        .environmentObject(settings)
        .environmentObject(store)
        .onAppear {
            switch ProcessInfo.processInfo.environment["LEOFRIC_INITIAL_TAB"] {
            case "nodes": selection = .nodes
            case "alerts": selection = .alerts
            case "chats": selection = .chats
            default: break
            }
        }
    }
}

#Preview {
    RootTabView()
}
