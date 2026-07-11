import SwiftUI

/// Thread list. Voice sessions from the Pi appear here automatically (their
/// session_id already exists in Supabase by the time this view fetches);
/// typed chats start via the compose button.
struct ChatsListView: View {
    @EnvironmentObject private var store: LeofricStore
    @State private var threads: [ConversationThread] = []
    @State private var isComposing = false

    var body: some View {
        NavigationStack {
            List(threads) { thread in
                NavigationLink(value: thread.id) {
                    ThreadRow(thread: thread)
                }
            }
            .navigationDestination(for: String.self) { sessionID in
                ChatThreadView(sessionID: sessionID)
            }
            .navigationTitle("Chats")
            .toolbar {
                Button {
                    isComposing = true
                } label: {
                    Image(systemName: "square.and.pencil")
                }
            }
            .refreshable { await refresh() }
            .task { await refresh() }
            .overlay {
                if threads.isEmpty {
                    ContentUnavailableView("No Chats Yet", systemImage: "message")
                }
            }
            .navigationDestination(isPresented: $isComposing) {
                ChatThreadView(sessionID: nil)
            }
        }
    }

    private func refresh() async {
        let messages = (try? await store.api.fetchConversations()) ?? []
        threads = ConversationThread.group(from: messages)
    }
}

private struct ThreadRow: View {
    let thread: ConversationThread

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(thread.id.hasPrefix("app-") ? "Typed chat" : "Voice session")
                    .font(.subheadline).bold()
                Spacer()
                if let date = thread.lastMessageAt {
                    Text(date, style: .relative).font(.caption).foregroundStyle(.secondary)
                }
            }
            Text(thread.preview)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
    }
}
