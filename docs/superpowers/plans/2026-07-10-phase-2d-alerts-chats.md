# Phase 2D — Alerts + Chats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The security timeline and the conversation surface — an Alerts tab showing every motion/person/identity event with photos, and a Chats tab where voice sessions from the Pi appear as threads automatically and the user can also type new chats from anywhere.

**Architecture:** Two new Mac-side pieces: a `_supabase_post` helper and one new endpoint, `POST /app/chat`, that mints/reuses a `session_id`, calls Ollama exactly like the existing `/chat`, and persists both turns to Supabase with `node_id="app"` — this is the one thing the app cannot do without a Mac-side addition, since `/chat` is a stateless proxy (the Pi persists client-side after calling it) and the app must never touch Supabase directly. On iOS: a shared `LeofricStore` (paying down a Phase 2C review finding) owns one `LeofricAPI` instance for all four tabs; `LeofricEvent`/`ConversationMessage` models mirror `/events`/`/conversations`; a pure `ConversationThread.group(from:)` function turns the flat conversation rows into threads by `session_id`; a small `ImageCache` (NSCache-backed, zero third-party deps) serves Alerts thumbnails and the full-photo view without refetching on every scroll.

**Tech Stack:** Same as 2B/2C — Flask + requests (Mac), SwiftUI + async/await (iOS), XCTest, XcodeGen, `xcodebuild` + iOS Simulator for verification.

## Global Constraints

- Do NOT change existing route JSON shapes: `GET /`, `POST /chat`, `GET /events`, `GET /conversations`, `GET /nodes`, `GET /feed`, `POST /ingest/frame/<node>`, `POST /ingest/event/<node>`, `GET /snapshot/<id>`. `POST /app/chat` is additive.
- The Mac's deployed venv gets NO new packages (flask + requests only).
- iOS: zero third-party dependencies; SwiftUI only; iOS 17+ deployment target; `CODE_SIGN_STYLE: Automatic`, no hardcoded `DEVELOPMENT_TEAM`.
- Motion events ARE visible in Alerts (per PROJECT_SPEC: "Raw motion is logged and visible in the app's Alerts timeline but does not notify by itself") — do not filter them out of `/events` reads; they simply have no `snapshot_id`.
- Supabase `created_at` timestamps are ISO-with-microseconds-and-colon-offset (e.g. `"2026-07-10T15:50:37.221648+00:00"`) — a DIFFERENT format from the Mac's own `/nodes.last_seen` (`"2026-07-10T15:59:29-0400"`, no colon in offset, seconds precision). Do not reuse `NodeStatus`'s `DateFormatter` pattern for these; parse only the first 19 characters (`yyyy-MM-dd'T'HH:mm:ss`) as UTC, mirroring the exact technique `macmini/server.py`'s own `_supabase_last_event_times()` already uses (`row["created_at"][:19]`) for this identical problem.
- Persistence failures on the Mac must never fail the user-facing action they're attached to (matches `storage/events.py`'s established philosophy: "Logging must never take down the main loop"). `POST /app/chat` must still return the brain's reply even if writing to Supabase fails.
- Simulator target for all iOS builds/tests in this plan: `iPhone 17 Pro`, UDID `F40A0E50-DEC8-4A68-9332-3146E8D56711`. If unavailable, recover via `xcrun simctl list devices available | grep "iPhone 17 Pro"`.
- Repo workflow: develop on the Mac at `/Users/danefroelicher/Leofric`, commit + push, `git pull` on the Pi only if a task touches Pi code (none in this plan — 2D is Mac + iOS only). Mac deployment: `cp macmini/server.py ~/leofric-brain/server.py`, then `kill $(lsof -tiTCP:5000 -sTCP:LISTEN)` (launchd restarts it via `com.leofric.brain`, KeepAlive).
- Run Mac tests with: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server -v`
- Run iOS tests with: `cd /Users/danefroelicher/Leofric/ios/LeofricApp && xcodebuild -project LeofricApp.xcodeproj -scheme LeofricApp -destination 'platform=iOS Simulator,id=F40A0E50-DEC8-4A68-9332-3146E8D56711' -derivedDataPath .build test`
- New files added in a brand-new subdirectory have required `xcodegen generate` (from `ios/LeofricApp/`) in every task so far this project, with the regenerated `project.pbxproj` committed alongside. Expect the same here.
- Ignore SourceKit-LSP editor diagnostics like "No such module 'XCTest'" or "cannot find type in scope" — confirmed false positives throughout this project (index lag after XcodeGen regeneration). Only trust actual `xcodebuild`/`xcodebuild test` output.
- Live-device verification against the real, running Mac + Pi is REQUIRED before this phase is considered done (not just unit tests) — Phase 2C proved a class of bug (iOS platform networking behavior) that only a live run against the real backend could catch.

---

### Task 1: Mac — `POST /app/chat` (mint/reuse session, persist both turns)

**Files:**
- Modify: `macmini/server.py` (add `_supabase_post` helper and the new route, after the existing `/conversations` route, before `if __name__ == "__main__":`)
- Test: `macmini/test_server.py` (append to `ApiTest`)

**Interfaces:**
- Consumes: `SUPABASE_URL`, `SUPABASE_KEY`, `SYSTEM_PROMPT`, `OLLAMA_URL`, `MODEL`, `requests` — all already in `server.py`.
- Produces: `POST /app/chat` body `{"message": str, "session_id": str|null, "history": [{"role","content"}]|omitted}` → `200 {"response": str, "session_id": str}`. `session_id` in the response is always non-null — either the one the caller passed, or a freshly minted `"app-{unix_ms}"`. Both turns are persisted to Supabase `conversations` with `node_id="app"`. `_supabase_post(table, row)` — new helper, POSTs one row via PostgREST, raises on failure (caller catches).

- [ ] **Step 1: Write the failing tests** — append to `macmini/test_server.py`'s `ApiTest` class:

```python
    # --- app-originated chat (Phase 2D) ---

    def _mock_ollama_and_supabase(self, reply="Hello there"):
        """Mocks both requests.post (Ollama /api/chat) and _supabase_post."""
        ollama_resp = mock.Mock()
        ollama_resp.json.return_value = {"message": {"content": reply}}
        ollama_resp.raise_for_status.return_value = None
        return mock.patch.object(server.requests, "post", return_value=ollama_resp)

    def test_app_chat_mints_session_id_when_absent(self):
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             self._mock_ollama_and_supabase() as post, \
             mock.patch.object(server, "_supabase_post") as supa_post:
            resp = self.client.post("/app/chat", json={"message": "hi"})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["response"], "Hello there")
        self.assertTrue(body["session_id"].startswith("app-"))
        self.assertEqual(supa_post.call_count, 2)
        user_row = supa_post.call_args_list[0].args[1]
        leofric_row = supa_post.call_args_list[1].args[1]
        self.assertEqual(user_row["role"], "user")
        self.assertEqual(user_row["content"], "hi")
        self.assertEqual(user_row["node_id"], "app")
        self.assertEqual(user_row["session_id"], body["session_id"])
        self.assertEqual(leofric_row["role"], "leofric")
        self.assertEqual(leofric_row["content"], "Hello there")

    def test_app_chat_reuses_provided_session_id(self):
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             self._mock_ollama_and_supabase(), \
             mock.patch.object(server, "_supabase_post") as supa_post:
            resp = self.client.post(
                "/app/chat", json={"message": "hi", "session_id": "app-123"}
            )
        self.assertEqual(resp.get_json()["session_id"], "app-123")
        self.assertEqual(supa_post.call_args_list[0].args[1]["session_id"], "app-123")

    def test_app_chat_requires_message(self):
        resp = self.client.post("/app/chat", json={})
        self.assertEqual(resp.status_code, 400)

    def test_app_chat_forwards_history_to_ollama(self):
        history = [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "reply"}]
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             self._mock_ollama_and_supabase() as post, \
             mock.patch.object(server, "_supabase_post"):
            self.client.post("/app/chat", json={"message": "hi", "history": history})
        sent_messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(sent_messages[0]["content"], server.SYSTEM_PROMPT)
        self.assertIn({"role": "user", "content": "earlier"}, sent_messages)
        self.assertEqual(sent_messages[-1], {"role": "user", "content": "hi"})

    def test_app_chat_still_returns_reply_if_persistence_fails(self):
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             self._mock_ollama_and_supabase(), \
             mock.patch.object(server, "_supabase_post", side_effect=OSError("down")):
            resp = self.client.post("/app/chat", json={"message": "hi"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["response"], "Hello there")

    def test_app_chat_works_without_supabase_configured(self):
        with mock.patch.object(server, "SUPABASE_URL", ""), \
             mock.patch.object(server, "SUPABASE_KEY", ""), \
             self._mock_ollama_and_supabase():
            resp = self.client.post("/app/chat", json={"message": "hi"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["response"], "Hello there")

    def test_app_chat_ollama_failure_is_502(self):
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             mock.patch.object(server.requests, "post", side_effect=OSError("down")):
            resp = self.client.post("/app/chat", json={"message": "hi"})
        self.assertEqual(resp.status_code, 502)

    def test_supabase_post_sends_row(self):
        resp = mock.Mock()
        resp.raise_for_status.return_value = None
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             mock.patch.object(server.requests, "post", return_value=resp) as post:
            server._supabase_post("conversations", {"role": "user", "content": "hi"})
        args, kwargs = post.call_args
        self.assertEqual(args[0], "http://sb/rest/v1/conversations")
        self.assertEqual(kwargs["json"], {"role": "user", "content": "hi"})
        self.assertEqual(kwargs["headers"]["apikey"], "key")
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server -v`
Expected: the 8 new tests FAIL (404s / `AttributeError: module has no attribute '_supabase_post'`); the existing 27 still pass.

- [ ] **Step 3: Implement in `macmini/server.py`**

Add `_supabase_post` right after `_supabase_get`:

```python
def _supabase_post(table, row):
    """Insert one row via PostgREST. Raises on any failure; callers decide
    whether that should fail the request or just be logged and swallowed."""
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=row,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        },
        timeout=10,
    )
    resp.raise_for_status()
