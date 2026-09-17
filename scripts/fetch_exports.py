"""Pull Earth Engine exports out of Drive into data/.

`earthengine authenticate` already grants the Drive scope, so the same
credentials that queued the export can fetch the result. That keeps the round
trip scriptable without enabling billing for a cloud bucket, which was the
tradeoff recorded in `docs/reviews/2026-09-15-step1-architecture.md`.

Run:
    python scripts/fetch_exports.py                # everything in the folder
    python scripts/fetch_exports.py --pattern 2020 # just one season
"""

import argparse
import json
import os
import pathlib
import sys

import ee
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import config  # noqa: E402

DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
CREDENTIALS = pathlib.Path.home() / ".config" / "earthengine" / "credentials"


def authorised_session():
    """Refresh the stored Earth Engine credentials into a usable Drive token."""
    stored = json.loads(CREDENTIALS.read_text())
    creds = Credentials(
        token=None,
        refresh_token=stored["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=ee.oauth.CLIENT_ID,
        client_secret=ee.oauth.CLIENT_SECRET,
        scopes=stored["scopes"],
    )
    creds.refresh(Request())
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {creds.token}"
    return session


def list_folder(session, folder_name):
    """Every file directly inside the named Drive folder."""
    folders = session.get(DRIVE_FILES, params={
        "q": f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder'",
        "fields": "files(id,name)",
    }).json().get("files", [])
    if not folders:
        raise SystemExit(f"no Drive folder named {folder_name!r}")

    files = session.get(DRIVE_FILES, params={
        "q": f"'{folders[0]['id']}' in parents and trashed = false",
        "fields": "files(id,name,size,createdTime)",
        "pageSize": 1000,
    }).json().get("files", [])

    # Earth Engine writes a NEW Drive file on every export rather than
    # overwriting, so re-exporting leaves two files with the same name. Keep
    # only the newest of each, or a correction silently fetches the version it
    # was meant to replace.
    newest = {}
    for entry in files:
        seen = newest.get(entry["name"])
        if seen is None or entry["createdTime"] > seen["createdTime"]:
            newest[entry["name"]] = entry
    return sorted(newest.values(), key=lambda f: f["name"])


def download(session, file_id, destination):
    """Stream one file to disk, then move it into place.

    Downloads to a .part file first so an interrupted transfer cannot leave a
    truncated GeoTIFF that later reads as valid but short.
    """
    partial = destination.with_suffix(destination.suffix + ".part")
    with session.get(DRIVE_FILES + f"/{file_id}", params={"alt": "media"}, stream=True) as response:
        response.raise_for_status()
        written = 0
        with open(partial, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 20):
                handle.write(chunk)
                written += len(chunk)
                if written % (50 << 20) < (1 << 20):
                    print(f"  {destination.name}: {written / 1e6:.0f} MB", flush=True)
    partial.replace(destination)
    print(f"  {destination.name}: done, {written / 1e6:.1f} MB")
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pattern", default="", help="only files whose name contains this")
    parser.add_argument("--out", default="data", help="destination directory")
    args = parser.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    session = authorised_session()
    files = [f for f in list_folder(session, config.DRIVE_FOLDER) if args.pattern in f["name"]]
    if not files:
        raise SystemExit(f"nothing in {config.DRIVE_FOLDER} matching {args.pattern!r}")

    for entry in files:
        destination = out / entry["name"]
        expected = int(entry.get("size", 0))
        if destination.exists() and destination.stat().st_size == expected:
            print(f"  {entry['name']}: already present, skipping")
            continue
        written = download(session, entry["id"], destination)
        if expected and written != expected:
            raise SystemExit(
                f"{entry['name']}: got {written} bytes, Drive reported {expected}"
            )

    print(f"\n{len(files)} file(s) in {out.resolve()}")


if __name__ == "__main__":
    raise SystemExit(main())
