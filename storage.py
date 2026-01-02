import os
from google.cloud import storage

def get_bucket():
    client = storage.Client()
    return client.bucket(os.environ["GCS_BUCKET"])
