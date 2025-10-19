import os, io, uuid, boto3, logging, traceback
from dotenv import load_dotenv
from botocore.exceptions import ClientError
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# -------------------------------------------------------------------
# Load environment variables
# -------------------------------------------------------------------
load_dotenv()

# -------------------------------------------------------------------
# Paths and setup
# -------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# -------------------------------------------------------------------
# Logging setup
# -------------------------------------------------------------------
LOG_FILE = BASE_DIR / "partyprint.log"
logger = logging.getLogger("partyprint")
logger.setLevel(logging.INFO)

# Rotating file handler (2 MB, 5 backups)
fh = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=5)
fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))

# Console handler
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))

logger.addHandler(fh)
logger.addHandler(ch)

logger.info("=== PartyPrint server starting ===")

# -------------------------------------------------------------------
# FastAPI setup
# -------------------------------------------------------------------
app = FastAPI(title="PartyPrint Demo")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# -------------------------------------------------------------------
# AWS setup
# -------------------------------------------------------------------
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
BUCKET = os.getenv("S3_BUCKET")
s3 = boto3.client("s3", region_name=AWS_REGION)

# -------------------------------------------------------------------
# Job storage (in-memory for demo)
# -------------------------------------------------------------------
jobs = []

# -------------------------------------------------------------------
# Middleware logging all requests
# -------------------------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"→ {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(f"← {request.method} {request.url.path} [{response.status_code}]")
        return response
    except Exception as e:
        logger.error(f"!! Error handling {request.url.path}: {e}")
        logger.error(traceback.format_exc())
        return HTMLResponse("Internal Server Error", status_code=500)

# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        logger.warning("index.html not found in static/")
        return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
    logger.info("Serving index.html")
    return HTMLResponse(index_file.read_text())

@app.post("/upload")
async def upload(image: UploadFile = File(...), user: str = Form("Anonymous")):
    """Handle uploads to S3 and enqueue job info."""
    job_id = str(uuid.uuid4())
    filename = f"{job_id}_{image.filename}"

    try:
        # Upload to S3
        s3.upload_fileobj(
            io.BytesIO(await image.read()),
            BUCKET,
            filename,
            ExtraArgs={"ContentType": image.content_type},
        )
        url = f"https://{BUCKET}.s3.amazonaws.com/{filename}"

        jobs.append({
            "id": job_id,
            "filename": filename,
            "user": user,
            "url": url,
            "done": False
        })

        logger.info(f"[UPLOAD] {filename} uploaded by {user}")
        return {"ok": True, "id": job_id, "path": url, "user": user}
    except ClientError as e:
        logger.error(f"[UPLOAD ERROR] {filename}: {e}")
        return {"ok": False, "error": str(e)}

@app.get("/queue")
def queue():
    pending = sum(not j["done"] for j in jobs)
    logger.info(f"[QUEUE] {len(jobs)} total jobs, {pending} pending")
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
    try:
        images = [{"path": j["url"], "user": j.get("user", "Anonymous")} for j in jobs]
        logger.info(f"[GALLERY] Returned {len(images)} images.")
        return {"images": images}
    except Exception as e:
        logger.error(f"[GALLERY ERROR] {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e), "images": []}
