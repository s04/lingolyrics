"""Plain lyrics from the public lyrics.ovh API (https://lyricsovh.docs.apiary.io)."""

from urllib.parse import quote

from syncedlyrics.providers.base import LRCProvider

from .utils import Lyrics


class LyricsOvh(LRCProvider):
    def __init__(self, title: str | None = None, artist: str | None = None):
        super().__init__()
        self.title, self.artist = title, artist

    def get_lrc(self, search_term: str) -> Lyrics | None:
        if not self.title or not self.artist:
            return None  # Never guess the artist/title boundary of a free-text query.
        url = "https://api.lyrics.ovh/v1/{}/{}".format(
            quote(self.artist, safe=""), quote(self.title, safe="")
        )
        response = self.session.get(url)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        text = response.json().get("lyrics")
        return Lyrics(unsynced=text.strip()) if isinstance(text, str) and text.strip() else None
