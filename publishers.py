"""Approved-only publishers for YouTube Shorts and Instagram Reels."""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import Any

import requests


def _caption_text(manifest: dict[str, Any]) -> str:
    caption = (manifest.get("caption") or "").strip()
    hashtags = (manifest.get("hashtags") or "").strip()
    return "\n\n".join(x for x in (caption, hashtags) if x)


def publish_youtube(video_path: str, manifest: dict[str, Any]) -> dict[str, str]:
    """Upload an approved video using an offline Google OAuth refresh token."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    client_json = os.environ.get("YOUTUBE_CLIENT_SECRETS_JSON", "").strip()
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()
    if not client_json or not refresh_token:
        raise RuntimeError("YOUTUBE_CLIENT_SECRETS_JSON و YOUTUBE_REFRESH_TOKEN تنظیم نشده‌اند")
    cfg = json.loads(client_json)
    installed = cfg.get("installed") or cfg.get("web") or cfg
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=installed.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=installed["client_id"],
        client_secret=installed["client_secret"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    service = build("youtube", "v3", credentials=creds, cache_discovery=False)
    title = (manifest.get("title") or manifest.get("topic") or "Pharma Short").strip()[:100]
    description = _caption_text(manifest)
    tags = [x.lstrip("#").strip() for x in (manifest.get("hashtags") or "").split() if x.strip()]
    body = {
        "snippet": {"title": title, "description": description[:5000], "tags": tags[:30], "categoryId": "27", "defaultLanguage": "fa"},
        "status": {"privacyStatus": os.environ.get("YOUTUBE_PRIVACY_STATUS", "unlisted"), "selfDeclaredMadeForKids": False},
    }
    request = service.videos().insert(
        part="snippet,status", body=body,
        media_body=MediaFileUpload(video_path, mimetype="video/mp4", resumable=True),
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    video_id = response["id"]
    return {"id": video_id, "url": f"https://youtu.be/{video_id}"}


def publish_instagram(video_path: str, manifest: dict[str, Any]) -> dict[str, str]:
    """Publish an approved Reel using Meta's resumable upload flow."""
    ig_id = os.environ.get("INSTAGRAM_USER_ID", "").strip()
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    version = os.environ.get("META_GRAPH_VERSION", "v26.0").strip()
    if not ig_id or not token:
        raise RuntimeError("INSTAGRAM_USER_ID و INSTAGRAM_ACCESS_TOKEN تنظیم نشده‌اند")
    base = f"https://graph.facebook.com/{version}"
    caption = _caption_text(manifest)[:2200]
    create = requests.post(
        f"{base}/{ig_id}/media",
        params={"media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true", "access_token": token},
        timeout=60,
    )
    create.raise_for_status()
    data = create.json()
    container_id, upload_uri = data.get("id"), data.get("uri")
    if not container_id or not upload_uri:
        raise RuntimeError(f"Instagram container ناقص است: {data}")
    size = Path(video_path).stat().st_size
    with open(video_path, "rb") as fh:
        upload = requests.post(
            upload_uri,
            headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)},
            data=fh,
            timeout=300,
        )
    upload.raise_for_status()
    for _ in range(30):
        status = requests.get(f"{base}/{container_id}", params={"fields": "status_code", "access_token": token}, timeout=30).json()
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"Instagram processing failed: {status}")
        time.sleep(10)
    else:
        raise TimeoutError("Instagram Reel container آماده انتشار نشد")
    published = requests.post(f"{base}/{ig_id}/media_publish", params={"creation_id": container_id, "access_token": token}, timeout=60)
    published.raise_for_status()
    media_id = published.json().get("id")
    if not media_id:
        raise RuntimeError(f"Instagram media id دریافت نشد: {published.text}")
    return {"id": media_id, "url": f"https://www.instagram.com/reel/{media_id}/"}


def publish_approved(video_path: str, manifest: dict[str, Any]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    if os.environ.get("ENABLE_YOUTUBE_PUBLISH", "true").lower() == "true":
        try: results["youtube"] = publish_youtube(video_path, manifest)
        except Exception as exc: errors["youtube"] = str(exc)
    if os.environ.get("ENABLE_INSTAGRAM_PUBLISH", "true").lower() == "true":
        try: results["instagram"] = publish_instagram(video_path, manifest)
        except Exception as exc: errors["instagram"] = str(exc)
    if errors and not results:
        raise RuntimeError("; ".join(f"{k}: {v}" for k, v in errors.items()))
    if errors: results["errors"] = errors
    return results
