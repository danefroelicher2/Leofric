#!/usr/bin/env python3
"""
Generates SSH host keys on Windows, embeds them in cloud-init user-data.
cloud-init's write_files module puts them directly into /etc/ssh/ on boot.
No execution needed on the Pi — just file writes.
"""

import os, re, subprocess, tempfile, base64, shutil, sys

DRIVE = "D:"

print("Generating SSH host keys on Windows...")
tmpdir = tempfile.mkdtemp()
entries = []

for key_type, extra_args in [("rsa", ["-b", "4096"]), ("ecdsa", ["-b", "256"]), ("ed25519", [])]:
    key_path = os.path.join(tmpdir, f"ssh_host_{key_type}_key")
    cmd = ["ssh-keygen", "-t", key_type, "-f", key_path, "-N", ""] + extra_args
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        print(f"  WARNING: {key_type} failed: {r.stderr.decode().strip()}")
        continue
    print(f"  Generated {key_type}")
    with open(key_path, "rb") as f:
        priv = base64.b64encode(f.read()).decode()
    with open(key_path + ".pub", "rb") as f:
        pub = base64.b64encode(f.read()).decode()
    entries.append(f"""\
  - path: /etc/ssh/ssh_host_{key_type}_key
    encoding: b64
    content: {priv}
    permissions: '0600'
    owner: root:root
  - path: /etc/ssh/ssh_host_{key_type}_key.pub
    encoding: b64
    content: {pub}
    permissions: '0644'
    owner: root:root""")

shutil.rmtree(tmpdir)

if not entries:
    print("ERROR: No keys generated. Is OpenSSH installed?")
    sys.exit(1)

USER_DATA = "#cloud-config\nwrite_files:\n" + "\n".join(entries) + """
runcmd:
  - [ systemctl, enable, ssh ]
  - [ systemctl, restart, ssh ]
"""

META_DATA = "instance-id: leofric-final\nlocal-hostname: leofric\n"

for fname, content in [("user-data", USER_DATA), ("meta-data", META_DATA)]:
    path = f"{DRIVE}/{fname}"
    with open(path, "w", newline="\n") as f:
        f.write(content)
    print(f"Written: {path}")

for fname in ["firstrun.sh", "init_fix.sh", "fix_ssh.sh"]:
    p = f"{DRIVE}/{fname}"
    if os.path.exists(p):
        os.remove(p)
        print(f"Deleted: {p}")

cmdline_path = f"{DRIVE}/cmdline.txt"
with open(cmdline_path) as f:
    cmdline = f.read().strip()

cleaned = re.sub(r"\s+systemd\.\S+", "", cmdline)
cleaned = re.sub(r"\s+init=\S+", "", cleaned)
cleaned = re.sub(
    r"ds=nocloud\S*",
    "ds=nocloud;seedfrom=/boot/firmware/;i=leofric-final",
    cleaned
).strip()

print(f"\nBefore: {cmdline}")
print(f"After:  {cleaned}")

with open(cmdline_path, "w", newline="\n") as f:
    f.write(cleaned + "\n")

print("\nDone. Eject D: and boot the Pi.")
print("Wait 2 minutes, then: ssh dane@leofric.local")
