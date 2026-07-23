# RESURRECTION.md — picking Leofric back up, years later

Written 2026-07-23, when the project was deliberately shelved (see README —
condo constraints, not technical failure). This document assumes: **you
remember nothing, the original Pi may be gone, and you now have a property
with multiple points worth watching.** Follow it top to bottom.

A Claude (or successor) session pointed at this repo should read `CLAUDE.md`
first — it's the working memory for AI-assisted sessions. This file is the
human runbook.

---

## 0. What to back up BEFORE decommissioning old hardware

These are gitignored and exist only on the machines. If the machines are
already wiped, section 5 explains what's rebuildable (everything, with
varying effort).

| Artifact | Where it lives | Why it matters |
|---|---|---|
| Pi `.env` | `~/leofric/.env` on the Pi | Supabase URL + service_role key, tuning overrides |
| `known_faces.npz` | `~/leofric/data/` on the Pi | Enrolled face embeddings (rebuildable by re-enrolling people) |
| Mac `.env` | `~/leofric-brain/.env` | Supabase creds + APNs key config |
| APNs `.p8` key | wherever `APNS_KEY_PATH` points on the Mac | Apple push auth key (re-issuable in the Apple dev portal) |
| `devices.json` | `~/leofric-brain/` | Registered iPhone push tokens (rebuilt automatically when the app runs) |
| Snapshots | `~/leofric-brain/snapshots/` | Historical alert photos — keep only if you care |

The Supabase project itself lives in Supabase's cloud — but **do not count on
it surviving the years**: the free tier pauses inactive projects and deletes
them after extended inactivity. That's fine — the history is expendable, and
the full schema needed to recreate the tables in a fresh project is recorded
in **[SUPABASE_SCHEMA.md](SUPABASE_SCHEMA.md)** (captured from the live DB at
shelving time).

## 1. Provision a fresh Pi node (repeat per node)

Hardware assumed: Pi 5 (8GB), a UVC webcam (was: Logitech BRIO), a USB mic
array (was: ReSpeaker 4-mic). Different peripherals are fine — everything is
addressed generically (`/dev/video0`, ALSA card index).

1. Flash Raspberry Pi OS (64-bit) with the imager; enable SSH. If SSH gives
   trouble, `docs/PI_IMAGER_SSH_FIX.md` was the fix last time.
2. ```bash
   sudo apt update && sudo apt install -y git python3-venv python3-dev portaudio19-dev
   git clone https://github.com/danefroelicher2/Leofric.git ~/leofric
   cd ~/leofric && python3 -m venv venv && venv/bin/pip install -r requirements.txt
   ```
   **⚠️ The #1 historical time sink:** Python-version wheel availability on
   aarch64. Before fighting any install error, check the library has wheels
   for the OS image's Python (`pip index versions <pkg>` or PyPI's JSON API).
   Four libraries were swapped for exactly this reason — `docs/DECISIONS.md`.
   A newer Python may re-break pins in `requirements.txt`; relax them
   deliberately, one at a time, running `tests/` as you go.
3. `venv/bin/python scripts/fetch_models.py` — downloads the vision models
   (MobileNet-SSD, YuNet, SFace) into `data/models/`.
4. `cp .env.example .env` and fill it in (Supabase creds; per-node
   `NODE_ID`/`NODE_ROLE` — see section 4).
5. Verify hardware: `scripts/` has the hardware check; camera should appear
   at `/dev/video0`, mic via `arecord -l` (set `MIC_CARD` accordingly).
6. Enroll faces (each household member, at the node's REAL mounting position
   and lighting — desk-distance enrollment degraded at range last time).
   Enrollment writes `data/known_faces.npz`; restore a backup instead if you
   have one and the camera is similar.
7. Install the service:
   ```bash
   sudo cp deploy/leofric.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now leofric
   journalctl -u leofric -f   # watch it come up
   ```
8. Reliability hardening that was already learned the hard way (do all
   three): official 27W PSU only; persistent journald
   (`Storage=persistent` in journald.conf); hardware watchdog enabled.
   History: a PMIC latch-off took the node down silently in Jul 2026.

## 2. Stand up the Mac brain

Any always-on Mac (or honestly any always-on box; the code is portable
Python — only the LaunchAgent bits are macOS-specific).

1. Install [Ollama](https://ollama.com), `ollama pull llama3.2` (or the era's
   equivalent small model; set `LEOFRIC_MODEL`).
