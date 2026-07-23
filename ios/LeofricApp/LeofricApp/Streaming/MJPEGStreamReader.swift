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
///
/// Connection failures are never silent: every failure lands in `status` as
/// `.retrying` with a human-readable reason, and the reader reconnects on
/// its own with capped exponential backoff (1s, 2s, 4s, then 8s forever) —
/// on iffy cellular the feed recovers by itself instead of spinning blank.
@MainActor
final class MJPEGStreamReader: NSObject, ObservableObject, URLSessionDataDelegate {
    enum Status: Equatable {
        case idle
        case connecting
        case streaming
        case retrying(attempt: Int, reason: String)
    }

    @Published private(set) var currentFrame: Data?
    @Published private(set) var isConnected = false
    @Published private(set) var status = Status.idle

    private var session: URLSession!
    private var task: URLSessionDataTask?
    private var retryTask: Task<Void, Never>?
    private var url: URL?
    private var retryAttempt = 0
    private var buffer = Data()

    override init() {
        super.init()
        let config = URLSessionConfiguration.ephemeral
        // Frames arrive at ~4fps, so 10s without a byte means the link is dead
        // (mid-stream stall on flaky cellular) or the host is unreachable —
        // either way the task errors out and the retry loop takes over,
        // instead of the 60s default leaving a blank screen for a minute.
        config.timeoutIntervalForRequest = 10
        session = URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }

    deinit {
        retryTask?.cancel()
        session.invalidateAndCancel()
    }

    func start(url: URL) {
        stop()
        self.url = url
        retryAttempt = 0
        openConnection()
    }

    func stop() {
        url = nil
        retryTask?.cancel()
        retryTask = nil
        task?.cancel()
        task = nil
        isConnected = false
        status = .idle
    }

    private func openConnection() {
        guard let url else { return }
        buffer.removeAll()
        status = .connecting
        let dataTask = session.dataTask(with: url)
        task = dataTask
        dataTask.resume()
    }

    /// Backoff before reconnect attempt `attempt+1`: 1s, 2s, 4s, capped at 8s
    /// so a feed that comes back (Mac restarts, cellular handoff) is picked up
    /// within seconds without hammering the server while it's down.
    nonisolated static func retryDelay(afterAttempt attempt: Int) -> TimeInterval {
        min(pow(2, TimeInterval(attempt - 1)), 8)
    }

    private func scheduleRetry(reason: String) {
        guard url != nil else { return }  // stopped — stay idle
        task?.cancel()
        task = nil
        isConnected = false
        retryAttempt += 1
        status = .retrying(attempt: retryAttempt, reason: reason)
        let delay = Self.retryDelay(afterAttempt: retryAttempt)
        retryTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard !Task.isCancelled else { return }
            self?.openConnection()
        }
    }

    nonisolated func urlSession(
        _ session: URLSession, dataTask: URLSessionDataTask,
        didReceive response: URLResponse,
        completionHandler: @escaping (URLSession.ResponseDisposition) -> Void
    ) {
        let statusCode = (response as? HTTPURLResponse)?.statusCode ?? -1
        let ok = statusCode == 200
        Task { @MainActor in
            guard dataTask === self.task else { return }  // stale task — ignore
            if ok {
                self.isConnected = true
                self.status = .streaming
                self.retryAttempt = 0
            } else {
                // e.g. 503 when the Pi has stopped sending frames to the Mac.
                self.scheduleRetry(reason: "feed unavailable (HTTP \(statusCode))")
            }
        }
        completionHandler(ok ? .allow : .cancel)
    }

    nonisolated func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        Task { @MainActor in
            guard dataTask === self.task else { return }
            self.buffer.append(data)
            while let frame = Self.extractFrame(from: &self.buffer) {
                self.currentFrame = frame
            }
        }
    }

    nonisolated func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        // Cancellation is always self-inflicted (stop(), node switch, or the
        // non-200 path above, which schedules its own retry) — never retry it.
        if let urlError = error as? URLError, urlError.code == .cancelled { return }
        let reason = error?.localizedDescription ?? "stream ended"
        Task { @MainActor in
            guard task === self.task else { return }
            self.scheduleRetry(reason: reason)
        }
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
