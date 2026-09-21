from unittest.mock import Mock

from models import LyricLine, Song
from spotify_service import SpotifyService


def service():
    obj = SpotifyService.__new__(SpotifyService)
    obj.current_song_cache = None
    obj.sp = Mock()
    obj.auth = None
    return obj


def test_metadata_and_repeated_timestamps():
    lines = service().parse_regular_lrc("[ar:Artist]\n[00:10.00][00:20.00]Hello\n[00:05]First")
    assert [(line.time_seconds, line.original) for line in lines] == [
        (5, "First"),
        (10, "Hello"),
        (20, "Hello"),
    ]


def test_refresh_preserves_loaded_lyrics():
    obj = service()
    obj.current_song_cache = Song(
        title="Song",
        artist="Artist",
        spotify_id="123",
        lyrics=[LyricLine(timestamp="[00:01]", time_seconds=1, original="Hello")],
    )
    obj.sp.current_user_playing_track.return_value = {
        "item": {"id": "123", "name": "Song", "artists": [{"name": "Artist"}]},
        "progress_ms": 2000,
        "is_playing": True,
    }
    song = obj.get_current_song_info()
    assert len(song.lyrics) == 1
    assert song.current_position == 2


def test_stopped_playback_clears_stale_song():
    obj = service()
    obj.current_song_cache = Song(title="Old", artist="Artist", spotify_id="123")
    obj.sp.current_user_playing_track.return_value = None
    assert obj.get_current_song_info() is None
    assert obj.current_song_cache is None
