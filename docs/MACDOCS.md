# Leofric — Mac Mini Brain: Operations & Hardening Runbook

**You are Claude, working directly on the Mac Mini via its Terminal. Read this
entire document before doing anything, then work top-to-bottom.**

> ### Your job (read this twice)
> The brain is **already built and running**. You are **NOT** rebuilding it.
> Your job is to **verify** it is healthy, **harden** it so it survives reboots
> and runs unattended for weeks, **prove** that with a real reboot test, and then
> **write down** what you found. If any step is already done and passes its check,
> say so and move on — don't redo it.

This is the only context you have. Everything you need is in this file. Where a
step needs the human (Dane) — a GUI click, a `sudo` password, a physical reboot —
it is marked **[DANE]**. Everything else you can run yourself in Terminal.

**Golden rule:** never claim something works until you've run the check command
and seen the expected output. Evidence before assertions.

---

## 0. The 60-second picture of the whole system

Leofric is a local-first home-intelligence system. Three machines:

- **Raspberry Pi 5** (`leofric.local`, user `dane`) — the *senses*. Camera + mic.
  It detects motion/people/faces, listens for the wake word "Hey Jarvis,"
  transcribes what you say, and logs events to Supabase (cloud). It runs 24/7 as a
  systemd service and already survives its own reboots.
- **This Mac Mini** (`Danes-Mac-mini-3.local`) — the *brain*. A tiny Flask web
  server on port 5000 wraps a local LLM (Ollama running Llama 3.2). The Pi sends it
  transcribed text over the home WiFi; it thinks and returns a text reply.
