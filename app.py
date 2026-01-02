import io
import json
import datetime
from flask import Flask, request, jsonify, render_template
from docx import Document

from storage import get_bucket

app = Flask(__name__)

# ---------------- HOME ----------------

@app.route("/")
def index():
    return render_template("index.html")

# ---------------- TEMPLATE APIs ----------------

@app.route("/templates", methods=["GET"])
def list_templates():
    modality = request.args.get("modality")
    bucket = get_bucket()

    blobs = bucket.list_blobs(prefix=f"templates/{modality}/")
    out = []

    for b in blobs:
        if b.name.endswith(".html"):
            out.append({
                "id": b.name,
                "name": b.name.split("/")[-1]
            })

    return jsonify(out)

@app.route("/templates/<path:blob_name>")
def load_template(blob_name):
    bucket = get_bucket()
    blob = bucket.blob(blob_name)
    return jsonify({"html": blob.download_as_text()})

@app.route("/templates/save", methods=["POST"])
def save_template():
    data = request.json
    bucket = get_bucket()

    path = f"templates/{data['modality']}/{data['name']}"
    blob = bucket.blob(path)

    blob.upload_from_string(
        data["html"],
        content_type="text/html"
    )

    return jsonify({"status": "ok"})

# ---------------- REPORT API ----------------

@app.route("/reports/save", methods=["POST"])
def save_report():
    data = request.json
    patient = data["patient"]

    # Create DOCX
    doc = Document()
    doc.add_heading("Radiology Report", level=1)

    doc.add_paragraph(
        f"Name: {patient['name']}    "
        f"Age/Sex: {patient['age']}/{patient['sex']}    "
        f"UHID: {patient['uhid']}\n"
        f"Ref: {patient['ref']}    "
        f"Date: {patient['date']}"
    )

    doc.add_paragraph("\n")
    doc.add_paragraph(data["final_html"])

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)

    # Upload to GCS
    today = datetime.date.today()
    filename = f"{patient['name']}_{today}.docx"

    path = f"reports/{today.year}/{today.month}/{filename}"

    bucket = get_bucket()
    blob = bucket.blob(path)

    blob.upload_from_file(
        bio,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    return jsonify({
        "status": "ok",
        "path": path
    })

# ---------------- TEST ----------------

@app.route("/test-gcs")
def test_gcs():
    bucket = get_bucket()
    blob = bucket.blob("test/hello.txt")
    blob.upload_from_string("GCS working")
    return jsonify({"status": "ok"})






