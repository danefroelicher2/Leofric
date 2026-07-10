import Foundation

/// Reads a multipart/x-mixed-replace MJPEG stream (as served by the Mac's
/// GET /feed) and publishes each decoded JPEG frame. AVPlayer cannot play
/// MJPEG, so this is Leofric's one piece of custom networking code.
@MainActor
final class MJPEGStreamReader: NSObject, ObservableObject, URLSessionDataDelegate {
    @Published private(set) var currentFrame: Data?
    @Published private(set) var isConnected = false

    private var session: URLSession!
    private var task: URLSessionDataTask?
    private var buffer = Data()

    override init() {
        super.init()
        session = URLSession(configuration: .ephemeral, delegate: self, delegateQueue: nil)
    }

    func start(url: URL) {
        stop()
        buffer.removeAll()
        let dataTask = session.dataTask(with: url)
        task = dataTask
        dataTask.resume()
    }

    func stop() {
        task?.cancel()
        task = nil
        isConnected = false
    }

    nonisolated func urlSession(
        _ session: URLSession, dataTask: URLSessionDataTask,
        didReceive response: URLResponse,
        completionHandler: @escaping (URLSession.ResponseDisposition) -> Void
    ) {
        let ok = (response as? HTTPURLResponse)?.statusCode == 200
        Task { @MainActor in self.isConnected = ok }
        completionHandler(ok ? .allow : .cancel)
    }

    nonisolated func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        Task { @MainActor in
            self.buffer.append(data)
            while let frame = Self.extractFrame(from: &self.buffer) {
                self.currentFrame = frame
            }
        }
    }

    nonisolated func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        Task { @MainActor in self.isConnected = false }
    }

    /// Pulls one JPEG frame out of `buffer` if a complete multipart part
    /// (boundary + headers + Content-Length bytes) is present, consuming
    /// those bytes. Returns nil if the buffer doesn't yet hold a full frame.
    nonisolated static func extractFrame(from buffer: inout Data) -> Data? {
        let boundaryMarker = Data("--leofricframe\r\n".utf8)
        guard let boundaryRange = buffer.range(of: boundaryMarker) else { return nil }
        let headerStart = boundaryRange.upperBound
        let headerTerminator = Data("\r\n\r\n".utf8)
        guard let headerEndRange = buffer.range(of: headerTerminator, in: headerStart..<buffer.endIndex) else {
            return nil
        }
        let headerData = buffer[headerStart..<headerEndRange.lowerBound]
        guard let headerString = String(data: headerData, encoding: .utf8),
              let contentLength = contentLength(fromHeaders: headerString) else {
            // Malformed headers: drop through this boundary so we don't get
            // stuck retrying the same bad bytes forever.
            buffer.removeSubrange(buffer.startIndex..<headerEndRange.upperBound)
            return nil
        }
        let jpegStart = headerEndRange.upperBound
        guard let jpegEnd = buffer.index(jpegStart, offsetBy: contentLength, limitedBy: buffer.endIndex) else {
            return nil  // full frame hasn't arrived yet
        }
        // The frame isn't complete until its trailing CRLF has also arrived —
        // without this check, a buffer that ends exactly at jpegEnd (CRLF not
        // yet received) would be mistaken for a complete frame.
        guard buffer.distance(from: jpegEnd, to: buffer.endIndex) >= 2 else {
            return nil  // trailing CRLF hasn't fully arrived yet
        }
        let jpegData = Data(buffer[jpegStart..<jpegEnd])
        let consumeEnd = buffer.index(jpegEnd, offsetBy: 2)
        buffer.removeSubrange(buffer.startIndex..<consumeEnd)
        return jpegData
    }

    private nonisolated static func contentLength(fromHeaders headers: String) -> Int? {
        for line in headers.split(separator: "\r\n") {
            let parts = line.split(separator: ":", maxSplits: 1)
            guard parts.count == 2,
                  parts[0].trimmingCharacters(in: .whitespaces).caseInsensitiveCompare("Content-Length") == .orderedSame
            else { continue }
            return Int(parts[1].trimmingCharacters(in: .whitespaces))
        }
        return nil
    }
}
