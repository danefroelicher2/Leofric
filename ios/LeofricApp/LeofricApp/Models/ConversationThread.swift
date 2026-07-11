import Foundation

/// A chat thread: one wake-word session or one app-composed conversation,
/// grouped from the Mac's flat `/conversations` rows by session_id. Voice
/// sessions get session_id `"leofric-<unix-seconds>"` (brain/conversation.py
/// on the Pi); app-typed chats get `"app-<unix-ms>"` (macmini/server.py's
/// POST /app/chat) — the prefix is cosmetic, grouping only cares that it's
/// present and shared.
struct ConversationThread: Identifiable {
    let id: String  // the session_id
    let messages: [ConversationMessage]  // oldest first

    var lastMessageAt: Date? {
        messages.last?.createdAtDate
    }

    var preview: String {
        messages.last?.content ?? ""
    }

    /// Groups a flat, any-order list of messages into threads. Rows with no
    /// session_id are dropped (shouldn't occur for rows written after
    /// Phase 2B/2D — both write paths always stamp one).
    static func group(from messages: [ConversationMessage]) -> [ConversationThread] {
        var bySession: [String: [ConversationMessage]] = [:]
        for message in messages {
            guard let sessionID = message.sessionID else { continue }
            bySession[sessionID, default: []].append(message)
        }
        let threads = bySession.map { sessionID, msgs in
            ConversationThread(
                id: sessionID,
                messages: msgs.sorted { ($0.createdAtDate ?? .distantPast) < ($1.createdAtDate ?? .distantPast) }
            )
        }
        return threads.sorted { ($0.lastMessageAt ?? .distantPast) > ($1.lastMessageAt ?? .distantPast) }
    }
}
