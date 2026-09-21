"""Short-lived isolation for third-party scraping adapters. Not a public API."""

import contextlib
import json
import sys

import syncedlyrics
from syncedlyrics.utils import TargetType

from lyrics_sources.kugou import Kugou
from lyrics_sources.lyricsovh import LyricsOvh
from lyrics_sources.qqmusic import QQMusic

if __name__ == "__main__":
    data = json.load(sys.stdin)
    # Keep provider diagnostics separate from the machine-readable response.
    with contextlib.redirect_stdout(sys.stderr):
        query = f"{data['title']} {data['artist']}"
        provider = sys.argv[1]
        if provider in {"Kugou", "QQMusic", "LyricsOvh"}:
            adapter = (
                QQMusic()
                if provider == "QQMusic"
                else {"Kugou": Kugou, "LyricsOvh": LyricsOvh}[provider](
                    title=data["title"], artist=data["artist"]
                )
            )
            result = adapter.get_lrc(query)
            text = result.to_str(TargetType.PREFER_SYNCED) if result else None
        else:
            text = syncedlyrics.search(query, providers=[provider])
    print(json.dumps(text))