2. ```bash
   mkdir -p ~/leofric-brain && cd ~/leofric-brain
   python3 -m venv venv
   venv/bin/pip install -r <repo>/macmini/requirements.txt
   cp <repo>/macmini/server.py <repo>/macmini/notify.py <repo>/macmini/apns.py .
   cp <repo>/macmini/.env.example .env   # then fill in
   ```
3. Run it under launchd so it survives reboots: the agent used was
   `~/Library/LaunchAgents/com.leofric.brain.plist` running
   `~/leofric-brain/venv/bin/python3 ~/leofric-brain/server.py` with stdout →
   `server.log` (add rotation; it grew to 377MB once). `docs/MACDOCS.md` has
   the original setup detail.
4. **Deploy model:** the brain is a *copy*, not a checkout. Mac server
   changes always flow repo → `cp` → kill the listener (launchd restarts it).
   Rationale and commands in `CLAUDE.md`.
5. Gotchas already paid for (details in the README highlights + specs):
   serve with waitress, never the Werkzeug dev server (no keep-alive); never
   write timer-paced polling loops in a LaunchAgent (macOS coalesces
   background timers ~2.3×) — the feed is event-driven for this reason.

## 3. The iOS app

`ios/LeofricApp/` — SwiftUI, XcodeGen, zero third-party dependencies.

1. `xcodegen generate` in `ios/LeofricApp/`, open the `.xcodeproj`, build to
   a physical iPhone. `DEVELOPMENT_TEAM` is pinned in `project.yml` — change
   it if the Apple account changed.
2. In the app's Nodes tab set the brain address. Use the Mac's **Tailscale
   MagicDNS name** (`http://<mac>.<tailnet>.ts.net:5000`) — one address that
   works at home and away. ATS already allows `*.ts.net` over HTTP (safe:
   WireGuard encrypts the tailnet).
3. Push notifications need the `.p8` APNs key + physical device:
   `docs/PHASE_2E_SETUP.md` is the complete runbook. **Note: real APNs
   delivery was never live-tested before shelving** — budget an hour for
   Stage C/D of that doc.
4. Remote access: Tailscale on the Mac and phone, same tailnet. The failure
   mode that actually happened: Mac Tailscale silently stopped → app spins.
   `tailscale status` on the Mac is the first diagnostic, always.

## 4. Going multi-node (the reason you're back)

The system is already multi-node; there is no migration, only addition:

- Each node: section 1 with a unique `NODE_ID` (e.g. `front-door`,
  `driveway`, `garage`) and a `NODE_ROLE` (`security` nodes trigger
  snapshots/pushes; other roles just stream + log).
- The brain needs zero config per node — nodes announce themselves by
  pushing frames/events; `/nodes` lists them; the app's node picker appears
  automatically at 2+.
- Per-node siting checklist (learned at the desk, never field-tested):
  WiFi throughput at the mount point (the stream wants ~1.3 MB/s sustained),
  power without extension-cord jank, camera field of view + backlight +
  night lighting (the BRIO has no IR), and re-tuned `MOTION_MIN_AREA` /
  detection thresholds per scene — all env-overridable per node.

## 5. Where development actually stopped

So future-you starts at the real frontier instead of rediscovering it:

- **Phase 2 complete and live-verified** (app, feed, chats, alerts, remote).
- **Not done:** real APNs push delivery test (Stage C/D of PHASE_2E_SETUP);
  smart/debounced alerting — `EVENT_LOGGING_ENABLED=0` is set in the Pi's
  `.env` *on purpose* because continuous presence spammed one event every few
  seconds. **Building debounced "presence session" alerting is the first
  Phase 3 task** (`docs/ROADMAP.md`), then flip the flag back on.
- **Deferred design, already written:** Mac-side H.264/LL-HLS transcode for
  smooth cellular viewing ("Approach B" in the 2026-07-23 live-feed spec).
- **Small TODOs:** custom "hey Leofric" wake word (drop `hey_leofric.onnx`
  into `data/models/` — code auto-detects it); minor app UX polish notes in
  ROADMAP 2D/2E.

## 6. Sanity checklist when it's all up

- Pi: `systemctl status leofric` active; journal shows "Streamer online →
  … (15.0 fps)" and "Streaming to the Mac."
- Mac: `curl localhost:5000/` → `{"status":"ok"}`; `curl localhost:5000/nodes`
  lists every node online; `/feed?node=<id>` streams.
- App: live feed moves like video (~15fps), node picker shows all nodes,
  chat answers, and (after Stage C) a test event pushes a photo notification.
- Pi load: was ~3.2/4.0 with one node's full pipeline — watch it if the
  vision loop grows.
