import os
import io
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import storage
from docx import Document

# ================= APP =================
app = Flask(__name__)
CORS(app)

# ================= GCS =================
BUCKET_NAME = os.environ.get("GCS_BUCKET")
if not BUCKET_NAME:
    raise RuntimeError("GCS_BUCKET environment variable not set")

client = storage.Client()  # uses GOOGLE_APPLICATION_CREDENTIALS
bucket = client.bucket(BUCKET_NAME)

# ================= BASIC =================
@app.route("/")
def home():
    return "SERVER RUNNING", 200

@app.route("/health")
def health():
    return "OK", 200

# ================= HELPERS =================
def list_files(prefix):
    files = []
    for blob in bucket.list_blobs(prefix=prefix):
        if not blob.name.endswith("/"):
            files.append(blob.name.split("/")[-1])
    return files

# =================================================
# REPORTS
# =================================================
@app.route("/save_report", methods=["POST"])
def save_report():
    data = request.get_json(force=True)

    modality = data.get("modality", "").upper()
    filename = data.get("filename")
    content = data.get("content")

    if not modality or not filename or not content:
        return jsonify({"error": "modality, filename, content required"}), 400

    path = f"reports/{modality}/{filename}"
    bucket.blob(path).upload_from_string(content, content_type="text/html")

    return jsonify({"status": "saved", "path": path}), 200


@app.route("/load_report", methods=["GET"])
def load_report():
    modality = request.args.get("modality", "").upper()
    filename = request.args.get("filename")

    if not modality or not filename:
        return jsonify({"error": "modality and filename required"}), 400

    path = f"reports/{modality}/{filename}"
    blob = bucket.blob(path)

    if not blob.exists():
        return jsonify({"error": "report not found"}), 404

    return jsonify({"content": blob.download_as_text()}), 200


@app.route("/list_reports", methods=["GET"])
def list_reports():
    modality = request.args.get("modality", "").upper()
    files = list_files(f"reports/{modality}/")

    return jsonify({
        "reports": [{"filename": f} for f in files]
    }), 200

# =================================================
# TEMPLATES
# =================================================
@app.route("/save_template", methods=["POST"])
def save_template():
    data = request.get_json(force=True)

    modality = data.get("modality", "").upper()
    filename = data.get("filename")
    content = data.get("content")

    if not modality or not filename or not content:
        return jsonify({"error": "modality, filename, content required"}), 400

    path = f"templates/{modality}/{filename}"
    bucket.blob(path).upload_from_string(content, content_type="text/html")

    return jsonify({"status": "saved", "path": path}), 200


@app.route("/load_template", methods=["GET"])
def load_template():
    modality = request.args.get("modality", "").upper()
    filename = request.args.get("filename")

    if not modality or not filename:
        return jsonify({"error": "modality and filename required"}), 400

    path = f"templates/{modality}/{filename}"
    blob = bucket.blob(path)

    if not blob.exists():
        return jsonify({"error": "template not found"}), 404

    return jsonify({"content": blob.download_as_text()}), 200


@app.route("/list_templates", methods=["GET"])
def list_templates():
    modality = request.args.get("modality", "").upper()
    files = list_files(f"templates/{modality}/")

    return jsonify({"templates": files}), 200

# =================================================
# WORD UPLOAD
# =================================================
@app.route("/upload_word_report", methods=["POST"])
def upload_word_report():
    if "file" not in request.files:
        return jsonify({"error": "file missing"}), 400

    file = request.files["file"]
    modality = request.form.get("upload_modality", "CT").upper()

    doc = Document(file)
    html = "<br>".join(p.text for p in doc.paragraphs if p.text.strip())

    filename = file.filename.replace(".docx", ".html")
    path = f"reports/{modality}/{filename}"

    bucket.blob(path).upload_from_string(html, content_type="text/html")

    return jsonify({
        "status": "uploaded",
        "filename": filename,
        "html": html
    }), 200

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


