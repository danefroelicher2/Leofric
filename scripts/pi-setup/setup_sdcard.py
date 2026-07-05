#!/usr/bin/env python3
"""
Writes firstrun.sh and updates cmdline.txt on the Pi's boot partition.
Run this once with the SD card mounted on Windows, then eject and boot the Pi.
"""

DRIVE = "D:"

# firstrun.sh is executed by systemd on the Pi's very first boot.
# It creates the WiFi config, enables SSH, sets the hostname and timezone,
# then removes itself so it never runs again.
lines = [
    "#!/bin/bash",
    "",
    "set +e",
    "",
    "CURRENT_HOSTNAME=$(cat /etc/hostname | tr -d \" \\t\\n\\r\")",
    "echo leofric > /etc/hostname",
    "sed -i \"s/127.0.1.1.*$CURRENT_HOSTNAME/127.0.1.1\\tleofric/g\" /etc/hosts",
    "",
    "systemctl enable ssh",
    "systemctl start ssh",
    "",
    # NetworkManager (default on Pi OS Bookworm) reads connection profiles
    # from this directory. The 600 permission is required — NM ignores files
    # that are world-readable.
    "mkdir -p /etc/NetworkManager/system-connections/",
    "cat > /etc/NetworkManager/system-connections/home.nmconnection << 'NMEOF'",
    "[connection]",
    "id=home",
    "type=wifi",
    "autoconnect=true",
    "",
    "[wifi]",
    "mode=infrastructure",
    "ssid=LacasaFroelicher-5G",
    "",
    "[wifi-security]",
    "auth-alg=open",
    "key-mgmt=wpa-psk",
    "psk=Cards24!",
    "",
    "[ipv4]",
    "method=auto",
    "",
    "[ipv6]",
    "addr-gen-mode=default",
    "method=auto",
    "NMEOF",
    "chmod 600 /etc/NetworkManager/system-connections/home.nmconnection",
    "",
    "rfkill unblock wifi",
    "",
    "rm -f /etc/localtime",
    "echo \"America/New_York\" > /etc/timezone",
    "dpkg-reconfigure -f noninteractive tzdata",
    "",
    # Self-destruct: remove this script and strip the systemd.run directive
    # from cmdline.txt so the Pi boots normally from here on.
    "rm -f /boot/firmware/firstrun.sh",
    "sed -i 's| systemd.run.*||g' /boot/firmware/cmdline.txt",
    "",
    "exit 0",
    "",
]

firstrun_path = DRIVE + "/firstrun.sh"
with open(firstrun_path, "w", newline="\n") as f:
    f.write("\n".join(lines))
print(f"Written:  {firstrun_path}")

# cmdline.txt is a single line. We append the systemd.run directives so the
# Pi's init system executes firstrun.sh immediately on first boot, then reboots.
cmdline_path = DRIVE + "/cmdline.txt"
with open(cmdline_path, "r") as f:
    cmdline = f.read().strip()

directive = (
    " systemd.run=/boot/firmware/firstrun.sh"
    " systemd.run_success_action=reboot"
    " systemd.unit=kernel-command-line.target"
)

if "systemd.run" not in cmdline:
    cmdline += directive

with open(cmdline_path, "w", newline="\n") as f:
    f.write(cmdline + "\n")
print(f"Updated:  {cmdline_path}")

print("\nDone. Eject the SD card safely, insert it into the Pi, and power on.")
print("The Pi will run setup on first boot and reboot automatically (~60s).")
print("After the second boot, wait 30s then run:  ssh dane@leofric.local")
