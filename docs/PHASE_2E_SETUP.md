# Phase 2E — Push Notifications & Remote Access: Builder Setup

**Status:** all Phase 2E code is complete, unit-tested, and deployed to the Mac.
What remains are the steps only you can do — generating Apple credentials,
building to a physical iPhone, and installing Tailscale. Push notifications
**cannot be verified without these**, which is why they're a separate runbook
rather than something the build session could prove working.

The code is designed so the whole push subsystem **no-ops silently until you add
the credentials below** — the brain already runs fine without them (verified),
so nothing here is urgent or breakable.

---

## What's already done (no action needed)

- **Mac brain:** `POST /devices` (registers your phone's push token, stored in
  `~/leofric-brain/devices.json`), a notification decision engine
  (`macmini/notify.py` — identity-aware text, per-node 60s cooldown, unknown
  persons always alert), an APNs sender (`macmini/apns.py` — HTTP/2 + ES256 JWT),
  and a best-effort push hook in `/ingest/event` that fires when a person or
  identity is detected at a security node. `httpx[http2]` + `PyJWT[crypto]` are
  installed in the deployment venv.
- **iOS app:** requests notification permission on launch, registers for remote
  notifications, and POSTs its device token to the Mac. A **Notification Service
  Extension** downloads the event's snapshot and attaches it, so the push arrives
  as a rich notification with the photo.

---

## Step 1 — Apple Developer portal (one-time)

1. **Create an APNs Auth Key:** developer.apple.com → Certificates, IDs & Profiles
   → **Keys** → **+**. Name it (e.g. "Leofric APNs"), tick **Apple Push
   Notifications service (APNs)**, Continue → Register → **Download** the `.p8`
   file. **You can only download it once** — save it somewhere safe.
   - Record the **Key ID** (10 chars, shown on the key's page).
   - Record your **Team ID** (top-right of the portal, or Membership page).
2. **Configure the App ID** `com.danefroelicher.Leofric` (Identifiers → your app
   ID): enable **Push Notifications** and **App Groups**. Under App Groups, create
   `group.com.danefroelicher.Leofric` and assign it to the App ID.

## Step 2 — Mac brain config

1. Copy the `.p8` to the Mac, e.g. `~/leofric-brain/AuthKey_XXXXXX.p8`.
2. Add to `~/leofric-brain/.env` (same file that holds the Supabase keys):
   ```
   APNS_KEY_PATH=/Users/danefroelicher/leofric-brain/AuthKey_XXXXXX.p8
   APNS_KEY_ID=<your 10-char Key ID>
   APNS_TEAM_ID=<your 10-char Team ID>
   APNS_BUNDLE_ID=com.danefroelicher.Leofric
   APNS_USE_SANDBOX=1
   ```
   **`APNS_USE_SANDBOX`:** `1` for a build you run from Xcode onto your phone
   (development APNs). `0` only for a TestFlight/App Store build (production APNs).
   Using the wrong one is the most common cause of "token is valid but no push
   arrives" — the sandbox and production APNs environments are separate.
3. Restart the brain: `kill $(lsof -tiTCP:5000 -sTCP:LISTEN)` (launchd relaunches
   it). Confirm it still answers: `curl -s http://localhost:5000/`.

## Step 3 — Build to your iPhone (Xcode)

1. Open `ios/LeofricApp/LeofricApp.xcodeproj` in Xcode.
2. For **both** the `LeofricApp` and `NotificationService` targets: Signing &
   Capabilities → select your **Team**. Confirm the **Push Notifications** and
   **App Groups** (`group.com.danefroelicher.Leofric`) capabilities are present
   on the app target, and the App Group is present on the extension target.
   (The entitlements files are already committed; you're just assigning the team.)
3. Plug in your iPhone, select it as the run destination, and Run. Accept the
   notification-permission prompt when the app launches.
4. Confirm the token registered — on the Mac:
   ```
   cat ~/leofric-brain/devices.json
   ```
   You should see a 64-hex-character token (not the `deadbeefcafe` test value).
5. **Local push test:** with your phone on the same WiFi and the app's Nodes-tab
   address pointing at the Mac, have someone walk in front of the Pi's camera (or
   `curl -s -X POST http://<mac>:5000/ingest/event/leofric -H 'Content-Type: application/json' -d '{"event_type":"identity","metadata":{"name":"unknown"}}'`
   from another machine). Expect a push: **"UNKNOWN PERSON at leofric"** with the
   snapshot photo.

## Step 4 — Tailscale (remote access)

The app already reads the Mac's address from the Nodes-tab setting, so remote
access is a network change, not a code change.

1. Install **Tailscale** on the Mac and on the iPhone; sign both into the **same**
   Tailscale account. (Free personal plan is enough.)
2. In the app's **Nodes** tab, set the Mac address to the Mac's Tailscale name,
   e.g. `http://danes-mac-mini-3.tailXXXX.ts.net:5000` (find it in the Tailscale
   app, or use the Tailscale IP `http://100.x.y.z:5000`).
3. The Notification Service Extension reads this same address from the shared App
   Group, so snapshot photos will download over Tailscale too when you're away.

## Step 5 — The Arizona test

1. Take your phone off home WiFi (cellular only; Tailscale stays connected).
2. Have someone trigger a person event at the node (walk in front of the camera).
3. Confirm: the push arrives on cellular within a few seconds, shows the photo,
   and tapping it opens the app with the live feed loading over Tailscale.

If that works, Phase 2 is done — the app is a real remote security camera.

---

## Troubleshooting

- **Token registers but no push:** almost always the sandbox/production mismatch
  (`APNS_USE_SANDBOX`). Xcode-signed dev builds need `=1`; TestFlight needs `=0`.
- **Push arrives but no photo:** the extension couldn't reach the snapshot URL —
  check the app's Nodes-tab address is reachable from the phone (over Tailscale
  when remote), and that the App Group id matches on both targets.
- **`didFailToRegisterForRemoteNotifications`:** the Push Notifications capability
  or provisioning profile isn't set on the app target — revisit Step 3.2.
- **Nothing in `devices.json`:** the phone never registered — check the app has
  notification permission (Settings → Leofric → Notifications) and was built to a
  **physical device** (the Simulator cannot obtain an APNs token).