```

Add the route after `conversations()` and before `if __name__ == "__main__":`:

```python
APP_CHAT_NODE_ID = "app"  # distinguishes typed chats from voice sessions (node_id="leofric")


@app.post("/app/chat")
def app_chat():
    """Typed chat from the iOS app: mints/reuses a session_id, calls the
    brain, and persists both turns — unlike /chat, which the Pi calls and
    persists client-side itself. Persistence is best-effort: a Supabase
    hiccup must never cost the user their answer."""
    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify(error="missing 'message'"), 400
    history = data.get("history") or []
    session_id = data.get("session_id") or f"{APP_CHAT_NODE_ID}-{int(time.time() * 1000)}"

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "messages": messages, "stream": False, "keep_alive": -1},
            timeout=120,
        )
        resp.raise_for_status()
        reply = resp.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        return jsonify(error=f"ollama request failed: {e}"), 502

    if SUPABASE_URL and SUPABASE_KEY:
        for role, content in (("user", message), ("leofric", reply)):
            try:
                _supabase_post(
                    "conversations",
                    {"node_id": APP_CHAT_NODE_ID, "session_id": session_id,
                     "role": role, "content": content},
                )
            except Exception:
                pass  # best-effort — the user still gets their reply below

    return jsonify(response=reply, session_id=session_id)
```

- [ ] **Step 4: Run the full suite; all pass**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server -v`
Expected: 35 tests, `OK`.

- [ ] **Step 5: Commit**

```bash
git add macmini/server.py macmini/test_server.py
git commit -m "brain: POST /app/chat — typed chats from the app get sessions + history

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Mac — deploy and verify live

**Files:** none created; deploys `macmini/server.py` to `~/leofric-brain/server.py`.

**Interfaces:**
- Consumes: Task 1 merged into `macmini/server.py`.
- Produces: the live Mac API serves `/app/chat`.

- [ ] **Step 1: Deploy**

```bash
cp /Users/danefroelicher/Leofric/macmini/server.py ~/leofric-brain/server.py
diff ~/leofric-brain/server.py /Users/danefroelicher/Leofric/macmini/server.py && echo IDENTICAL
kill $(lsof -tiTCP:5000 -sTCP:LISTEN)
sleep 4
curl -s http://localhost:5000/
```
Expected: `IDENTICAL`, then the health JSON.

- [ ] **Step 2: Verify live**

```bash
curl -s -X POST http://localhost:5000/app/chat -H 'Content-Type: application/json' \
  -d '{"message":"say hello in exactly three words"}'
```
Expected: `{"response":"...", "session_id":"app-<digits>"}`.

```bash
curl -s 'http://localhost:5000/conversations?node_id=app&limit=2' | python3 -m json.tool
```
Expected: two rows (role `user` and `leofric`), both with the same `session_id` from above.

- [ ] **Step 3: Push**

```bash
git push
```

---

### Task 3: iOS — `LeofricStore` (shared API instance) + refactor existing views

**Files:**
- Create: `ios/LeofricApp/LeofricApp/Store/LeofricStore.swift`
- Modify: `ios/LeofricApp/LeofricApp/Views/RootTabView.swift`
- Modify: `ios/LeofricApp/LeofricApp/Views/LiveFeedView.swift`
- Modify: `ios/LeofricApp/LeofricApp/Views/NodesView.swift`

**Interfaces:**
- Consumes: `AppSettings`, `LeofricAPI` (both already exist, unchanged signatures).
- Produces: `final class LeofricStore: ObservableObject` with `init(settings: AppSettings)`, `@Published private(set) var api: LeofricAPI` (rebuilt whenever `settings.baseURL` changes). `RootTabView` constructs one `LeofricStore` and injects it via `.environmentObject(store)` alongside the existing `.environmentObject(settings)`. Tasks 8 and 9 (Alerts, Chats views) consume `@EnvironmentObject private var store: LeofricStore` instead of constructing their own `LeofricAPI`.

- [ ] **Step 1: Write `ios/LeofricApp/LeofricApp/Store/LeofricStore.swift`**

```swift
import Combine
import Foundation

/// Owns the single LeofricAPI instance every tab shares, rebuilt whenever
/// the user changes the Mac's address in Settings. Fixes a Phase 2C review
/// finding: LiveFeedView and NodesView each built their own LeofricAPI,
/// which would have quadrupled once Alerts and Chats needed one too.
final class LeofricStore: ObservableObject {
    @Published private(set) var api: LeofricAPI

    private var cancellable: AnyCancellable?

    init(settings: AppSettings) {
        api = Self.makeAPI(from: settings)
        cancellable = settings.$baseURLString
            .sink { [weak self] _ in
                guard let self else { return }
                self.api = Self.makeAPI(from: settings)
            }
    }

