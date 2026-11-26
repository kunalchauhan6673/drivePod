"""Minimal local MP3 player with a playlist.

Setup:   pip install pygame
Usage:   python mp3_player.py                 plays every .mp3 in the "songs" folder
                                              next to this script (created if missing)
         python mp3_player.py path/to/folder  plays every .mp3 in that folder
         python mp3_player.py song1.mp3 ...   plays specific files

Commands:
  play | pause | resume | stop
  next | prev
  list
  vol <0-100>
  loop [on|off]     repeat the current song
  quit
"""

import os
import sys
import threading
import time

import pygame


def build_playlist(paths):
    """Accept files and/or folders; return a list of .mp3 file paths."""
    tracks = []
    for p in paths:
        if os.path.isdir(p):
            names = sorted(n for n in os.listdir(p) if n.lower().endswith(".mp3"))
            tracks.extend(os.path.join(p, n) for n in names)
        elif os.path.isfile(p):
            tracks.append(p)
        else:
            raise FileNotFoundError(f"Not found: {p}")
    if not tracks:
        raise FileNotFoundError("No .mp3 files found in the given path(s).")
    return tracks


class MP3Player:
    def __init__(self, tracks):
        pygame.mixer.init()
        pygame.mixer.music.set_volume(0.5)
        self.tracks = tracks
        self.index = 0
        self.state = "stopped"  # stopped | playing | paused
        self.loop = False
        self.lock = threading.RLock()
        self._running = True
        # Background thread: moves to the next track when a song ends.
        threading.Thread(target=self._watch, daemon=True).start()

    @property
    def current_name(self):
        return os.path.basename(self.tracks[self.index])

    def _start_current(self):
        """Load and play the current track. Returns False if it can't be loaded."""
        try:
            pygame.mixer.music.load(self.tracks[self.index])
            # loops=-1 repeats forever; loops=0 plays once
            pygame.mixer.music.play(loops=-1 if self.loop else 0)
        except pygame.error as e:
            print(f"\nCan't play {self.current_name}: {e}")
            self.state = "stopped"
            return False
        self.state = "playing"
        print(f"\nNow playing [{self.index + 1}/{len(self.tracks)}]: {self.current_name}")
        return True

    def play(self):
        with self.lock:
            self._start_current()

    def pause(self):
        with self.lock:
            if self.state == "playing":
                pygame.mixer.music.pause()
                self.state = "paused"

    def resume(self):
        with self.lock:
            if self.state == "paused":
                pygame.mixer.music.unpause()
                self.state = "playing"

    def stop(self):
        with self.lock:
            pygame.mixer.music.stop()
            self.state = "stopped"

    def next(self):
        with self.lock:
            self.index = (self.index + 1) % len(self.tracks)
            self._start_current()

    def prev(self):
        with self.lock:
            self.index = (self.index - 1) % len(self.tracks)
            self._start_current()

    def set_volume(self, percent):
        percent = max(0, min(100, percent))
        pygame.mixer.music.set_volume(percent / 100)
        return percent

    def set_loop(self, enabled):
        self.loop = enabled

    def _watch(self):
        while self._running:
            time.sleep(0.5)
            with self.lock:
                if self.state == "playing" and not pygame.mixer.music.get_busy():
                    # Song finished on its own: go to the next one, or stop at the end.
                    if self.index < len(self.tracks) - 1:
                        self.index += 1
                        self._start_current()
                    else:
                        self.state = "stopped"
                        print("\nPlaylist finished.")

    def close(self):
        self._running = False
        self.stop()
        pygame.mixer.quit()


def main():
    if len(sys.argv) >= 2:
        paths = sys.argv[1:]
    else:
        # No arguments: use a "songs" folder next to this script.
        songs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "songs")
        if not os.path.isdir(songs_dir):
            os.makedirs(songs_dir)
            print(f"Created folder: {songs_dir}")
            print("Put your .mp3 files in it, then run the player again.")
            sys.exit(0)
        paths = [songs_dir]

    try:
        tracks = build_playlist(paths)
        player = MP3Player(tracks)
    except (FileNotFoundError, pygame.error) as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Loaded {len(tracks)} track(s).")
    print("Commands: play | pause | resume | stop | next | prev | list | "
          "vol <0-100> | loop [on|off] | quit")

    while True:
        try:
            parts = input(f"[{player.state}] > ").strip().lower().split()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not parts:
            continue

        cmd = parts[0]
        if cmd == "play":
            player.play()
        elif cmd == "pause":
            player.pause()
        elif cmd == "resume":
            player.resume()
        elif cmd == "stop":
            player.stop()
        elif cmd in ("next", "n"):
            player.next()
        elif cmd in ("prev", "previous", "p"):
            player.prev()
        elif cmd == "list":
            for i, t in enumerate(player.tracks):
                marker = ">" if i == player.index else " "
                print(f" {marker} {i + 1}. {os.path.basename(t)}")
        elif cmd in ("vol", "volume"):
            if len(parts) == 2 and parts[1].isdigit():
                print(f"Volume: {player.set_volume(int(parts[1]))}%")
            else:
                print("Usage: vol <0-100>")
        elif cmd == "loop":
            if len(parts) == 1:
                player.set_loop(not player.loop)  # no argument: toggle
            elif parts[1] in ("on", "off"):
                player.set_loop(parts[1] == "on")
            else:
                print("Usage: loop [on|off]")
                continue
            msg = f"Loop: {'on' if player.loop else 'off'}"
            if player.state != "stopped":
                msg += " (applies the next time a song starts)"
            print(msg)
        elif cmd in ("quit", "exit", "q"):
            break
        else:
            print("Unknown command.")

    player.close()


if __name__ == "__main__":
    main()