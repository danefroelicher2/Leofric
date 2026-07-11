import XCTest
@testable import LeofricApp

@MainActor
final class ImageCacheTests: XCTestCase {
    // Smallest possible valid JPEG (1x1 white pixel) — enough for UIImage(data:) to decode.
    private let tinyJPEGBase64 =
        "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAj/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdABmX/9k="

    private var tinyJPEG: Data { Data(base64Encoded: tinyJPEGBase64)! }

    private func makeCache() -> ImageCache { ImageCache() }

    private func makeSession(handler: @escaping (URLRequest) -> (HTTPURLResponse, Data)) -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [CacheMockURLProtocol.self]
        CacheMockURLProtocol.requestHandler = handler
        return URLSession(configuration: config)
    }

    func testFetchesAndReturnsImage() async {
        let session = makeSession { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, self.tinyJPEG)
        }
        let cache = makeCache()
        let image = await cache.image(for: URL(string: "http://mac.test:5000/snapshot/x")!, session: session)
        XCTAssertNotNil(image)
    }

    func testSecondCallDoesNotRefetch() async {
        var fetchCount = 0
        let session = makeSession { request in
            fetchCount += 1
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, self.tinyJPEG)
        }
        let cache = makeCache()
        let url = URL(string: "http://mac.test:5000/snapshot/x")!
        _ = await cache.image(for: url, session: session)
        _ = await cache.image(for: url, session: session)
        XCTAssertEqual(fetchCount, 1)
    }

    func testReturnsNilOnNetworkFailure() async {
        let session = makeSession { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 500, httpVersion: nil, headerFields: nil)!
            return (response, Data())
        }
        let cache = makeCache()
        let image = await cache.image(for: URL(string: "http://mac.test:5000/snapshot/x")!, session: session)
        XCTAssertNil(image)
    }

    func testDifferentURLsCachedSeparately() async {
        let session = makeSession { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, self.tinyJPEG)
        }
        let cache = makeCache()
        let imageA = await cache.image(for: URL(string: "http://mac.test:5000/snapshot/a")!, session: session)
        let imageB = await cache.image(for: URL(string: "http://mac.test:5000/snapshot/b")!, session: session)
        XCTAssertNotNil(imageA)
        XCTAssertNotNil(imageB)
    }
}

final class CacheMockURLProtocol: URLProtocol {
    static var requestHandler: ((URLRequest) -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = Self.requestHandler else { return }
        let (response, data) = handler(request)
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
