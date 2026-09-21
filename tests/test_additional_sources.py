import base64
from unittest.mock import Mock

import pytest

from lyrics_sources.kugou import Kugou
from lyrics_sources.lyricsovh import LyricsOvh
from lyrics_sources.qqmusic import QQMusic
from lyrics_sources.utils import identify_lyrics_type


def response(data, status=200):
    result = Mock(status_code=status)
    result.json.return_value = data
    return result


def test_kugou_candidate_key_and_lrc():
    provider = Kugou(title="Song", artist="Artist")
    provider.session.get = Mock(
        side_effect=[
            response(
                {
                    "status": 200,
                    "candidates": [
                        {"id": "1", "accesskey": "synthetic", "song": "Song", "singer": "Artist"}
                    ],
                }
            ),
            response({"status": 200, "content": base64.b64encode(b"[00:01]Fixture").decode()}),
        ]
    )
    assert provider.get_lrc("Song Artist").synced == "[00:01]Fixture"
    assert provider.session.get.call_args.kwargs["params"]["accesskey"] == "synthetic"


def test_qq_current_public_cgi():
    provider = QQMusic()
    provider.session.get = Mock(
        return_value=response(
            {
                "code": 0,
                "data": {
                    "song": {
                        "itemlist": [{"mid": "x", "id": "1", "name": "Song", "singer": "Artist"}]
                    }
                },
            }
        )
    )
    provider.session.post = Mock(
        return_value=response(
            {
                "code": 0,
                "req_0": {
                    "code": 0,
                    "data": {"songID": 1, "lyric": base64.b64encode(b"[00:01]Fixture").decode()},
                },
            }
        )
    )
    assert provider.get_lrc("Song Artist").synced == "[00:01]Fixture"
    assert provider.session.post.call_args.kwargs["json"]["req_0"]["param"]["crypt"] == 0


def test_lyricsovh_encodes_metadata():
    provider = LyricsOvh(title="A/B?", artist="Été")
    provider.session.get = Mock(return_value=response({"lyrics": "Plain fixture"}))
    assert provider.get_lrc("").unsynced == "Plain fixture"
    assert provider.session.get.call_args.args[0].endswith("/%C3%89t%C3%A9/A%2FB%3F")


@pytest.mark.parametrize(
    ("provider", "data"), [(Kugou(), {"status": 500}), (QQMusic(), {"code": -1310})]
)
def test_body_error_is_not_a_miss(provider, data):
    provider.session.get = Mock(return_value=response(data))
    with pytest.raises(RuntimeError):
        provider.get_lrc("Song Artist")


def test_short_plain_text_is_not_synced():
    assert identify_lyrics_type("Short plain text") == "plaintext"
    assert identify_lyrics_type("[Chorus]\nText") == "plaintext"
    assert identify_lyrics_type("[00:01]Text") == "synced"
