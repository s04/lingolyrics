"""Kugou's public lyric search/download protocol; no private account credentials."""

import base64

from syncedlyrics.providers.base import LRCProvider

from .utils import Lyrics, get_best_match, identify_lyrics_type


class Kugou(LRCProvider):
    ROOT_URL = "https://lyrics.kugou.com"

    def __init__(self, title: str | None = None, artist: str | None = None):
        super().__init__()
        self.title, self.artist = title, artist

    def get_lrc(self, search_term: str) -> Lyrics | None:
        query = f"{self.artist} - {self.title}" if self.title and self.artist else search_term
        response = self.session.get(
            self.ROOT_URL + "/search",
            params={"ver": 1, "man": "yes", "client": "pc", "keyword": query},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != 200:
            raise RuntimeError(f"Kugou search status {payload.get('status')}")
        candidates = payload.get("candidates", [])
        candidates = [
            item
            for item in candidates
            if isinstance(item, dict) and item.get("id") and item.get("accesskey")
        ]
        candidate = get_best_match(
            candidates,
            query,
            lambda item: f"{item.get('singer', '')} - {item.get('song', '')}",
        )
        if not candidate:
            return None
        response = self.session.get(
            self.ROOT_URL + "/download",
            params={
                "ver": 1,
                "client": "pc",
                "id": candidate["id"],
                "accesskey": candidate["accesskey"],
                "fmt": "lrc",
                "charset": "utf8",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != 200:
            raise RuntimeError(f"Kugou download status {payload.get('status')}")
        encoded = payload.get("content")
        if not isinstance(encoded, str) or not encoded:
            return None
        text = base64.b64decode(encoded, validate=True).decode("utf-8-sig")
        if identify_lyrics_type(text) != "synced":
            return None
        return Lyrics(synced=text)
