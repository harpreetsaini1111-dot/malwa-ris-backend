import io
from flask import Flask, request, jsonify, render_template
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from docx import Document
from bs4 import BeautifulSoup

from drive import get_drive_service

app = Flask(__name__)

# ===== DRIVE ROOT IDS =====
TEMPLATES_ROOT_ID = "1Pv6AQsCyDZZciUnnLCJAgaiISd9Qdpwa"
REPORTS_ROOT_ID   = "14MQZDL9DP7BZF45MbRIlKsReVJ5CSJV3"

MONTHS = {
    "01": "01_January", "02": "02_February", "03": "03_March",
    "04": "04_April", "05": "05_May", "06": "06_June",
    "07": "07_July", "08": "08_August", "09": "09_September",
    "10": "10_October", "11": "11_November", "12": "12_December"
}

# ---------- HELPERS ----------

def get_or_create_folder(service, name, parent_id):
    q = (
        f"'{parent_id}' in parents and "
        f"name='{name}' and "
        f"mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    res = service.files().list(q=q, fields="files(id)").execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]

    folder = service.files().create(
        body={
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id]
        },
        fields="id"
    ).execute()

    return folder["id"]

def html_to_docx(html, patient, title):
    doc = Document()
    doc.add_heading(title, 1)

    p = doc.add_paragraph()
    p.add_run(f"Patient: {patient['name']}   ")
    p.add_run(f"Age/Sex: {patient['age']}/{patient['sex']}   ")
    p.add_run(f"UHID: {patient['uhid']}\n")
    p.add_run(f"Ref: {patient['ref']}   ")
    p.add_run(f"Date: {patient['date']}")

    doc.add_paragraph("")

    soup = BeautifulSoup(html, "html.parser")
    for el in soup.find_all(["h1", "h2", "h3", "p"]):
        if el.name.startswith("h"):
            doc.add_heading(el.get_text(), level=2)
        else:
            doc.add_paragraph(el.get_text())

    return doc

# ---------- ROUTES ----------

@app.route("/")
def index():
    return render_template("index.html")

# ===== TEMPLATE APIs =====

@app.route("/templates")
def list_templates():
    modality = request.args.get("modality")
    service = get_drive_service()

    folder_id = get_or_create_folder(service, modality, TEMPLATES_ROOT_ID)
    q = f"'{folder_id}' in parents and trashed=false"

    res = service.files().list(
        q=q, fields="files(id,name,mimeType)"
    ).execute()

    files = [
        {"id": f["id"], "name": f["name"]}
        for f in res.get("files", [])
        if f["mimeType"] != "application/vnd.google-apps.folder"
    ]

    return jsonify(files)

@app.route("/templates/<file_id>")
def load_template(file_id):
    service = get_drive_service()
    req = service.files().get_media(fileId=file_id)

    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    return jsonify({"html": fh.getvalue().decode("utf-8")})

@app.route("/templates/save", methods=["POST"])
def save_template():
    data = request.json
    service = get_drive_service()

    folder_id = get_or_create_folder(service, data["modality"], TEMPLATES_ROOT_ID)

    media = MediaIoBaseUpload(
        io.BytesIO(data["html"].encode("utf-8")),
        mimetype="text/html",
        resumable=False
    )

    service.files().create(
        body={
            "name": data["name"],
            "parents": [folder_id]
        },
        media_body=media
    ).execute()

    return jsonify({"status": "saved"})

# ===== REPORT API =====

@app.route("/reports/save", methods=["POST"])
def save_report():
    data = request.json
    service = get_drive_service()

    modality = data["modality"]
    patient = data["patient"]
    html = data["final_html"]

    modality_id = get_or_create_folder(service, modality, REPORTS_ROOT_ID)
    year_id = get_or_create_folder(service, patient["date"][:4], modality_id)
    month_id = get_or_create_folder(
        service,
        MONTHS[patient["date"][5:7]],
        year_id
    )

    patient_folder = f"{patient['uhid']}_{patient['name'].replace(' ', '_')}"
    patient_id = get_or_create_folder(service, patient_folder, month_id)

    doc = html_to_docx(html, patient, f"{modality} Report")
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)

    media = MediaIoBaseUpload(
        bio,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        resumable=False
    )

    file = service.files().create(
        body={
            "name": f"{modality}_{patient['date']}.docx",
            "parents": [patient_id]
        },
        media_body=media,
        fields="webViewLink"
    ).execute()

    return jsonify({"status": "saved", "link": file["webViewLink"]})

# ---------- RUN ----------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)






