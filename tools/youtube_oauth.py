#!/usr/bin/env python3
"""Create a YouTube offline refresh token locally.

Usage:
  python tools/youtube_oauth.py client_secret.json

The browser consent happens on the user's own computer. The token is printed
once so it can be pasted directly into GitHub Actions Secrets; never commit it.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/youtube_oauth.py /path/to/client_secret.json")
    path = Path(sys.argv[1]).expanduser()
    if not path.is_file():
        raise SystemExit(f"File not found: {path}")
    config = json.loads(path.read_text(encoding="utf-8"))
    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    credentials = flow.run_local_server(
        host="localhost", port=0, access_type="offline", prompt="consent", open_browser=True
    )
    if not credentials.refresh_token:
        raise SystemExit("Google did not return a refresh token; revoke the grant and run again.")
    print("\nYOUTUBE_REFRESH_TOKEN (store only in GitHub Secret):\n")
    print(credentials.refresh_token)
    print("\nDo not commit this value or send it in chat.")


if __name__ == "__main__":
    main()
