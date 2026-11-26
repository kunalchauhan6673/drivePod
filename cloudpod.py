"""CloudPod: pick a song from Google Drive, download it, and play it.

Setup:   pip install -r requirements.txt   (and see the Google setup steps)
Usage:   python cloudpod.py

Flow:  sign in -> list MP3s in your "CloudPod Music" Drive folder -> pick a number
       -> only that song is downloaded -> it plays with the normal player controls.
Type 'cloud' at the player prompt to pick another song from Drive.
"""

import os
import shutil
import sys

import pygame

from drive_auth import AuthError
from drive_client import FOLDER_NAME, DriveClient, DriveError
from mp3_player import MP3Player, run_controls

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")  # temporary files live here
DELETE_DOWNLOADS_ON_EXIT = True  # set to False to keep downloaded songs


def format_size(size_bytes):
    if not size_bytes:
        return "size unknown"
    return f"{int(size_bytes) / (1024 * 1024):.1f} MB"


def choose_song(songs):
    """Show the numbered list and return the chosen song (or None if the user cancels)."""
    print(f"\nSongs in your '{FOLDER_NAME}' folder:")
    for number, song in enumerate(songs, start=1):
        print(f"  {number}. {song['name']}  ({format_size(song.get('size'))})")

    while True:
        try:
            choice = input("Enter a song number (or press Enter to cancel): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if choice in ("", "q", "quit", "cancel"):
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(songs):
            return songs[int(choice) - 1]
        print(f"Please enter a number from 1 to {len(songs)}.")


def download(drive, song):
    """Download one song. Returns the local path, or None if it failed."""
    print(f"Downloading '{song['name']}'...")
    try:
        return drive.download_song(song, DOWNLOAD_DIR)
    except (DriveError, AuthError) as e:
        print(f"Download failed: {e}")
        return None


def refresh_songs(drive, old_songs):
    """Get a fresh song list from Drive. If that fails, keep using the old list."""
    try:
        return drive.get_songs()
    except (DriveError, AuthError) as e:
        print(f"Couldn't refresh the song list: {e}")
        return old_songs


def cleanup_downloads():
    if DELETE_DOWNLOADS_ON_EXIT and os.path.isdir(DOWNLOAD_DIR):
        shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True)


def main():
    # 1) Sign in and get the song list.
    try:
        drive = DriveClient()
        songs = drive.get_songs()
    except (DriveError, AuthError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    player = None
    try:
        # 2) Keep asking until one song has downloaded successfully.
        while player is None:
            song = choose_song(songs)
            if song is None:
                return  # user cancelled before playing anything
            path = download(drive, song)
            if path is None:
                songs = refresh_songs(drive, songs)  # e.g. the file was deleted on Drive
                continue
            try:
                player = MP3Player([path])  # your existing player, unchanged
            except pygame.error as e:
                print(f"Error: couldn't start the audio system: {e}")
                return
            player.play()

        # 3) The 'cloud' command lets you pick more songs while the player is running.
        def pick_another():
            nonlocal songs
            songs = refresh_songs(drive, songs)
            song = choose_song(songs)
            if song is None:
                return
            path = download(drive, song)
            if path:
                player.add_and_play(path)

        run_controls(player, cloud_handler=pick_another)
    finally:
        if player is not None:
            player.close()  # release the audio file before deleting downloads
        cleanup_downloads()


if __name__ == "__main__":
    main()
