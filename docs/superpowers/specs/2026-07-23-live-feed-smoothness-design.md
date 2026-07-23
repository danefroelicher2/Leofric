# Live feed smoothness — design (Approach A: tune the MJPEG pipeline)

Date: 2026-07-23 · Status: approved by Dane (conversation) · Approach chosen over
Mac-side H.264/HLS transcoding ("Approach B", deferred — see Decision record below).

## Problem

The Live tab plays at 4fps — a slideshow. The BRIO already captures 1280x720@30
on the Pi; the choppiness is `STREAM_FPS = 4` (Pi push rate) and `FEED_FPS = 4`
(Mac re-broadcast rate), chosen conservatively for MJPEG's bandwidth cost.

## Non-goals (explicit)

- No H.264/HLS/WebRTC. Real video compression is Approach B, deferred until
  we've lived with 15fps and judged whether remote/cellular viewing needs it.
- No iOS app changes. The MJPEG reader renders frames as they arrive.
- No change to the vision/identity pipeline — it reads the camera directly and
  is untouched. The only coupling is Pi CPU, which we measure (below).

## Changes

### 1. Pi — `config.py`
- `STREAM_FPS` default: `4` → `15`.
- `STREAM_JPEG_QUALITY` stays 70: these frames double as alert snapshots
  (`/snapshot/<id>` photos in push notifications), so quality is worth keeping.
- Deploy note: check the Pi's `.env` for a `STREAM_FPS` override that would
  silently defeat the new default.

### 2. Mac — `macmini/server.py`
- `FEED_FPS`: `4` → `15`.
- `_mjpeg_stream` gets send/skip logic: only yield when the ingested frame is
  NEW (its `at` timestamp changed), with a ~1s keepalive re-send of the last
  frame during quiet gaps. Rationale: at 15fps, blind re-broadcast wastes real
  bandwidth on the cellular leg whenever the Pi sends slower than the feed
  ticks; the keepalive keeps the app's 10s stall detector satisfied. The
  existing stale-stream cutoff (end stream after `NODE_ONLINE_WINDOW_SECONDS`)
  is unchanged.

### 3. iOS — nothing
No rebuild needed; the current build on Dane's phone benefits immediately.

## Testing & verification

- Unit test (macmini/test_server.py): the stream yields a fresh frame, skips
  an unchanged frame within the keepalive window, re-sends after the keepalive
  window, and still ends when frames go stale.
- Live verification after deploy:
  - measure delivered fps from `/feed` (count JPEG parts over ~5s of curl);
  - Pi CPU before/after (`top`/loadavg with streamer at 15fps) to confirm the
    detection pipeline keeps its headroom — the one real trade-off risk;
  - eyeball the Live tab on the phone.

## Rollback

Both rates are env-overridable (`STREAM_FPS` in the Pi's `.env`, `FEED_FPS` in
the Mac's `~/leofric-brain/.env`). If 15fps stutters on cellular or taxes the
Pi, dial back without a code revert.

## Implementation addendum (2026-07-23) — the config bump alone wasn't enough

Raising the rates delivered only ~6-9fps. Three deeper bottlenecks were found
(each measured, not guessed) and fixed:

1. **Werkzeug 3.x closes every connection** (keep-alive support was removed
   from the dev server), so each frame POST paid a fresh TCP handshake + mDNS
   lookup: ~50ms fixed overhead. Fix: serve with **waitress** (production
   WSGI, keep-alive, single-process; dev-server fallback if not installed).
   POST time dropped 58ms → 17.5ms. New Mac-brain dep: `waitress`.
2. **`requests` per-call overhead under GIL contention**: standalone, a frame
   POST took 17ms; inside the service — sharing the GIL with vision + audio
   inference — it stretched to ~100ms. Fix: the streamer now uses stdlib
   `http.client` over one persistent connection (a fraction of the Python
   bytecode per frame). Covered by new `tests/test_streamer.py` against a
   real local HTTP server, including server-restart recovery.
3. **macOS timer coalescing** stretched the feed generator's 66ms polling
   sleeps to ~150ms (the brain is a background LaunchAgent subject to timer
   throttling), capping /feed at 6fps while the Pi pushed 15. Fix: /feed is
   now **event-driven** — each ingest notifies a condition variable and
   waiting streams forward the frame immediately. `FEED_FPS` no longer
   exists; the feed forwards at whatever rate the node pushes.

**Measured result:** /feed delivers 14.9fps, median inter-frame gap 67ms
(max 86ms), locally and over Tailscale. Pi load ~2.9 → ~3.2 of 4.0 (~10% of
capacity for 3.75× the frame rate).

## Decision record — why A over B (Mac-side H.264/LL-HLS)

- A fixes the observed complaint (choppy everywhere, including at home) for
  ~an evening of work; B only improves the remote/cellular case and makes the
  at-home feed *worse* (2–5s latency vs near-instant MJPEG).
- Whether 15fps "feels live enough" is perceptual — A is the cheap experiment
  that decides if B is needed at all.
- B adds silent-failure surface on the remote path (ffmpeg process, second
  player path) — the exact category that caused the July trip outage.
- Nothing is wasted: B, if built, transcodes A's higher-fps ingest stream.
- Trigger to revisit B: remote/cellular viewing still disappoints after living
  with A, or watching-while-traveling becomes the primary usage.
