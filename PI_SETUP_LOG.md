# Leofric — Raspberry Pi Setup Log

## Current Status: BLOCKED — Waiting on Hardware

SSH host keys do not exist on the Pi. A **CP2102 USB-to-TTL serial adapter** has been ordered.
When it arrives, follow the **Pickup Instructions** section at the bottom of this file.

---

## Hardware

- Raspberry Pi 5 8GB
- 128GB microSD card
- No monitor, no keyboard — headless SSH only
- WiFi only — no Ethernet
- Development machine: Windows 11 PC
- Pi Imager v2.0.7

---

## What Is Actually On The Pi Right Now

The Pi boots successfully and is on the network. Everything below is confirmed working:

- **Hostname:** `leofric` (responds to `leofric.local` via mDNS)
- **User:** `dane` created via `userconf.txt` on the boot partition
- **WiFi:** Connected — Pi is reachable at `fe80::8aa2:9eff:fe09:2d1e%12` (IPv6 link-local)
- **SSH daemon:** Running and listening on port 22
- **SSH host keys:** DO NOT EXIST — this is the only remaining problem

The Pi is one command away from being fully working.

---

## Root Cause

Pi Imager v2.0.7 failed to generate `firstrun.sh` on the boot partition across 5+ flash attempts
on this Windows machine. This is either a version issue (2.0.7 predates Pi 5 Bookworm support)
or a Windows permissions issue.

`firstrun.sh` is the script that Pi OS uses on first boot to:
- Create the user account
- Enable SSH
- **Generate SSH host keys** ← this is the step that never happened

We manually wrote a `firstrun.sh` that enabled SSH and configured WiFi, but missed the SSH host
key generation step. Everything else on the Pi is configured. Only the host keys are missing.

---

## Everything We Tried (And Why It Failed)

### Attempt 1 — Manual firstrun.sh via setup_sdcard.py
Wrote `firstrun.sh` and `userconf.txt` to the boot partition manually. Also modified `cmdline.txt`
with `systemd.run=/boot/firmware/firstrun.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target`.

**Result:** WiFi and hostname configured (firstrun.sh ran), but SSH host keys were never generated
because our script called `systemctl enable ssh` but not `ssh-keygen -A`. The Pi got stuck in
the limited `kernel-command-line.target` boot state.

### Attempt 2 — fix_sdcard.py
Removed `firstrun.sh` and stripped `systemd.run` directives from `cmdline.txt` to escape the
stuck boot loop.

**Result:** Pi now boots normally but SSH still has no host keys.

### Attempt 3 — fix_ssh_keys.py (systemd.run without kernel-command-line.target)
Wrote `fix_ssh.sh` to the boot partition containing `ssh-keygen -A` and added
`systemd.run=/boot/firmware/fix_ssh.sh` to `cmdline.txt` (without `kernel-command-line.target`).

**Result:** Script never ran. Confirmed by checking that `fix_ssh.sh` was still present on
the boot partition after booting. `systemd.run` without `kernel-command-line.target` is
ignored on Pi OS Bookworm.

### Attempt 4 — WSL mount of ext4 partition
Tried `wsl --mount \\.\PHYSICALDRIVE1 --partition 2 --type ext4` to mount the Pi's root
partition in WSL and write SSH host keys directly to `/etc/ssh/`.

**Result:** Failed with `Error code: Wsl/Service/AttachDisk/MountDisk/HCS/0x8007000f`.
WSL2 cannot attach removable media (SD cards) to its Hyper-V VM. Known limitation.

### Attempt 5 — init= kernel parameter
Added `init=/boot/firmware/init_fix.sh` to `cmdline.txt`. This is supposed to replace PID 1
with our script.

**Result:** Wrong approach. The `init=` parameter looks for the file on the ext4 root
filesystem, not the FAT32 boot partition. `/boot/firmware/` is an empty mount point on ext4
until systemd mounts the FAT32 partition there — which hasn't happened yet when `init=` runs.
Script was never executed.

### Attempt 6 — cloud-init with seedfrom (first attempt)
Changed `ds=nocloud;i=rpi-imager-1781294579815` in `cmdline.txt` to
`ds=nocloud;seedfrom=/boot/firmware/;i=leofric-fix-03`. Wrote `user-data` and `meta-data`
to the boot partition with runcmd to generate SSH keys.

**Result:** Did not work. Unknown whether cloud-init is installed on Pi OS Lite, or whether
the seedfrom mechanism fires early enough in boot before `/boot/firmware` is mounted.

