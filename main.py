#!/usr/bin/env python3
import os, io, uuid, sqlite3, boto3, logging, traceback, time
from dotenv import load_dotenv
from botocore.exceptions import ClientError
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.wsgi import WSGIMiddleware
from flask import Flask, Response
from pathlib import Path

# -------------------------------------------------------------------
# Environment + Paths
# -------------------------------------------------------------------
load_dotenv()
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "jobs.db"
LOG_PATH = BASE_DIR / "partyprint.log"
UPLOAD_DIR.mkdir(exist_ok=True)

# -------------------------------------------------------------------
# Logging setup
# -------------------------------------------------------------------
logger = logging.getLogger("partyprint")
logger.setLevel(logging.INFO)
fh = RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=5)
fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
logger.addHandler(fh)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
logger.addHandler(ch)
logger.info("=== PartyPrint server starting ===")

# -------------------------------------------------------------------
# Database setup (SQLite)
# -------------------------------------------------------------------
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                filename TEXT,
                user TEXT,
                url TEXT,
                status TEXT DEFAULT 'uploaded',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    logger.info("Database initialized: jobs.db")

def db_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            return cur.fetchall()
        conn.commit()

init_db()

# -------------------------------------------------------------------
# AWS setup
# -------------------------------------------------------------------
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
BUCKET = os.getenv("S3_BUCKET")
s3 = boto3.client("s3", region_name=AWS_REGION)

# -------------------------------------------------------------------
# FastAPI setup
# -------------------------------------------------------------------
app = FastAPI(title="PartyPrint Demo")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# -------------------------------------------------------------------
# Middleware
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
        return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
    return HTMLResponse(index_file.read_text())

@app.post("/upload")
async def upload(image: UploadFile = File(...), user: str = Form("Anonymous")):
    """Upload image to S3 and queue job in DB."""
    job_id = str(uuid.uuid4())
    filename = f"{job_id}_{image.filename}"

    try:
        s3.upload_fileobj(
            io.BytesIO(await image.read()),
            BUCKET,
            filename,
            ExtraArgs={"ContentType": image.content_type},
        )
        url = f"https://{BUCKET}.s3.amazonaws.com/{filename}"
        db_query(
            "INSERT INTO jobs (id, filename, user, url, status) VALUES (?, ?, ?, ?, ?)",
            (job_id, filename, user, url, "uploaded")
        )
        logger.info(f"[UPLOAD] {filename} uploaded by {user}")
        return {"ok": True, "id": job_id, "path": url, "user": user}
    except ClientError as e:
        logger.error(f"[UPLOAD ERROR] {filename}: {e}")
        return {"ok": False, "error": str(e)}

@app.get("/jobs")
def list_jobs():
    """View all jobs."""
    rows = db_query("SELECT id, filename, user, url, status, created_at FROM jobs ORDER BY created_at DESC", fetch=True)
    return {"jobs": [dict(zip(["id", "filename", "user", "url", "status", "created_at"], r)) for r in rows]}

@app.post("/print/{job_id}")
def trigger_print(job_id: str):
    """Mark a specific uploaded job as ready to print."""
    rows = db_query("SELECT id FROM jobs WHERE id = ?", (job_id,), fetch=True)
    if not rows:
        logger.warning(f"[PRINT] Job ID not found: {job_id}")
        return JSONResponse({"ok": False, "error": "Job not found"}, status_code=404)

    db_query("UPDATE jobs SET status = 'queued' WHERE id = ?", (job_id,))
    logger.info(f"[PRINT] Job {job_id} manually triggered for printing.")
    return {"ok": True, "message": "Job queued for printing."}



@app.get("/next-job")
def next_job():
    """Printer polls for next queued job."""
    rows = db_query("""
        SELECT id, filename, user, url
        FROM jobs
        WHERE status = 'queued'
        ORDER BY created_at ASC
        LIMIT 1
    """, fetch=True)

    if not rows:
        return {"id": None, "filename": None, "user": None, "url": None}

    job = dict(zip(["id", "filename", "user", "url"], rows[0]))
    db_query("UPDATE jobs SET status = 'printing' WHERE id = ?", (job["id"],))
    logger.info(f"[DISPATCH] Job {job['id']} sent to printer.")
    return job


@app.post("/mark-printed/{job_id}")
def mark_printed(job_id: str):
    """Printer confirms successful print."""
    db_query("UPDATE jobs SET status = 'printed' WHERE id = ?", (job_id,))
    logger.info(f"[PRINTED] Job {job_id} marked complete")
    return {"ok": True}


@app.get("/gallery")
def gallery():
    """Return all uploaded images (persistent via DB)."""
    try:
        rows = db_query(
            "SELECT url, user, status, created_at FROM jobs ORDER BY created_at DESC",
            fetch=True
        )
        images = [
            {
                "path": r[0],
                "user": r[1] or "Anonymous",
                "status": r[2],
                "created_at": r[3]
            }
            for r in rows
        ]
        logger.info(f"[GALLERY] Returned {len(images)} images from DB.")
        return {"images": images}
    except Exception as e:
        logger.error(f"[GALLERY ERROR] {e}")
        logger.error(traceback.format_exc())
        return {"error": str(e), "images": []}


# -------------------------------------------------------------------
# Flask bridge for live log streaming
# -------------------------------------------------------------------
flask_bridge = Flask(__name__)

@flask_bridge.route("/logs")
def stream_logs():
    """Server-Sent Events for real-time logs."""
    def generate():
        if not os.path.exists(LOG_PATH):
            yield "data: (no log file yet)\n\n"
            return
        with open(LOG_PATH, "r") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if line:
                    yield f"data: {line.strip()}\n\n"
                time.sleep(0.5)
    return Response(generate(), mimetype="text/event-stream")

app.mount("/admin", WSGIMiddleware(flask_bridge))

# -------------------------------------------------------------------
# Run server
# -------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)
