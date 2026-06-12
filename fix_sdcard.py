#!/usr/bin/env python3
"""
Removes the systemd.run boot loop from cmdline.txt and deletes firstrun.sh.
Run this with the SD card mounted as D:, then re-insert the card and boot.
"""

import os
import re

DRIVE = "D:"

# Remove firstrun.sh so it can't run again
firstrun_path = DRIVE + "/firstrun.sh"
if os.path.exists(firstrun_path):
    os.remove(firstrun_path)
    print(f"Deleted:  {firstrun_path}")
else:
    print(f"Not found (already gone): {firstrun_path}")

# Strip the systemd.run directives from cmdline.txt so the Pi boots normally
cmdline_path = DRIVE + "/cmdline.txt"
with open(cmdline_path, "r") as f:
    cmdline = f.read().strip()

print(f"\nBefore: {cmdline}")

# Remove everything from ' systemd.run' onward
cleaned = re.sub(r" systemd\.run\S*", "", cmdline)
cleaned = re.sub(r" systemd\.unit\S*", "", cleaned)
cleaned = re.sub(r"\s+", " ", cleaned).strip()

print(f"After:  {cleaned}")

with open(cmdline_path, "w", newline="\n") as f:
    f.write(cleaned + "\n")

print("\nDone. Eject the SD card, insert into Pi, power on.")
print("Wait 2 minutes, then: ssh dane@leofric.local")
