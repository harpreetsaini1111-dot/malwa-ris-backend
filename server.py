import os, io, json, uuid
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

from docx import Document
import mammoth

# ================= CONFIG =================

SCOPES = ["https://www.googleapis.com/auth/drive"]
ROOT_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]
SERVICE_ACCOUNT_JSON = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])

# ================= APP =================

app = Flask(__name__)
CORS(app)

creds = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_JSON, scopes=SCOPES
)
drive = build("drive", "v3", credentials=creds)

# ================= DRIVE HELPERS =================

def find_or_create_folder(name, parent):
    q = (
        f"'{parent}' in parents and "
        f"name='{name}' and "
        f"mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    r = drive.files().list(q=q, fields="files(id)").execute()
    if r["files"]:
        return r["files"][0]["id"]

    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent]
    }
    f = drive.files().create(body=meta, fields="id").execute()
    return f["id"]

def upload_bytes(name, data, parent, mime="text/html"):
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=False)
    f = drive.files().create(
        body={"name": name, "parents": [parent]},
        media_body=media,
        fields="id"
    ).execute()
    return f["id"]

def download_bytes(file_id):
    req = drive.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh

# ================= INDEX =================

def load_index():
    r = drive.files().list(
        q=f"'{ROOT_FOLDER_ID}' in parents and name='reports.json' and trashed=false",
        fields="files(id)"
    ).execute()

    if not r["files"]:
        return [], None

    fid = r["files"][0]["id"]
    data = json.load(download_bytes(fid))
    return data, fid

def save_index(data, fid):
    raw = json.dumps(data, indent=2).encode()
    media = MediaIoBaseUpload(io.BytesIO(raw), mimetype="application/json")
    if fid:
        drive.files().update(fileId=fid, media_body=media).execute()
    else:
        upload_bytes("reports.json", raw, ROOT_FOLDER_ID, "application/json")

# ================= UTIL =================

def word_to_html(file_bytes):
    with io.BytesIO(file_bytes) as f:
        result = mammoth.convert_to_html(f)
    return result.value

def html_to_word(html):
    doc = Document()
    doc.add_heading("Radiology Report", level=1)
    doc.add_paragraph(html)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf

# ================= ROUTES =================

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# -------- SAVE REPORT FROM EDITOR --------

@app.route("/api/save_report", methods=["POST"])
def save_report():
    p = request.json
    rid = str(uuid.uuid4())

    modality_folder = find_or_create_folder(p["modality"], ROOT_FOLDER_ID)

    html_id = upload_bytes(
        f"{p['patient_name']}_{rid}.html",
        p["html"].encode("utf-8"),
        modality_folder
    )

    index, fid = load_index()
    index.append({
        "id": rid,
        "patient_name": p["patient_name"],
        "uhid": p.get("uhid",""),
        "date": p.get("date",""),
        "modality": p["modality"],
        "html_file_id": html_id
    })
    save_index(index, fid)

    return jsonify({"status": "saved"})

# -------- UPLOAD WORD REPORT --------

@app.route("/api/upload_report", methods=["POST"])
def upload_report():
    f = request.files["file"]
    modality = request.form["modality"]
    patient = request.form.get("patient_name", "Uploaded_Report")
    rid = str(uuid.uuid4())

    modality_folder = find_or_create_folder(modality, ROOT_FOLDER_ID)

    html = word_to_html(f.read())
    html_id = upload_bytes(
        f"{patient}_{rid}.html",
        html.encode(),
        modality_folder
    )

    index, fid = load_index()
    index.append({
        "id": rid,
        "patient_name": patient,
        "uhid": "",
        "date": "",
        "modality": modality,
        "html_file_id": html_id
    })
    save_index(index, fid)

    return jsonify({"status": "uploaded"})

# -------- SEARCH REPORTS --------

@app.route("/api/reports")
def search_reports():
    p = request.args.get("patient_name","").lower()
    index,_ = load_index()

    out = []
    for r in index:
        if p and p not in r["patient_name"].lower():
            continue
        out.append(r)
    return jsonify(out)

# -------- LOAD REPORT INTO EDITOR --------

@app.route("/api/load_report/<rid>")
def load_report(rid):
    index,_ = load_index()
    r = next(x for x in index if x["id"] == rid)
    html = download_bytes(r["html_file_id"]).read().decode()
    return jsonify({"html": html})

# -------- DOWNLOAD WORD --------

@app.route("/api/download_word/<rid>")
def download_word(rid):
    index,_ = load_index()
    r = next(x for x in index if x["id"] == rid)
    html = download_bytes(r["html_file_id"]).read().decode()
    buf = html_to_word(html)
    return send_file(buf, as_attachment=True,
                     download_name=f"{r['patient_name']}.docx")

# ================= TEMPLATES (DRIVE) =================

def templates_root():
    return find_or_create_folder("Templates", ROOT_FOLDER_ID)

@app.route("/api/templates/<modality>")
def list_templates(modality):
    root = templates_root()
    folder = find_or_create_folder(modality, root)

    files = drive.files().list(
        q=f"'{folder}' in parents and trashed=false",
        fields="files(id,name)"
    ).execute().get("files", [])

    return jsonify(files)

@app.route("/api/load_template/<template_id>")
def load_template(template_id):
    html = download_bytes(template_id).read().decode("utf-8")
    return jsonify({"html": html})

# ================= RUN =================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))





