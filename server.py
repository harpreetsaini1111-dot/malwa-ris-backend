import os
import io
import time
import html

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from google.cloud import storage

from docx import Document
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

# =========================================================
# APP
# =========================================================
app = Flask(__name__)
CORS(app)

# =========================================================
# GCS SETUP
# =========================================================
BUCKET_NAME = os.environ.get("GCS_BUCKET")
if not BUCKET_NAME:
    raise RuntimeError("GCS_BUCKET environment variable not set")

client = storage.Client()
bucket = client.bucket(BUCKET_NAME)

# =========================================================
# HELPERS
# =========================================================
def auto_name(path: str) -> str:
    """Auto-rename file if it already exists"""
    blob = bucket.blob(path)
    if not blob.exists():
        return path
    base, ext = os.path.splitext(path)
    return f"{base}_{int(time.time())}{ext}"

def upload_bytes(path: str, data: bytes, content_type: str):
    path = auto_name(path)
    blob = bucket.blob(path)
    blob.upload_from_string(
        data,
        content_type=content_type or "application/octet-stream"
    )
    return path

def html_to_docx(html_text: str) -> bytes:
    """Used ONLY for reports created inside the editor"""
    doc = Document()
    for line in html_text.replace("<br>", "\n").split("\n"):
        doc.add_paragraph(line)
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.read()

def html_to_pdf(html_text: str) -> bytes:
    bio = io.BytesIO()
    styles = getSampleStyleSheet()
    pdf = SimpleDocTemplate(bio)
    pdf.build([Paragraph(html_text, styles["Normal"])])
    bio.seek(0)
    return bio.read()

def docx_to_html(file_obj) -> str:
    """Convert DOCX template to simple HTML for editor"""
    doc = Document(file_obj)
    blocks = []
    for p in doc.paragraphs:
        text = html.escape(p.text)
        if text.strip():
            blocks.append(f"<p>{text}</p>")
    return "\n".join(blocks)

# =========================================================
# BASIC
# =========================================================
@app.route("/")
def home():
    return "SERVER RUNNING", 200

# =========================================================
# SAVE REPORT (EDITOR → DOCX)
# =========================================================
@app.route("/save_report", methods=["POST"])
def save_report():
    d = request.json

    modality = d["modality"]
    patient = d.get("patient_name", "UNKNOWN").replace(" ", "_")
    date = d.get("date", "")
    html_text = d.get("content", "")

    filename = f"{patient}_{date}.docx"
    path = f"reports/{modality}/{filename}"

    saved = upload_bytes(
        path,
        html_to_docx(html_text),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    return jsonify({"saved": [saved], "skipped": []})

# =========================================================
# SAVE TEMPLATE (EDITOR HTML)
# =========================================================
@app.route("/save_template", methods=["POST"])
def save_template():
    d = request.json
    modality = d["modality"]
    name = d["name"].replace(" ", "_") + ".html"

    path = f"templates/{modality}/{name}"
    saved = upload_bytes(
        path,
        d["content"].encode("utf-8"),
        "text/html"
    )

    return jsonify({"saved": [saved], "skipped": []})

# =========================================================
# LIST TEMPLATES
# =========================================================
@app.route("/list_templates")
def list_templates():
    modality = request.args.get("modality")
    prefix = f"templates/{modality}/"

    templates = [
        b.name.split("/")[-1]
        for b in bucket.list_blobs(prefix=prefix)
        if not b.name.endswith("/")
    ]

    return jsonify({"templates": templates})

# =========================================================
# LOAD TEMPLATE (HTML ONLY)
# =========================================================
@app.route("/load_template")
def load_template():
    modality = request.args["modality"]
    filename = request.args["filename"]

    blob = bucket.blob(f"templates/{modality}/{filename}")
    return jsonify({"content": blob.download_as_text()})

# =========================================================
# BATCH UPLOAD TEMPLATES (HTML + DOCX → HTML)
# =========================================================
@app.route("/batch_upload_templates", methods=["POST"])
def batch_upload_templates():
    modality = request.form["modality"]
    saved, skipped = [], []

    for f in request.files.getlist("files"):
        try:
            base = os.path.splitext(f.filename)[0]

            # HTML template
            if f.filename.lower().endswith(".html"):
                content = f.read().decode("utf-8", errors="ignore")
                path = f"templates/{modality}/{base}.html"
                saved.append(upload_bytes(path, content.encode("utf-8"), "text/html"))

            # DOCX template → convert to HTML
            elif f.filename.lower().endswith(".docx"):
                html_content = docx_to_html(f)
                path = f"templates/{modality}/{base}.html"
                saved.append(upload_bytes(path, html_content.encode("utf-8"), "text/html"))

            else:
                skipped.append({
                    "file": f.filename,
                    "reason": "Unsupported template format"
                })

        except Exception as e:
            skipped.append({
                "file": f.filename,
                "reason": str(e)
            })

    return jsonify({"saved": saved, "skipped": skipped})

# =========================================================
# BATCH UPLOAD REPORTS (RAW STORAGE – SAFE)
# =========================================================
@app.route("/batch_upload_reports_auto", methods=["POST"])
def batch_upload_reports_auto():
    modality = request.form["modality"]
    saved, skipped = [], []

    for f in request.files.getlist("files"):
        try:
            path = f"reports/{modality}/{f.filename}"
            saved.append(upload_bytes(
                path,
                f.read(),
                f.content_type
            ))
        except Exception as e:
            skipped.append({"file": f.filename, "reason": str(e)})

    return jsonify({"saved": saved, "skipped": skipped})

# =========================================================
# LIST REPORTS
# =========================================================
@app.route("/list_reports")
def list_reports():
    modality = request.args.get("modality")
    prefix = f"reports/{modality}/" if modality else "reports/"

    reports = []
    for b in bucket.list_blobs(prefix=prefix):
        if b.name.endswith("/"):
            continue
        reports.append({
            "filename": b.name.split("/")[-1],
            "path": b.name
        })

    return jsonify({"reports": reports})

# =========================================================
# DOWNLOAD REPORT
# =========================================================
@app.route("/download_report")
def download_report():
    path = request.args["path"]
    rtype = request.args.get("type", "docx")

    blob = bucket.blob(path)
    data = blob.download_as_bytes()

    if rtype == "pdf":
        pdf = html_to_pdf(data.decode(errors="ignore"))
        return send_file(
            io.BytesIO(pdf),
            as_attachment=True,
            download_name=os.path.basename(path).replace(".docx", ".pdf")
        )

    return send_file(
        io.BytesIO(data),
        as_attachment=True,
        download_name=os.path.basename(path)
    )

# =========================================================
# RUN (RENDER)
# =========================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)





