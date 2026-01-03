import os
from google.cloud import storage

BUCKET_NAME = os.environ.get("GCS_BUCKET")

def get_bucket():
    if not BUCKET_NAME:
        raise RuntimeError("GCS_BUCKET environment variable not set")

    client = storage.Client()  # uses GOOGLE_APPLICATION_CREDENTIALS
    bucket = client.bucket(BUCKET_NAME)
    return bucket
