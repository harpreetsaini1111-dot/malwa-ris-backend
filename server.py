import os, io, time
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from google.cloud import storage
from docx import Document
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

# ================= APP =================
app = Flask(__name__)
CORS(app)

# ================= GCS =================
BUCKET_NAME = os.environ.get("GCS_BUCKET")
if not BUCKET_NAME:
    raise RuntimeError("GCS_BUCKET not set")

client = storage.Client()
bucket = client.bucket(BUCKET_NAME)

# ================= HELPERS =================
def auto_name(path):
    blob = bucket.blob(path)
    if not blob.exists():
        return path
    base, ext = os.path.splitext(path)
    return f"{base}_{int(time.time())}{ext}"

def upload_bytes(path, data, content_type):
    path = auto_name(path)
    blob = bucket.blob(path)
    blob.upload_from_string(data, content_type=content_type)
    return path

def html_to_docx(html):
    doc = Document()
    for line in html.replace("<br>", "\n").split("\n"):
        doc.add_paragraph(line)
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.read()

def html_to_pdf(html):
    bio = io.BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(bio)
    doc.build([Paragraph(html, styles["Normal"])])
    bio.seek(0)
    return bio.read()

# ================= BASIC =================
@app.route("/")
def home():
    return "SERVER RUNNING", 200

# ================= SAVE REPORT =================
@app.route("/save_report", methods=["POST"])
def save_report():
    d = request.json
    modality = d["modality"]
    name = d["patient_name"].replace(" ", "_")
    date = d["date"]
    html = d["content"]

    filename = f"{name}_{date}.docx"
    path = f"reports/{modality}/{filename}"

    saved = upload_bytes(
        path,
        html_to_docx(html),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    return jsonify({"saved": [saved], "skipped": []})

# ================= SAVE TEMPLATE =================
@app.route("/save_template", methods=["POST"])
def save_template():
    d = request.json
    modality = d["modality"]
    name = d["name"].replace(" ", "_") + ".html"
    path = f"templates/{modality}/{name}"

    saved = upload_bytes(path, d["content"], "text/html")
    return jsonify({"saved": [saved], "skipped": []})

# ================= LIST TEMPLATES =================
@app.route("/list_templates")
def list_templates():
    modality = request.args.get("modality")
    prefix = f"templates/{modality}/"

    files = [
        b.name.split("/")[-1]
        for b in bucket.list_blobs(prefix=prefix)
        if not b.name.endswith("/")
    ]
    return jsonify({"templates": files})

# ================= LOAD TEMPLATE =================
@app.route("/load_template")
def load_template():
    modality = request.args["modality"]
    filename = request.args["filename"]
    blob = bucket.blob(f"templates/{modality}/{filename}")
    return jsonify({"content": blob.download_as_text()})

# ================= BATCH UPLOAD TEMPLATES =================
@app.route("/batch_upload_templates", methods=["POST"])
def batch_upload_templates():
    modality = request.form["modality"]
    saved, skipped = [], []

    for f in request.files.getlist("files"):
        try:
            path = f"templates/{modality}/{f.filename}"
            saved.append(upload_bytes(
                path,
                f.read(),
                f.content_type or "application/octet-stream"
            ))
        except Exception as e:
            skipped.append({"file": f.filename, "reason": str(e)})

    return jsonify({"saved": saved, "skipped": skipped})

# ================= BATCH UPLOAD REPORTS (FIXED) =================
@app.route("/batch_upload_reports_auto", methods=["POST"])
def batch_upload_reports_auto():
    modality = request.form["modality"]
    saved, skipped = [], []

    for f in request.files.getlist("files"):
        try:
            # DO NOT parse DOCX files. Ever.
            path = f"reports/{modality}/{f.filename}"
            saved.append(upload_bytes(
                path,
                f.read(),
                f.content_type or "application/octet-stream"
            ))
        except Exception as e:
            skipped.append({"file": f.filename, "reason": str(e)})

    return jsonify({"saved": saved, "skipped": skipped})

# ================= LIST REPORTS =================
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

# ================= DOWNLOAD REPORT =================
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






