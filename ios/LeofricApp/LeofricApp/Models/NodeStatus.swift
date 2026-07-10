import Foundation

/// Mirrors one entry of the Mac's `GET /nodes` response exactly.
/// `role` and the parsed date are optional: a node the Mac only knows about
/// via its Supabase fallback (never streamed a frame) has no role, and any
/// unexpected timestamp format degrades to nil rather than failing the whole
/// decode.
struct NodeStatus: Decodable, Identifiable, Equatable {
    var id: String { name }

    let name: String
    let online: Bool
    let lastSeen: String
    let streaming: Bool
    let role: String?

    enum CodingKeys: String, CodingKey {
        case name, online, streaming, role
        case lastSeen = "last_seen"
    }

    /// The Mac formats last_seen as e.g. "2026-07-10T15:59:29-0400" (no colon
    /// in the offset). Foundation's ISO8601DateFormatter can reject that
    /// shape, so this uses an explicit DateFormatter matching the Mac's
    /// exact pattern instead.
    var lastSeenDate: Date? {
        Self.dateFormatter.date(from: lastSeen)
    }

    private static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ssZ"
        return formatter
    }()
}

struct NodesResponse: Decodable {
    let nodes: [NodeStatus]
}
