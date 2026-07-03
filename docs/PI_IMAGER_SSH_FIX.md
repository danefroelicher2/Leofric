# Pi Imager SSH Fix — Headless Pi 5 on Windows

## Hardware

- Raspberry Pi 5 8GB
- 128GB microSD card
- Headless — no monitor, no keyboard, SSH only
- WiFi only, no Ethernet
- Development machine: Windows 11 PC
- Pi Imager v2.0.10

---

## The Bug

Pi Imager v2.0.10 uses **cloud-init** (not firstrun.sh) for OS customization on Pi OS Bookworm.
It writes `user-data`, `meta-data`, and `network-config` to the FAT32 boot partition.

Pi Imager's generated `user-data` is missing `ssh-keygen -A` in runcmd. SSH daemon starts on
first boot but has no host keys. Every connection attempt is closed immediately during key
exchange with `kex_exchange_identification: Connection closed by remote host`.

Pi Imager also writes the username field incorrectly — it used `danefroelicher` instead of `dane`.

---

## The Fix

Pull the SD card. Mount boot partition on Windows (shows as D:).

**1. Edit `D:\user-data`** — add `ssh-keygen -A` to runcmd and fix the username:

```yaml
#cloud-config
manage_resolv_conf: false

hostname: leofric
manage_etc_hosts: true
packages:
- avahi-daemon
apt:
  preserve_sources_list: true
  conf: |
    Acquire {
      Check-Date "false";
    };
timezone: America/New_York
keyboard:
  model: pc105
  layout: "us"
user:
  name: dane
  shell: /bin/bash
  lock_passwd: false
  passwd: "<keep the hash Pi Imager wrote>"
ssh_pwauth: true
runcmd:
  - /usr/bin/ssh-keygen -A
  - systemctl enable --now ssh
```

**2. Edit `D:\meta-data`** — change the instance-id to force cloud-init to re-run:

```
instance-id: leofric-ssh-fix
local-hostname: leofric
```

**3. Edit `D:\cmdline.txt`** — update the `i=` parameter to match the new instance-id:

Find `ds=nocloud;i=rpi-imager-XXXXXXXXX` and change it to `ds=nocloud;i=leofric-ssh-fix`.
Leave everything else in cmdline.txt untouched.

**4.** Eject, insert SD card in Pi, power on, wait 2 minutes.

**5.** Connect:

```powershell
ssh dane@leofric.local
```

---

## Why Other Approaches Don't Work on Pi 5 Bookworm

| Approach | Why It Fails |
|---|---|
| `systemd.run` in cmdline.txt | Removed/ignored on Pi OS Bookworm Pi 5 |
| `init=` pointing to FAT32 file | `init=` looks on ext4 root, not FAT32 boot partition |
| WSL mount of ext4 partition | WSL2 Hyper-V cannot attach removable media (SD cards) |
| `seedfrom=/boot/firmware/` in cmdline.txt | Not needed — Pi OS cloud-init already reads from /boot/firmware/ by default |

---

## Confirming cloud-init Ran

Add this to runcmd to copy the cloud-init log to the boot partition, then read it from Windows:

```yaml
  - cp /var/log/cloud-init.log /boot/firmware/cloud-init.log
```

After booting, `D:\cloud-init.log` will exist if cloud-init ran.

---

## Mac Mini Context (Do Not Touch)

- IP: `192.168.1.46`
- Flask API: port 5000, auto-starts on boot
- Ollama: Llama 3.2 installed, auto-starts on boot
- Both services are configured and running — do not rebuild
