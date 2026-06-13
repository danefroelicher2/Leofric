#!/usr/bin/env python3
"""
Writes a minimal firstrun.sh that generates SSH host keys, then cleans up.
Uses the exact Pi OS mechanism: systemd.run + kernel-command-line.target.
Pi will reboot automatically after the script runs.
"""

import os, re

DRIVE = "D:"

FIRSTRUN = """\
#!/bin/bash
/usr/bin/ssh-keygen -t rsa     -b 4096 -f /etc/ssh/ssh_host_rsa_key     -N "" 2>/dev/null || true
/usr/bin/ssh-keygen -t ecdsa   -b 256  -f /etc/ssh/ssh_host_ecdsa_key   -N "" 2>/dev/null || true
/usr/bin/ssh-keygen -t ed25519         -f /etc/ssh/ssh_host_ed25519_key  -N "" 2>/dev/null || true
chmod 600 /etc/ssh/ssh_host_*_key 2>/dev/null || true
chmod 644 /etc/ssh/ssh_host_*_key.pub 2>/dev/null || true
sed -i 's/ systemd\\.run[^ ]*//g' /boot/firmware/cmdline.txt 2>/dev/null || true
sed -i 's/ systemd\\.unit[^ ]*//g' /boot/firmware/cmdline.txt 2>/dev/null || true
rm -f /boot/firmware/firstrun.sh /boot/firmware/user-data /boot/firmware/meta-data 2>/dev/null || true
"""

path = f"{DRIVE}/firstrun.sh"
with open(path, "w", newline="\n") as f:
    f.write(FIRSTRUN)
print(f"Written: {path}")

for fname in ["user-data", "meta-data", "init_fix.sh", "fix_ssh.sh"]:
    p = f"{DRIVE}/{fname}"
    if os.path.exists(p):
        os.remove(p)
        print(f"Deleted: {p}")

cmdline_path = f"{DRIVE}/cmdline.txt"
with open(cmdline_path) as f:
    cmdline = f.read().strip()

cleaned = re.sub(r"\s+systemd\.\S+", "", cmdline)
cleaned = re.sub(r"\s+init=\S+", "", cleaned)
cleaned = re.sub(r"ds=nocloud\S*", "ds=nocloud;i=rpi-imager-1781294579815", cleaned).strip()

new_cmdline = (
    cleaned
    + " systemd.run=/boot/firmware/firstrun.sh"
    + " systemd.run_success_action=reboot"
    + " systemd.unit=kernel-command-line.target"
)

print(f"\nBefore: {cmdline}")
print(f"After:  {new_cmdline}")

with open(cmdline_path, "w", newline="\n") as f:
    f.write(new_cmdline + "\n")

print("\nDone. Eject D:, insert in Pi, power on.")
print("The Pi will run firstrun.sh, generate SSH keys, then REBOOT itself.")
print("Wait 3 minutes for the full cycle, then: ssh dane@leofric.local")
