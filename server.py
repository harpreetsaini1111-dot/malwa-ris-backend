import os
import io
import requests
import mammoth

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from docx import Document

# ================= APP SETUP =================

app = Flask(__name__)
CORS(app)

# ================= GOOGLE DRIVE SETUP =================

SCOPES = ["https://www.googleapis.com/auth/drive"]

CREDS_PATH = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
DRIVE_ROOT_ID = os.environ["DRIVE_ROOT_ID"]

creds = service_account.Credentials.from_service_account_file(
    CREDS_PATH,
    scopes=SCOPES
)

drive = build("drive", "v3", credentials=creds)

# ================= ROOT =================

@app.route("/")
def home():
    return jsonify({"status": "ok", "service": "Malwa RIS Backend"})

# ================= WORD → HTML =================

@app.route("/api/word_to_html", methods=["POST"])
def word_to_html():
    f = request.files["file"]
    html = mammoth.convert_to_html(io.BytesIO(f.read())).value
    return jsonify({"html": html})

# ================= SAVE REPORT =================

@app.route("/api/save_report", methods=["POST"])
def save_report():
    data = request.json

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

    filename = f"{data['patient_name']}_{data['uhid']}_{data['date']}.docx"

    file = drive.files().create(
        body={
            "name": filename,
            "parents": [DRIVE_ROOT_ID]
        },
        media_body=media,
        fields="id"
    ).execute()

    return jsonify({"status": "saved", "id": file["id"]})

# ================= LIST REPORTS =================

@app.route("/api/reports")
def reports():
    q = "trashed=false"

    files = drive.files().list(
        q=q,
        fields="files(id,name)"
    ).execute().get("files", [])

    out = []
    for f in files:
        parts = f["name"].rsplit("_", 2)
        if len(parts) == 3:
            out.append({
                "id": f["id"],
                "patient_name": parts[0],
                "uhid": parts[1],
                "date": parts[2].replace(".docx", ""),
                "modality": "—"
            })

    return jsonify(out)

# ================= DOWNLOAD =================

@app.route("/api/download_word/<file_id>")
def download_word(file_id):
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
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))





