import XCTest
@testable import LeofricApp

/// Fixtures use raw SOI...EOI JPEG byte sequences with NO multipart boundary
/// or header text — this matches what iOS's URLSession actually delivers to
/// didReceive(data:) for multipart/x-mixed-replace responses (confirmed by
/// hex-dumping bytes received against the live Mac /feed stream: they start
/// with the JPEG SOI/JFIF marker `ff d8 ff e0`, never boundary text). An
/// earlier version of this parser targeted the raw multipart wire format
/// (as seen by curl or a non-Apple HTTP client) and passed against synthetic
/// fixtures built that way, but never worked against the real device stream
/// — this file's fixtures were corrected to match observed reality.
final class MJPEGStreamReaderTests: XCTestCase {
    private let tinyJPEG = Data([0xFF, 0xD8, 0xFF, 0xD9])

    func testExtractsCompleteFrame() {
        var buffer = tinyJPEG
        let frame = MJPEGStreamReader.extractFrame(from: &buffer)
        XCTAssertEqual(frame, tinyJPEG)
        XCTAssertTrue(buffer.isEmpty)
    }

    func testReturnsNilOnIncompleteFrame() {
        var partial = tinyJPEG.prefix(tinyJPEG.count - 1)  // EOI not fully arrived
        let frame = MJPEGStreamReader.extractFrame(from: &partial)
        XCTAssertNil(frame)
    }

    func testExtractsTwoConsecutiveFrames() {
        let secondJPEG = Data([0xFF, 0xD8, 0x00, 0xAB, 0xFF, 0xD9])
        var buffer = tinyJPEG
        buffer.append(secondJPEG)

        let first = MJPEGStreamReader.extractFrame(from: &buffer)
        XCTAssertEqual(first, tinyJPEG)

        let second = MJPEGStreamReader.extractFrame(from: &buffer)
        XCTAssertEqual(second, secondJPEG)

        XCTAssertTrue(buffer.isEmpty)
    }

    func testReturnsNilOnEmptyBuffer() {
        var buffer = Data()
        XCTAssertNil(MJPEGStreamReader.extractFrame(from: &buffer))
    }

    func testDropsGarbageBytesBeforeFirstSOI() {
        var buffer = Data([0x00, 0x11, 0x22])  // stray bytes, not a JPEG start
        buffer.append(tinyJPEG)
        let frame = MJPEGStreamReader.extractFrame(from: &buffer)
        XCTAssertEqual(frame, tinyJPEG)
    }

    func testPreservesSplitSOIAcrossTwoAppends() {
        // Simulates a TCP read boundary landing between the SOI's two bytes.
        var buffer = Data([0xFF])
        XCTAssertNil(MJPEGStreamReader.extractFrame(from: &buffer))
        XCTAssertEqual(buffer, Data([0xFF]))  // the lone 0xFF must survive, not be dropped

        buffer.append(Data([0xD8, 0xFF, 0xD9]))
        let frame = MJPEGStreamReader.extractFrame(from: &buffer)
        XCTAssertEqual(frame, tinyJPEG)
    }

    func testRetryDelayBacksOffExponentiallyAndCaps() {
        XCTAssertEqual(MJPEGStreamReader.retryDelay(afterAttempt: 1), 1)
        XCTAssertEqual(MJPEGStreamReader.retryDelay(afterAttempt: 2), 2)
        XCTAssertEqual(MJPEGStreamReader.retryDelay(afterAttempt: 3), 4)
        XCTAssertEqual(MJPEGStreamReader.retryDelay(afterAttempt: 4), 8)
        XCTAssertEqual(MJPEGStreamReader.retryDelay(afterAttempt: 10), 8)
    }

    /// An unreachable host must surface as a .retrying status (with a reason the
    /// UI can show) instead of the pre-fix behavior: a silent, permanent spinner.
    @MainActor
    func testConnectionFailureSchedulesRetryInsteadOfGoingSilent() async throws {
        let reader = MJPEGStreamReader()
        // Port 9 on localhost: nothing listens there, so the connection is
        // refused almost immediately — no external network involved.
        reader.start(url: URL(string: "http://127.0.0.1:9/feed")!)

        try await pollUntil(timeout: 5) {
            if case .retrying = reader.status { return true }
            return false
        }
        guard case .retrying(let attempt, let reason) = reader.status else {
            return XCTFail("expected .retrying, got \(reader.status)")
        }
        XCTAssertGreaterThanOrEqual(attempt, 1)
        XCTAssertFalse(reason.isEmpty)
    }

    /// A user-initiated stop must land on .idle and must NOT keep retrying.
    @MainActor
    func testStopCancelsPendingRetry() async throws {
        let reader = MJPEGStreamReader()
        reader.start(url: URL(string: "http://127.0.0.1:9/feed")!)
        try await pollUntil(timeout: 5) {
            if case .retrying = reader.status { return true }
            return false
        }

        reader.stop()
        XCTAssertEqual(reader.status, .idle)

        // Give any stray retry task a chance to fire; status must stay .idle.
        try await Task.sleep(nanoseconds: 1_500_000_000)
        XCTAssertEqual(reader.status, .idle)
    }

    @MainActor
    private func pollUntil(timeout: TimeInterval, _ condition: () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while !condition() {
            if Date() > deadline {
                XCTFail("condition not met within \(timeout)s")
                return
            }
            try await Task.sleep(nanoseconds: 50_000_000)
        }
    }
}
