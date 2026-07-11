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
}
