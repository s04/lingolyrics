import time

import spotipy
from spotipy.oauth2 import SpotifyOAuth

import cache_service
from lyrics_service import fetch_lyrics, parse_lyrics
from models import Song


class SpotifyService:
    def __init__(self, client_id: str | None, client_secret: str | None, redirect_uri: str | None):
        self.current_song_cache = None
        self.auth = None
        self.sp = None
        self.configured = bool(client_id and client_secret and redirect_uri)
        if self.configured:
            self.auth = SpotifyOAuth(
                scope="user-read-currently-playing user-read-playback-state",
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                open_browser=False,
                requests_timeout=10,
            )
            self.sp = spotipy.Spotify(auth_manager=self.auth, requests_timeout=10, retries=1)

    def require_connection(self):
        if not self.sp:
            raise ValueError(
                "Add Spotify credentials to .env, restart, and choose Connect Spotify. You can try the demo or search lyrics now."
            )
        if self.auth and not self.auth.get_cached_token():
            raise ValueError("Connect Spotify first, then play a track and try again.")

    def parse_regular_lrc(self, lrc):
        return parse_lyrics(lrc)[0]

    def parse_enhanced_lrc(self, lrc):
        return parse_lyrics(lrc)[0]

    def get_current_song_info(self) -> Song | None:
        self.require_connection()
        current = self.sp.current_user_playing_track()
        track = current.get("item") if current else None
        if not track or not track.get("id") or not track.get("artists"):
            self.current_song_cache = None
            return None
        if self.current_song_cache and self.current_song_cache.spotify_id == track["id"]:
            song = self.current_song_cache
        else:
            song = Song(
                title=track["name"],
                artist=", ".join(a["name"] for a in track["artists"]),
                spotify_id=track["id"],
                album=(track.get("album") or {}).get("name", ""),
                duration=(track.get("duration_ms") or 0) / 1000 or None,
                primary_artist=track["artists"][0]["name"],
            )
        song.current_position = (current.get("progress_ms") or 0) / 1000
        song.is_playing = current.get("is_playing", False)
        self.current_song_cache = song
        return song

    def get_lyrics_for_song(self, song: Song, provider="auto", refresh=False) -> Song:
        key = f"lyrics-v3:{song.title}:{song.artist}:{song.album}:{song.duration}:{provider}"
        cached = None if refresh else cache_service.get_from_cache(key)
        if (
            isinstance(cached, dict)
            and isinstance(cached.get("text"), str)
            and isinstance(cached.get("source"), str)
        ):
            text, source = cached["text"], cached["source"]
        else:
            text, source = fetch_lyrics(
                song.title,
                song.primary_artist or song.artist,
                provider,
                album=song.album,
                duration=song.duration,
            )
            cache_service.save_to_cache(key, {"text": text, "source": source})
        song.lyrics, song.synced = parse_lyrics(text)
        song.lyrics_source = source
        if not song.lyrics:
            raise ValueError("This source returned no usable lyric lines. Try another source.")
        return song

    def get_current_playback_state(self):
        self.require_connection()
        playback = self.sp.current_playback()
        if not playback or not playback.get("item"):
            return {"is_playing": False, "position": 0, "track_id": None, "timestamp": time.time()}
        return {
            "is_playing": playback.get("is_playing", False),
            "position": (playback.get("progress_ms") or 0) / 1000,
            "track_id": playback["item"].get("id"),
            "timestamp": time.time(),
        }