    private static func makeAPI(from settings: AppSettings) -> LeofricAPI {
        LeofricAPI(baseURL: settings.baseURL ?? URL(string: "http://invalid.local:0")!)
    }
}
```

- [ ] **Step 2: Wire it into `ios/LeofricApp/LeofricApp/Views/RootTabView.swift`** — replace the whole file. This task only wires the two EXISTING tabs through the new store; Alerts and Chats are added as their own tabs by Tasks 8 and 9 (each of those tasks replaces this same file with its own complete, growing version — no commenting-out or cross-task restoration needed):

```swift
import SwiftUI

struct RootTabView: View {
    @StateObject private var settings = AppSettings()
    @StateObject private var store: LeofricStore
    @State private var selection = Tab.live

    private enum Tab: Hashable {
        case live, nodes
    }

    init() {
        let settings = AppSettings()
        _settings = StateObject(wrappedValue: settings)
        _store = StateObject(wrappedValue: LeofricStore(settings: settings))
    }

    var body: some View {
        TabView(selection: $selection) {
            LiveFeedView()
                .tabItem { Label("Live", systemImage: "video.fill") }
                .tag(Tab.live)

            NodesView()
                .tabItem { Label("Nodes", systemImage: "server.rack") }
                .tag(Tab.nodes)
        }
        .environmentObject(settings)
        .environmentObject(store)
        .onAppear {
            // Lets headless verification (xcodebuild + simctl screenshot) jump
            // straight to a tab without GUI scripting. No-op for real users.
            if ProcessInfo.processInfo.environment["LEOFRIC_INITIAL_TAB"] == "nodes" {
                selection = .nodes
            }
        }
    }
}

#Preview {
    RootTabView()
}
```

- [ ] **Step 3: Refactor `LiveFeedView.swift`** to consume the shared store instead of constructing its own `LeofricAPI`. Add the property (next to the existing `@EnvironmentObject private var settings: AppSettings` line):
```swift
    @EnvironmentObject private var store: LeofricStore
