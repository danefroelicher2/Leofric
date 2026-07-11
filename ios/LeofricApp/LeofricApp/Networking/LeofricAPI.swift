import Foundation

enum LeofricAPIError: Error, Equatable {
    case invalidResponse
    case httpStatus(Int)
}

/// The single HTTP client for talking to the Mac. The app never talks to
/// Supabase or Ollama directly — everything goes through this one surface,
/// matching macmini/server.py's contract exactly.
struct LeofricAPI {
    let baseURL: URL
    let session: URLSession

    init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    func health() async throws -> Bool {
        let (_, response) = try await session.data(from: baseURL)
        guard let http = response as? HTTPURLResponse else { throw LeofricAPIError.invalidResponse }
        return http.statusCode == 200
    }

    func fetchNodes() async throws -> [NodeStatus] {
        let url = baseURL.appendingPathComponent("nodes")
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse else { throw LeofricAPIError.invalidResponse }
        guard http.statusCode == 200 else { throw LeofricAPIError.httpStatus(http.statusCode) }
        return try JSONDecoder().decode(NodesResponse.self, from: data).nodes
    }

    func fetchEvents(limit: Int = 100, eventType: String? = nil, nodeID: String? = nil) async throws -> [LeofricEvent] {
        var components = URLComponents(url: baseURL.appendingPathComponent("events"), resolvingAgainstBaseURL: false)!
        var items = [URLQueryItem(name: "limit", value: String(limit))]
        if let eventType { items.append(URLQueryItem(name: "event_type", value: eventType)) }
        if let nodeID { items.append(URLQueryItem(name: "node_id", value: nodeID)) }
        components.queryItems = items
        let (data, response) = try await session.data(from: components.url!)
        guard let http = response as? HTTPURLResponse else { throw LeofricAPIError.invalidResponse }
        guard http.statusCode == 200 else { throw LeofricAPIError.httpStatus(http.statusCode) }
        return try JSONDecoder().decode(EventsResponse.self, from: data).events
    }

    func feedURL(node: String) -> URL {
        var components = URLComponents(url: baseURL.appendingPathComponent("feed"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "node", value: node)]
        return components.url!
    }
}
