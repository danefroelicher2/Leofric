#!/usr/bin/env python3
"""
Uses init= kernel parameter to run a one-time script as PID 1.
The script generates SSH host keys, cleans itself up, then execs systemd.
No WSL, no ext4 drivers needed — runs directly on the Pi's root filesystem.
"""

import os, re

DRIVE = "D:"

INIT_SCRIPT = """\
#!/bin/bash
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true
mount -t proc proc /proc 2>/dev/null || true
mount -t sysfs sysfs /sys 2>/dev/null || true
/usr/bin/ssh-keygen -t rsa     -b 4096 -f /etc/ssh/ssh_host_rsa_key     -N "" 2>/dev/null || true
/usr/bin/ssh-keygen -t ecdsa   -b 256  -f /etc/ssh/ssh_host_ecdsa_key   -N "" 2>/dev/null || true
/usr/bin/ssh-keygen -t ed25519         -f /etc/ssh/ssh_host_ed25519_key  -N "" 2>/dev/null || true
chmod 600 /etc/ssh/ssh_host_*_key 2>/dev/null || true
chmod 644 /etc/ssh/ssh_host_*_key.pub 2>/dev/null || true
mkdir -p /boot/firmware
mount /dev/mmcblk0p1 /boot/firmware 2>/dev/null || true
sed -i 's/ init=[^ ]*//g' /boot/firmware/cmdline.txt 2>/dev/null || true
rm -f /boot/firmware/init_fix.sh 2>/dev/null || true
umount /boot/firmware 2>/dev/null || true
exec /sbin/init "$@"
"""

script_path = f"{DRIVE}/init_fix.sh"
with open(script_path, "w", newline="\n") as f:
    f.write(INIT_SCRIPT)
print(f"Written: {script_path}")

cmdline_path = f"{DRIVE}/cmdline.txt"
with open(cmdline_path) as f:
    cmdline = f.read().strip()

cleaned = re.sub(r"\s+init=\S+", "", cmdline)
cleaned = re.sub(r"\s+systemd\.\S+", "", cleaned).strip()
new_cmdline = cleaned + " init=/boot/firmware/init_fix.sh"

print(f"\nBefore: {cmdline}")
print(f"After:  {new_cmdline}")

with open(cmdline_path, "w", newline="\n") as f:
    f.write(new_cmdline + "\n")

print("\nDone. Eject D:, insert in Pi, power on.")
print("Wait 90 seconds, then: ssh dane@leofric.local")
