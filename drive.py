 import os, json
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive"]

def get_drive_service():
    creds_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    creds_dict = json.loads(creds_json)

    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )

    return build("drive", "v3", credentials=creds)
