import os
import io
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
    out = []
    for blob in bucket.list_blobs(prefix=prefix):
        if not blob.name.endswith("/"):
            out.append(blob.name)
    return out

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

# =================================================
# REPORTS
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

    return jsonify({
        "status": "saved",
        "filename": fname,
        "path": path
    }), 200


@app.route("/list_reports", methods=["GET"])
def list_reports():
    modality = request.args.get("modality", "").upper()
    name = request.args.get("name", "").lower()
    date = request.args.get("date", "").replace("-", "")

    prefix = f"reports/{modality}/"
    blobs = list_files(prefix)

    reports = []
    for p in blobs:
        fn = p.split("/")[-1]
        if name and name not in fn.lower():
            continue
        if date and date not in fn:
            continue
        reports.append({"filename": fn, "path": p})

    return jsonify({"reports": reports}), 200


@app.route("/download_report", methods=["GET"])
def download_report():
    path = request.args.get("path")
    typ = request.args.get("type")

    blob = bucket.blob(path)
    if not blob.exists():
        return jsonify({"error": "not found"}), 404

    html = blob.download_as_text()

    if typ == "docx":
        return send_file(html_to_docx(html),
                         as_attachment=True,
                         download_name="report.docx")

    if typ == "pdf":
        return send_file(html_to_pdf(html),
                         as_attachment=True,
                         download_name="report.pdf")

    return jsonify({"error": "invalid type"}), 400

# =================================================
# TEMPLATES
# =================================================
@app.route("/save_template", methods=["POST"])
def save_template():
    d = request.get_json(force=True)
    modality = d.get("modality", "").upper()
    content = d.get("content")

    if not modality or not content:
        return jsonify({"error": "missing template fields"}), 400

    fname = f"template_{int(datetime.utcnow().timestamp())}.html"
    path = f"templates/{modality}/{fname}"

    bucket.blob(path).upload_from_string(content, content_type="text/html")

    return jsonify({
        "status": "saved",
        "filename": fname,
        "path": path
    }), 200


@app.route("/list_templates", methods=["GET"])
def list_templates():
    modality = request.args.get("modality", "").upper()
    files = list_files(f"templates/{modality}/")
    return jsonify({"templates": [f.split("/")[-1] for f in files]}), 200


@app.route("/load_template", methods=["GET"])
def load_template():
    modality = request.args.get("modality", "").upper()
    filename = request.args.get("filename")

    path = f"templates/{modality}/{filename}"
    blob = bucket.blob(path)

    if not blob.exists():
        return jsonify({"error": "not found"}), 404

    return jsonify({"content": blob.download_as_text()}), 200


@app.route("/batch_upload_templates", methods=["POST"])
def batch_upload_templates():
    modality = request.form.get("modality", "").upper()
    files = request.files.getlist("files")

    if not modality or not files:
        return jsonify({"error": "modality and files required"}), 400

    saved = []

    for f in files:
        name = f.filename.lower()

        if name.endswith(".docx"):
            doc = Document(f)
            html = "<br>".join(p.text for p in doc.paragraphs if p.text.strip())
            fname = f.filename.replace(".docx", ".html")

        elif name.endswith(".html"):
            html = f.read().decode("utf-8")
            fname = f.filename

        else:
            continue

        path = f"templates/{modality}/{fname}"
        bucket.blob(path).upload_from_string(html, content_type="text/html")
        saved.append(fname)

    return jsonify({
        "status": "uploaded",
        "count": len(saved),
        "files": saved
    }), 200

# =================================================
# EDITOR EXPORT
# =================================================
@app.route("/export_docx", methods=["POST"])
def export_docx():
    html = request.get_json(force=True).get("html", "")
    return send_file(html_to_docx(html),
                     as_attachment=True,
                     download_name="report.docx")


@app.route("/export_pdf", methods=["POST"])
def export_pdf():
    html = request.get_json(force=True).get("html", "")
    return send_file(html_to_pdf(html),
                     as_attachment=True,
                     download_name="report.pdf")

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)




