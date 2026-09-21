"""Lyrics retrieval with explicit providers, bounded requests, and source attribution."""

import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import httpx

from models import LyricLine

PROVIDERS = {
    "auto": "Automatic · LRCLIB first",
    "lrclib": "LRCLIB",
    "NetEase": "NetEase",
    "Kugou": "Kugou",
    "QQMusic": "QQ Music",
    "LyricsOvh": "lyrics.ovh · plain text",
    "Musixmatch": "Musixmatch",
    "Megalobiz": "Megalobiz",
    "Genius": "Genius · plain text",
}
TIMESTAMP = re.compile(r"\[(\d+):([0-5]\d(?:\.\d+)?)\]")


def parse_lyrics(text: str) -> tuple[list[LyricLine], bool]:
    lines = []
    offset = re.search(r"\[offset:([+-]?\d+)\]", text, re.I)
    offset_seconds = int(offset[1]) / 1000 if offset else 0
    for raw in text.splitlines():
        stamps = list(TIMESTAMP.finditer(raw))
        words = re.sub(r"<\d+:[\d.]+>", "", TIMESTAMP.sub("", raw)).strip()
        if stamps:
            for stamp in stamps:
                lines.append(
                    LyricLine(
                        timestamp=stamp[0],
                        time_seconds=max(0, int(stamp[1]) * 60 + float(stamp[2]) + offset_seconds),
                        original=words,
                    )
                )
        elif not re.match(r"^\s*\[[a-z]+:", raw, re.I) and words:
            # Enhanced LRC occasionally has only word timestamps.
            enhanced = re.search(r"<(\d+):([\d.]+)>", raw)
            if enhanced:
                lines.append(
                    LyricLine(
                        timestamp=f"[{enhanced[1]}:{enhanced[2]}]",
                        time_seconds=int(enhanced[1]) * 60 + float(enhanced[2]) + offset_seconds,
                        original=words,
                    )
                )
    if lines:
        return sorted(lines, key=lambda line: line.time_seconds), True
    return [
        LyricLine(timestamp="", time_seconds=0, original=line.strip())
        for line in text.splitlines()
        if line.strip() and not re.match(r"^\s*\[[a-z]+:", line, re.I)
    ], False


class InstrumentalTrack(ValueError):
    """A successful provider lookup explicitly identified an instrumental."""


def normalized_name(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def select_candidate(candidates, title, artist, duration):
    if not isinstance(candidates, list):
        return None
    matching = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        if normalized_name(str(item.get("trackName", ""))) != normalized_name(title):
            continue
        if normalized_name(str(item.get("artistName", ""))) != normalized_name(artist):
            continue
        if duration is not None:
            candidate_duration = item.get("duration")
            if (
                not isinstance(candidate_duration, (int, float))
                or abs(candidate_duration - duration) > 3
            ):
                continue
        if item.get("syncedLyrics") or item.get("plainLyrics") or item.get("instrumental"):
            matching.append(item)
    # Synchronization is a preference only after identity has been checked.
    return max(matching, key=lambda item: bool(item.get("syncedLyrics")), default=None)


def fetch_lyrics(
    title: str,
    artist: str,
    provider: str = "auto",
    *,
    album: str = "",
    duration: float | None = None,
) -> tuple[str, str]:
    if provider not in PROVIDERS:
        raise ValueError("Choose a supported lyrics source.")
    executable = os.getenv("LYRICFETCH_BINARY", "").strip()
    if executable and provider not in {"Genius", "Megalobiz"}:
        return fetch_with_lyricfetch(executable, title, artist, provider, album, duration)
    failures = []
    if provider in ("auto", "lrclib"):
        try:
            with httpx.Client(
                timeout=12,
                headers={"User-Agent": "LingoLyrics/2.0 (https://github.com/s04/lingolyrics)"},
            ) as client:
                params = {"track_name": title, "artist_name": artist}
                if album:
                    params["album_name"] = album
                if duration is not None:
                    params["duration"] = duration
                response = client.get("https://lrclib.net/api/get", params=params)
                if response.status_code == 404:
                    # Only accept same-title, same-artist candidates. Never silently
                    # substitute a live/remix version or a similarly named artist.
                    response = client.get(
                        "https://lrclib.net/api/search",
                        params={"track_name": title, "artist_name": artist},
                    )
                    response.raise_for_status()
                    candidates = response.json()
                    data = select_candidate(candidates, title, artist, duration)
                else:
                    response.raise_for_status()
                    data = response.json()
                if isinstance(data, dict):
                    if data.get("instrumental") is True:
                        raise InstrumentalTrack(
                            "This source identifies the track as instrumental; there are no sung lyrics."
                        )
                    text = data.get("syncedLyrics") or data.get("plainLyrics")
                    if isinstance(text, str) and text.strip():
                        return text, "LRCLIB"
        except InstrumentalTrack:
            raise
        except (httpx.HTTPError, ValueError):
            failures.append("LRCLIB")
    names = (
        ["NetEase", "Kugou", "QQMusic", "LyricsOvh"]
        if provider == "auto"
        else ([provider] if provider != "lrclib" else [])
    )
    for name in names:
        try:
            text = fetch_legacy_provider(title, artist, name)
            if text:
                return text, name
        except Exception:
            failures.append(name)
    if failures:
        raise RuntimeError(
            "Some lyrics sources could not be reached. Try another source or retry shortly."
        )
    raise ValueError(
        "No lyrics found. Try another lyrics source or check the song and artist names."
    )


def fetch_legacy_provider(title: str, artist: str, provider: str) -> str | None:
    """A hard deadline also stops upstream recursive retries, unlike socket timeouts."""
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("lyrics_worker.py")), provider],
        input=json.dumps({"title": title, "artist": artist}),
        text=True,
        capture_output=True,
        timeout=10,
        check=True,
    )
    data = json.loads(result.stdout)
    return data if isinstance(data, str) else None


def fetch_with_lyricfetch(
    executable: str, title: str, artist: str, provider: str, album: str, duration: float | None
) -> tuple[str, str]:
    """Use the standalone Go core when configured, with a second process deadline."""
    command = [executable, "--stdin", "--include-text", "--budget", "25s"]
    if provider != "auto":
        command.extend(["--providers", provider.lower()])
    try:
        process = subprocess.run(
            command,
            input=json.dumps(
                {"title": title, "artist": artist, "album": album, "duration": duration or 0}
            ),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=27,
            check=False,
        )
        if process.returncode not in (0, 1):
            raise RuntimeError("The lyricfetch executable could not complete this lookup.")
        data = json.loads(process.stdout)
        lyric = data["lyrics"]
        if isinstance(lyric, dict) and isinstance(lyric.get("text"), str) and lyric["text"].strip():
            source = next(
                (name for name in PROVIDERS if name.lower() == lyric.get("source")), "lyricfetch"
            )
            return lyric["text"], "LRCLIB" if source == "lrclib" else source
        attempts = data["attempts"]
        if any(item.get("status") == "instrumental" for item in attempts):
            raise InstrumentalTrack("This source identifies the track as instrumental.")
        if any(
            item.get("status") in {"unavailable", "timeout", "canceled", "invalid_response"}
            for item in attempts
        ):
            raise RuntimeError("Some lyrics sources could not be reached. Try another source.")
    except InstrumentalTrack:
        raise
    except (OSError, subprocess.TimeoutExpired, KeyError, TypeError, AttributeError, ValueError):
        raise RuntimeError(
            "Could not read a response from the configured lyricfetch executable."
        ) from None
    raise ValueError("No lyrics found. Check the song and artist names or try another source.")
