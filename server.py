import os, io, re
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
    return [b.name for b in bucket.list_blobs(prefix=prefix) if not b.name.endswith("/")]

def strip_html(html):
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</p>|</div>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "", html)
    return html

def html_to_docx(html):
    doc = Document()
    for line in strip_html(html).splitlines():
        if line.strip():
            doc.add_paragraph(line)
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio

def html_to_pdf(html):
    bio = io.BytesIO()
    c = canvas.Canvas(bio, pagesize=A4)
    width, height = A4
    y = height - 40

    for line in strip_html(html).splitlines():
        if y < 40:
            c.showPage()
            y = height - 40
        c.drawString(40, y, line)
        y -= 14

    c.save()
    bio.seek(0)
    return bio

# =================================================
# SAVE REPORT
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
        return jsonify({"error": "missing fields"}), 400

    dt = datetime.fromisoformat(date)
    fname = f"{safe(name)}_{safe(pid)}_{dt.strftime('%Y%m%d')}.html"
    path = f"reports/{modality}/{dt.year}/{dt.month:02d}/{fname}"

    bucket.blob(path).upload_from_string(content, content_type="text/html")
    return jsonify({"status": "saved", "path": path})

# =================================================
# BATCH UPLOAD REPORTS
# =================================================
@app.route("/batch_upload_reports_auto", methods=["POST"])
def batch_upload_reports_auto():
    modality = request.form.get("modality", "").upper()
    files = request.files.getlist("files")

    saved, skipped = [], []

    for f in files:
        html = None

        if f.filename.lower().endswith(".docx"):
            doc = Document(f)
            raw = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            html = raw.replace("\n", "<br>")
        elif f.filename.lower().endswith(".html"):
            html = f.read().decode("utf-8")
        else:
            skipped.append(f.filename)
            continue

        text = strip_html(html)
        m_name = re.search(r"name\s*[:\-]\s*(.+)", text, re.I)
        m_pid = re.search(r"(id|uhid)\s*[:\-]\s*(.+)", text, re.I)
        m_date = re.search(r"(\d{2}[-/]\d{2}[-/]\d{4})", text)

        if not all([m_name, m_pid, m_date]):
            skipped.append(f.filename)
            continue

        name = m_name.group(1).strip()
        pid = m_pid.group(2).strip()
        dt = datetime.strptime(m_date.group(1).replace("/", "-"), "%d-%m-%Y")

        fname = f"{safe(name)}_{safe(pid)}_{dt.strftime('%Y%m%d')}.html"
        path = f"reports/{modality}/{dt.year}/{dt.month:02d}/{fname}"

        bucket.blob(path).upload_from_string(html, content_type="text/html")
        saved.append(path)

    return jsonify({"saved": saved, "skipped": skipped})

# =================================================
# LIST REPORTS
# =================================================
@app.route("/list_reports")
def list_reports():
    modality = request.args.get("modality", "").upper()
    name = request.args.get("name", "").lower()
    fdate = request.args.get("from", "").replace("-", "")
    tdate = request.args.get("to", "").replace("-", "")

    prefix = f"reports/{modality}/" if modality else "reports/"
    reports = []

    for p in list_files(prefix):
        fn = os.path.basename(p)
        if name and name not in fn.lower():
            continue

        m = re.search(r"_(\d{8})\.html$", fn)
        if not m:
            continue

        d = m.group(1)
        if fdate and d < fdate:
            continue
        if tdate and d > tdate:
            continue

        reports.append({"filename": fn, "path": p})

    return jsonify({"reports": reports})

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
        return send_file(html_to_docx(html), as_attachment=True, download_name=f"{base}.docx")
    if typ == "pdf":
        return send_file(html_to_pdf(html), as_attachment=True, download_name=f"{base}.pdf")

    return jsonify({"error": "invalid type"}), 400

# =================================================
# TEMPLATES
# =================================================
@app.route("/save_template", methods=["POST"])
def save_template():
    d = request.get_json(force=True)
    modality = d.get("modality", "").upper()
    name = safe(d.get("name", "template"))
    content = d.get("content", "")

    path = f"templates/{modality}/{name}.html"
    bucket.blob(path).upload_from_string(content, content_type="text/html")
    return jsonify({"status": "saved", "path": path})

@app.route("/list_templates")
def list_templates():
    modality = request.args.get("modality", "").upper()
    prefix = f"templates/{modality}/"
    files = list_files(prefix)
    names = [os.path.basename(f) for f in files]
    return jsonify({"templates": names})

@app.route("/load_template")
def load_template():
    modality = request.args.get("modality", "").upper()
    filename = request.args.get("filename")
    path = f"templates/{modality}/{filename}"

    blob = bucket.blob(path)
    if not blob.exists():
        return jsonify({"error": "not found"}), 404

    return jsonify({"content": blob.download_as_text()})

@app.route("/batch_upload_templates", methods=["POST"])
def batch_upload_templates():
    modality = request.form.get("modality", "").upper()
    files = request.files.getlist("files")

    saved = []
    for f in files:
        name = safe(os.path.splitext(f.filename)[0])
        content = (
            f.read().decode("utf-8")
            if f.filename.lower().endswith(".html")
            else "\n".join(p.text for p in Document(f).paragraphs).replace("\n", "<br>")
        )
        path = f"templates/{modality}/{name}.html"
        bucket.blob(path).upload_from_string(content, content_type="text/html")
        saved.append(path)

    return jsonify({"saved": saved})

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)





