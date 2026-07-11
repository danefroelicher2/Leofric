import Foundation

/// Mirrors one row of the Mac's `GET /conversations` response.
struct ConversationMessage: Decodable, Identifiable, Equatable {
    let id: Int
    let createdAt: String
    let nodeID: String
    let sessionID: String?
    let role: String  // "user" or "leofric"
    let content: String

    enum CodingKeys: String, CodingKey {
        case id, role, content
        case createdAt = "created_at"
        case nodeID = "node_id"
        case sessionID = "session_id"
    }

    /// Same defensive parsing as LeofricEvent.createdAtDate — see that type's
    /// doc comment for why this only reads the first 19 characters.
    var createdAtDate: Date? {
        Self.dateFormatter.date(from: String(createdAt.prefix(19)))
    }

    static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return formatter
    }()
}

struct ConversationsResponse: Decodable {
    let conversations: [ConversationMessage]
}
