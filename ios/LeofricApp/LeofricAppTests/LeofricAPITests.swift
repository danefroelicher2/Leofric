import XCTest
@testable import LeofricApp

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
}
