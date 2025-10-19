from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from logging.handlers import RotatingFileHandler
import logging, os, uuid, traceback

# -------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
LOG_FILE = BASE_DIR / "partyprint.log"

UPLOAD_DIR.mkdir(exist_ok=True)

# -------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------
logger = logging.getLogger("partyprint")
logger.setLevel(logging.INFO)

# File handler with rotation (2 MB, 5 backups)
fh = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=5)
fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))

# Console handler
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))

logger.addHandler(fh)
logger.addHandler(ch)

logger.info("=== PartyPrint server starting ===")

# -------------------------------------------------------------------
# App setup
# -------------------------------------------------------------------
app = FastAPI(title="PartyPrint Demo")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/files", StaticFiles(directory=UPLOAD_DIR), name="files")

jobs = []

# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request for debugging."""
    logger.info(f"→ {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(f"← {request.method} {request.url.path} [{response.status_code}]")
        return response
    except Exception as e:
        logger.error(f"!! Error handling {request.url.path}: {e}")
        logger.error(traceback.format_exc())
        return HTMLResponse("Internal Server Error", status_code=500)

@app.get("/", response_class=HTMLResponse)
def index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        logger.warning("index.html not found in static/")
        return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
    logger.info("Serving index.html")
    return HTMLResponse(index_file.read_text())

from fastapi import Form

@app.post("/upload")
async def upload(
    image: UploadFile = File(...),
    user: str = Form("Anonymous")
):
    """Handle uploads and enqueue them with user info"""
    job_id = str(uuid.uuid4())
    filename = f"{job_id}_{image.filename}"
    path = UPLOAD_DIR / filename

    logger.info(f"[UPLOAD] Receiving {filename} from {user}")
    try:
        with open(path, "wb") as f:
            f.write(await image.read())

        jobs.append({
            "id": job_id,
            "filename": filename,
            "path": str(path),
            "user": user,
            "done": False
        })

        logger.info(f"[UPLOAD] Saved {filename} ({path}) by {user}")
        return {"ok": True, "id": job_id, "path": f"/files/{filename}", "user": user}
    except Exception as e:
        logger.error(f"[UPLOAD ERROR] {filename}: {e}")
        return {"ok": False, "error": str(e)}


@app.get("/queue")
def queue():
    logger.info(f"[QUEUE] {len(jobs)} total jobs, {sum(not j['done'] for j in jobs)} pending")
    return {"jobs": jobs}

@app.get("/next-job")
def next_job():
    for j in jobs:
        if not j["done"]:
            j["done"] = True
            logger.info(f"[DISPATCH] Job {j['filename']} marked done.")
            return j
    logger.info("[DISPATCH] No pending jobs.")
    return {"id": None, "filename": None}

@app.get("/gallery")
def gallery():
    logger.info("[GALLERY] Building gallery view...")
    images = []
    try:
        for j in jobs:
            path = j.get("path")
            if not path:
                logger.warning(f"[GALLERY] Skipping job without path: {j}")
                continue
            filename = os.path.basename(path)
            images.append({
                "path": f"/files/{filename}",
                "user": j.get("user", "Anonymous")
            })
        logger.info(f"[GALLERY] Returned {len(images)} images.")
        return {"images": images}
    except Exception as e:
        logger.error(f"[GALLERY ERROR] {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e), "images": []}
