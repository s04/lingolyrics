from unittest.mock import Mock

import pytest

import cache_service
import spotify_service
from models import Song
from spotify_service import SpotifyService


def test_episode_does_not_become_song():
    service = SpotifyService(None, None, None)
    service.sp = Mock()
    service.sp.current_user_playing_track.return_value = {
        "item": {"id": "episode", "type": "episode"}
    }
    assert service.get_current_song_info() is None


def test_spotify_metadata_forwarded():
    service = SpotifyService(None, None, None)
    service.sp = Mock()
    service.sp.current_user_playing_track.return_value = {
        "item": {
            "id": "id",
            "name": "Song",
            "artists": [{"name": "First"}, {"name": "Second"}],
            "album": {"name": "Album"},
            "duration_ms": 180000,
        },
        "progress_ms": None,
        "is_playing": False,
    }
    song = service.get_current_song_info()
    assert (song.artist, song.primary_artist, song.album, song.duration) == (
        "First, Second",
        "First",
        "Album",
        180,
    )
    assert song.current_position == 0


def test_lyrics_cache_and_refresh(monkeypatch):
    service = SpotifyService(None, None, None)
    song = Song(title="Song", artist="Artist", spotify_id="id", album="Album", duration=180)
    fetch = Mock(return_value=("[00:01]Hello", "LRCLIB"))
    monkeypatch.setattr(spotify_service, "fetch_lyrics", fetch)
    for _ in range(2):
        result = service.get_lyrics_for_song(song)
        assert result.lyrics[0].original == "Hello"
    assert fetch.call_count == 1
    fetch.assert_called_with("Song", "Artist", "auto", album="Album", duration=180)
    service.get_lyrics_for_song(song, refresh=True)
    assert fetch.call_count == 2


def test_bad_cache_refetches(monkeypatch):
    service = SpotifyService(None, None, None)
    song = Song(title="Song", artist="Artist", spotify_id="id")
    cache_service.save_to_cache("lyrics-v3:Song:Artist::None:auto", {"text": "Hello"})
    monkeypatch.setattr(
        spotify_service, "fetch_lyrics", lambda *a, **kw: ("Plain lyric", "NetEase")
    )
    assert service.get_lyrics_for_song(song).synced is False


def test_missing_token_never_triggers_interactive_auth():
    service = SpotifyService(None, None, None)
    service.sp = Mock()
    service.auth = Mock()
    service.auth.get_cached_token.return_value = None
    with pytest.raises(ValueError, match="Connect Spotify"):
        service.get_current_song_info()
    service.sp.current_user_playing_track.assert_not_called()


def test_playback_without_track():
    service = SpotifyService(None, None, None)
    service.sp = Mock()
    service.sp.current_playback.return_value = None
    state = service.get_current_playback_state()
    assert state["track_id"] is None
    assert state["is_playing"] is False


def test_playback_track_id_and_progress():
    service = SpotifyService(None, None, None)
    service.sp = Mock()
    service.sp.current_playback.return_value = {
        "item": {"id": "abc"},
        "progress_ms": 1234,
        "is_playing": True,
    }
    state = service.get_current_playback_state()
    assert state["track_id"] == "abc"
    assert state["position"] == 1.234
