import httpx
import pytest

import lyrics_service
from lyrics_service import fetch_lyrics, parse_lyrics


@pytest.mark.parametrize(
    ("text", "expected", "synced"),
    [
        ("[ar:Artist]\n[ti:Song]\n[00:01.25]Hello", [(1.25, "Hello")], True),
        ("[00:02]<00:02.00>Hello <00:02.50>world", [(2, "Hello world")], True),
        ("<00:02.00>Hello <00:02.50>world", [(2, "Hello world")], True),
        ("First line\n\nSecond line", [(0, "First line"), (0, "Second line")], False),
        ("[offset:-500]\n[00:00.10]Start\n[00:01]Next", [(0, "Start"), (0.5, "Next")], True),
        ("[00:01]hello\n[00:02]", [(1, "hello"), (2, "")], True),
        ("[ar:Artist]", [], False),
    ],
)
def test_parsing(text, expected, synced):
    lines, timing = parse_lyrics(text)
    assert timing is synced
    assert [(line.time_seconds, line.original) for line in lines] == expected


def test_lrclib_plain_fallback(monkeypatch):
    def get(self, url, **kwargs):
        assert kwargs["params"] == {"track_name": "Song", "artist_name": "Artist"}
        return httpx.Response(
            200,
            json={"syncedLyrics": None, "plainLyrics": "Hello"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.Client, "get", get)
    assert fetch_lyrics("Song", "Artist", "lrclib") == ("Hello", "LRCLIB")


def test_no_result(monkeypatch):
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda *a, **kw: httpx.Response(
            200, json=[], request=httpx.Request("GET", "https://lrclib.net/api/get")
        ),
    )
    with pytest.raises(ValueError, match="No lyrics"):
        fetch_lyrics("Song", "Artist", "lrclib")


def test_unknown_provider():
    with pytest.raises(ValueError, match="supported"):
        fetch_lyrics("Song", "Artist", "injected")


def test_lrclib_search_rejects_wrong_versions_and_prefers_synced(monkeypatch):
    candidates = [
        {"trackName": "Song", "artistName": "Wrong", "syncedLyrics": "wrong"},
        {"trackName": "Song (Live)", "artistName": "Artist", "syncedLyrics": "wrong"},
        {"trackName": "Song", "artistName": "Artist", "duration": 900, "syncedLyrics": "wrong"},
        {"trackName": "Song", "artistName": "Artist", "duration": 180, "plainLyrics": "plain"},
        {
            "trackName": "Song",
            "artistName": "Artist",
            "duration": 181,
            "syncedLyrics": "[00:01]correct",
        },
    ]

    def get(self, url, **kwargs):
        return httpx.Response(
            404 if url.endswith("/get") else 200, json=candidates, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx.Client, "get", get)
    assert fetch_lyrics("Song", "Artist", "lrclib", duration=180) == ("[00:01]correct", "LRCLIB")


def test_instrumental_does_not_try_other_providers(monkeypatch):
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda self, url, **kw: httpx.Response(
            200, json={"instrumental": True}, request=httpx.Request("GET", url)
        ),
    )
    monkeypatch.setattr(
        lyrics_service,
        "fetch_legacy_provider",
        lambda *args: pytest.fail("must not scrape an instrumental"),
    )
    with pytest.raises(lyrics_service.InstrumentalTrack):
        fetch_lyrics("Song", "Artist")


def test_outage_falls_back_to_next_provider(monkeypatch):
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda self, url, **kw: httpx.Response(503, request=httpx.Request("GET", url)),
    )
    monkeypatch.setattr(lyrics_service, "fetch_legacy_provider", lambda *args: "[00:01]hello")
    assert fetch_lyrics("Song", "Artist") == ("[00:01]hello", "NetEase")


def test_legacy_subprocess_is_bounded_without_shell(monkeypatch):
    import subprocess

    def run(command, **kwargs):
        assert kwargs["timeout"] == 10
        assert kwargs.get("shell", False) is False
        assert "$(secret)" not in command
        raise subprocess.TimeoutExpired(command, 10)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match="could not be reached"):
        fetch_lyrics("$(secret)", "Artist", "Musixmatch")


def test_malformed_candidates_do_not_match():
    assert lyrics_service.select_candidate({"invalid": True}, "Song", "Artist", None) is None
    assert (
        lyrics_service.select_candidate(
            [None, {}, {"trackName": "Song", "artistName": "Other"}], "Song", "Artist", None
        )
        is None
    )


def test_go_engine_uses_stdin_and_preserves_provenance(monkeypatch):
    import json
    import subprocess
    from types import SimpleNamespace

    monkeypatch.setenv("LYRICFETCH_BINARY", "/trusted/lyricfetch")

    def run(command, **kwargs):
        assert command[0] == "/trusted/lyricfetch"
        assert "$(secret)" not in command
        assert kwargs["timeout"] == 27
        assert not kwargs.get("shell")
        assert json.loads(kwargs["input"])["duration"] == 180
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"lyrics": {"text": "[00:01]Fixture", "source": "kugou"}, "attempts": []}
            ),
        )

    monkeypatch.setattr(subprocess, "run", run)
    assert fetch_lyrics("$(secret)", "Artist", duration=180) == ("[00:01]Fixture", "Kugou")


@pytest.mark.parametrize(
    ("status", "error"),
    [
        ("not_found", ValueError),
        ("instrumental", lyrics_service.InstrumentalTrack),
        ("unavailable", RuntimeError),
    ],
)
def test_go_engine_preserves_failure_outcomes(monkeypatch, status, error):
    import json
    import subprocess
    from types import SimpleNamespace

    monkeypatch.setenv("LYRICFETCH_BINARY", "/trusted/lyricfetch")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=1, stdout=json.dumps({"lyrics": None, "attempts": [{"status": status}]})
        ),
    )
    with pytest.raises(error):
        fetch_lyrics("Song", "Artist")


def test_go_engine_missing_binary(monkeypatch):
    import subprocess

    monkeypatch.setenv("LYRICFETCH_BINARY", "/missing/lyricfetch")

    def run(*args, **kwargs):
        raise FileNotFoundError("private details")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match="configured lyricfetch"):
        fetch_lyrics("Song", "Artist")
