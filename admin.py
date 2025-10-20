#!/usr/bin/env python3
import os, time, logging
from dotenv import load_dotenv
from flask import (
    Flask, Response, render_template_string,
    redirect, url_for, request, flash
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from logging.handlers import RotatingFileHandler
from flask_mail import Mail

# ------------------------------------------------------------------
# Load environment
# ------------------------------------------------------------------
load_dotenv("/home/ubuntu/.env")

app = Flask(__name__)
app.secret_key = os.getenv("ADMIN_SECRET", "devsecret")

# Shared cookie configuration (so admin + subapps can share sessions if desired)
app.config["SESSION_COOKIE_DOMAIN"] = ".emits.ai"
app.config["SESSION_COOKIE_SAMESITE"] = "None"
app.config["SESSION_COOKIE_SECURE"] = True

# ------------------------------------------------------------------
# Database Configuration
# ------------------------------------------------------------------
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
if not os.path.exists("logs"):
    os.mkdir("logs")

log_path= "/home/ubuntu/partyprint-demo/partyprint.log"

file_handler = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=5)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
file_handler.setFormatter(formatter)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info("PartyPrint Admin Started")

LOG_PATH = log_path

# ------------------------------------------------------------------
# Email (optional, ready for password reset expansion)
# ------------------------------------------------------------------
app.config["MAIL_SERVER"] = os.getenv("EMAIL_SERVER")
app.config["MAIL_PORT"] = int(os.getenv("EMAIL_PORT"))
app.config["MAIL_USE_TLS"] = os.getenv("EMAIL_USE_TLS", "True").lower() in ["true", "1", "yes"]
app.config["MAIL_USERNAME"] = os.getenv("EMAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("EMAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("EMAIL_USERNAME")
app.config["MAIL_USE_SSL"] = False

mail = Mail(app)

# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------
class AdminUser(UserMixin, db.Model):
    __tablename__ = "partyprint_admin_users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

# ------------------------------------------------------------------
# Login manager
# ------------------------------------------------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return AdminUser.query.get(int(user_id))

# ------------------------------------------------------------------
# Routes: Register / Login / Logout
# ------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"]
        if AdminUser.query.filter_by(email=email).first():
            flash("👻 That email is already registered — the spirits remember you.")
            return redirect(url_for("register"))
        hashed = generate_password_hash(password)
        new_user = AdminUser(email=email, password_hash=hashed)
        db.session.add(new_user)
        db.session.commit()
        app.logger.info(f"New admin registered: {email}")
        flash("🎃 You’re in! The portal awaits. Please log in below.")
        return redirect(url_for("login"))

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>PartyPrint Admin – Registration</title>
        <style>
            body {
                background: radial-gradient(circle at center, #0a0a0a 0%, #000 100%);
                color: #ff6600;
                font-family: 'Courier New', monospace;
                text-align: center;
                padding-top: 5rem;
                overflow: hidden;
            }
            h2 {
                font-size: 2rem;
                text-shadow: 0 0 10px #ff6600, 0 0 20px #ff3300;
                animation: flicker 2s infinite alternate;
            }
            @keyframes flicker {
                from { opacity: 1; }
                to { opacity: 0.7; }
            }
            form {
                display: inline-block;
                background: rgba(255, 102, 0, 0.05);
                border: 1px solid #ff6600;
                border-radius: 8px;
                padding: 2rem;
                margin-top: 1rem;
                box-shadow: 0 0 15px #ff3300;
            }
            input {
                display: block;
                margin: 1rem auto;
                padding: 0.5rem;
                width: 250px;
                border: 1px solid #ff6600;
                border-radius: 4px;
                background: #111;
                color: #ffcc66;
                text-align: center;
            }
            button {
                background: #ff6600;
                color: #000;
                border: none;
                padding: 0.75rem 2rem;
                border-radius: 4px;
                font-weight: bold;
                cursor: pointer;
                transition: background 0.3s;
            }
            button:hover {
                background: #ffaa00;
                color: #111;
                box-shadow: 0 0 15px #ff6600;
            }
            a {
                color: #ff9933;
                text-decoration: none;
            }
            a:hover {
                text-decoration: underline;
            }
            .pumpkin {
                position: absolute;
                bottom: -60px;
                left: 50%;
                transform: translateX(-50%);
                font-size: 100px;
                animation: float 4s ease-in-out infinite;
            }
            @keyframes float {
                0%, 100% { transform: translate(-50%, 0); }
                50% { transform: translate(-50%, -10px); }
            }
        </style>
    </head>
    <body>
        <h2>🎃 PartyPrint Admin Registration 🎃</h2>
        <form method="POST">
            <input name="email" placeholder="Email (for spooky invites)">
            <input name="password" type="password" placeholder="Secret incantation">
            <button type="submit">Join the Coven</button>
        </form>
        <p><a href="/login">Already among the living? Log in</a></p>
        <div class="pumpkin">🎃</div>
    </body>
    </html>
    """)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"]
        user = AdminUser.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            app.logger.info(f"Admin logged in: {email}")
            return redirect(url_for("dashboard"))
        flash("💀 Invalid incantation — the portal remains closed.")

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>PartyPrint Admin – Login</title>
        <style>
            body {
                background: radial-gradient(circle at center, #0a0a0a 0%, #000 100%);
                color: #ff6600;
                font-family: 'Courier New', monospace;
                text-align: center;
                padding-top: 5rem;
                overflow: hidden;
            }
            h2 {
                font-size: 2rem;
                text-shadow: 0 0 10px #ff6600, 0 0 20px #ff3300;
                animation: flicker 2s infinite alternate;
            }
            @keyframes flicker {
                from { opacity: 1; }
                to { opacity: 0.7; }
            }
            form {
                display: inline-block;
                background: rgba(255, 102, 0, 0.05);
                border: 1px solid #ff6600;
                border-radius: 8px;
                padding: 2rem;
                margin-top: 1rem;
                box-shadow: 0 0 15px #ff3300;
            }
            input {
                display: block;
                margin: 1rem auto;
                padding: 0.5rem;
                width: 250px;
                border: 1px solid #ff6600;
                border-radius: 4px;
                background: #111;
                color: #ffcc66;
                text-align: center;
            }
            button {
                background: #ff6600;
                color: #000;
                border: none;
                padding: 0.75rem 2rem;
                border-radius: 4px;
                font-weight: bold;
                cursor: pointer;
                transition: background 0.3s;
            }
            button:hover {
                background: #ffaa00;
                color: #111;
                box-shadow: 0 0 15px #ff6600;
            }
            a {
                color: #ff9933;
                text-decoration: none;
            }
            a:hover {
                text-decoration: underline;
            }
            .bat {
                position: absolute;
                top: 20px;
                left: -60px;
                font-size: 60px;
                animation: fly 10s linear infinite;
            }
            @keyframes fly {
                0% { left: -60px; transform: rotate(0deg); }
                50% { left: 50%; transform: rotate(10deg); }
                100% { left: 110%; transform: rotate(0deg); }
            }
        </style>
    </head>
    <body>
        <div class="bat">🦇</div>
        <h2>🕸️ PartyPrint Admin Login 🕸️</h2>
        <form method="POST">
            <input name="email" placeholder="Email of the Initiate">
            <input name="password" type="password" placeholder="Secret Spell">
            <button type="submit">Enter the Portal</button>
        </form>
        <p><a href="/register">New spirit? Register here</a></p>
    </body>
    </html>
    """)


@app.route("/logout")
@login_required
def logout():
    app.logger.info(f"Admin logged out: {current_user.email}")
    logout_user()
    return redirect(url_for("login"))

# ------------------------------------------------------------------
# Dashboard (protected)
# ------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>PartyPrint Admin Dashboard</title>
        <style>
            body {{
                background:#0b0b0b;
                color:#0f0;
                font-family:monospace;
                padding:1rem;
                overflow:hidden;
            }}
            h2 {{
                color:#ff6600;
                text-shadow:0 0 10px #ff6600;
            }}
            #log {{
                background:#000;
                border:1px solid #222;
                padding:1rem;
                height:80vh;
                overflow-y:scroll;
                white-space:pre-wrap;
                line-height:1.3;
            }}
            #controls {{
                margin-top:0.5rem;
            }}
            button {{
                background:#ff6600;
                border:none;
                padding:0.5rem 1rem;
                color:#000;
                font-weight:bold;
                border-radius:4px;
                cursor:pointer;
            }}
            button:hover {{
                background:#ffaa00;
            }}
        </style>
    </head>
    <body>
        <h2>🎃 Welcome, {current_user.email}</h2>
        <a href='/logout' style='color:#ff9933;'>Logout</a>
        <pre id="log"></pre>
        <div id="controls">
            <button id="jumpBottom" style="display:none;">Jump to Bottom</button>
        </div>

        <script>
          const logEl = document.getElementById("log");
          const jumpBtn = document.getElementById("jumpBottom");
          let autoScroll = true;

          // Detect manual scroll
          logEl.addEventListener("scroll", () => {{
              const nearBottom = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 20;
              if (!nearBottom) {{
                  autoScroll = false;
                  jumpBtn.style.display = "inline-block";
              }} else {{
                  autoScroll = true;
                  jumpBtn.style.display = "none";
              }}
          }});

          jumpBtn.addEventListener("click", () => {{
              logEl.scrollTop = logEl.scrollHeight;
              autoScroll = true;
              jumpBtn.style.display = "none";
          }});

          // Stream logs via SSE
          const evt = new EventSource("/stream_logs");
          evt.onmessage = e => {{
              logEl.textContent += e.data + "\\n";
              if (autoScroll) {{
                  logEl.scrollTop = logEl.scrollHeight;
              }}
          }};
        </script>
    </body>
    </html>
    """
    return render_template_string(html)


# ------------------------------------------------------------------
# Live log stream (SSE)
# ------------------------------------------------------------------
@app.route("/stream_logs")
@login_required
def stream_logs():
    def generate():
        if not os.path.exists(LOG_PATH):
            yield "data: (No log file found)\n\n"
            return
        with open(LOG_PATH, "r") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if line:
                    yield f"data: {line.strip()}\n\n"
                time.sleep(0.5)
    return Response(generate(), mimetype="text/event-stream")

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5051, debug=False)