```
Then in `start()`, change:
```swift
        guard let baseURL = settings.baseURL else { return }
        let api = LeofricAPI(baseURL: baseURL)
        if let fetched = try? await api.fetchNodes(), !fetched.isEmpty {
```
to:
```swift
        guard settings.baseURL != nil else { return }
        let api = store.api
        if let fetched = try? await api.fetchNodes(), !fetched.isEmpty {
```
And in `connect(node:)`, change:
```swift
        guard let baseURL = settings.baseURL else {
            errorMessage = "Set the Mac's address in the Nodes tab."
            return
        }
        errorMessage = nil
        let api = LeofricAPI(baseURL: baseURL)
        reader.start(url: api.feedURL(node: node))
```
to:
```swift
        guard settings.baseURL != nil else {
            errorMessage = "Set the Mac's address in the Nodes tab."
            return
        }
        errorMessage = nil
        reader.start(url: store.api.feedURL(node: node))
```
(The `guard` still exists to produce the error message when no valid URL is configured at all; the API instance itself now always comes from `store.api`, which `LeofricStore` keeps in sync with `settings.baseURLString` — see Step 1's `sink`.)

- [ ] **Step 4: Refactor `NodesView.swift`** the same way. Add `@EnvironmentObject private var store: LeofricStore` next to the existing `@EnvironmentObject private var settings: AppSettings` line. In `refresh()`, change:
```swift
    private func refresh() async {
        guard let baseURL = settings.baseURL else {
            brainHealthy = false
            return
        }
        let api = LeofricAPI(baseURL: baseURL)
        brainHealthy = try? await api.health()
        nodes = (try? await api.fetchNodes()) ?? nodes
    }
```
to:
```swift
    private func refresh() async {
        guard settings.baseURL != nil else {
            brainHealthy = false
            return
        }
        let api = store.api
        brainHealthy = try? await api.health()
        nodes = (try? await api.fetchNodes()) ?? nodes
    }
```

- [ ] **Step 5: Build and run the full test suite**

```bash
cd /Users/danefroelicher/Leofric/ios/LeofricApp && xcodebuild \
  -project LeofricApp.xcodeproj -scheme LeofricApp \
  -destination 'platform=iOS Simulator,id=F40A0E50-DEC8-4A68-9332-3146E8D56711' \
  -derivedDataPath .build build test 2>&1 | tail -20
```
Expected: `** BUILD SUCCEEDED **`, `** TEST SUCCEEDED **`, the same 14 tests as before (this task is a pure refactor — no new tests, existing behavior unchanged, just where the `LeofricAPI` instance comes from).

- [ ] **Step 6: Commit**

```bash
git add ios/LeofricApp/LeofricApp/Store/ ios/LeofricApp/LeofricApp/Views/RootTabView.swift \
        ios/LeofricApp/LeofricApp/Views/LiveFeedView.swift ios/LeofricApp/LeofricApp/Views/NodesView.swift \
        ios/LeofricApp/LeofricApp.xcodeproj
git commit -m "ios: LeofricStore — one shared LeofricAPI instance for all tabs

Addresses a Phase 2C final-review finding before Alerts/Chats would
have tripled the duplication. LiveFeedView/NodesView refactored to
consume it.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: iOS — `LeofricEvent` model + `LeofricAPI.fetchEvents`

**Files:**
- Create: `ios/LeofricApp/LeofricApp/Models/LeofricEvent.swift`
- Modify: `ios/LeofricApp/LeofricApp/Networking/LeofricAPI.swift`
- Modify: `ios/LeofricApp/LeofricAppTests/LeofricAPITests.swift`

**Interfaces:**
- Consumes: nothing new from earlier tasks.
- Produces: `struct LeofricEvent: Decodable, Identifiable` with `id: Int`, `createdAt: String`, `createdAtDate: Date?` (computed), `eventType: String`, `nodeID: String`, `metadata: Metadata`; nested `struct Metadata: Decodable` with `area: Int?`, `count: Int?`, `name: String?`, `similarity: Double?`, `snapshotID: String?`. `LeofricAPI.fetchEvents(limit: Int = 100, eventType: String? = nil, nodeID: String? = nil) async throws -> [LeofricEvent]`. Task 8 (`AlertsView`) consumes this directly.

- [ ] **Step 1: Write the failing tests** — append to `LeofricAppTests.swift`'s class:

```swift
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danefroelicher/Leofric/ios/LeofricApp && xcodebuild -project LeofricApp.xcodeproj -scheme LeofricApp -destination 'platform=iOS Simulator,id=F40A0E50-DEC8-4A68-9332-3146E8D56711' -derivedDataPath .build test 2>&1 | tail -30`
Expected: `** TEST FAILED **` — `cannot find 'LeofricEvent' in scope` / `value of type 'LeofricAPI' has no member 'fetchEvents'`.

- [ ] **Step 3: Write `ios/LeofricApp/LeofricApp/Models/LeofricEvent.swift`**

```swift
import Foundation

/// Mirrors one row of the Mac's `GET /events` response. `metadata`'s fields
/// are all optional since the shape varies by event_type: motion carries
/// `area`, person carries `count`, identity carries `name`/`similarity` and
/// (when a fresh frame was available) `snapshot_id`.
struct LeofricEvent: Decodable, Identifiable {
    let id: Int
    let createdAt: String
    let eventType: String
    let nodeID: String
    let metadata: Metadata

    enum CodingKeys: String, CodingKey {
        case id, metadata
        case createdAt = "created_at"
        case eventType = "event_type"
        case nodeID = "node_id"
    }

    struct Metadata: Decodable {
        let area: Int?
        let count: Int?
        let name: String?
        let similarity: Double?
        let snapshotID: String?

        enum CodingKeys: String, CodingKey {
            case area, count, name, similarity
            case snapshotID = "snapshot_id"
        }
    }

    /// Supabase's created_at is `"...T...microseconds+00:00"` — a different
    /// shape from the Mac's own `/nodes.last_seen` format. Parsed the same
    /// defensive way `macmini/server.py` parses this exact field: take only
    /// the first 19 characters (`yyyy-MM-dd'T'HH:mm:ss`) as UTC, ignoring
    /// fractional seconds and offset — sufficient for display/sort ordering.
    var createdAtDate: Date? {
        Self.dateFormatter.date(from: String(createdAt.prefix(19)))
    }

    static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return formatter
    }()
}

struct EventsResponse: Decodable {
    let events: [LeofricEvent]
}
```

- [ ] **Step 4: Add `fetchEvents` to `ios/LeofricApp/LeofricApp/Networking/LeofricAPI.swift`** — add this method inside the `LeofricAPI` struct, after `fetchNodes()`:

```swift
    func fetchEvents(limit: Int = 100, eventType: String? = nil, nodeID: String? = nil) async throws -> [LeofricEvent] {
        var components = URLComponents(url: baseURL.appendingPathComponent("events"), resolvingAgainstBaseURL: false)!
        var items = [URLQueryItem(name: "limit", value: String(limit))]
        if let eventType { items.append(URLQueryItem(name: "event_type", value: eventType)) }
        if let nodeID { items.append(URLQueryItem(name: "node_id", value: nodeID)) }
        components.queryItems = items
        let (data, response) = try await session.data(from: components.url!)
        guard let http = response as? HTTPURLResponse else { throw LeofricAPIError.invalidResponse }
        guard http.statusCode == 200 else { throw LeofricAPIError.httpStatus(http.statusCode) }
        return try JSONDecoder().decode(EventsResponse.self, from: data).events
    }
```

- [ ] **Step 5: Run to verify all tests pass**

Run: `cd /Users/danefroelicher/Leofric/ios/LeofricApp && xcodebuild -project LeofricApp.xcodeproj -scheme LeofricApp -destination 'platform=iOS Simulator,id=F40A0E50-DEC8-4A68-9332-3146E8D56711' -derivedDataPath .build test 2>&1 | tail -30`
Expected: `** TEST SUCCEEDED **`; 18 tests total (14 prior + 4 new).

- [ ] **Step 6: Commit**

```bash
git add ios/LeofricApp/LeofricApp/Models/LeofricEvent.swift \
        ios/LeofricApp/LeofricApp/Networking/LeofricAPI.swift \
        ios/LeofricApp/LeofricAppTests/LeofricAPITests.swift \
        ios/LeofricApp/LeofricApp.xcodeproj
git commit -m "ios: LeofricEvent model + LeofricAPI.fetchEvents

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: iOS — `ConversationMessage` model + `ConversationThread` grouping

**Files:**
- Create: `ios/LeofricApp/LeofricApp/Models/ConversationMessage.swift`
- Create: `ios/LeofricApp/LeofricApp/Models/ConversationThread.swift`
- Create: `ios/LeofricApp/LeofricAppTests/ConversationThreadTests.swift`

**Interfaces:**
- Consumes: nothing new from earlier tasks.
- Produces: `struct ConversationMessage: Decodable, Identifiable, Equatable` with `id: Int`, `createdAt: String`, `createdAtDate: Date?`, `nodeID: String`, `sessionID: String?`, `role: String`, `content: String`. `struct ConversationThread: Identifiable` with `id: String` (the session_id), `messages: [ConversationMessage]` (chronological, oldest first), `lastMessageAt: Date?`, `preview: String` (last message's content, truncated); `static func group(from messages: [ConversationMessage]) -> [ConversationThread]` — groups by `sessionID` (rows with a nil `sessionID` are dropped — shouldn't happen for rows written after Phase 2B/2D, since both the Pi and `/app/chat` always stamp one), sorts each thread's messages oldest-first, and sorts threads newest-activity-first. Tasks 6 and 9 consume this.

- [ ] **Step 1: Write the failing test** — `ios/LeofricApp/LeofricAppTests/ConversationThreadTests.swift`:

```swift
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danefroelicher/Leofric/ios/LeofricApp && xcodebuild -project LeofricApp.xcodeproj -scheme LeofricApp -destination 'platform=iOS Simulator,id=F40A0E50-DEC8-4A68-9332-3146E8D56711' -derivedDataPath .build test 2>&1 | tail -30`
Expected: `** TEST FAILED **` — `cannot find 'ConversationMessage' in scope`.

- [ ] **Step 3: Write `ios/LeofricApp/LeofricApp/Models/ConversationMessage.swift`**

```swift
import Foundation

/// Mirrors one row of the Mac's `GET /conversations` response.
struct ConversationMessage: Decodable, Identifiable, Equatable {
    let id: Int
    let createdAt: String
    let nodeID: String
    let sessionID: String?
    let role: String  // "user" or "leofric"
    let content: String

    enum CodingKeys: String, CodingKey {
        case id, role, content
        case createdAt = "created_at"
        case nodeID = "node_id"
        case sessionID = "session_id"
    }

    /// Same defensive parsing as LeofricEvent.createdAtDate — see that type's
    /// doc comment for why this only reads the first 19 characters.
    var createdAtDate: Date? {
        Self.dateFormatter.date(from: String(createdAt.prefix(19)))
    }

    static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return formatter
    }()
}

struct ConversationsResponse: Decodable {
    let conversations: [ConversationMessage]
}
```

- [ ] **Step 4: Write `ios/LeofricApp/LeofricApp/Models/ConversationThread.swift`**

```swift
import Foundation

/// A chat thread: one wake-word session or one app-composed conversation,
/// grouped from the Mac's flat `/conversations` rows by session_id. Voice
/// sessions get session_id `"leofric-<unix-seconds>"` (brain/conversation.py
/// on the Pi); app-typed chats get `"app-<unix-ms>"` (macmini/server.py's
/// POST /app/chat) — the prefix is cosmetic, grouping only cares that it's
/// present and shared.
struct ConversationThread: Identifiable {
    let id: String  // the session_id
    let messages: [ConversationMessage]  // oldest first

    var lastMessageAt: Date? {
        messages.last?.createdAtDate
    }

    var preview: String {
        messages.last?.content ?? ""
    }

    /// Groups a flat, any-order list of messages into threads. Rows with no
    /// session_id are dropped (shouldn't occur for rows written after
    /// Phase 2B/2D — both write paths always stamp one).
    static func group(from messages: [ConversationMessage]) -> [ConversationThread] {
        var bySession: [String: [ConversationMessage]] = [:]
        for message in messages {
            guard let sessionID = message.sessionID else { continue }
            bySession[sessionID, default: []].append(message)
        }
        let threads = bySession.map { sessionID, msgs in
            ConversationThread(
                id: sessionID,
                messages: msgs.sorted { ($0.createdAtDate ?? .distantPast) < ($1.createdAtDate ?? .distantPast) }
            )
        }
        return threads.sorted { ($0.lastMessageAt ?? .distantPast) > ($1.lastMessageAt ?? .distantPast) }
    }
}
```

- [ ] **Step 5: Run to verify all tests pass**

Run: `cd /Users/danefroelicher/Leofric/ios/LeofricApp && xcodebuild -project LeofricApp.xcodeproj -scheme LeofricApp -destination 'platform=iOS Simulator,id=F40A0E50-DEC8-4A68-9332-3146E8D56711' -derivedDataPath .build test 2>&1 | tail -30`
Expected: `** TEST SUCCEEDED **`; 24 tests total (18 prior + 6 new).

- [ ] **Step 6: Commit**

```bash
git add ios/LeofricApp/LeofricApp/Models/ConversationMessage.swift \
        ios/LeofricApp/LeofricApp/Models/ConversationThread.swift \
        ios/LeofricApp/LeofricAppTests/ConversationThreadTests.swift \
        ios/LeofricApp/LeofricApp.xcodeproj
git commit -m "ios: ConversationMessage model + ConversationThread grouping

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: iOS — `LeofricAPI.fetchConversations` + `sendAppChat` + `snapshotURL`

**Files:**
- Modify: `ios/LeofricApp/LeofricApp/Networking/LeofricAPI.swift`
- Modify: `ios/LeofricApp/LeofricAppTests/LeofricAPITests.swift`

**Interfaces:**
- Consumes: `ConversationMessage`/`ConversationsResponse` (Task 5).
- Produces: `LeofricAPI.fetchConversations(limit: Int = 200, sessionID: String? = nil, nodeID: String? = nil) async throws -> [ConversationMessage]`; `struct AppChatResponse: Decodable { let response: String; let sessionID: String }` with `CodingKeys` mapping `session_id`; `LeofricAPI.sendAppChat(message: String, sessionID: String?, history: [[String: String]] = []) async throws -> AppChatResponse` (POSTs to `/app/chat`); `LeofricAPI.snapshotURL(id: String) -> URL` (GET `/snapshot/<id>`, no query params). Tasks 7–9 consume all three.

- [ ] **Step 1: Write the failing tests** — append to `LeofricAPITests.swift`:

```swift
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
```

Note: `URLRequest` doesn't expose a body for stream-based requests directly via `.httpBody` once handed to `URLProtocol` in all cases — if `request.httpBody` is `nil` inside the mock handler (because `URLSession` moved the body to `httpBodyStream`), read it via:
```swift
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
```
Add this extension near the top of `LeofricAPITests.swift` (outside the test class), since `URLProtocol`'s intercepted requests for a POST with a `Data` body typically arrive via `httpBodyStream`, not `httpBody`, when going through a custom protocol.

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danefroelicher/Leofric/ios/LeofricApp && xcodebuild -project LeofricApp.xcodeproj -scheme LeofricApp -destination 'platform=iOS Simulator,id=F40A0E50-DEC8-4A68-9332-3146E8D56711' -derivedDataPath .build test 2>&1 | tail -30`
Expected: `** TEST FAILED **` — `value of type 'LeofricAPI' has no member 'fetchConversations'` etc.

- [ ] **Step 3: Add to `ios/LeofricApp/LeofricApp/Networking/LeofricAPI.swift`** — add `AppChatResponse` above the `LeofricAPI` struct, and the three new methods inside it, after `fetchEvents`:

```swift
struct AppChatResponse: Decodable {
    let response: String
    let sessionID: String

    enum CodingKeys: String, CodingKey {
        case response
        case sessionID = "session_id"
    }
}
```

```swift
    func fetchConversations(limit: Int = 200, sessionID: String? = nil, nodeID: String? = nil) async throws -> [ConversationMessage] {
        var components = URLComponents(url: baseURL.appendingPathComponent("conversations"), resolvingAgainstBaseURL: false)!
        var items = [URLQueryItem(name: "limit", value: String(limit))]
        if let sessionID { items.append(URLQueryItem(name: "session_id", value: sessionID)) }
        if let nodeID { items.append(URLQueryItem(name: "node_id", value: nodeID)) }
        components.queryItems = items
        let (data, response) = try await session.data(from: components.url!)
        guard let http = response as? HTTPURLResponse else { throw LeofricAPIError.invalidResponse }
        guard http.statusCode == 200 else { throw LeofricAPIError.httpStatus(http.statusCode) }
        return try JSONDecoder().decode(ConversationsResponse.self, from: data).conversations
    }

    func sendAppChat(message: String, sessionID: String?, history: [[String: String]] = []) async throws -> AppChatResponse {
        var body: [String: Any] = ["message": message, "history": history]
        if let sessionID { body["session_id"] = sessionID }
        var request = URLRequest(url: baseURL.appendingPathComponent("app/chat"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw LeofricAPIError.invalidResponse }
        guard http.statusCode == 200 else { throw LeofricAPIError.httpStatus(http.statusCode) }
        return try JSONDecoder().decode(AppChatResponse.self, from: data)
    }

    func snapshotURL(id: String) -> URL {
        baseURL.appendingPathComponent("snapshot").appendingPathComponent(id)
    }
```

- [ ] **Step 4: Run to verify all tests pass**

Run: `cd /Users/danefroelicher/Leofric/ios/LeofricApp && xcodebuild -project LeofricApp.xcodeproj -scheme LeofricApp -destination 'platform=iOS Simulator,id=F40A0E50-DEC8-4A68-9332-3146E8D56711' -derivedDataPath .build test 2>&1 | tail -30`
Expected: `** TEST SUCCEEDED **`; 28 tests total (24 prior + 4 new).

- [ ] **Step 5: Commit**

```bash
git add ios/LeofricApp/LeofricApp/Networking/LeofricAPI.swift \
        ios/LeofricApp/LeofricAppTests/LeofricAPITests.swift
git commit -m "ios: LeofricAPI.fetchConversations + sendAppChat + snapshotURL

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: iOS — `ImageCache`

**Files:**
- Create: `ios/LeofricApp/LeofricApp/Support/ImageCache.swift`
- Create: `ios/LeofricApp/LeofricAppTests/ImageCacheTests.swift`

**Interfaces:**
- Consumes: nothing new from earlier tasks (only `Foundation`/`UIKit`).
- Produces: `@MainActor final class ImageCache: ObservableObject` with `static let shared: ImageCache`, `func image(for url: URL, session: URLSession = .shared) async -> UIImage?` (returns the cached image if present; otherwise fetches, caches, and returns it; returns `nil` on any failure without throwing — a bad thumbnail must never crash a list). Task 8 (`AlertsView`) consumes this for snapshot thumbnails and the full-photo view.

- [ ] **Step 1: Write the failing tests** — `ios/LeofricApp/LeofricAppTests/ImageCacheTests.swift`:

```swift
import XCTest
@testable import LeofricApp

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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danefroelicher/Leofric/ios/LeofricApp && xcodebuild -project LeofricApp.xcodeproj -scheme LeofricApp -destination 'platform=iOS Simulator,id=F40A0E50-DEC8-4A68-9332-3146E8D56711' -derivedDataPath .build test 2>&1 | tail -30`
Expected: `** TEST FAILED **` — `cannot find 'ImageCache' in scope`.

- [ ] **Step 3: Write `ios/LeofricApp/LeofricApp/Support/ImageCache.swift`**

```swift
import UIKit

/// A small in-memory image cache for Alerts thumbnails and the full-photo
/// view, so scrolling a list doesn't refetch the same snapshot repeatedly.
/// NSCache-backed rather than a third-party library, per the zero-dependency
/// constraint — this is the whole feature, nothing more is needed at this
/// app's scale.
@MainActor
final class ImageCache: ObservableObject {
    static let shared = ImageCache()

    private let cache = NSCache<NSURL, UIImage>()

    func image(for url: URL, session: URLSession = .shared) async -> UIImage? {
        if let cached = cache.object(forKey: url as NSURL) {
            return cached
        }
        guard let (data, response) = try? await session.data(from: url),
              let http = response as? HTTPURLResponse, http.statusCode == 200,
              let image = UIImage(data: data)
        else {
            return nil
        }
        cache.setObject(image, forKey: url as NSURL)
        return image
    }
}
```

- [ ] **Step 4: Run to verify all tests pass**

Run: `cd /Users/danefroelicher/Leofric/ios/LeofricApp && xcodebuild -project LeofricApp.xcodeproj -scheme LeofricApp -destination 'platform=iOS Simulator,id=F40A0E50-DEC8-4A68-9332-3146E8D56711' -derivedDataPath .build test 2>&1 | tail -30`
Expected: `** TEST SUCCEEDED **`; 32 tests total (28 prior + 4 new).

- [ ] **Step 5: Commit**

```bash
git add ios/LeofricApp/LeofricApp/Support/ImageCache.swift \
        ios/LeofricApp/LeofricAppTests/ImageCacheTests.swift \
        ios/LeofricApp/LeofricApp.xcodeproj
git commit -m "ios: ImageCache — NSCache-backed thumbnail/photo cache

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: iOS — Alerts tab (`AlertsView` + `AlertDetailView`)

**Files:**
- Create: `ios/LeofricApp/LeofricApp/Views/AlertsView.swift`
- Create: `ios/LeofricApp/LeofricApp/Views/AlertDetailView.swift`
- Modify: `ios/LeofricApp/LeofricApp/Views/RootTabView.swift` (uncomment the `AlertsView()` tab entry stubbed in Task 3)

**Interfaces:**
- Consumes: `LeofricEvent`/`EventsResponse` (Task 4), `LeofricStore`/`store.api.fetchEvents` (Tasks 3–4), `ImageCache.shared` + `store.api.snapshotURL(id:)` (Tasks 6–7).
- Produces: `AlertsView` (the tab root — list + filter), `AlertDetailView` (full photo + "Watch Live" button, navigates to the Live tab).

**Scope note:** the ROADMAP says "filter by node/type." This task implements the type filter only — `fetchEvents(nodeID:)` already exists (Task 4) so a node filter is a one-line addition whenever it's needed, but with exactly one node (`leofric`) in the system today, a node-filter menu with a single always-selected option is pure clutter. Add it when Phase 4 (second node) actually exists.

- [ ] **Step 1: Write `ios/LeofricApp/LeofricApp/Views/AlertDetailView.swift`**

```swift
import SwiftUI

/// Full-size photo for one alert, with a way back to the live feed for that
/// node. There is no in-app tab-programmatic-navigation primitive wired up
/// yet (RootTabView's `selection` is private) — "Watch Live" is a dismiss +
/// instruction rather than an automatic tab jump, matching the simplest
/// correct behavior for this phase; wiring a shared tab-selection binding is
/// a cheap follow-up if this proves annoying in daily use.
struct AlertDetailView: View {
    let event: LeofricEvent
    @EnvironmentObject private var store: LeofricStore
    @Environment(\.dismiss) private var dismiss
    @State private var image: UIImage?

    var body: some View {
        VStack(spacing: 16) {
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
            } else {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 200)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(event.eventType.capitalized)
                    .font(.headline)
                if let name = event.metadata.name {
                    Text(name == "unknown" ? "Unknown person" : name.capitalized)
                        .foregroundStyle(name == "unknown" ? .red : .primary)
                }
                Text(event.nodeID)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Button("Watch Live") { dismiss() }
                .buttonStyle(.borderedProminent)

            Spacer()
        }
        .padding()
        .navigationTitle("Alert")
        .task { await loadImage() }
    }

    private func loadImage() async {
        guard let snapshotID = event.metadata.snapshotID else { return }
        image = await ImageCache.shared.image(for: store.api.snapshotURL(id: snapshotID))
    }
}
```

- [ ] **Step 2: Write `ios/LeofricApp/LeofricApp/Views/AlertsView.swift`**

```swift
import SwiftUI

/// The security timeline: every motion/person/identity event, newest first,
/// with a thumbnail when one exists (person/identity only — motion has no
/// snapshot_id, per the Mac's design). Filter by event type via a menu.
struct AlertsView: View {
    @EnvironmentObject private var store: LeofricStore
    @State private var events: [LeofricEvent] = []
    @State private var filter: String? = nil  // nil = all types
    @State private var isLoading = false

    private let filterOptions: [(label: String, value: String?)] = [
        ("All", nil), ("Motion", "motion"), ("Person", "person"), ("Identity", "identity"),
    ]

    var body: some View {
        NavigationStack {
            List(events) { event in
                NavigationLink(value: event) {
                    AlertRow(event: event)
                }
            }
            .navigationDestination(for: LeofricEvent.self) { event in
                AlertDetailView(event: event)
            }
            .navigationTitle("Alerts")
            .toolbar {
                Menu {
                    ForEach(filterOptions, id: \.label) { option in
                        Button(option.label) {
                            filter = option.value
                            Task { await refresh() }
                        }
                    }
                } label: {
                    Image(systemName: "line.3.horizontal.decrease.circle")
                }
            }
            .refreshable { await refresh() }
            .task { await refresh() }
            .overlay {
                if events.isEmpty && !isLoading {
                    ContentUnavailableView("No Alerts Yet", systemImage: "bell.slash")
                }
            }
        }
    }

    private func refresh() async {
        isLoading = true
        defer { isLoading = false }
        events = (try? await store.api.fetchEvents(eventType: filter)) ?? events
    }
}

private struct AlertRow: View {
    let event: LeofricEvent
    @EnvironmentObject private var store: LeofricStore
    @State private var thumbnail: UIImage?

    var body: some View {
        HStack(spacing: 12) {
            Group {
                if let thumbnail {
                    Image(uiImage: thumbnail).resizable().aspectRatio(contentMode: .fill)
                } else {
                    Image(systemName: iconName)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(width: 56, height: 56)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .background(Color.secondary.opacity(0.1), in: RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline).bold()
                if let date = event.createdAtDate {
                    Text(date, style: .relative)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
        }
        .task { await loadThumbnail() }
    }

    private var title: String {
        switch event.eventType {
        case "identity":
            let name = event.metadata.name ?? "unknown"
            return name == "unknown" ? "Unknown person" : name.capitalized
        case "person": return "Person detected"
        case "motion": return "Motion"
        default: return event.eventType.capitalized
        }
    }

    private var iconName: String {
        switch event.eventType {
        case "identity": return "person.crop.circle"
        case "person": return "figure.walk"
        default: return "sensor.tag.radiowaves.forward"
        }
    }

    private func loadThumbnail() async {
        guard let snapshotID = event.metadata.snapshotID else { return }
        thumbnail = await ImageCache.shared.image(for: store.api.snapshotURL(id: snapshotID))
    }
}

extension LeofricEvent: Hashable {
    static func == (lhs: LeofricEvent, rhs: LeofricEvent) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}
```

- [ ] **Step 3: Add the Alerts tab to `RootTabView.swift`** — replace the whole file with this (adds `AlertsView` as the second tab; `ChatsListView` is not part of this app yet — Task 9 adds the fourth tab in its own complete rewrite of this same file):

```swift
import SwiftUI

struct RootTabView: View {
    @StateObject private var settings = AppSettings()
    @StateObject private var store: LeofricStore
    @State private var selection = Tab.live

    private enum Tab: Hashable {
        case live, alerts, nodes
    }

    init() {
        let settings = AppSettings()
        _settings = StateObject(wrappedValue: settings)
        _store = StateObject(wrappedValue: LeofricStore(settings: settings))
    }

    var body: some View {
        TabView(selection: $selection) {
            LiveFeedView()
                .tabItem { Label("Live", systemImage: "video.fill") }
                .tag(Tab.live)

            AlertsView()
                .tabItem { Label("Alerts", systemImage: "bell.fill") }
                .tag(Tab.alerts)

            NodesView()
                .tabItem { Label("Nodes", systemImage: "server.rack") }
                .tag(Tab.nodes)
        }
        .environmentObject(settings)
        .environmentObject(store)
        .onAppear {
            switch ProcessInfo.processInfo.environment["LEOFRIC_INITIAL_TAB"] {
            case "nodes": selection = .nodes
            case "alerts": selection = .alerts
            default: break
            }
        }
    }
}

#Preview {
    RootTabView()
}
```

- [ ] **Step 4: Build and test**

```bash
cd /Users/danefroelicher/Leofric/ios/LeofricApp && xcodebuild \
  -project LeofricApp.xcodeproj -scheme LeofricApp \
  -destination 'platform=iOS Simulator,id=F40A0E50-DEC8-4A68-9332-3146E8D56711' \
  -derivedDataPath .build build test 2>&1 | tail -20
```
Expected: `** BUILD SUCCEEDED **`, `** TEST SUCCEEDED **`, same 32 tests as before (this task adds views, not new unit tests — visual verification happens in Task 10 against the live Mac).

- [ ] **Step 5: Commit**

```bash
git add ios/LeofricApp/LeofricApp/Views/AlertsView.swift \
        ios/LeofricApp/LeofricApp/Views/AlertDetailView.swift \
        ios/LeofricApp/LeofricApp/Views/RootTabView.swift \
        ios/LeofricApp/LeofricApp.xcodeproj
git commit -m "ios: Alerts tab — event timeline with thumbnails, filter, detail view

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: iOS — Chats tab (`ChatsListView` + `ChatThreadView`)

**Files:**
- Create: `ios/LeofricApp/LeofricApp/Views/ChatsListView.swift`
- Create: `ios/LeofricApp/LeofricApp/Views/ChatThreadView.swift`
- Modify: `ios/LeofricApp/LeofricApp/Views/RootTabView.swift` (uncomment the `ChatsListView()` tab entry)

**Interfaces:**
- Consumes: `ConversationMessage`/`ConversationThread` (Task 5), `store.api.fetchConversations`/`sendAppChat` (Task 6).
- Produces: `ChatsListView` (thread list + compose button), `ChatThreadView` (message bubbles + input, ~2s polling while visible).

- [ ] **Step 1: Write `ios/LeofricApp/LeofricApp/Views/ChatThreadView.swift`**

```swift
import SwiftUI

/// One thread, iMessage-style. `sessionID` is nil only for a brand-new
/// compose flow — it becomes known the moment the first message's response
/// arrives (the Mac mints it), and every message after that carries it.
struct ChatThreadView: View {
    @State var sessionID: String?
    @EnvironmentObject private var store: LeofricStore
    @State private var messages: [ConversationMessage] = []
    @State private var draft = ""
    @State private var isSending = false
    @State private var pollTask: Task<Void, Never>?

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(messages) { message in
                            MessageBubble(message: message).id(message.id)
                        }
                    }
                    .padding()
                }
                .onChange(of: messages.count) { _, _ in
                    if let lastID = messages.last?.id {
                        withAnimation { proxy.scrollTo(lastID, anchor: .bottom) }
                    }
                }
            }

            HStack {
                TextField("Message", text: $draft, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                Button("Send") { Task { await send() } }
                    .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSending)
            }
            .padding()
        }
        .navigationTitle("Chat")
        .navigationBarTitleDisplayMode(.inline)
        .task { await loadInitial() }
        .onAppear { startPolling() }
        .onDisappear { pollTask?.cancel() }
    }

    private func loadInitial() async {
        guard let sessionID else { return }  // new compose flow — nothing to load yet
        messages = (try? await store.api.fetchConversations(sessionID: sessionID)) ?? []
    }

    private func startPolling() {
        pollTask?.cancel()
        pollTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                if Task.isCancelled { break }
                await refreshIfNeeded()
            }
        }
    }

    private func refreshIfNeeded() async {
        guard let sessionID else { return }
        guard let fresh = try? await store.api.fetchConversations(sessionID: sessionID) else { return }
        if fresh.count != messages.count {
            messages = fresh
        }
    }

    private func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draft = ""
        isSending = true
        defer { isSending = false }

        let historyPairs = messages.map { ["role": $0.role == "leofric" ? "assistant" : "user", "content": $0.content] }
        guard let result = try? await store.api.sendAppChat(message: text, sessionID: sessionID, history: historyPairs) else {
            draft = text  // restore on failure so the user doesn't lose their message
            return
        }
        sessionID = result.sessionID
        messages = (try? await store.api.fetchConversations(sessionID: result.sessionID)) ?? messages
    }
}

private struct MessageBubble: View {
    let message: ConversationMessage

    var body: some View {
        HStack {
            if message.role == "leofric" { bubble; Spacer(minLength: 40) }
            else { Spacer(minLength: 40); bubble }
        }
    }

    private var bubble: some View {
        Text(message.content)
            .padding(10)
            .background(message.role == "leofric" ? Color.secondary.opacity(0.2) : Color.accentColor)
            .foregroundStyle(message.role == "leofric" ? Color.primary : Color.white)
            .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}
```

- [ ] **Step 2: Write `ios/LeofricApp/LeofricApp/Views/ChatsListView.swift`**

```swift
import SwiftUI

/// Thread list. Voice sessions from the Pi appear here automatically (their
/// session_id already exists in Supabase by the time this view fetches);
/// typed chats start via the compose button.
struct ChatsListView: View {
    @EnvironmentObject private var store: LeofricStore
    @State private var threads: [ConversationThread] = []
    @State private var isComposing = false

    var body: some View {
        NavigationStack {
            List(threads) { thread in
                NavigationLink(value: thread.id) {
                    ThreadRow(thread: thread)
                }
            }
            .navigationDestination(for: String.self) { sessionID in
                ChatThreadView(sessionID: sessionID)
            }
            .navigationTitle("Chats")
            .toolbar {
                Button {
                    isComposing = true
                } label: {
                    Image(systemName: "square.and.pencil")
                }
            }
            .refreshable { await refresh() }
            .task { await refresh() }
            .overlay {
                if threads.isEmpty {
                    ContentUnavailableView("No Chats Yet", systemImage: "message")
                }
            }
            .navigationDestination(isPresented: $isComposing) {
                ChatThreadView(sessionID: nil)
            }
        }
    }

    private func refresh() async {
        let messages = (try? await store.api.fetchConversations()) ?? []
        threads = ConversationThread.group(from: messages)
    }
}

private struct ThreadRow: View {
    let thread: ConversationThread

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(thread.id.hasPrefix("app-") ? "Typed chat" : "Voice session")
                    .font(.subheadline).bold()
                Spacer()
                if let date = thread.lastMessageAt {
                    Text(date, style: .relative).font(.caption).foregroundStyle(.secondary)
                }
            }
            Text(thread.preview)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
    }
}
```

- [ ] **Step 3: Add the Chats tab to `RootTabView.swift`** — replace the whole file with this final, four-tab version:

```swift
import SwiftUI

struct RootTabView: View {
    @StateObject private var settings = AppSettings()
    @StateObject private var store: LeofricStore
    @State private var selection = Tab.live

    private enum Tab: Hashable {
        case live, alerts, chats, nodes
    }

    init() {
        let settings = AppSettings()
        _settings = StateObject(wrappedValue: settings)
        _store = StateObject(wrappedValue: LeofricStore(settings: settings))
    }

    var body: some View {
        TabView(selection: $selection) {
            LiveFeedView()
                .tabItem { Label("Live", systemImage: "video.fill") }
                .tag(Tab.live)

            AlertsView()
                .tabItem { Label("Alerts", systemImage: "bell.fill") }
                .tag(Tab.alerts)

            ChatsListView()
                .tabItem { Label("Chats", systemImage: "message.fill") }
                .tag(Tab.chats)

            NodesView()
                .tabItem { Label("Nodes", systemImage: "server.rack") }
                .tag(Tab.nodes)
        }
        .environmentObject(settings)
        .environmentObject(store)
        .onAppear {
            switch ProcessInfo.processInfo.environment["LEOFRIC_INITIAL_TAB"] {
            case "nodes": selection = .nodes
            case "alerts": selection = .alerts
            case "chats": selection = .chats
            default: break
            }
        }
    }
}

#Preview {
    RootTabView()
}
```

- [ ] **Step 4: Build and test**

```bash
cd /Users/danefroelicher/Leofric/ios/LeofricApp && xcodebuild \
  -project LeofricApp.xcodeproj -scheme LeofricApp \
  -destination 'platform=iOS Simulator,id=F40A0E50-DEC8-4A68-9332-3146E8D56711' \
  -derivedDataPath .build build test 2>&1 | tail -20
```
Expected: `** BUILD SUCCEEDED **`, `** TEST SUCCEEDED **`, same 32 tests (UI-only task; Task 10 verifies live).

- [ ] **Step 5: Commit**

```bash
git add ios/LeofricApp/LeofricApp/Views/ChatsListView.swift \
        ios/LeofricApp/LeofricApp/Views/ChatThreadView.swift \
        ios/LeofricApp/LeofricApp/Views/RootTabView.swift \
        ios/LeofricApp/LeofricApp.xcodeproj
git commit -m "ios: Chats tab — thread list, compose, iMessage-style thread view

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 10: End-to-end live verification + ROADMAP close-out

**Files:**
- Modify: `docs/ROADMAP.md`

**Interfaces:**
- Consumes: the complete app from Tasks 1–9.

- [ ] **Step 1: Confirm the Mac brain and at least one real event/conversation exist**

```bash
curl -s --max-time 5 http://localhost:5000/nodes
curl -s 'http://localhost:5000/events?limit=1'
curl -s 'http://localhost:5000/conversations?limit=1'
```
Expected: real JSON for all three (the Pi has been running continuously; if `/conversations` is empty, that's fine — a fresh app-composed message in Step 4 below will populate it).

- [ ] **Step 2: Rebuild, fresh-install, launch onto the Alerts tab, screenshot**

```bash
cd /Users/danefroelicher/Leofric/ios/LeofricApp && xcodebuild \
  -project LeofricApp.xcodeproj -scheme LeofricApp \
  -destination 'platform=iOS Simulator,id=F40A0E50-DEC8-4A68-9332-3146E8D56711' \
  -derivedDataPath .build build 2>&1 | tail -10
xcrun simctl boot F40A0E50-DEC8-4A68-9332-3146E8D56711 2>&1 || true
xcrun simctl uninstall F40A0E50-DEC8-4A68-9332-3146E8D56711 com.danefroelicher.Leofric 2>&1 || true
xcrun simctl install F40A0E50-DEC8-4A68-9332-3146E8D56711 \
  .build/Build/Products/Debug-iphonesimulator/LeofricApp.app
SIMCTL_CHILD_LEOFRIC_INITIAL_TAB=alerts xcrun simctl launch F40A0E50-DEC8-4A68-9332-3146E8D56711 com.danefroelicher.Leofric
sleep 4
xcrun simctl io F40A0E50-DEC8-4A68-9332-3146E8D56711 screenshot /tmp/leofric-alerts-tab.png
```
Report this path in your DONE report. Expected when viewed: a list of real events (motion/person/identity) with relative timestamps; person/identity rows should show a real thumbnail photo, not a placeholder icon, if the Pi has logged one recently (within `SNAPSHOT_KEEP`'s window — should be true given the Pi runs continuously).

- [ ] **Step 3: Tap an alert with a photo, screenshot the detail view** — same `SIMCTL_CHILD_LEOFRIC_INITIAL_TAB` trick doesn't reach a specific row; this one genuinely needs a tap. Use `xcrun simctl` to simulate a touch is not directly supported — instead, verify the detail view's CODE path (not a live tap) by confirming Step 2's list screenshot shows real thumbnails (proving `AlertRow`'s `ImageCache` fetch path works against the live Mac), which exercises the same `store.api.snapshotURL(id:)` + `ImageCache.shared.image(for:)` call `AlertDetailView` also uses — this is sufficient evidence the underlying data path works; a manual on-device tap-through is deferred to the user's own testing pass (explicitly planned for after Phase 2E, per the human's direction this session).

- [ ] **Step 4: Send a real typed chat message through the running app** — this proves `POST /app/chat` end-to-end, not just via curl. Relaunch onto the Chats tab, use the compose flow via a direct API call standing in for the tap (the app has no scriptable text-entry either) — verify the SAME code path by calling the live endpoint exactly as `sendAppChat` does:

```bash
curl -s -X POST http://localhost:5000/app/chat -H 'Content-Type: application/json' \
  -d '{"message":"Phase 2D live verification — please reply with one short sentence."}'
```
Expected: `{"response":"...", "session_id":"app-<ms>"}`. Then:

```bash
SIMCTL_CHILD_LEOFRIC_INITIAL_TAB=chats xcrun simctl launch F40A0E50-DEC8-4A68-9332-3146E8D56711 com.danefroelicher.Leofric
sleep 4
xcrun simctl io F40A0E50-DEC8-4A68-9332-3146E8D56711 screenshot /tmp/leofric-chats-tab.png
```
Report this path. Expected: the Chats tab's thread list shows a "Typed chat" row (the one just created via curl) — proving `ChatsListView.refresh()` → `fetchConversations()` → `ConversationThread.group(from:)` correctly surfaces app-originated sessions written by `/app/chat`, exercising the full real pipeline this phase built (Mac persistence → app read → client-side grouping → list render).

- [ ] **Step 5: Report all screenshot paths** in your DONE report: `/tmp/leofric-alerts-tab.png`, `/tmp/leofric-chats-tab.png`. The controller will view both directly.

- [ ] **Step 6: Update `docs/ROADMAP.md`** — find `### 2D — Alerts + Chats`, check off the two `[CODE]` items (leave the `[YOU]` on-device item unchecked — the human has explicitly deferred on-device testing until after 2E), and append a completion note following the 2A/2B/2C pattern: state what was verified live (real event thumbnails rendering, a real `/app/chat` message appearing as a thread), the test count, and the plan file path.

- [ ] **Step 7: Commit and push**

```bash
cd /Users/danefroelicher/Leofric
git add docs/ROADMAP.md
git commit -m "docs: Phase 2D complete — Alerts + Chats verified against live Mac

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
git push
```
