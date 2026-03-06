import hashlib
import mimetypes
import requests
from typing import Optional
from sqlalchemy.orm import Session
from app import models

DEFAULT_TIMEOUT = 15


def file_sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def upload_or_reuse(
    session: Session,
    cfg: models.AppConfig,
    file_name: str,
    data: bytes,
    logger,
) -> Optional[int]:
    file_hash = file_sha1(data)
    existing = session.query(models.MediaHash).get(file_hash)
    if existing:
        logger("INFO", None, f"Reuse media hash for {file_name}")
        return existing.wp_media_id

    mime, _ = mimetypes.guess_type(file_name)
    mime = mime or "application/octet-stream"
    url = f"{cfg.wp_base_url}/wp-json/wp/v2/media"
    headers = {
        "Content-Disposition": f'attachment; filename="{file_name}"',
        "Content-Type": mime,
    }
    auth = (cfg.wp_username, cfg.wp_app_password)
    resp = requests.post(
        url, headers=headers, data=data, auth=auth, timeout=DEFAULT_TIMEOUT
    )
    if resp.status_code not in (200, 201):
        logger("ERROR", None, f"WP upload failed {resp.status_code}: {resp.text[:200]}")
        return None
    wp_id = resp.json().get("id")
    session.add(models.MediaHash(file_hash=file_hash, wp_media_id=wp_id))
    session.commit()
    return wp_id
