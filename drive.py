import os
import json
import io

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive"]

def get_drive_service():
    service_account_info = json.loads(
        os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    )

    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=SCOPES
    )

    service = build("drive", "v3", credentials=creds)
    return service
