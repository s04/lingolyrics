"""QQ Music public smartbox discovery and GetPlayLyricInfo CGI protocol."""

import base64

from syncedlyrics.providers.base import LRCProvider

from .utils import Lyrics, get_best_match, identify_lyrics_type


class QQMusic(LRCProvider):
    def get_lrc(self, search_term: str) -> Lyrics | None:
        response = self.session.get(
            "https://c.y.qq.com/splcloud/fcgi-bin/smartbox_new.fcg",
            params={"key": search_term, "format": "json"},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"QQ Music search code {payload.get('code')}")
        candidates = payload.get("data", {}).get("song", {}).get("itemlist", [])
        candidates = [item for item in candidates if isinstance(item, dict) and item.get("mid")]
        candidate = get_best_match(
            candidates,
            search_term,
            lambda item: f"{item.get('name', '')} {item.get('singer', '')}",
        )
        if not candidate:
            return None
        response = self.session.post(
            "https://u.y.qq.com/cgi-bin/musicu.fcg",
            json={
                "comm": {"format": "json"},
                "req_0": {
                    "module": "music.musichallSong.PlayLyricInfo",
                    "method": "GetPlayLyricInfo",
                    "param": {
                        "songMid": candidate["mid"],
                        "crypt": 0,
                        "lrc_t": 0,
                        "qrc": 0,
                        "qrc_t": 0,
                        "roma": 0,
                        "roma_t": 0,
                        "trans": 0,
                        "trans_t": 0,
                        "needSingingAnnotations": False,
                        "type": 1,
                    },
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("req_0", {})
        if payload.get("code") != 0 or result.get("code") != 0:
            raise RuntimeError(f"QQ Music lyric codes {payload.get('code')}/{result.get('code')}")
        data = result.get("data", {})
        if (
            candidate.get("id")
            and data.get("songID")
            and str(candidate["id"]) != str(data["songID"])
        ):
            raise RuntimeError("QQ Music returned a different song ID")
        encoded = data.get("lyric")
        if not isinstance(encoded, str) or not encoded:
            return None
        text = base64.b64decode(encoded, validate=True).decode("utf-8-sig")
        return Lyrics(synced=text) if identify_lyrics_type(text) == "synced" else None
