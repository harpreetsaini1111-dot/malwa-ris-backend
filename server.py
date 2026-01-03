import os
import io
from flask import Flask, request, jsonify
from flask_cors import CORS

from google.cloud import storage

app = Flask(__name__)
CORS(app)

# ---------- GCS SETUP ----------
BUCKET_NAME = os.environ.get("GCS_BUCKET")

client = storage.Client()  # uses GOOGLE_APPLICATION_CREDENTIALS automatically
bucket = client.bucket(BUCKET_NAME)

# ---------- ROOT (IMPORTANT) ----------
@app.route("/")
def home():
    return "SERVER RUNNING", 200

# ---------- HEALTH ----------
@app.route("/health")
def health():
    return "OK", 200

# ---------- SAVE REPORT ----------
@app.route("/save_report", methods=["POST"])
def save_report():
    data = request.get_json(force=True)

    filename = data.get("filename")
    content = data.get("content")

    if not filename or not content:
        return jsonify({"error": "filename and content required"}), 400

    blob = bucket.blob(f"reports/{filename}")
    blob.upload_from_string(content, content_type="text/plain")

    return jsonify({"status": "saved", "file": filename})

# ---------- LOAD REPORT ----------
@app.route("/load_report", methods=["GET"])
def load_report():
    filename = request.args.get("filename")

    if not filename:
        return jsonify({"error": "filename required"}), 400

    blob = bucket.blob(f"reports/{filename}")

    if not blob.exists():
        return jsonify({"error": "file not found"}), 404

    content = blob.download_as_text()
    return jsonify({"content": content})

# ---------- RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)








