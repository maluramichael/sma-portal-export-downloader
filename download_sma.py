#!/usr/bin/env python3
"""
Download the diagnostic exports (ONLINE / ONLINE5M) of an SMA inverter.
Validates downloads are real ZIP files, reuses sessions.

Configuration through environment variables or options (options win):
    SMA_HOST          inverter address, e.g. 192.168.1.50 or https://192.168.1.50   (--host)
    SMA_PASS          password of the user group                                    (no option, keeps it out of ps)
    SMA_GROUP         user group, "istl" (installer) or "user", default istl        (--group)
    SMA_DATA_DIR      download directory, default ./data                             (--dest)
    SMA_SESSION_FILE  where the session id is kept, default <tmp>/sma_session.txt

Usage:
    python3 download_sma.py                          # Download all missing ONLINE5M archives
    python3 download_sma.py -r ONLINE                # Download ONLINE archives
    python3 download_sma.py --one DA260115.ZIP       # Download one specific file
    python3 download_sma.py --redownload-broken      # Re-download broken ZIPs
    python3 download_sma.py --dry-run                # List what would be downloaded
    python3 download_sma.py --dest /backup/pv        # Files go to /backup/pv/<report>/
"""

import os
import sys
import argparse
import tempfile
import requests
import urllib3
from zipfile import ZipFile, BadZipFile

urllib3.disable_warnings()

SMA_HOST = os.environ.get("SMA_HOST", "")
SMA_GROUP = os.environ.get("SMA_GROUP", "istl")
SMA_PASS = os.environ.get("SMA_PASS", "")
SESSION_FILE = os.environ.get("SMA_SESSION_FILE", os.path.join(tempfile.gettempdir(), "sma_session.txt"))
DATA_BASE = os.environ.get("SMA_DATA_DIR", "data")


def normalize_host(host):
    """The inverter only speaks HTTPS with a self-signed certificate; accept a bare address."""
    host = host.strip().rstrip("/")
    if host and not host.startswith(("http://", "https://")):
        host = "https://" + host
    return host


