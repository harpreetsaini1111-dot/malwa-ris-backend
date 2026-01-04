import os
import io
import re
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from google.cloud import storage
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ================= APP =================
app = Flask(__name__)
CORS(app)

# ================= GCS =================
BUCKET_NAME = os.environ.get("GCS_BUCKET")
if not BUCKET_NAME:
    raise RuntimeError("GCS_BUCKET not set")

client = storage.Client()
bucket = client.bucket(BUCKET_NAME)

# ================= BASIC =================
@app.route("/")
def home():
    return "SERVER RUNNING", 200

@app.route("/health")
def health():
    return "OK", 200

# ================= HELPERS =================
def safe(text):
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in text)

def list_files(prefix):
    return [
        b.name
        for b in bucket.list_blobs(prefix=prefix)
        if not b.name.endswith("/")
    ]

def html_to_docx(html):
    doc = Document()
    for line in html.replace("<br>", "\n").split("\n"):
        doc.add_paragraph(line)
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio

def html_to_pdf(html):
    bio = io.BytesIO()
    c = canvas.Canvas(bio, pagesize=A4)
    text = c.beginText(40, 800)
    for line in html.replace("<br>", "\n").split("\n"):
        text.textLine(line)
    c.drawText(text)
    c.showPage()
    c.save()
    bio.seek(0)
    return bio

def extract_patient_details(text):
    name = pid = date = None

    patterns = {
        "name": r"(patient\s*name|name\s*of\s*patient)\s*[:\-]\s*(.+)",
        "pid": r"(patient\s*(id|uhid)|uhid)\s*[:\-]\s*(.+)",
        "date": r"(date|study\s*date)\s*[:\-]\s*(\d{2}[-/]\d{2}[-/]\d{4})"
    }

    for line in text.splitlines():
        if not name:
            m = re.search(patterns["name"], line, re.I)
            if m:
                name = m.group(2).strip()
        if not pid:
            m = re.search(patterns["pid"], line, re.I)
            if m:
                pid = m.group(3).strip()
        if not date:
            m = re.search(patterns["date"], line, re.I)
            if m:
                date = m.group(3).replace("/", "-")

    return name, pid, date

# =================================================
# SAVE REPORT (EDITOR)
# =================================================
@app.route("/save_report", methods=["POST"])
def save_report():
    d = request.get_json(force=True)

    modality = d.get("modality", "").upper()
    name = d.get("patient_name")
    pid = d.get("patient_id")
    date = d.get("date")
    content = d.get("content")

    if not all([modality, name, pid, date, content]):
        return jsonify({"error": "missing report fields"}), 400

    dt = datetime.fromisoformat(date)
    fname = f"{safe(name)}_{safe(pid)}_{dt.strftime('%Y%m%d')}.html"
    path = f"reports/{modality}/{dt.year}/{dt.month:02d}/{fname}"

    bucket.blob(path).upload_from_string(content, content_type="text/html")

    return jsonify({"status": "saved", "path": path}), 200

# =================================================
# BATCH UPLOAD REPORTS
# =================================================
@app.route("/batch_upload_reports_auto", methods=["POST"])
def batch_upload_reports_auto():
    modality = request.form.get("modality", "").upper()
    files = request.files.getlist("files")

    if not modality or not files:
        return jsonify({"error": "modality and files required"}), 400

    saved, skipped = [], []

    for f in files:
        text = ""

        if f.filename.lower().endswith(".docx"):
            doc = Document(f)
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        elif f.filename.lower().endswith(".html"):
            text = f.read().decode("utf-8")
        else:
            skipped.append(f.filename)
            continue

        name, pid, date_str = extract_patient_details(text)
        if not all([name, pid, date_str]):
            skipped.append(f.filename)
            continue

        try:
            dt = datetime.strptime(date_str, "%d-%m-%Y")
        except ValueError:
            skipped.append(f.filename)
            continue

        fname = f"{safe(name)}_{safe(pid)}_{dt.strftime('%Y%m%d')}.html"
        path = f"reports/{modality}/{dt.year}/{dt.month:02d}/{fname}"

        html = text.replace("\n", "<br>")
        bucket.blob(path).upload_from_string(html, content_type="text/html")
        saved.append(path)

    return jsonify({
        "status": "uploaded",
        "count": len(saved),
        "saved": saved,
        "skipped": skipped
    }), 200

# =================================================
# LIST REPORTS  ✅ FIXED
# =================================================
@app.route("/list_reports")
def list_reports():
    modality = request.args.get("modality", "").upper()
    name = request.args.get("name", "").lower()
    date = request.args.get("date", "").replace("-", "")

    # ✅ FIX: correct prefix handling
    prefix = "reports/"
    if modality:
        prefix = f"reports/{modality}/"

    files = list_files(prefix)
    reports = []

    for p in files:
        fn = p.split("/")[-1]
        if name and name not in fn.lower():
            continue
        if date and date not in fn:
            continue
        reports.append({
            "filename": fn,
            "path": p
        })

    return jsonify({"reports": reports}), 200

# =================================================
# DOWNLOAD REPORT
# =================================================
@app.route("/download_report")
def download_report():
    path = request.args.get("path")
    typ = request.args.get("type")

    blob = bucket.blob(path)
    if not blob.exists():
        return jsonify({"error": "not found"}), 404

    html = blob.download_as_text()
    base = os.path.splitext(os.path.basename(path))[0]

    if typ == "docx":
        return send_file(
            html_to_docx(html),
            as_attachment=True,
            download_name=f"{base}.docx"
        )

    if typ == "pdf":
        return send_file(
            html_to_pdf(html),
            as_attachment=True,
            download_name=f"{base}.pdf"
        )

    return jsonify({"error": "invalid type"}), 400

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)






