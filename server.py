import os
import io
import json
import requests

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

import mammoth
from docx import Document

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload


# ================== APP ==================

app = Flask(__name__)
CORS(app)


# ================== GOOGLE DRIVE SETUP ==================

SCOPES = ["https://www.googleapis.com/auth/drive"]

SERVICE_ACCOUNT_INFO = json.loads(
    os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
)

credentials = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO, scopes=SCOPES
)

drive = build("drive", "v3", credentials=credentials)

ROOT_FOLDER_NAME = "Malwa_RIS_Reports"


def get_or_create_folder(name, parent_id=None):
    query = (
        f"name='{name}' and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"trashed=false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"

    res = drive.files().list(
        q=query,
        fields="files(id,name)"
    ).execute()

    files = res.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = drive.files().create(
        body=metadata,
        fields="id"
    ).execute()

    return folder["id"]


ROOT_FOLDER_ID = get_or_create_folder(ROOT_FOLDER_NAME)


# ================== ROUTES ==================

@app.route("/")
def home():
    return "Malwa RIS backend running"


# ---------- TEMPLATE FROM GITHUB URL ----------

@app.route("/api/template_from_url", methods=["POST"])
def template_from_url():
    try:
        data = request.get_json()
        url = data.get("url")

        if not url:
            return jsonify({"error": "URL missing"}), 400

        r = requests.get(url, timeout=20)
        r.raise_for_status()

        docx_bytes = io.BytesIO(r.content)

        result = mammoth.convert_to_html(docx_bytes)
        html = result.value

        return jsonify({"html": html})

    except Exception as e:
        print("TEMPLATE_FROM_URL ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


# ---------- UPLOAD WORD → HTML ----------

@app.route("/api/word_to_html", methods=["POST"])
def word_to_html():
    try:
        file = request.files["file"]
        docx_bytes = io.BytesIO(file.read())

        result = mammoth.convert_to_html(docx_bytes)
        html = result.value

        return jsonify({"html": html})

    except Exception as e:
        print("WORD_TO_HTML ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


# ---------- SAVE REPORT TO GOOGLE DRIVE ----------

@app.route("/api/save_report", methods=["POST"])
def save_report():
    data = request.json

    patient = data["patient_name"]
    uhid = data["uhid"]
    modality = data["modality"]
    html = data["html"]

    modality_folder_id = get_or_create_folder(modality, ROOT_FOLDER_ID)

    doc = Document()
    doc.add_paragraph(f"Patient: {patient} | UHID: {uhid} | Modality: {modality}")
    doc.add_paragraph("")

    # Very simple HTML → text (safe & predictable)
    text = (
        html.replace("<br>", "\n")
            .replace("<p>", "")
            .replace("</p>", "\n")
            .replace("&nbsp;", " ")
    )

    for line in text.split("\n"):
        if line.strip():
            doc.add_paragraph(line.strip())

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    filename = f"{patient}_{uhid}_{modality}.docx".replace(" ", "_")

    media = MediaIoBaseUpload(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    drive.files().create(
        body={
            "name": filename,
            "parents": [modality_folder_id]
        },
        media_body=media,
        fields="id"
    ).execute()

    return jsonify({"status": "saved"})


# ---------- FETCH REPORT LIST ----------

@app.route("/api/reports", methods=["GET"])
def fetch_reports():
    results = []

    for modality in ["CT", "MRI", "XRAY", "USG"]:
        folder_id = get_or_create_folder(modality, ROOT_FOLDER_ID)

        files = drive.files().list(
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


# ---------- DOWNLOAD WORD ----------

@app.route("/api/download_word/<file_id>")
def download_word(file_id):
    request_drive = drive.files().get_media(fileId=file_id)

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


# ================== RUN ==================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


