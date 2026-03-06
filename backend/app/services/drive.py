import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SERVICE_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service-account.json")


def get_drive_client():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_FILE, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def list_folder_files(client, folder_id: str, page_size: int = 1000):
    files = []
    page_token = None
    while True:
        resp = (
            client.files()
            .list(
                q=f"'{folder_id}' in parents and trashed=false",
                spaces="drive",
                pageSize=page_size,
                fields="nextPageToken, files(id, name, modifiedTime)",
                pageToken=page_token,
            )
            .execute()
        )
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    latest = {}
    for f in files:
        name = f["name"]
        if name not in latest or f["modifiedTime"] > latest[name]["modifiedTime"]:
            latest[name] = f
    return latest


def download_file(client, file_id: str):
    request = client.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return fh.read()
