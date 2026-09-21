"""Use the existing adapter contract with strict timestamp recognition."""

import re

from syncedlyrics.utils import Lyrics, get_best_match

__all__ = ["Lyrics", "get_best_match", "identify_lyrics_type"]


def identify_lyrics_type(text: str) -> str:
    return (
        "synced" if re.search(r"^\s*\[\d+:[0-5]\d(?:\.\d+)?\]", text, re.MULTILINE) else "plaintext"
    )
