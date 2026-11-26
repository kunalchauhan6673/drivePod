"""Talks to Google Drive (API v3): find the music folder, list MP3s, download one song."""

import os
import re

import httplib2
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from drive_auth import AuthError, get_credentials, sign_out

FOLDER_NAME = "CloudPod Music"
FOLDER_MIME = "application/vnd.google-apps.folder"

# Problems with the internet connection (or the disk) show up as these.
NETWORK_ERRORS = (OSError, httplib2.HttpLib2Error)


class DriveError(Exception):
    """Something went wrong talking to Drive. The message is safe to show the user."""


class FolderNotFoundError(DriveError):
    """The 'CloudPod Music' folder doesn't exist in this Google account."""


class DownloadError(DriveError):
    """A song could not be downloaded."""


def _describe(error):
    """Turn a Google HttpError into a short, friendly sentence."""
    status = error.resp.status
    if status == 403:
        return ("Google Drive refused the request (403). Check that the Drive API is "
                "enabled for your project, that you signed in with the right account, "
                "and that you haven't hit a usage limit.")
    if status == 404:
        return "That file or folder wasn't found on Drive (404). It may have been moved or deleted."
    if status == 429 or status >= 500:
        return f"Google Drive is busy or unavailable right now ({status}). Try again in a moment."
    return f"Google Drive returned an error ({status})."


def _safe_filename(name):
    """Remove characters Windows doesn't allow in file names."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    if not cleaned:
        cleaned = "song"
    if not cleaned.lower().endswith(".mp3"):
        cleaned += ".mp3"
    return cleaned


class DriveClient:
    def __init__(self):
        self.service = None
        self._connect()

    def _connect(self):
        creds = get_credentials()  # may open the browser the first time
        # cache_discovery=False avoids a harmless warning from the Google library
        self.service = build("drive", "v3", credentials=creds, cache_discovery=False)

    # ------------------------------------------------------------------ helpers

    def _call(self, action):
        """Run action(). If Google says our login expired, sign in again once and retry.

        Any failure is turned into a DriveError / AuthError with a friendly message.
        """
        reauthed = False
        while True:
            try:
                return action()
            except (HttpError, RefreshError) as e:
                expired = isinstance(e, RefreshError) or e.resp.status == 401
                if expired and not reauthed:
                    print("\nYour Google login expired. Signing in again...")
                    sign_out()
                    self._connect()
                    reauthed = True
                    continue  # retry the same action with the new login
                if isinstance(e, RefreshError):
                    raise AuthError("Your Google login couldn't be renewed. Please run again and sign in.")
                raise DriveError(_describe(e))
            except NETWORK_ERRORS as e:
                raise DriveError(f"Network problem while talking to Google Drive: {e}")

    def _list(self, **kwargs):
        return self._call(lambda: self.service.files().list(spaces="drive", **kwargs).execute())

    # --------------------------------------------------------------- public API

    def find_music_folder(self, name=FOLDER_NAME):
        """Return the Drive ID of the folder called `name`."""
        safe_name = name.replace("\\", "\\\\").replace("'", "\\'")
        query = f"name = '{safe_name}' and mimeType = '{FOLDER_MIME}' and trashed = false"
        folders = self._list(q=query, fields="files(id, name)", pageSize=10).get("files", [])

        if not folders:
            raise FolderNotFoundError(
                f"Couldn't find a folder named '{name}' in your Google Drive.\n"
                "  Create it (exact name, including capitals) and upload some MP3s into it."
            )
        if len(folders) > 1:
            print(f"Note: found {len(folders)} folders named '{name}'. Using the first one.")
        return folders[0]["id"]

    def list_mp3s(self, folder_id):
        """Return a list of MP3 files in the folder, as dicts with id, name and size."""
        query = f"'{folder_id}' in parents and trashed = false and mimeType != '{FOLDER_MIME}'"
        songs = []
        page_token = None
        while True:  # Drive returns results in pages
            result = self._list(
                q=query,
                orderBy="name",
                fields="nextPageToken, files(id, name, size, mimeType)",
                pageSize=100,
                pageToken=page_token,
            )
            for f in result.get("files", []):
                if f["name"].lower().endswith(".mp3") or f.get("mimeType") == "audio/mpeg":
                    songs.append(f)
            page_token = result.get("nextPageToken")
            if not page_token:
                return songs

    def get_songs(self):
        """Find the music folder and return its MP3 files (a fresh list every time)."""
        songs = self.list_mp3s(self.find_music_folder())
        if not songs:
            raise DriveError(
                f"The '{FOLDER_NAME}' folder has no MP3 files. Upload some and try again."
            )
        return songs

    def download_song(self, song, dest_dir):
        """Download ONE song into dest_dir and return the local file path.

        Each song goes in its own sub-folder (named after its Drive ID), so two songs
        with the same name can never overwrite each other.
        """
        song_dir = os.path.join(dest_dir, song["id"])
        final_path = os.path.join(song_dir, _safe_filename(song["name"]))
        temp_path = final_path + ".part"
        expected_size = int(song.get("size") or 0)

        # Already downloaded earlier in this session? Reuse it.
        if expected_size and os.path.isfile(final_path) and os.path.getsize(final_path) == expected_size:
            print("Already downloaded - using the saved copy.")
            return final_path

        try:
            os.makedirs(song_dir, exist_ok=True)
            self._call(lambda: self._download_to(song["id"], temp_path))

            # Make sure we got the whole file, not half of it.
            if expected_size and os.path.getsize(temp_path) != expected_size:
                raise DownloadError(
                    "The download was incomplete (the file is smaller than expected). Please try again."
                )
            os.replace(temp_path, final_path)  # only a COMPLETE file gets the real name
            return final_path
        except OSError as e:
            raise DownloadError(f"Couldn't save the song to your computer: {e}")
        finally:
            if os.path.exists(temp_path):  # clean up any half-finished download
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _download_to(self, file_id, path):
        request = self.service.files().get_media(fileId=file_id)
        with open(path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request, chunksize=1024 * 1024)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    print(f"\r  Downloading... {int(status.progress() * 100)}%", end="", flush=True)
        print()
