# Leofric — Raspberry Pi Setup Log

## Session: 2026-06-12

### Goal
Flash a fresh 128GB SD card with Raspberry Pi OS Lite 64-bit and get SSH working on the Pi 5 8GB so development can begin.

---

## Hardware

- Raspberry Pi 5 8GB
- 128GB microSD card
- No monitor, no keyboard — headless SSH only
- WiFi only — no Ethernet cable available
- Development machine: Windows 11 PC with Windows Terminal
- Pi Imager v2.0.7

---

## What We Did

### 1. Flashed the SD Card
Used Raspberry Pi Imager v2.0.7 on Windows.

- Device: Raspberry Pi 5
- OS: Raspberry Pi OS Lite (64-bit)
- Storage: 128GB microSD

Discovered that Pi Imager's OS customization (the step that generates `firstrun.sh` on the boot partition) was consistently not applying on this machine across 5+ flash attempts. The boot partition would have all expected Pi OS files but no `firstrun.sh`, meaning no user account, no SSH config, and no WiFi config were ever written.

### 2. Manual Boot Partition Fix

Since Imager's customization was broken, we fixed the boot partition manually.

**Files written to the boot partition (D:\ when mounted on Windows):**

**`userconf.txt`** — Creates the `dane` user on first boot. Content:
```
dane:$6$rounds=656000$5vq.LNZxjV2EjzoA$o7UgyoFnODGH36TeSOERaA9nXSAACfJWHnJQr8/KR2Tzq3hbWYELW0XB835kfMor9rUxL6LzYkHjWyuTZ8B/x/
```
This is the SHA-512 hashed version of the password chosen during setup. The `userconf.txt` mechanism is built into Pi OS and runs independently of `firstrun.sh`.

**`firstrun.sh`** — Written manually using `setup_sdcard.py`. Configured:
- Hostname: `leofric`
- SSH: enabled
- WiFi: NetworkManager keyfile for `LacasaFroelicher-5G` (may need to be corrected — see Known Issues)
- Timezone: `America/New_York`

**`cmdline.txt`** — Modified by `setup_sdcard.py` to append:
```
systemd.run=/boot/firmware/firstrun.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target
```
This tells Pi OS to execute `firstrun.sh` on the very first boot, then reboot.

### 3. Where Things Stand

The Pi boots and is reachable on the network via IPv6 link-local:
```
fe80::8aa2:9eff:fe09:2d1e%12
```
mDNS resolves: `ping leofric.local` responds.

However, SSH fails with:
```
kex_exchange_identification: Connection closed by remote host
```

**Root cause:** The `systemd.unit=kernel-command-line.target` directive boots the Pi into a limited systemd target. In this state, SSH host keys are never generated. The SSH daemon starts but immediately closes connections because it has no host keys to present. The Pi appears to be stuck in this limited boot state rather than completing the firstrun cycle and rebooting into a normal boot.

---

## What To Do Next Session

### Step 1 — Fix the Boot Partition

Pull the SD card, mount as D: on Windows, run:
```powershell
python C:\Users\danef\Downloads\Programming\Current\Leofric\fix_sdcard.py
```

This script:
- Deletes `firstrun.sh` from the boot partition
- Strips the `systemd.run` directives from `cmdline.txt`

This allows the Pi to do a full normal boot where SSH host keys are generated and `userconf.txt` creates the `dane` user.

### Step 2 — Boot and SSH In

Eject card, insert into Pi, power on. Wait 2 minutes, then:
```powershell
ssh dane@leofric.local
```

Enter the password set during `userconf.txt` generation.

### Step 3 — Configure WiFi (if needed)

If SSH works but the Pi has no WiFi (check with `ip a` inside the Pi), configure it manually:
```bash
sudo nmcli dev wifi connect "SSID_HERE" password "PASSWORD_HERE"
```

**Known issue:** The SSID `LacasaFroelicher-5G` may be incorrect. The 2.4GHz network may be the right one. Check available networks with:
```bash
sudo nmcli dev wifi list
```

### Step 4 — System Updates

Once SSHed in:
```bash
sudo apt update && sudo apt upgrade -y
```

### Step 5 — Begin Leofric Software Setup

Phase One core loop:
- Camera pipeline (OpenCV)
- Motion detection
- Person detection (lightweight model on Pi)
- Wake word detection (Porcupine / Picovoice)
- Audio transcription (Whisper or similar, local on Pi)
- Communication with Mac Mini Flask API at 192.168.1.46:5000

---

## Files in This Repo

| File | Purpose |
|---|---|
| `PROJECT_SPEC.md` | Full system specification — hardware, phases, architecture |
| `BUILDER_PROFILE.md` | Who is building this and why |
| `setup_sdcard.py` | Wrote `firstrun.sh` and updated `cmdline.txt` on boot partition |
| `fix_sdcard.py` | Clears the stuck boot loop — run before next boot attempt |
| `PI_SETUP_LOG.md` | This file |

---

## Known Issues

| Issue | Status | Fix |
|---|---|---|
| Pi Imager customization not generating `firstrun.sh` | Worked around manually | `setup_sdcard.py` does what Imager should have |
| SSH closes during key exchange | Fix ready | Run `fix_sdcard.py`, boot normally |
| WiFi SSID may be wrong (`LacasaFroelicher-5G` vs 2.4GHz name) | Unverified | Fix with `nmcli` once SSHed in |
| WiFi not configured if firstrun.sh didn't complete | Possible | Fix with `nmcli` once SSHed in via link-local |

---

## Mac Mini Context

Do not touch the Mac Mini setup. It is already configured:
- IP: `192.168.1.46`
- Flask API: port 5000, auto-starts on boot
- Ollama: Llama 3.2 installed, auto-starts on boot

The Pi will communicate with the Mac Mini once the core pipeline is running.
