import XCTest
@testable import LeofricApp

extension URLRequest {
    func httpBodyStreamData() -> Data? {
        guard let stream = httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let bufferSize = 4096
        var buffer = [UInt8](repeating: 0, count: bufferSize)
        while stream.hasBytesAvailable {
            let read = stream.read(&buffer, maxLength: bufferSize)
            if read > 0 { data.append(buffer, count: read) }
        }
        return data
    }
}

final class MockURLProtocol: URLProtocol {
    static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = MockURLProtocol.requestHandler else {
            XCTFail("MockURLProtocol.requestHandler not set")
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

final class LeofricAPITests: XCTestCase {
    private func makeAPI() -> LeofricAPI {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: config)
        return LeofricAPI(baseURL: URL(string: "http://mac.test:5000")!, session: session)
    }

    override func tearDown() {
        MockURLProtocol.requestHandler = nil
        super.tearDown()
    }

    func testHealthReturnsTrueOn200() async throws {
        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data("{}".utf8))
        }
        let ok = try await makeAPI().health()
        XCTAssertTrue(ok)
    }

    func testFetchNodesDecodesResponse() async throws {
        let json = """
        {"nodes":[{"name":"leofric","online":true,"last_seen":"2026-07-10T15:59:29-0400","streaming":true,"role":"security"}]}
        """
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/nodes")
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(json.utf8))
        }
        let nodes = try await makeAPI().fetchNodes()
        XCTAssertEqual(nodes.count, 1)
        XCTAssertEqual(nodes[0].name, "leofric")
        XCTAssertEqual(nodes[0].role, "security")
        XCTAssertNotNil(nodes[0].lastSeenDate)
    }

    func testFetchNodesHandlesNullRole() async throws {
        let json = """
        {"nodes":[{"name":"leofric","online":false,"last_seen":"2026-07-10T15:59:29-0400","streaming":false,"role":null}]}
        """
        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(json.utf8))
        }
        let nodes = try await makeAPI().fetchNodes()
        XCTAssertNil(nodes[0].role)
    }

    func testFetchNodesThrowsOnServerError() async throws {
        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 503, httpVersion: nil, headerFields: nil)!
            return (response, Data())
        }
        do {
            _ = try await makeAPI().fetchNodes()
            XCTFail("expected to throw")
        } catch LeofricAPIError.httpStatus(let code) {
            XCTAssertEqual(code, 503)
        }
    }

    func testFeedURLIncludesNodeQueryParam() {
        let url = makeAPI().feedURL(node: "leofric")
        XCTAssertEqual(url.path, "/feed")
        XCTAssertTrue(url.query?.contains("node=leofric") ?? false)
    }

    func testFetchEventsDecodesPersonEvent() async throws {
        let json = """
        {"events":[{"id":7203,"created_at":"2026-07-10T15:50:37.221648+00:00",
        "event_type":"person","node_id":"leofric","metadata":{"count":1}}]}
        """
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/events")
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(json.utf8))
        }
        let events = try await makeAPI().fetchEvents()
        XCTAssertEqual(events.count, 1)
        XCTAssertEqual(events[0].eventType, "person")
        XCTAssertEqual(events[0].metadata.count, 1)
        XCTAssertNil(events[0].metadata.snapshotID)
        XCTAssertNotNil(events[0].createdAtDate)
    }

    func testFetchEventsDecodesIdentityEventWithSnapshot() async throws {
        let json = """
        {"events":[{"id":7202,"created_at":"2026-07-10T15:50:21.107107+00:00",
        "event_type":"identity","node_id":"leofric",
        "metadata":{"name":"dane","similarity":0.608,"snapshot_id":"leofric-1783713537239"}}]}
        """
        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(json.utf8))
        }
        let events = try await makeAPI().fetchEvents()
        XCTAssertEqual(events[0].metadata.name, "dane")
        XCTAssertEqual(events[0].metadata.snapshotID, "leofric-1783713537239")
    }

    func testFetchEventsDecodesMotionEventNoSnapshot() async throws {
        let json = """
        {"events":[{"id":1,"created_at":"2026-07-10T15:50:37.221648+00:00",
        "event_type":"motion","node_id":"leofric","metadata":{"area":5661}}]}
        """
        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(json.utf8))
        }
        let events = try await makeAPI().fetchEvents()
        XCTAssertEqual(events[0].metadata.area, 5661)
        XCTAssertNil(events[0].metadata.snapshotID)
    }

    func testFetchEventsPassesFilters() async throws {
        MockURLProtocol.requestHandler = { request in
            let query = request.url?.query ?? ""
            XCTAssertTrue(query.contains("event_type=person"))
            XCTAssertTrue(query.contains("node_id=leofric"))
            XCTAssertTrue(query.contains("limit=50"))
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data("{\"events\":[]}".utf8))
        }
        _ = try await makeAPI().fetchEvents(limit: 50, eventType: "person", nodeID: "leofric")
    }

    func testFetchConversationsDecodesAndFilters() async throws {
        let json = """
        {"conversations":[{"id":44,"created_at":"2026-07-10T20:21:32.355662+00:00",
        "node_id":"app","session_id":"app-123","role":"leofric","content":"hi there"}]}
        """
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/conversations")
            XCTAssertTrue((request.url?.query ?? "").contains("session_id=app-123"))
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data(json.utf8))
        }
        let messages = try await makeAPI().fetchConversations(sessionID: "app-123")
        XCTAssertEqual(messages.count, 1)
        XCTAssertEqual(messages[0].sessionID, "app-123")
        XCTAssertEqual(messages[0].role, "leofric")
    }

    func testSendAppChatPostsAndDecodesSessionID() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/app/chat")
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data("{\"response\":\"hi\",\"session_id\":\"app-999\"}".utf8))
        }
        let result = try await makeAPI().sendAppChat(message: "hello", sessionID: nil)
        XCTAssertEqual(result.response, "hi")
        XCTAssertEqual(result.sessionID, "app-999")
    }

    func testSendAppChatIncludesSessionIDInBodyWhenProvided() async throws {
        var capturedBody: Data?
        MockURLProtocol.requestHandler = { request in
            capturedBody = request.httpBodyStreamData() ?? request.httpBody
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data("{\"response\":\"hi\",\"session_id\":\"app-1\"}".utf8))
        }
        _ = try await makeAPI().sendAppChat(message: "hello", sessionID: "app-1")
        let body = try XCTUnwrap(capturedBody)
        let json = try JSONSerialization.jsonObject(with: body) as? [String: Any]
        XCTAssertEqual(json?["session_id"] as? String, "app-1")
        XCTAssertEqual(json?["message"] as? String, "hello")
    }

    func testSnapshotURLHasNoQueryParams() {
        let url = makeAPI().snapshotURL(id: "leofric-123")
        XCTAssertEqual(url.path, "/snapshot/leofric-123")
        XCTAssertNil(url.query)
    }
}
