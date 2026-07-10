# Leofric — Mac Mini Brain: Status

**Machine:** `Danes-Mac-mini-3.local` · **Last full verification: 2026-07-10** (on the Mac itself)
**Where we are:** Phase 1 COMPLETE. The brain is healthy, verified end-to-end from the Pi,
and the cold-boot prerequisites are in place. Two items remain before the Mac is declared
bulletproof: the reboot test and Ollama keep-alive (details below). Next build phase: 2A
(expand the Mac API for the iOS app).

---

## Address

- **Canonical address (what the Pi uses):** `http://Danes-Mac-mini-3.local:5000` —
  verified from the Pi on 2026-07-10 (ping 9ms, health JSON returned). The Pi's `.env`
  sets `MAC_MINI_URL` to this hostname, and it is now also the default in `config.py`.
- **Current IP:** `192.168.1.19` (Wi-Fi `en1`, MAC `14:98:77:44:72:81`). DHCP-assigned,
  **not reserved** (Nighthawk router exposes no reservation UI) — which is fine, because
  the hostname is the drift-proof path. All stale `192.168.1.46` references were purged
  from the repo (commit `cb8a696`).

## Verification results (runbook Steps 1–4, run 2026-07-10)

- Health: `curl localhost:5000/` → `{"model":"llama3.2","service":"leofric-brain","status":"ok"}` ✅
- Chat: `{"message":"say hello in exactly three words"}` → `{"response":"Good day here"}` ✅
- From the Pi by hostname: `curl http://Danes-Mac-mini-3.local:5000/` → health JSON ✅
- Binding: `Python *:5000` (0.0.0.0, LAN-reachable) ✅
- Deployment drift: `~/leofric-brain/server.py` is **identical** to repo `macmini/server.py` ✅
- venv: Flask 3.1.3 + requests 2.32.5 present ✅
- Ollama: `llama3.2:latest` pulled, serving on 11434 ✅
- Crash recovery: kill-tested previously; launchd relaunched the brain in ~2s ✅

## Cold-boot readiness (runbook Step 4)

- **FileVault: OFF** and **auto-login: ON** (`danefroelicher`) — the recommended
  appliance configuration is **already in place**. Per-user LaunchAgents will fire
  after an unattended reboot.
- ✅ **REBOOT TEST PASSED (2026-07-10).** `sudo reboot`, nobody touched the Mac.
  Within ~2 minutes, verified from the Pi by hostname:
  - `curl http://Danes-Mac-mini-3.local:5000/` →
    `{"model":"llama3.2","service":"leofric-brain","status":"ok"}`
  - `POST /chat {"message":"who are you?"}` → `{"response":"I am Leofric, your home
    intelligence assistant. ..."}`
  - `ollama ps` after first chat → `llama3.2 ... 100% GPU ... UNTIL Forever`
    (per-request keep-alive survives reboot, as designed).
  - All other live jobs (fbscalper, clawdbot) auto-restarted; `pmset` settings
    (`sleep 0 disksleep 0 womp 1`) persisted.
  **The brain self-heals from a cold boot. Hardening is complete.**

## Ollama keep-alive (runbook Step 5) — DONE 2026-07-10 ✅

Implemented **per-request** instead of only via env var (deliberate deviation from the
runbook): `server.py` now sends `"keep_alive": -1` in every Ollama request, so the
model stays resident **no matter which Ollama launch mechanism owns port 11434**.
Verified: `ollama ps` → `llama3.2:latest ... 100% GPU ... UNTIL Forever` (~2.5 GB RAM,
intended). The env var was also added to `com.ollama.server.plist` as backup.

Background: **two Ollama startup mechanisms** coexist — the menu-bar app (currently
serving 11434) and the `com.ollama.server` LaunchAgent (fail-looping on the taken
port). Left intentionally: with per-request keep-alive both behave identically, and
the retrying agent acts as a hot-standby that grabs the port if the app ever dies.

## Sleep / power

`pmset -g custom` (AC): `sleep 0`, `womp 1`, `displaysleep 0` ✅. `disksleep` is `10`
not `0` — needs an interactive sudo (**[DANE]**: `sudo pmset -c sleep 0 disksleep 0 womp 1`).
Low risk either way on this hardware.

## Firewall

macOS Application Firewall **disabled** — nothing blocks port 5000. Leave as-is on the
trusted home LAN. If ever enabled, allow `~/leofric-brain/venv/bin/python3` incoming.

## Shared machine — jobs to protect

This Mac is not Leofric-only. Live user LaunchAgents: `com.dane.fbscalper` (live job —
do not disrupt without telling Dane), `com.clawdbot.gateway` (localhost:18789–18792),
`com.mercia.server` (currently crash-looping, exit 78 — unrelated to Leofric, flagged
to Dane). None conflict with Leofric's ports (5000, 11434).

## Related Pi-side reliability work (2026-07-10)

Recorded here because the Mac is the ops vantage point (Mac has SSH key to the Pi):

- **Outage root-caused:** the Pi died 2026-07-09 15:27:44 mid-write — PMIC latch-off
  from a power sag (solid red LED, power present, SoC off; required physical replug).
  Electrical, not software/thermal. PSU is the official 27W (5A negotiated).
- **Fixes applied & verified on the Pi:** journald made persistent (was RAM-only —
  crash evidence had been self-erasing), hardware watchdog enabled (15s), bootloader
  EEPROM updated Nov 2025 → May 2026, clean reboot verified, `leofric.service`
  auto-started and reached this Mac's brain.
- **Cooling:** Armor Lite V5 active cooler installed 2026-07-10 — detected on the PWM
  fan header, firmware-controlled (off <50°C; steps at 50/60/67.5/75°C). Pi runs
  ~51–55°C under full vision load, zero throttling. Power cost negligible (<1W fan,
  ~2.7W board core rails measured).
- **Residual risk:** a future PMIC latch-off cannot be fixed in software (the SoC is
  powered off). Recommended: smart plug on the Pi's PSU for remote power-cycling
  and/or a small UPS. **[DANE]** decide.

## Remaining checklist before "bulletproof"

1. ~~Reboot test~~ **PASSED 2026-07-10** — headless cold-boot recovery proven.
2. ~~Ollama keep-alive~~ **DONE** — per-request `keep_alive:-1`, verified `UNTIL Forever`.
3. ~~disksleep 0~~ **DONE** — `pmset` now `sleep 0 disksleep 0 womp 1`, survives reboot.
4. Optional hardware: smart plug / UPS for the Pi (**[DANE]**, whenever).

**Hardening is COMPLETE. The Mac is ready for Phase 2A (API expansion for the iOS app).**
