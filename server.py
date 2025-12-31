from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import uuid
import datetime
import io
import requests

from docx import Document
import mammoth
from bs4 import BeautifulSoup

# ---------------- BASIC APP SETUP ----------------

app = Flask(__name__)
CORS(app)

# Use Render persistent disk if available
BASE_STORAGE = "/data/reports" if os.path.exists("/data") else "storage/reports"
os.makedirs(BASE_STORAGE, exist_ok=True)

# Simple in-memory index (OK for now)
REPORT_INDEX = {}

# ---------------- HEALTH CHECK ----------------

@app.route("/")
def home():
    return "Malwa RIS backend running"

# ---------------- WORD TEMPLATE FROM GITHUB URL ----------------

@app.route("/api/template_from_url", methods=["POST"])
def template_from_url():
    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({"error": "Template URL missing"}), 400

    r = requests.get(url)
    if r.status_code != 200:
        return jsonify({"error": "Failed to download template"}), 400

    with mammoth.convert_to_html(io.BytesIO(r.content)) as result:
        html = result.value

    return jsonify({"html": html})

# ---------------- UPLOAD WORD FILE → HTML ----------------

@app.route("/api/word_to_html", methods=["POST"])
def word_to_html():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    with mammoth.convert_to_html(file) as result:
        html = result.value

    return jsonify({"html": html})

# ---------------- SAVE REPORT (HTML → DOCX) ----------------

@app.route("/api/save_report", methods=["POST"])
def save_report():
    data = request.json

    patient = data.get("patient_name", "Unknown")
    uhid = data.get("uhid", "NA")
    modality = data.get("modality", "GEN").upper()
    study = data.get("study", "Report")
    html = data.get("html", "")

    report_id = str(uuid.uuid4())
    year = str(datetime.datetime.now().year)

    modality_dir = os.path.join(BASE_STORAGE, modality, year)
    os.makedirs(modality_dir, exist_ok=True)

    filename = (
        f"{patient}_{uhid}_{modality}_{study}_{datetime.date.today()}.docx"
        .replace(" ", "_")
    )

    filepath = os.path.join(modality_dir, filename)

    doc = Document()

    # Header info (NOT hospital name)
    doc.add_paragraph(
        f"Patient Name: {patient}    "
        f"UHID: {uhid}    "
        f"Modality: {modality}"
    )
    doc.add_paragraph("")

    soup = BeautifulSoup(html, "html.parser")

    for p in soup.find_all(["p", "li"]):
        text = p.get_text(" ").strip()
        if text:
            doc.add_paragraph(text)

    doc.save(filepath)

    REPORT_INDEX[report_id] = {
        "id": report_id,
        "patient": patient,
        "uhid": uhid,
        "modality": modality,
        "study": study,
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "path": filepath
    }

    return jsonify({"id": report_id})

# ---------------- FETCH SAVED REPORTS ----------------

@app.route("/api/reports")
def fetch_reports():
    return jsonify(list(REPORT_INDEX.values()))

# ---------------- DOWNLOAD WORD REPORT ----------------

@app.route("/api/download_word/<rid>")
def download_word(rid):
    report = REPORT_INDEX.get(rid)

    if not report:
        return "Report not found", 404

    path = report["path"]

    if not os.path.exists(path):
        return "File missing on server", 404

    return send_file(path, as_attachment=True)

# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