### Attempt 7 — firstrun.sh with kernel-command-line.target (corrected version)
Rewrote `firstrun.sh` to include `ssh-keygen -A` and added `systemd.unit=kernel-command-line.target`
back to `cmdline.txt`.

**Result:** Script still never ran. Confirmed `firstrun.sh` was still present on boot partition
after booting. **Key finding:** `systemd.run + kernel-command-line.target` does NOT work on
Pi OS Bookworm for Pi 5. This mechanism was removed or changed. Pi completely ignores these
cmdline parameters.

### Attempt 8 — cloud-init write_files with pre-generated keys
Generated SSH host keys on Windows, base64-encoded them, embedded them in cloud-init `user-data`
using the `write_files` module. This bypasses any key generation on the Pi — keys are just
written as file content.

**Result:** Still failed. Either cloud-init is not installed on Pi OS Lite, or the seedfrom
parameter is not being processed correctly.

---

## What We Know For Certain

| Fact | Confirmed |
|---|---|
| Pi boots and connects to WiFi | ✓ |
| `leofric.local` resolves via mDNS | ✓ |
| SSH daemon is running on port 22 | ✓ |
| SSH host keys do not exist | ✓ |
| `systemd.run` is ignored on Pi OS Bookworm | ✓ |
| WSL cannot mount SD cards | ✓ |
| `init=` looks on ext4, not FAT32 | ✓ |
| cloud-init seedfrom may not work / not installed | Likely |

---

## Current State of the SD Card

The boot partition (`/boot/firmware`, mounted as D: on Windows) currently has:

- `cmdline.txt` — contains `ds=nocloud;seedfrom=/boot/firmware/;i=leofric-final`
- `user-data` — cloud-init user-data with write_files (SSH keys, base64 encoded)
- `meta-data` — instance-id: leofric-final
- `userconf.txt` — creates `dane` user on boot

---

## Hardware Purchased

**HJHYUL CP2102 USB to TTL Serial Adapter**
- CP2102 chip (Windows drivers install automatically)
- 3.3V output (required — Pi GPIO is 3.3V)
- Includes jumper wires

---

## Pickup Instructions — Do This When The Adapter Arrives

### Step 1 — Install the CP2102 driver (if Windows doesn't auto-install)
Plug the adapter into your PC. Windows should auto-detect and install the CP2102 driver.
Open Device Manager and confirm a COM port appears under "Ports (COM & LPT)".
Note the COM number (e.g., COM3).

### Step 2 — Install PuTTY (if not already installed)
Download from putty.org. Standard install.

### Step 3 — Wire the adapter to the Pi GPIO header
Power the Pi OFF before wiring.

```
Pi GPIO Pin 8  (TXD) ──→ Adapter RX
Pi GPIO Pin 10 (RXD) ──→ Adapter TX
Pi GPIO Pin 6  (GND) ──→ Adapter GND
```

Pi 5 GPIO header pinout reference:
```
 [1]  [2]
 [3]  [4]
 [5]  [6] ← GND
 [7]  [8] ← TXD (GPIO 14)
 [9] [10] ← RXD (GPIO 15)
```
Pin 1 is nearest the USB ports on a Pi 5. Count down the left column: 1, 3, 5, 7, 9...
Count down the right column: 2, 4, 6, 8, 10...

### Step 4 — Open PuTTY
- Connection type: Serial
- Serial line: COM3 (or whatever your Device Manager shows)
- Speed: 115200
- Click Open

### Step 5 — Power on the Pi
The Pi boots. You should see boot messages in the PuTTY window followed by a login prompt.

### Step 6 — Log in
```
Username: dane
Password: (whatever you set when we ran setup_sdcard.py)
```

### Step 7 — Generate SSH host keys
```bash
sudo ssh-keygen -A
sudo systemctl restart ssh
```

### Step 8 — Verify SSH works from your PC
Open a new PowerShell window and run:
```powershell
ssh dane@leofric.local
```

SSH should connect and ask for your password. You are in.

### Step 9 — From here, begin Phase One
Once SSH is working, the Pi setup is complete and Phase One development can begin:
- Camera pipeline (OpenCV)
- Motion detection
- Person detection
- Wake word (Porcupine)
- Audio transcription (Whisper)
- Communication with Mac Mini Flask API at 192.168.1.46:5000

---

## Mac Mini Context (Do Not Touch)

- IP: `192.168.1.46`
- Flask API: port 5000, auto-starts on boot
- Ollama: Llama 3.2 installed, auto-starts on boot
- Both services are configured and running — do not rebuild