- **iPhone app** — the *face*. Not built yet (that's the next phase). Leofric never
  speaks out loud — it answers through text in the app. That's intentional.

**Your machine (the Mac) is the brain.** If the Mac is asleep, unreachable, or the
brain server isn't running, the Pi hears you but has nothing to answer with. So the
Mac's job is simple and absolute: **be awake, be reachable, and have the brain
running — always, including after a power blip when nobody is around.**

---

## 1. What we *believe* is already true (VERIFY — do not trust this table)

This is the state recorded at the end of the last Mac session. Treat every row as a
claim to check, not a fact to rely on. You will verify each below.

| Thing | Believed value |
|---|---|
| Hostname | `Danes-Mac-mini-3.local` |
| IP address | `192.168.1.19` — DHCP-assigned, **drifts over time** (no router reservation possible) |
| LLM | Ollama `llama3.2:latest` (3.2B, Q4_K_M), Ollama ~0.30.5 |
| Brain server | `~/leofric-brain/server.py`, Python venv at `~/leofric-brain/venv`, binds `0.0.0.0:5000` |
| Auto-start | 2 LaunchAgents: `~/Library/LaunchAgents/com.ollama.server.plist` (ollama) + `com.leofric.brain.plist` (Flask), both `RunAtLoad` + `KeepAlive` |
| Crash recovery | **Tested** — killed the server, launchd restarted it in ~2s |
| **Reboot recovery** | **NEVER TESTED** ← this is the #1 risk you are here to close |
| Sleep | `pmset` on AC: `sleep 0`, `womp 1` (wake-on-network). `disksleep 10` (should be 0) |
| Firewall | macOS Application Firewall **disabled** (so nothing blocks port 5000) |
| SSH to the Pi | The Mac has an ed25519 key installed on the Pi — you can `ssh dane@leofric.local` |

**Why the IP drift doesn't matter:** the Pi is configured to reach the Mac by its
**hostname** `Danes-Mac-mini-3.local`, which always resolves to this machine no
matter what IP DHCP hands out. Do **not** try to "fix" this by hardcoding an IP
anywhere — the hostname is the drift-proof solution and it's already in place.

---

## 2. Step 0 — Connect to GitHub and get your bearings

You need the repo on this Mac for two reasons: to read this doc from source and to
diff the running server against the canonical copy. The repo is **private**
(`github.com/danefroelicher2/Leofric`).

```bash
# Do you already have it? The repo may already be cloned.
ls ~/leofric 2>/dev/null && echo "repo present" || echo "need to clone"

# If you need to clone — SSH (preferred) or gh CLI. This is private, so auth is required.
# Option A (SSH key already set up on this Mac):
git clone git@github.com:danefroelicher2/Leofric.git ~/leofric
# Option B (GitHub CLI):
gh auth status || gh auth login      # [DANE] may need to complete a browser login
gh repo clone danefroelicher2/Leofric ~/leofric

# Once present, always start from a clean pull:
cd ~/leofric && git pull
```

**Critical distinction — two different folders, do not confuse them:**
- `~/leofric` = the **git repo** (docs + reference code). Read-only reference here.
- `~/leofric-brain` = the **running deployment** (the actual server + venv that
  serves port 5000). This is what's live.

You edit/verify the running thing in `~/leofric-brain`; you read docs and the
canonical `macmini/server.py` in `~/leofric`.

---

## 3. Step 1 — Verify the brain is alive right now

Run these in order. Each shows what you should see.

```bash
# 3a. Ollama is installed and the model is present:
ollama --version                 # expect a version string, e.g. 0.30.x
ollama list                      # expect a row for llama3.2 (e.g. "llama3.2:latest")

# 3b. Ollama is actually serving:
curl -s http://localhost:11434/api/tags | head -c 200 ; echo   # expect JSON listing models

# 3c. The brain health check (this is the exact contract the Pi depends on):
curl -s http://localhost:5000/ ; echo
# EXPECT exactly:
# {"model":"llama3.2","service":"leofric-brain","status":"ok"}

# 3d. The brain actually thinks:
curl -s -X POST http://localhost:5000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"say hello in exactly three words"}' ; echo
# EXPECT: {"response":"...three-ish words..."} with real model text.
```

**If 3c/3d fail** (connection refused, error JSON): the brain server isn't running
or Ollama is down. Skip to **Troubleshooting** (Section 12), fix it, then come back.

---

## 4. Step 2 — Verify the running deployment matches the repo

We want the live server to be exactly the canonical code — no silent drift.

```bash
# 4a. The running server file exists:
ls -l ~/leofric-brain/server.py

# 4b. It matches the repo's canonical copy (no output = identical):
diff ~/leofric-brain/server.py ~/leofric/macmini/server.py \
  && echo "IDENTICAL — good" \
  || echo "DIFFERENT — investigate before proceeding"

# 4c. The venv has what it needs:
~/leofric-brain/venv/bin/pip list | grep -Ei 'flask|requests'   # expect both present

# 4d. Confirm what's actually listening on :5000 and that it's bound to 0.0.0.0
#     (not just 127.0.0.1 — it MUST be reachable from the Pi):
lsof -iTCP:5000 -sTCP:LISTEN -n -P
# EXPECT a python process listening on *:5000 (the * / 0.0.0.0 matters).
```

If 4b reports DIFFERENT, read both files and reconcile — the Pi is written against
the repo contract (Section 11). Do not change the routes or JSON shapes.

---

## 5. Step 3 — Verify crash recovery (KeepAlive)

The brain should relaunch itself within seconds if it ever dies.

```bash
# 5a. Look at both LaunchAgents. Confirm RunAtLoad + KeepAlive are true and the
#     ProgramArguments point at the right paths.
cat ~/Library/LaunchAgents/com.leofric.brain.plist
cat ~/Library/LaunchAgents/com.ollama.server.plist

# 5b. Confirm launchd has them loaded:
launchctl list | grep -Ei 'leofric|ollama'   # expect a line for each

# 5c. Kill-test the brain and watch it come back:
BRAIN_PID=$(lsof -tiTCP:5000 -sTCP:LISTEN)
echo "brain pid = $BRAIN_PID"
kill -9 "$BRAIN_PID"
sleep 4
curl -s http://localhost:5000/ ; echo   # EXPECT the health JSON again — launchd relaunched it
```

If the health check does NOT come back after the kill, `KeepAlive` isn't working —
inspect the plist (Section 12) before continuing. Crash recovery is table stakes.

---

## 6. Step 4 — THE BIG ONE: make it start on a *cold boot* (fix the #1 vulnerability)

This is the single most important part of this whole document. **Read all of it
before acting.**

### The problem, in plain terms
The brain currently starts from a **per-user LaunchAgent** (`~/Library/LaunchAgents`).
Per-user agents only run **once a user is logged in and has a GUI session**. The
crash-recovery test in Step 5 passed because Dane *was* logged in at the time.

But a real reboot is different. If this Mac has **FileVault (disk encryption) ON**
and **auto-login OFF**, then after a reboot macOS sits at the password screen with
**no user session** — so the brain (and Ollama) **never start** until someone
physically types the password. That means: power blips at 3am → Mac reboots →
brain is dead until Dane comes home and logs in. That is exactly the "it didn't
work a week later" failure we're eliminating.

### Diagnose
```bash
# 6a. Is FileVault on?
fdesetup status            # "FileVault is On." or "FileVault is Off."

# 6b. Is auto-login configured? (prints a username if on; error/blank if off)
sudo defaults read /Library/Preferences/com.apple.loginwindow autoLoginUser 2>/dev/null \
  || echo "auto-login: OFF"
```

### Choose the fix (decision tree)

**Recommended path — simplest and keeps GPU acceleration:**
This Mac is a dedicated, physically-secured home server, not a traveling laptop, so
it's reasonable to run it like an appliance:

> **FileVault OFF + auto-login ON + the existing per-user LaunchAgents.**

With auto-login on, a full GUI user session exists moments after boot, so the
LaunchAgents fire automatically **and** Ollama keeps full Metal/GPU access (fast
replies). This is the standard way to run a headless Mac mini server.

- **[DANE]** Turn **off** FileVault: System Settings → Privacy & Security →
  FileVault → Turn Off. (Decryption may take a while in the background.)
- **[DANE]** Turn **on** auto-login: System Settings → Users & Groups → (unlock) →
  set "Automatically log in as" → `dane`, enter password.
  *(macOS will not allow auto-login while FileVault is on — that's why FileVault
  comes off first.)*

**Alternative path — if Dane wants to KEEP FileVault on:**
Then per-user agents can't run headless, so convert both services to **system
LaunchDaemons** in `/Library/LaunchDaemons`, which start at boot *before* any login.
Caveat: Ollama running before a GUI login may fall back to **CPU** (Metal GPU can
require a user session). Llama 3.2 (3B) on Apple-Silicon CPU is still usable, just
slower on the first tokens. Trade reliability-without-login for a bit of speed.

To convert (do for BOTH the brain and ollama), example for the brain:
```bash
# [DANE — needs sudo] Create a LaunchDaemon that runs as user 'dane' at boot.
sudo tee /Library/LaunchDaemons/com.leofric.brain.plist >/dev/null <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.leofric.brain</string>
  <key>UserName</key><string>dane</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/dane/leofric-brain/venv/bin/python3</string>
    <string>/Users/dane/leofric-brain/server.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/dane/leofric-brain/server.log</string>
  <key>StandardErrorPath</key><string>/Users/dane/leofric-brain/server.log</string>
</dict></plist>
PLIST
sudo chown root:wheel /Library/LaunchDaemons/com.leofric.brain.plist
sudo chmod 644 /Library/LaunchDaemons/com.leofric.brain.plist
# Remove the old per-user agent so they don't fight over port 5000:
launchctl unload -w ~/Library/LaunchAgents/com.leofric.brain.plist 2>/dev/null
mv ~/Library/LaunchAgents/com.leofric.brain.plist ~/Library/LaunchAgents/com.leofric.brain.plist.disabled
# Load the daemon:
sudo launchctl bootstrap system /Library/LaunchDaemons/com.leofric.brain.plist
```
Do the equivalent for Ollama (`ProgramArguments` = the full path to `ollama` +
`serve`; find it with `which ollama`). Then re-run the Step 1 health checks.

**Whichever path you choose, it is NOT proven until the reboot test in Step 8.**

---

## 7. Step 5 — Keep the model warm (so replies are fast even after days idle)

By default Ollama **unloads the model from memory after 5 minutes idle**. That means
the first "Hey Jarvis" after a quiet night makes Dane wait several seconds while the
model reloads. For a "walk up any time and it just answers" feel, keep it resident.

Set `OLLAMA_KEEP_ALIVE=-1` (keep loaded forever) in Ollama's environment. Add it to
whichever launch item runs `ollama serve` (the LaunchAgent `com.ollama.server.plist`,
or the LaunchDaemon if you converted). Add this block inside its `<dict>`:

```xml
<key>EnvironmentVariables</key>
<dict>
  <key>OLLAMA_KEEP_ALIVE</key><string>-1</string>
</dict>
```

Then reload that launch item (`launchctl unload -w <plist> && launchctl load -w <plist>`,
or `sudo launchctl bootstrap system ...` for a daemon) and confirm:

```bash
ollama ps    # after one /chat call, the model should stay listed (not expire)
```

Trade-off: keeps ~2–3 GB RAM occupied continuously. On this Mac that's fine and it's
exactly what you want for an always-ready assistant.

---

## 8. Step 6 — Power & sleep hardening

A sleeping Mac is an unreachable brain. Lock this down.

```bash
# 8a. See current settings:
pmset -g custom

# 8b. [DANE — needs sudo] Enforce: never sleep on AC, never disk-sleep, wake on network:
sudo pmset -c sleep 0 disksleep 0 womp 1

# 8c. Verify the change took (AC / "AC Power" block should show sleep 0, disksleep 0, womp 1):
pmset -g custom
```

Also, physically: keep the Mac on a **stable outlet** (ideally the same one, not a
switched power strip). A small UPS would make power blips a non-event, but that's
optional and not required to call this bulletproof.

---

## 9. Step 7 — Network reachability & hostname stability

The entire Pi↔Mac link rides on the hostname resolving over the LAN.

```bash
# 9a. Confirm this Mac's names:
scutil --get LocalHostName     # expect: Danes-Mac-mini-3   (this yields .local mDNS name)
scutil --get ComputerName

# 9b. Note the current IP (informational — the Pi uses the hostname, not this):
ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1

# 9c. THE REAL TEST — resolve the Mac *from the Pi* by hostname:
ssh dane@leofric.local 'ping -c 2 Danes-Mac-mini-3.local'
# EXPECT replies. If it resolves, the drift-proof link is confirmed.

# 9d. And the Pi can reach the brain by hostname:
ssh dane@leofric.local 'curl -s http://Danes-Mac-mini-3.local:5000/ ; echo'
# EXPECT the health JSON.
```

**Firewall:** it's currently disabled, so nothing blocks port 5000 — leave it as-is
for maximum reliability on a trusted home network. *If* Dane ever turns the macOS
firewall on, you must then explicitly allow incoming connections for the venv's
python binary (`~/leofric-brain/venv/bin/python3`) or the Pi will get
connection-refused. Note this; don't enable the firewall just to "be safe" — on a
trusted LAN it only adds a failure mode here.

**Optional belt-and-suspenders (only if hostname resolution ever proves flaky):**
set a manual static IP in System Settings → Network → Wi-Fi → Details → TCP/IP →
Configure IPv4: Manually — but choose an address **outside** the router's DHCP pool
to avoid collisions, and if you do, tell the Pi-side Claude so `MAC_MINI_URL` can be
updated. The hostname approach is preferred; don't do this unless needed.

---

## 10. Step 8 — THE REBOOT TEST (this is the proof; do not skip)

Everything above is theory until this passes. This proves the brain comes back with
**nobody touching the Mac**.

1. **[DANE]** From the Mac Terminal: `sudo reboot`
2. Wait ~90 seconds. **Do not log in manually** if you're testing the LaunchDaemon
   path (you want to prove it works headless). If you chose the recommended
   auto-login path, it will log itself in — that's expected and fine.
3. From **another machine** (e.g. SSH into the Pi from your laptop, or use the Pi
   directly), hit the brain by hostname:
   ```bash
   # from the Pi:
   curl -s http://Danes-Mac-mini-3.local:5000/ ; echo
   # EXPECT: {"model":"llama3.2","service":"leofric-brain","status":"ok"}
   curl -s -X POST http://Danes-Mac-mini-3.local:5000/chat \
     -H 'Content-Type: application/json' -d '{"message":"who are you?"}' ; echo
   # EXPECT: a short first-person reply as "Leofric".
   ```

- ✅ **If both answer** after the reboot with the Mac untouched → **the brain is
  bulletproof.** Record it (Section 13).
- ❌ **If they don't** → the cold-boot start isn't working. Go back to **Step 4**:
  either you still have FileVault-on + no auto-login (recommended path not applied),
  or the LaunchDaemon paths are wrong. Fix and reboot-test again. Do not declare
  victory until this passes.

---

## 11. Step 9 — Full-system end-to-end test (Mac + Pi together)

Close the loop the way a human actually uses it.

```bash
# 11a. Confirm the Pi's node service is up:
ssh dane@leofric.local 'systemctl is-active leofric'    # expect: active

# 11b. [DANE] Physically: stand in front of the Pi's camera, say
#      "Hey Jarvis, who are you". Then check the Pi's log for the round trip:
ssh dane@leofric.local 'journalctl -u leofric -n 30 --no-pager'
# EXPECT to see: wake word -> heard: <your words> -> leofric: <coherent reply>
```

**Ultimate test (optional but satisfying):** reboot BOTH machines
(`sudo reboot` on the Mac, `ssh dane@leofric.local 'sudo reboot'` on the Pi),
walk away for two minutes, come back, and do the "Hey Jarvis" test with nobody
having logged into anything. If it answers, the entire distributed system
self-heals from a total power loss. That's the bar.

---

## 12. Troubleshooting quick reference

**Brain unreachable from the Pi (`curl` connection refused / timeout):**
1. Is the Mac awake/on? `caffeinate -u -t 1` won't help remotely; check it's powered.
2. On the Mac: `curl -s http://localhost:5000/` — works locally but not from Pi?
   → binding or firewall. Confirm `lsof -iTCP:5000` shows `*:5000` (0.0.0.0), and
   the firewall is off (`/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate`).
3. Hostname won't resolve from the Pi? Confirm both are on the same WiFi/subnet and
   the router doesn't have "AP/client isolation" on. Temporary workaround: use the
   Mac's current IP (`ipconfig getifaddr en0`).

**Brain health fails locally (`curl localhost:5000` refused):**
- `launchctl list | grep leofric` — is it loaded? Check `~/leofric-brain/server.log`
  for a Python traceback. Common causes: venv missing flask/requests, or Ollama down.

**Ollama errors / `/chat` returns `ollama request failed`:**
- `ollama list` (model present?), `ollama ps` (loaded?), `curl localhost:11434/api/tags`.
- Restart: `launchctl unload/load` the ollama plist, or `ollama serve` manually to
  see errors.

**First reply after idle is very slow:** `OLLAMA_KEEP_ALIVE` isn't set — redo Step 5.

**After a reboot the brain is dead until login:** the cold-boot fix (Step 4) isn't in
effect — FileVault is still on without auto-login, or the LaunchDaemon is misconfigured.

---

## 13. The API contract — DO NOT CHANGE (reference)

The Pi's client is written against this exactly. Match it or the Pi breaks.

**`GET /`** → `{"status":"ok","service":"leofric-brain","model":"llama3.2"}`

**`POST /chat`** — body `{"message":"...","history":[{"role":"user","content":"..."},...]}`
(`history` may be empty) → `{"response":"..."}`. On error, non-200 with `{"error":"..."}`.

The canonical server code lives in the repo at `macmini/server.py` and should be
identical to `~/leofric-brain/server.py` (you verified this in Step 4). It listens on
`0.0.0.0:5000` and forwards to Ollama's `/api/chat` with a fixed Leofric system
prompt.

---

## 14. Report back — update `MAC_STATUS.md` and push

When you finish, rewrite `~/leofric/docs/MAC_STATUS.md` to reflect reality, then
commit and push so the Pi-side Claude sees the current truth. Record:

- **Cold-boot path chosen** (FileVault-off + auto-login, or LaunchDaemon) and why.
- **Reboot test result** — did the brain answer headless? Paste the `curl` outputs.
- **Keep-alive** — is `OLLAMA_KEEP_ALIVE=-1` set and confirmed via `ollama ps`?
- **Sleep** — paste the relevant `pmset -g custom` lines (sleep 0, disksleep 0, womp 1).
- **Firewall** — state (on/off) and any rule added.
- **Hostname/IP** — confirmed hostname resolves from the Pi; note the current IP.
- **Anything you changed or couldn't complete**, and the exact next step to finish it.

```bash
cd ~/leofric
git add docs/MAC_STATUS.md
git commit -m "Mac hardening: reboot-proof brain + keep-alive (verified)"
git push origin main
```

---

## 15. Out of scope for now (Phase 2 — do NOT build yet)

Later the Mac will also serve the iOS app: `GET /events`, `GET /feed` (MJPEG live
camera), `GET /conversations`, `GET /nodes`, plus push notifications. **Ignore these
for now.** This runbook is only about making the existing `/chat` brain unbreakable.
When mobile work begins, those endpoints get added here — but not until the brain is
proven bulletproof by the reboot test in Section 10.
