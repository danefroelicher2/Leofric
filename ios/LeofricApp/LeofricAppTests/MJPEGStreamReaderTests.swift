import XCTest
@testable import LeofricApp

final class MJPEGStreamReaderTests: XCTestCase {
    private let tinyJPEG = Data([0xFF, 0xD8, 0xFF, 0xD9])

    private func framePart(jpeg: Data) -> Data {
        var part = Data("--leofricframe\r\n".utf8)
        part.append(Data("Content-Type: image/jpeg\r\n".utf8))
        part.append(Data("Content-Length: \(jpeg.count)\r\n\r\n".utf8))
        part.append(jpeg)
        part.append(Data("\r\n".utf8))
        return part
    }

    func testExtractsCompleteFrame() {
        var buffer = framePart(jpeg: tinyJPEG)
        let frame = MJPEGStreamReader.extractFrame(from: &buffer)
        XCTAssertEqual(frame, tinyJPEG)
        XCTAssertTrue(buffer.isEmpty)
    }

    func testReturnsNilOnIncompleteFrame() {
        let full = framePart(jpeg: tinyJPEG)
        var partial = full.prefix(full.count - 2)  // missing the trailing \r\n
        let frame = MJPEGStreamReader.extractFrame(from: &partial)
        XCTAssertNil(frame)
    }

    func testExtractsTwoConsecutiveFrames() {
        let secondJPEG = Data([0xFF, 0xD8, 0x00, 0xFF, 0xD9])
        var buffer = framePart(jpeg: tinyJPEG)
        buffer.append(framePart(jpeg: secondJPEG))

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
}
