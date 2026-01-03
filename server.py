import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import storage

# ================= APP SETUP =================
app = Flask(__name__)
CORS(app)

# ================= GCS SETUP =================
BUCKET_NAME = os.environ.get("GCS_BUCKET")

if not BUCKET_NAME:
    raise RuntimeError("GCS_BUCKET environment variable not set")

client = storage.Client()  # uses GOOGLE_APPLICATION_CREDENTIALS
bucket = client.bucket(BUCKET_NAME)

# ================= BASIC ROUTES =================
@app.route("/")
def home():
    return "SERVER RUNNING", 200

@app.route("/health")
def health():
    return "OK", 200

@app.route("/version")
def version():
    return jsonify({"version": "RIS_GCS_V1"}), 200

# =================================================
# REPORTS
# =================================================
@app.route("/save_report", methods=["POST"])
def save_report():
    data = request.get_json(force=True)

    modality = data.get("modality")
    filename = data.get("filename")
    content = data.get("content")

    if not modality or not filename or not content:
        return jsonify({
            "error": "modality, filename, and content are required"
        }), 400

    modality = modality.upper()

    path = f"reports/{modality}/{filename}"

    blob = bucket.blob(path)
    blob.upload_from_string(
        content,
        content_type="text/html"
    )

    return jsonify({
        "status": "report saved",
        "path": path
    }), 200


@app.route("/load_report", methods=["GET"])
def load_report():
    modality = request.args.get("modality")
    filename = request.args.get("filename")

    if not modality or not filename:
        return jsonify({
            "error": "modality and filename required"
        }), 400

    modality = modality.upper()
    path = f"reports/{modality}/{filename}"

    blob = bucket.blob(path)

    if not blob.exists():
        return jsonify({"error": "report not found"}), 404

    return jsonify({
        "content": blob.download_as_text()
    }), 200

# =================================================
# TEMPLATES
# =================================================
@app.route("/save_template", methods=["POST"])
def save_template():
    data = request.get_json(force=True)

    modality = data.get("modality")
    filename = data.get("filename")
    content = data.get("content")

    if not modality or not filename or not content:
        return jsonify({
            "error": "modality, filename, and content are required"
        }), 400

    modality = modality.upper()
    path = f"templates/{modality}/{filename}"

    blob = bucket.blob(path)
    blob.upload_from_string(
        content,
        content_type="text/html"
    )

    return jsonify({
        "status": "template saved",
        "path": path
    }), 200


@app.route("/load_template", methods=["GET"])
def load_template():
    modality = request.args.get("modality")
    filename = request.args.get("filename")

    if not modality or not filename:
        return jsonify({
            "error": "modality and filename required"
        }), 400

    modality = modality.upper()
    path = f"templates/{modality}/{filename}"

    blob = bucket.blob(path)

    if not blob.exists():
        return jsonify({"error": "template not found"}), 404

    return jsonify({
        "content": blob.download_as_text()
    }), 200

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

