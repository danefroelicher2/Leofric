#!/usr/bin/env python3
"""
Adds a one-time SSH host key generation script to the boot partition.
Run with the SD card mounted as D:, then eject and boot the Pi.
The script on the Pi cleans itself up after running.
"""

import os

DRIVE = "D:"

# This script runs on the Pi during boot, generates host keys, then self-destructs
FIX_SSH_SCRIPT = """\
#!/bin/bash
ssh-keygen -A
systemctl enable ssh
systemctl restart ssh
sed -i 's/ systemd\\.run[^ ]*//g' /boot/firmware/cmdline.txt
rm -f /boot/firmware/fix_ssh.sh
"""

script_path = DRIVE + "/fix_ssh.sh"
with open(script_path, "w", newline="\n") as f:
    f.write(FIX_SSH_SCRIPT)
print(f"Written:  {script_path}")

cmdline_path = DRIVE + "/cmdline.txt"
with open(cmdline_path, "r") as f:
    cmdline = f.read().strip()

print(f"\nBefore: {cmdline}")

cmdline += " systemd.run=/boot/firmware/fix_ssh.sh systemd.run_success_action=none"

print(f"After:  {cmdline}")

with open(cmdline_path, "w", newline="\n") as f:
    f.write(cmdline + "\n")

print("\nDone. Eject the SD card, insert into Pi, power on.")
print("Wait 3 minutes, then: ssh dane@leofric.local")
