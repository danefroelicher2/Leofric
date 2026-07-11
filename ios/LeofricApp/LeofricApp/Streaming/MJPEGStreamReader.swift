import Foundation

/// Reads a multipart/x-mixed-replace MJPEG stream (as served by the Mac's
/// GET /feed) and publishes each decoded JPEG frame. AVPlayer cannot play
/// MJPEG, so this is Leofric's one piece of custom networking code.
///
/// iOS's URLSession has built-in handling for `multipart/x-mixed-replace`
/// responses: it strips the boundary markers and part headers (e.g.
/// `--leofricframe\r\nContent-Type: ...\r\nContent-Length: ...\r\n\r\n`)
/// before `didReceive data:` ever sees them, delivering raw JPEG bytes only
/// — confirmed by hex-dumping the actual bytes received against the live
/// Mac stream (the first bytes are the JPEG SOI/JFIF marker `ff d8 ff e0`,
/// never the boundary text). So frames are detected via JPEG's own framing
/// instead: SOI (0xFFD8) starts a frame, EOI (0xFFD9) ends it.
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

    private nonisolated static let soi = Data([0xFF, 0xD8])
    private nonisolated static let eoi = Data([0xFF, 0xD9])

    /// Pulls one complete JPEG frame (SOI...EOI, inclusive) out of `buffer`,
    /// consuming those bytes and dropping anything before the first SOI.
    /// Returns nil if a full frame isn't present yet.
    nonisolated static func extractFrame(from buffer: inout Data) -> Data? {
        guard let soiRange = buffer.range(of: soi) else {
            // No frame start yet — drop any trailing single 0xFF byte in case
            // it's the first half of an SOI split across two network reads,
            // but clear everything else so a garbage buffer can't grow forever.
            if buffer.last == 0xFF {
                buffer.removeSubrange(buffer.startIndex..<buffer.index(before: buffer.endIndex))
            } else {
                buffer.removeAll()
            }
            return nil
        }
        if soiRange.lowerBound > buffer.startIndex {
            buffer.removeSubrange(buffer.startIndex..<soiRange.lowerBound)
        }
        let searchStart = buffer.index(buffer.startIndex, offsetBy: 2)
        guard searchStart <= buffer.endIndex,
              let eoiRange = buffer.range(of: eoi, in: searchStart..<buffer.endIndex) else {
            return nil  // frame not fully arrived yet
        }
        let frameEnd = eoiRange.upperBound
        let jpegData = Data(buffer[buffer.startIndex..<frameEnd])
        buffer.removeSubrange(buffer.startIndex..<frameEnd)
        return jpegData
    }
}
