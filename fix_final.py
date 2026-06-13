#!/usr/bin/env python3
"""
Writes SSH host keys directly to the Pi's root partition via WSL.
Run from an Administrator PowerShell prompt with the SD card mounted as D:.
"""

import subprocess, sys, re, os, json

DRIVE = "D:"

# Clean boot partition
print("Cleaning boot partition...")
cmdline_path = f"{DRIVE}/cmdline.txt"
if os.path.exists(cmdline_path):
    with open(cmdline_path) as f:
        txt = f.read().strip()
    cleaned = re.sub(r"\s+systemd\.\S+", "", txt).strip()
    with open(cmdline_path, "w", newline="\n") as f:
        f.write(cleaned + "\n")
    print(f"  cmdline.txt: {cleaned}")

for fname in ["fix_ssh.sh", "firstrun.sh"]:
    p = f"{DRIVE}/{fname}"
    if os.path.exists(p):
        os.remove(p)
        print(f"  Deleted {fname}")

# Find SD card disk number
print("\nFinding SD card...")
r = subprocess.run(
    ["powershell", "-Command", "Get-Disk | Select-Object Number, Size | ConvertTo-Json"],
    capture_output=True, text=True
)
disks = json.loads(r.stdout)
if isinstance(disks, dict):
    disks = [disks]
sd = [d for d in disks if 0 < d["Size"] < 200_000_000_000]
if not sd:
    print("ERROR: SD card not found. Is it inserted?")
    sys.exit(1)
N = sd[0]["Number"]
print(f"  PHYSICALDRIVE{N} ({sd[0]['Size'] // (1024**3)} GB)")

# Release Windows' lock on the disk by removing the D: access path
print(f"\nReleasing Windows lock on PHYSICALDRIVE{N}...")
release_cmd = (
    "$p = Get-Partition -DriveLetter D; "
    "Remove-PartitionAccessPath -DiskNumber $p.DiskNumber "
    "-PartitionNumber $p.PartitionNumber -AccessPath 'D:\\'"
)
r = subprocess.run(["powershell", "-Command", release_cmd], capture_output=True, text=True)
if r.returncode != 0:
    print(f"  WARNING: {r.stderr.strip()}")
else:
    print("  D: released.")

# Mount the ext4 root partition in WSL
print(f"\nMounting PHYSICALDRIVE{N} partition 2 in WSL...")
r = subprocess.run(
    f'wsl --mount \\\\.\\PHYSICALDRIVE{N} --partition 2 --type ext4',
    shell=True, capture_output=True, text=True
)
out = (r.stdout + r.stderr).strip()
print(f"  {out if out else 'OK'}")
if r.returncode != 0 and "already" not in out.lower():
    print("ERROR: wsl --mount failed.")
    print(out)
    sys.exit(1)

# Generate SSH host keys directly into the Pi's /etc/ssh/
print("\nGenerating SSH host keys...")
wsl_cmd = f"""
set -e
MP=$(ls /mnt/wsl/ 2>/dev/null | grep -i 'physicaldrive{N}' | head -1)
[ -z "$MP" ] && {{ echo "ERROR: mount not found under /mnt/wsl/"; ls /mnt/wsl/ 2>/dev/null; exit 1; }}
MP="/mnt/wsl/$MP"
echo "  Writing to: $MP/etc/ssh/"
[ ! -d "$MP/etc/ssh" ] && {{ echo "ERROR: $MP/etc/ssh missing - wrong partition?"; exit 1; }}
ssh-keygen -t rsa     -b 4096 -f $MP/etc/ssh/ssh_host_rsa_key     -N "" -q
ssh-keygen -t ecdsa   -b 256  -f $MP/etc/ssh/ssh_host_ecdsa_key   -N "" -q
ssh-keygen -t ed25519         -f $MP/etc/ssh/ssh_host_ed25519_key  -N "" -q
chmod 600 $MP/etc/ssh/ssh_host_*_key
chmod 644 $MP/etc/ssh/ssh_host_*_key.pub
echo "  Keys written:"
ls $MP/etc/ssh/ssh_host_*
"""
r = subprocess.run(["wsl", "-u", "root", "bash", "-c", wsl_cmd], text=True)
if r.returncode != 0:
    subprocess.run(f'wsl --unmount \\\\.\\PHYSICALDRIVE{N}', shell=True)
    sys.exit(1)

# Unmount
print("\nUnmounting...")
subprocess.run(f'wsl --unmount \\\\.\\PHYSICALDRIVE{N}', shell=True, capture_output=True)

print("\n" + "=" * 52)
print("  HOST KEYS WRITTEN. SSH WILL WORK ON NEXT BOOT.")
print("=" * 52)
print("  1. Eject D: in File Explorer")
print("  2. Insert SD card in Pi and power on")
print("  3. Wait 90 seconds")
print("  4. ssh dane@leofric.local")
