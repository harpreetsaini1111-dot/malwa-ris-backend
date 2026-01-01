import os
import io
import requests
import mammoth

from flask import Flask, request, jsonify, redirect, send_file
from flask_cors import CORS

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from docx import Document

# ================= APP SETUP =================

app = Flask(__name__)
CORS(app)

# ================= ENV VARIABLES =================

CLIENT_ID = os.getenv("919763430938-9cuvvfi9m259890lveqrlua3rqtamob8.apps.googleusercontent.com")
CLIENT_SECRET = os.getenv("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")
REDIRECT_URI = os.getenv("https://malwa-ris-backend.onrender.com/oauth2callback")

missing = []
if not CLIENT_ID:
    missing.append("919763430938-9cuvvfi9m259890lveqrlua3rqtamob8.apps.googleusercontent.com")
if not CLIENT_SECRET:
    missing.append("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")
if not REDIRECT_URI:
    missing.append("https://malwa-ris-backend.onrender.com/oauth2callback")

if missing:
    raise RuntimeError("Missing environment variables: " + ", ".join(missing))

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

credentials = None  # stored in memory (single-user demo style)

# ================= ROOT =================

@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "service": "Malwa RIS Backend",
        "message": "Server is running"
    })

# ================= OAUTH =================

def get_oauth_flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id": "919763430938-9cuvvfi9m259890lveqrlua3rqtamob8.apps.googleusercontent.com",
                "client_secret": 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,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["https://malwa-ris-backend.onrender.com/oauth2callback"],
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

@app.route("/login")
def login():
    flow = get_oauth_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent"
    )
    return redirect(auth_url)

@app.route("/oauth2callback")
def oauth2callback():
    global credentials
    flow = get_oauth_flow()
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    return "Login successful. You can close this tab."

def get_drive():
    if not credentials:
        raise RuntimeError("User not logged in")
    return build("drive", "v3", credentials=credentials)

# ================= TEMPLATE LOAD =================

@app.route("/api/template_from_url", methods=["POST"])
def template_from_url():
    url = request.json["url"]
    r = requests.get(url)
    html = mammoth.convert_to_html(io.BytesIO(r.content)).value
    return jsonify({"html": html})

@app.route("/api/word_to_html", methods=["POST"])
def word_to_html():
    f = request.files["file"]
    html = mammoth.convert_to_html(io.BytesIO(f.read())).value
    return jsonify({"html": html})

# ================= SAVE REPORT =================

@app.route("/api/save_report", methods=["POST"])
def save_report():
    if not credentials:
        return jsonify({"login_required": True}), 401

    data = request.json
    drive = get_drive()

    doc = Document()
    text = data["html"].replace("<p>", "").replace("</p>", "\n")
    for line in text.split("\n"):
        if line.strip():
            doc.add_paragraph(line)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    media = MediaIoBaseUpload(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    file = drive.files().create(
        body={
            "name": f"{data['patient_name']}_{data['uhid']}.docx"
        },
        media_body=media,
        fields="id"
    ).execute()

    return jsonify({"status": "saved", "file_id": file["id"]})

# ================= LIST REPORTS =================

@app.route("/api/reports")
def reports():
    if not credentials:
        return jsonify([])

    drive = get_drive()
    files = drive.files().list(
        q="trashed=false",
        fields="files(id,name)"
    ).execute()["files"]

    return jsonify(files)

# ================= DOWNLOAD =================

@app.route("/api/download_word/<file_id>")
def download_word(file_id):
    drive = get_drive()
    request_drive = drive.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    MediaIoBaseDownload(fh, request_drive).next_chunk()
    fh.seek(0)

    return send_file(
        fh,
        as_attachment=True,
        download_name="report.docx"
    )

# ================= RUN =================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )




