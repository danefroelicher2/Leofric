import SwiftUI

/// One thread, iMessage-style. `sessionID` is nil only for a brand-new
/// compose flow — it becomes known the moment the first message's response
/// arrives (the Mac mints it), and every message after that carries it.
struct ChatThreadView: View {
    @State var sessionID: String?
    @EnvironmentObject private var store: LeofricStore
    @State private var messages: [ConversationMessage] = []
    @State private var draft = ""
    @State private var isSending = false
    @State private var pollTask: Task<Void, Never>?

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(messages) { message in
                            MessageBubble(message: message).id(message.id)
                        }
                    }
                    .padding()
                }
                .onChange(of: messages.count) { _, _ in
                    if let lastID = messages.last?.id {
                        withAnimation { proxy.scrollTo(lastID, anchor: .bottom) }
                    }
                }
            }

            HStack {
                TextField("Message", text: $draft, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                Button("Send") { Task { await send() } }
                    .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSending)
            }
            .padding()
        }
        .navigationTitle("Chat")
        .navigationBarTitleDisplayMode(.inline)
        .task { await loadInitial() }
        .onAppear { startPolling() }
        .onDisappear { pollTask?.cancel() }
    }

    private func loadInitial() async {
        guard let sessionID else { return }  // new compose flow — nothing to load yet
        messages = sortedOldestFirst((try? await store.api.fetchConversations(sessionID: sessionID)) ?? [])
    }

    private func startPolling() {
        pollTask?.cancel()
        pollTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                if Task.isCancelled { break }
                await refreshIfNeeded()
            }
        }
    }

    private func refreshIfNeeded() async {
        guard let sessionID else { return }
        guard let fresh = try? await store.api.fetchConversations(sessionID: sessionID) else { return }
        // Conversations are append-only, so only apply a poll result that has
        // strictly MORE messages — this prevents a slow/stale poll (older server
        // state, fewer rows) from erasing a message the user just sent.
        if fresh.count > messages.count {
            messages = sortedOldestFirst(fresh)
        }
    }

    private func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draft = ""
        isSending = true
        defer { isSending = false }

        let historyPairs = messages.map { ["role": $0.role == "leofric" ? "assistant" : "user", "content": $0.content] }
        guard let result = try? await store.api.sendAppChat(message: text, sessionID: sessionID, history: historyPairs) else {
            draft = text  // restore on failure so the user doesn't lose their message
            return
        }
        sessionID = result.sessionID
        messages = sortedOldestFirst((try? await store.api.fetchConversations(sessionID: result.sessionID)) ?? messages)
    }

    /// The Mac returns conversation rows newest-first; the UI, scroll-to-bottom,
    /// and the history sent to the brain all need them oldest-first.
    private func sortedOldestFirst(_ rows: [ConversationMessage]) -> [ConversationMessage] {
        rows.sorted { ($0.createdAtDate ?? .distantPast) < ($1.createdAtDate ?? .distantPast) }
    }
}

private struct MessageBubble: View {
    let message: ConversationMessage

    var body: some View {
        HStack {
            if message.role == "leofric" { bubble; Spacer(minLength: 40) }
            else { Spacer(minLength: 40); bubble }
        }
    }

    private var bubble: some View {
        Text(message.content)
            .padding(10)
            .background(message.role == "leofric" ? Color.secondary.opacity(0.2) : Color.accentColor)
            .foregroundStyle(message.role == "leofric" ? Color.primary : Color.white)
            .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}
