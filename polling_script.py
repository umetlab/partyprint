#!/usr/bin/env python3
import requests, time, os, subprocess
from pathlib import Path

SERVER = "https://party.emits.ai"  # main app domain
DOWNLOAD_DIR = Path("/tmp/partyprints")
DOWNLOAD_DIR.mkdir(exist_ok=True)

def download_and_print(url, job_id):
    """Download the image and send to local printer"""
    local_path = DOWNLOAD_DIR / f"{job_id}.jpg"
    r = requests.get(url, stream=True)
    if r.status_code == 200:
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
        print(f"📥 Downloaded {local_path}")
        # print using system command (CUPS / lp)
        subprocess.run(["lp", str(local_path)])
        print("🖨️ Sent to printer.")
        requests.post(f"{SERVER}/mark-printed/{job_id}")
    else:
        print(f"⚠️ Failed to download {url} (status {r.status_code})")

def main():
    print("🎉 PartyPrint client started — polling for print jobs...")
    while True:
        try:
            r = requests.get(f"{SERVER}/next-job", timeout=10)
            job = r.json()
            if job.get("id"):
                print(f"🆕 Printing job {job['id']} from {job['user']}")
                download_and_print(job["url"], job["id"])
            else:
                time.sleep(3)
        except Exception as e:
            print("❌ Error polling:", e)
            time.sleep(5)

if __name__ == "__main__":
    main()
