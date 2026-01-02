import os
import io
import json
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# ================= APP SETUP =================

app = Flask(__name__)
CORS(app)

# ================= GOOGLE CONFIG =================

SCOPES = ["https://www.googleapis.com/auth/drive"]

SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
if not SERVICE_ACCOUNT_JSON:
    raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON environment variable")

service_account_info = json.loads(SERVICE_ACCOUNT_JSON)

credentials = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=SCOPES
)

drive_service = build("drive", "v3", credentials=credentials)

DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")  # optional

# ================= ROOT (THIS IS THE FIX) =================

@app.route("/")
def root():
    return jsonify({
        "service": "Malwa RIS Backend",
        "status": "running",
        "endpoints": [
            "/health",
            "/upload",
            "/files",
            "/download/<file_id>"
        ]
    })

# ================= HEALTH CHECK =================

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# ================= UPLOAD FILE =================

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    filename = file.filename

    file_metadata = {"name": filename}
    if DRIVE_FOLDER_ID:
        file_metadata["parents"] = [DRIVE_FOLDER_ID]

    media = MediaIoBaseUpload(
        io.BytesIO(file.read()),
        mimetype=file.content_type,
        resumable=True
    )

    uploaded = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name"
    ).execute()

    return jsonify({
        "message": "File uploaded",
        "file_id": uploaded["id"],
        "file_name": uploaded["name"]
    })

# ================= LIST FILES =================

@app.route("/files", methods=["GET"])
def list_files():
    query = None
    if DRIVE_FOLDER_ID:
        query = f"'{DRIVE_FOLDER_ID}' in parents"

    results = drive_service.files().list(
        q=query,
        pageSize=50,
        fields="files(id, name, mimeType)"
    ).execute()

    return jsonify(results.get("files", []))

# ================= DOWNLOAD FILE =================

@app.route("/download/<file_id>", methods=["GET"])
def download_file(file_id):
    meta = drive_service.files().get(
        fileId=file_id,
        fields="name"
    ).execute()

    request_drive = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request_drive)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    fh.seek(0)

    return send_file(
        fh,
        as_attachment=True,
        download_name=meta["name"]
    )

# ================= RUN =================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)







