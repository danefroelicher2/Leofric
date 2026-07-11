import XCTest
@testable import LeofricApp

final class ConversationThreadTests: XCTestCase {
    private func message(id: Int, session: String, role: String, content: String, at: String) -> ConversationMessage {
        ConversationMessage(id: id, createdAt: at, nodeID: "leofric", sessionID: session, role: role, content: content)
    }

    func testGroupsBySessionID() {
        let messages = [
            message(id: 1, session: "leofric-100", role: "user", content: "hi", at: "2026-07-10T10:00:00.000000+00:00"),
            message(id: 2, session: "leofric-100", role: "leofric", content: "hello", at: "2026-07-10T10:00:05.000000+00:00"),
            message(id: 3, session: "app-200", role: "user", content: "typed msg", at: "2026-07-10T11:00:00.000000+00:00"),
        ]
        let threads = ConversationThread.group(from: messages)
        XCTAssertEqual(threads.count, 2)
        XCTAssertEqual(threads.first(where: { $0.id == "leofric-100" })?.messages.count, 2)
        XCTAssertEqual(threads.first(where: { $0.id == "app-200" })?.messages.count, 1)
    }

    func testMessagesWithinThreadAreOldestFirst() {
        let messages = [
            message(id: 2, session: "s1", role: "leofric", content: "second", at: "2026-07-10T10:00:05.000000+00:00"),
            message(id: 1, session: "s1", role: "user", content: "first", at: "2026-07-10T10:00:00.000000+00:00"),
        ]
        let thread = ConversationThread.group(from: messages).first!
        XCTAssertEqual(thread.messages.map(\.content), ["first", "second"])
    }

    func testThreadsSortedNewestActivityFirst() {
        let messages = [
            message(id: 1, session: "old", role: "user", content: "a", at: "2026-07-10T09:00:00.000000+00:00"),
            message(id: 2, session: "new", role: "user", content: "b", at: "2026-07-10T11:00:00.000000+00:00"),
        ]
        let threads = ConversationThread.group(from: messages)
        XCTAssertEqual(threads.map(\.id), ["new", "old"])
    }

    func testPreviewIsLastMessageContent() {
        let messages = [
            message(id: 1, session: "s1", role: "user", content: "first", at: "2026-07-10T10:00:00.000000+00:00"),
            message(id: 2, session: "s1", role: "leofric", content: "the latest reply", at: "2026-07-10T10:00:05.000000+00:00"),
        ]
        let thread = ConversationThread.group(from: messages).first!
        XCTAssertEqual(thread.preview, "the latest reply")
    }

    func testRowsWithoutSessionIDAreDropped() {
        let noSession = ConversationMessage(id: 1, createdAt: "2026-07-10T10:00:00.000000+00:00", nodeID: "leofric", sessionID: nil, role: "user", content: "orphan")
        let threads = ConversationThread.group(from: [noSession])
        XCTAssertTrue(threads.isEmpty)
    }

    func testEmptyInputProducesEmptyOutput() {
        XCTAssertTrue(ConversationThread.group(from: []).isEmpty)
    }
}
