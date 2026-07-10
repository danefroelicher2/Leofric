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
- ⚠️ **Reboot test still NOT run.** This is the one remaining proof. Reason it was
  deferred: this Mac also runs live non-Leofric jobs (notably `com.dane.fbscalper`);
  all have RunAtLoad+KeepAlive and will auto-restart after a reboot, but Dane wants
  to schedule the reboot deliberately so he can check those jobs afterward.
  **[DANE]** run `sudo reboot`, wait ~90s without touching the Mac, then from the Pi:
  `curl -s http://Danes-Mac-mini-3.local:5000/` — expect the health JSON.

## Ollama keep-alive (runbook Step 5) — NOT DONE, known issue

`ollama ps` shows the model **unloads after idle**, so the first reply after a quiet
period takes several extra seconds while llama3.2 reloads.

Complication found: **two competing Ollama startup mechanisms** exist —
1. the Ollama **menu-bar app** (Electron, login item) — this is what actually serves
   port 11434 today;
2. the `com.ollama.server` LaunchAgent (`ollama serve`) — currently **failing on every
   retry (exit 1)** because the app already owns the port. Harmless but messy.

Fix plan (do together with the reboot test): pick ONE mechanism — recommend the
LaunchAgent with `OLLAMA_KEEP_ALIVE=-1` in its `EnvironmentVariables` and the menu-bar
app removed from login items — then reboot and confirm `ollama ps` keeps the model
resident (~2–3 GB RAM, intended).

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

1. **[DANE]** Reboot test (Section 10 of MACDOCS) — the final proof. Coordinate with
   fbscalper.
2. Ollama keep-alive + de-dupe the double startup (do with #1).
3. **[DANE]** `sudo pmset -c disksleep 0` (minor).
4. Optional hardware: smart plug / UPS for the Pi.

After #1–2 pass, the brain is done hardening and Phase 2A (API expansion for the iOS
app) can begin on this Mac.
