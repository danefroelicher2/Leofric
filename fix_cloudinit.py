#!/usr/bin/env python3
"""
Uses cloud-init nocloud seedfrom to run ssh-keygen during boot.
cloud-init runs after /boot/firmware is mounted, so it can read these files.
"""

import os, re

DRIVE = "D:"

USER_DATA = """\
#cloud-config
users: []
runcmd:
  - [ ssh-keygen, -A ]
  - [ systemctl, enable, ssh ]
  - [ systemctl, restart, ssh ]
"""

META_DATA = """\
instance-id: leofric-fix-03
local-hostname: leofric
"""

for fname, content in [("user-data", USER_DATA), ("meta-data", META_DATA)]:
    path = f"{DRIVE}/{fname}"
    with open(path, "w", newline="\n") as f:
        f.write(content)
    print(f"Written: {path}")

for fname in ["init_fix.sh", "fix_ssh.sh", "firstrun.sh"]:
    p = f"{DRIVE}/{fname}"
    if os.path.exists(p):
        os.remove(p)
        print(f"Deleted: {p}")

cmdline_path = f"{DRIVE}/cmdline.txt"
with open(cmdline_path) as f:
    cmdline = f.read().strip()

cleaned = re.sub(r"\s+init=\S+", "", cmdline)
cleaned = re.sub(r"\s+systemd\.\S+", "", cleaned)
cleaned = re.sub(
    r"ds=nocloud\S*",
    "ds=nocloud;seedfrom=/boot/firmware/;i=leofric-fix-03",
    cleaned
).strip()

print(f"\nBefore: {cmdline}")
print(f"After:  {cleaned}")

with open(cmdline_path, "w", newline="\n") as f:
    f.write(cleaned + "\n")

print("\nDone. Eject D:, insert in Pi, power on.")
print("Wait 2 minutes, then: ssh dane@leofric.local")
