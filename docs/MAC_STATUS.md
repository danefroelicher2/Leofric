# Leofric — Mac Mini Brain: Status (Phase 1J)

**Machine:** `Danes-Mac-mini-3.local`

## Final Mac IP

`192.168.1.19` — DHCP-assigned (Wi-Fi, interface `en1`, MAC `14:98:77:44:72:81`).

**Deviation:** the spec asked for a router-side DHCP reservation (or manual static
IP) so the address stops drifting. That reservation was **not** completed — the
owner's Nighthawk router only exposes the Mac Mini under "devices online," not a
reservation UI they could use, so we recorded the current IP as-is instead. If
this address changes again, update the Pi's `MAC_MINI_URL` accordingly.

## Model

`llama3.2:latest` (3.2B params, Q4_K_M quantization) — already pulled and running
under Ollama 0.30.5 before this session started.

## API contract confirmation

Both routes served exactly as specified in section 2, verified twice: once
locally on the Mac, and again from the Pi (`dane@leofric.local`) over the LAN.

**Health check**, from the Pi:
```
$ curl -v --max-time 5 http://192.168.1.19:5000/
< HTTP/1.1 200 OK
< Server: Werkzeug/3.1.8 Python/3.9.6
< Content-Type: application/json
{"model":"llama3.2","service":"leofric-brain","status":"ok"}
```

**Chat**, from the Pi:
```
$ curl -s -X POST http://192.168.1.19:5000/chat -H 'Content-Type: application/json' \
       -d '{"message":"who are you?"}'
{"response":"I am Leofric, your home's AI assistant. I monitor and control various
systems to ensure a comfortable living space. What would you like assistance with
today?"}
```
Conversation `history` was also exercised locally and correctly carried into the
Ollama request.

## Auto-start

Two LaunchAgents, both `RunAtLoad` + `KeepAlive`:

- `~/Library/LaunchAgents/com.ollama.server.plist` → `ollama serve`. Pre-existing
  from before this session; left untouched.
- `~/Library/LaunchAgents/com.leofric.brain.plist` → runs
  `~/leofric-brain/venv/bin/python3 ~/leofric-brain/server.py`, logs to
  `~/leofric-brain/server.log`. Created this session.

**Verified:** killed the brain server process (`kill -9`); launchd restarted it
within ~2 seconds and the health check passed again immediately after.
**Not verified:** an actual reboot test — the machine was not restarted during
this session. Recommend a manual reboot test before treating Phase 1J as fully
closed.

## Sleep

`pmset -g custom` (AC Power): `sleep 0`, `womp 1` — both already configured
before this session (not something we had to change). The Mac will not sleep on
AC power and can be woken over the network.

**Deviation:** `disksleep` is `10`, not `0` as the spec's suggested command sets.
Running `sudo pmset -c sleep 0 disksleep 0 womp 1` requires an interactive sudo
password prompt that couldn't be supplied non-interactively this session — left
as a follow-up if disk spin-down ever becomes an issue (unlikely to affect
network reachability on this hardware, but flagging per spec).

## Firewall

macOS Application Firewall is **disabled** (`State = 0`). No allow-rule for
`python3`/`:5000` was needed as a result. If the firewall is ever turned on,
allow incoming connections for the venv's `python3` binary
(`~/leofric-brain/venv/bin/python3`).

## Other notes / deviations

- SSH from the Mac Mini to the Pi was not previously trusted. Generated a new
  ed25519 keypair on the Mac (`~/.ssh/id_ed25519`) and installed it in the Pi's
  `~/.ssh/authorized_keys` via `ssh-copy-id`, so future sessions can reach the Pi
  directly from the Mac for testing. This is unrelated to the brain server itself
  but was needed to run the LAN-side verification in section 6 of the spec.
- No other deviations from `server.py` in section 4 — copied verbatim from
  `macmini/server.py` in the repo.
