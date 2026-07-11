import Foundation

/// Mirrors one row of the Mac's `GET /events` response. `metadata`'s fields
/// are all optional since the shape varies by event_type: motion carries
/// `area`, person carries `count`, identity carries `name`/`similarity` and
/// (when a fresh frame was available) `snapshot_id`.
struct LeofricEvent: Decodable, Identifiable {
    let id: Int
    let createdAt: String
    let eventType: String
    let nodeID: String
    let metadata: Metadata

    enum CodingKeys: String, CodingKey {
        case id, metadata
        case createdAt = "created_at"
        case eventType = "event_type"
        case nodeID = "node_id"
    }

    struct Metadata: Decodable {
        let area: Int?
        let count: Int?
        let name: String?
        let similarity: Double?
        let snapshotID: String?

        enum CodingKeys: String, CodingKey {
            case area, count, name, similarity
            case snapshotID = "snapshot_id"
        }
    }

    /// Supabase's created_at is `"...T...microseconds+00:00"` — a different
    /// shape from the Mac's own `/nodes.last_seen` format. Parsed the same
    /// defensive way `macmini/server.py` parses this exact field: take only
    /// the first 19 characters (`yyyy-MM-dd'T'HH:mm:ss`) as UTC, ignoring
    /// fractional seconds and offset — sufficient for display/sort ordering.
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

struct EventsResponse: Decodable {
    let events: [LeofricEvent]
}
