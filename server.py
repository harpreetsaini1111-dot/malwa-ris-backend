import os, io, json, uuid
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from docx import Document

# ================= SETUP =================

app = Flask(__name__)
CORS(app)

SCOPES = ["https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_JSON = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
ROOT_FOLDER = os.environ["DRIVE_FOLDER_ID"]

creds = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_JSON, scopes=SCOPES
)
drive = build("drive", "v3", credentials=creds)

# ================= HELPERS =================

def get_folder(name):
    q = f"'{ROOT_FOLDER}' in parents and name='{name}' and mimeType='application/vnd.google-apps.folder'"
    r = drive.files().list(q=q, fields="files(id)").execute()
    return r["files"][0]["id"]

def upload_file(name, data, parent):
    media = MediaIoBaseUpload(io.BytesIO(data), resumable=True)
    f = drive.files().create(
        body={"name": name, "parents": [parent]},
        media_body=media,
        fields="id"
    ).execute()
    return f["id"]

def download_file(file_id):
    req = drive.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh

def load_index():
    try:
        r = drive.files().list(
            q=f"'{ROOT_FOLDER}' in parents and name='reports.json'",
            fields="files(id)"
        ).execute()
        fid = r["files"][0]["id"]
        return json.load(download_file(fid)), fid
    except:
        return [], None

def save_index(data, fid):
    raw = json.dumps(data, indent=2).encode()
    media = MediaIoBaseUpload(io.BytesIO(raw), resumable=True)
    if fid:
        drive.files().update(fileId=fid, media_body=media).execute()
    else:
        upload_file("reports.json", raw, ROOT_FOLDER)

# ================= ROOT =================

@app.route("/")
def root():
    return jsonify({"status":"running","service":"Malwa RIS Backend"})

@app.route("/health")
def health():
    return jsonify({"status":"ok"})

# ================= TEMPLATES =================

@app.route("/api/upload_template", methods=["POST"])
def upload_template():
    f = request.files["file"]
    modality = request.form["modality"]
    folder = get_folder(modality)
    upload_file(f.filename, f.read(), folder)
    return jsonify({"status":"uploaded"})

@app.route("/api/templates/<modality>")
def list_templates(modality):
    folder = get_folder(modality)
    r = drive.files().list(
        q=f"'{folder}' in parents",
        fields="files(id,name)"
    ).execute()
    return jsonify(r["files"])

@app.route("/api/load_template", methods=["POST"])
def load_template():
    fid = request.json["file_id"]
    data = download_file(fid).read().decode(errors="ignore")
    return jsonify({"html": data})

# ================= REPORTS =================

@app.route("/api/save_report", methods=["POST"])
def save_report():
    payload = request.json
    rid = str(uuid.uuid4())
    index, fid = load_index()

    index.append({
        "id": rid,
        "patient_name": payload["patient_name"],
        "uhid": payload["uhid"],
        "date": payload["date"],
        "modality": payload["modality"],
        "html": payload["html"]
    })

    save_index(index, fid)
    return jsonify({"status":"saved"})

@app.route("/api/reports")
def search_reports():
    p = request.args.get("patient_name","").lower()
    u = request.args.get("uhid","").lower()
    d = request.args.get("date","")

    index,_ = load_index()
    out=[]
    for r in index:
        if p and p not in r["patient_name"].lower(): continue
        if u and u not in r["uhid"].lower(): continue
        if d and d != r["date"]: continue
        out.append(r)
    return jsonify(out)

@app.route("/api/download_word/<rid>")
def download_word(rid):
    index,_ = load_index()
    r = next(x for x in index if x["id"]==rid)

    doc = Document()
    doc.add_heading("Radiology Report",1)
    doc.add_paragraph(f"Patient: {r['patient_name']}")
    doc.add_paragraph(f"UHID: {r['uhid']}")
    doc.add_paragraph(f"Date: {r['date']}")
    doc.add_paragraph("")
    doc.add_paragraph(r["html"])

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    return send_file(buf, as_attachment=True,
        download_name=f"{r['patient_name']}.docx")

# ================= RUN =================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))








