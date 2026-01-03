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

# ---------- HEALTH ----------
@app.route("/health")
def health():
    return "OK", 200

# ---------- SAVE REPORT ----------
@app.route("/save_report", methods=["POST"])
def save_report():
    data = request.json
    filename = data["filename"]
    content = data["content"]

    blob = bucket.blob(f"reports/{filename}")
    blob.upload_from_string(content, content_type="text/plain")

    return jsonify({"status": "saved", "file": filename})

# ---------- LOAD REPORT ----------
@app.route("/load_report", methods=["GET"])
def load_report():
    filename = request.args.get("filename")
    blob = bucket.blob(f"reports/{filename}")

    if not blob.exists():
        return jsonify({"error": "file not found"}), 404

    content = blob.download_as_text()
    return jsonify({"content": content})

# ---------- RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)







