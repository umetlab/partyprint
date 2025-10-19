import time, requests, subprocess, os

API_URL = "https://party.emits.ai/files"
PRINTED_TRACKER = "/tmp/printed.log"

printed = set()
if os.path.exists(PRINTED_TRACKER):
    printed = set(open(PRINTED_TRACKER).read().splitlines())

while True:
    try:
        files = requests.get(API_URL, timeout=5).json()
        for f in files:
            name = f["name"]
            if name not in printed:
                print(f"🖨️ Printing {name}...")
                url = f"https://party.emits.ai/files/{name}"
                local_path = f"/tmp/{name}"
                with open(local_path, "wb") as out:
                    out.write(requests.get(url).content)

                subprocess.run(["lp", "-d", "Canon_CP1500", local_path])
                printed.add(name)
                open(PRINTED_TRACKER, "a").write(name + "\n")
        time.sleep(5)
    except Exception as e:
        print("Error:", e)
        time.sleep(10)
