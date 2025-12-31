from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import requests
import mammoth
import io
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from docx import Document

app = Flask(__name__)
CORS(app)

# ===================== GOOGLE DRIVE SETUP =====================

SCOPES = ["https://www.googleapis.com/auth/drive"]

SERVICE_ACCOUNT_INFO = json.loads(
    os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
)

credentials = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO, scopes=SCOPES
)

drive_service = build("drive", "v3", credentials=credentials)

ROOT_FOLDER_NAME = "Malwa_RIS_Reports"

def get_or_create_folder(name, parent_id=None):
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    res = drive_service.files().list(q=query, fields="files(id)").execute()
    files = res.get("files", [])

    if files:
        return files[0]["id"]

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = drive_service.files().create(
        body=metadata, fields="id"
    ).execute()

    return folder["id"]

ROOT_FOLDER_ID = get_or_create_folder(ROOT_FOLDER_NAME)

# ===================== TEMPLATE FROM GITHUB =====================

@app.route("/api/template_from_url", methods=["POST"])
def template_from_url():
    try:
        url = request.json.get("url")
        r = requests.get(url, timeout=20)
        r.raise_for_status()

        docx = io.BytesIO(r.content)
        result = mammoth.convert_to_html(docx)

        return jsonify({"html": result.value})

    except Exception as e:
        print("TEMPLATE LOAD ERROR:", e)
        return jsonify({"error": str(e)}), 500

# ===================== WORD → HTML =====================

@app.route("/api/word_to_html", methods=["POST"])
def word_to_html():
    try:
        f = request.files["file"]
        docx = io.BytesIO(f.read())
        result = mammoth.convert_to_html(docx)
        return jsonify({"html": result.value})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===================== SAVE REPORT =====================

@app.route("/api/save_report", methods=["POST"])
def save_report():
    data = request.json

    patient = data["patient_name"]
    uhid = data["uhid"]
    modality = data["modality"]
    html = data["html"]

    modality_folder = get_or_create_folder(modality, ROOT_FOLDER_ID)

    doc = Document()
    doc.add_paragraph("", style=None)
    doc.add_paragraph(html.replace("<br>", "\n"))

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    filename = f"{patient}_{uhid}.docx"

    media = MediaIoBaseUpload(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    file_metadata = {
        "name": filename,
        "parents": [modality_folder]
    }

    drive_service.files().create(
        body=file_metadata,
        media_body=media
    ).execute()

    return jsonify({"status": "saved"})

# ===================== FETCH REPORTS =====================

@app.route("/api/reports", methods=["GET"])
def fetch_reports():
    results = []

    for modality in ["CT", "MRI", "XRAY", "USG"]:
        folder_id = get_or_create_folder(modality, ROOT_FOLDER_ID)
        files = drive_service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id,name)"
        ).execute().get("files", [])

        for f in files:
            results.append({
                "id": f["id"],
                "filename": f["name"],
                "modality": modality
            })

    return jsonify(results)

# ===================== DOWNLOAD WORD =====================

@app.route("/api/download_word/<file_id>")
def download_word(file_id):
    request_drive = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request_drive)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    fh.seek(0)
    return send_file(
        fh,
        as_attachment=True,
        download_name="report.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

# ===================== RUN =====================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)