def load_session():
    try:
        with open(SESSION_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def save_session(sid):
    with open(SESSION_FILE, "w") as f:
        f.write(sid)


def login():
    print("Login...")
    r = requests.post(
        f"{SMA_HOST}/dyn/login.json",
        json={"right": SMA_GROUP, "pass": SMA_PASS},
        verify=False, timeout=10
    )
    data = r.json()
    if "result" in data and "sid" in data["result"]:
        sid = data["result"]["sid"]
        save_session(sid)
        print(f"  Session: {sid}")
        return sid
    print(f"  Login failed: {data}", file=sys.stderr)
    return None


def logout(sid):
    print("Logout...")
    requests.post(
        f"{SMA_HOST}/dyn/logout.json?sid={sid}",
        json={}, verify=False, timeout=10
    )


def get_session():
    """Get a working session, reusing existing if possible."""
    sid = load_session()
    if sid:
        # Test if session works
        r = requests.post(
            f"{SMA_HOST}/dyn/getFS.json?sid={sid}",
            json={"destDev": [], "path": "/DIAGNOSE/ONLINE5M/"},
            verify=False, timeout=10
        )
        if "result" in r.json():
            print(f"Reusing session: {sid}")
            return sid
    return login()


def list_remote_files(sid, report_type):
    """List available files on the inverter."""
    path = f"/DIAGNOSE/{report_type}/"
    r = requests.post(
        f"{SMA_HOST}/dyn/getFS.json?sid={sid}",
        json={"destDev": [], "path": path},
        verify=False, timeout=10
    )
    data = r.json()
    if "result" not in data:
        print(f"Error listing files: {data}", file=sys.stderr)
        return []

    device = list(data["result"].values())[0]
    dir_path = list(device.keys())[0]
    files = [f["f"] for f in device[dir_path] if "f" in f]
    return sorted(files)


def download_file(sid, report_type, filename, dest_path):
    """Download a single file from the inverter. Returns True if successful."""
    url = f"{SMA_HOST}/fs/DIAGNOSE/{report_type}/{filename}?sid={sid}"
    tmp_path = dest_path + ".part"

    try:
        r = requests.post(
            url, json={}, verify=False, timeout=60
        )
    except requests.RequestException as e:
        print(f"  ERROR downloading {filename}: {e}", file=sys.stderr)
        return False

    if r.status_code != 200:
        print(f"  ERROR {filename}: HTTP {r.status_code}", file=sys.stderr)
        return False

    # Write to temp file first
    with open(tmp_path, "wb") as f:
        f.write(r.content)

    # Validate: if it's a ZIP file, try to open it
    if filename.endswith(".ZIP"):
        try:
            z = ZipFile(tmp_path)
            z.close()
        except BadZipFile:
            print(f"  BROKEN {filename}: not a valid ZIP (server returned {len(r.content)} bytes)", file=sys.stderr)
            # Check if it's an error page
            try:
                text = r.content.decode("utf-8", errors="replace")[:200]
                if "500" in text or "Error" in text:
                    print(f"    Server error: {text[:100]}", file=sys.stderr)
            except Exception:
                pass
            os.remove(tmp_path)
            return False

    # Move to final destination
    os.rename(tmp_path, dest_path)
    return True


def find_broken_zips(data_dir):
    """Find ZIP files that are not valid."""
    broken = []
    for f in sorted(os.listdir(data_dir)):
        if not f.endswith(".ZIP"):
            continue
        fp = os.path.join(data_dir, f)
        try:
            z = ZipFile(fp)
            z.close()
        except BadZipFile:
            broken.append(f)
    return broken


def main():
    parser = argparse.ArgumentParser(description="Download SMA diagnostic files")
    parser.add_argument("-r", "--report", default="ONLINE5M", choices=["ONLINE", "ONLINE5M"])
    parser.add_argument("--one", help="Download only this specific file")
    parser.add_argument("--redownload-broken", action="store_true", help="Find and re-download broken ZIPs")
    parser.add_argument("--dry-run", action="store_true", help="List what would be downloaded")
    parser.add_argument("--host", help="inverter address (env SMA_HOST)")
    parser.add_argument("--group", choices=["istl", "user"], help="user group (env SMA_GROUP, default istl)")
    parser.add_argument("--dest", help="download directory, files go to <dest>/<report>/ (env SMA_DATA_DIR, default ./data)")
    args = parser.parse_args()

    global SMA_HOST, SMA_GROUP, DATA_BASE
    SMA_HOST = normalize_host(args.host or SMA_HOST)
    SMA_GROUP = args.group or SMA_GROUP
    DATA_BASE = args.dest or DATA_BASE
    if not SMA_HOST:
        parser.error("inverter address missing: use --host or SMA_HOST")
    if not SMA_PASS:
        parser.error("password missing: set SMA_PASS")

    data_dir = os.path.join(DATA_BASE, args.report)
    os.makedirs(data_dir, exist_ok=True)

    sid = None if args.dry_run else get_session()

    if args.redownload_broken:
        broken = find_broken_zips(data_dir)
        if not broken:
            print("No broken ZIPs found!")
            return
        print(f"Found {len(broken)} broken ZIPs")
        if args.dry_run:
            for f in broken:
                print(f"  Would re-download: {f}")
            return
        for f in broken:
            os.remove(os.path.join(data_dir, f))
            print(f"Deleted broken: {f}")
        # Now download them
        to_download = broken
    elif args.one:
        to_download = [args.one]
    else:
        # List remote files and find missing ones
        if not sid and not args.dry_run:
            print("No session, cannot list remote files", file=sys.stderr)
            sys.exit(1)

        if args.dry_run:
            sid = get_session()

        remote_files = list_remote_files(sid, args.report)
        archives = [f for f in remote_files if f.endswith(".ZIP")]
        local_files = set(os.listdir(data_dir))
        to_download = [f for f in archives if f not in local_files]

        if not to_download:
            print(f"All {len(archives)} archives already downloaded.")
            if not args.dry_run:
                logout(sid)
            return

        print(f"Remote: {len(archives)} archives, Local: {len(local_files)} files, Missing: {len(to_download)}")

    if args.dry_run:
        for f in to_download:
            print(f"  Would download: {f}")
        print(f"\nTotal: {len(to_download)} files")
        return

    downloaded = 0
    failed = 0
    for i, f in enumerate(sorted(to_download)):
        dest = os.path.join(data_dir, f)
        print(f"[{i+1}/{len(to_download)}] {f}", end=" ")
        if download_file(sid, args.report, f, dest):
            print("OK")
            downloaded += 1
        else:
            failed += 1

    print(f"\nDone: {downloaded} downloaded, {failed} failed")
    logout(sid)


if __name__ == "__main__":
    main()
