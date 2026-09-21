import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import main
from demo import demo_song
from spotify_service import SpotifyService


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "PREFERENCES_PATH", tmp_path / "prefs.json")
    monkeypatch.setattr(
        main,
        "user_preferences",
        {
            "languages": ["en"],
            "translation_profile": main.DEFAULT_PROFILE,
            "custom_model": "",
            "lyrics_provider": "auto",
        },
    )
    monkeypatch.setattr(main, "active_song", None)
    monkeypatch.setattr(main, "selected_languages", [])
    monkeypatch.setattr(main, "workspace_lock", asyncio.Lock())
    monkeypatch.setattr(main, "spotify_service", SpotifyService(None, None, None))
    with TestClient(main.app) as client:
        yield client


def test_home_without_credentials(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Listen a little" in response.text
    assert "English" in response.text
    assert len(main.SUPPORTED_LANGUAGES) > 100
    assert client.get("/health").json()["status"] == "ok"


def test_demo_export_and_repeat(client):
    for _ in range(3):
        response = client.post("/demo")
        assert "Une fenêtre ouverte" in response.text
        assert "<script" not in response.text
        assert "The light comes into the room" in response.text
    export = client.get("/export")
    assert export.status_code == 200
    assert "attachment" in export.headers["content-disposition"]
    assert "en: The light" in export.text


def test_missing_spotify_preserves_workspace(client):
    client.post("/demo")
    response = client.get("/get-song-and-lyrics")
    assert response.headers["hx-retarget"] == "#notice"
    assert "Spotify credentials" in response.text
    assert main.active_song.demo


def test_save_preferences_reload(client):
    response = client.post(
        "/preferences",
        data={
            "languages": ["es", "fr"],
            "profile": "openrouter/custom",
            "custom_model": "provider/model",
            "lyrics_provider": "NetEase",
        },
    )
    assert "Settings saved" in response.text
    assert main.load_preferences()["languages"] == ["es", "fr"]
    assert main.profile()["model"] == "openrouter:provider/model"
    from bs4 import BeautifulSoup

    page = BeautifulSoup(client.get("/").text, "html.parser")
    assert page.select_one('input[value="es"]').has_attr("checked")


@pytest.mark.parametrize(
    "form",
    [
        {"languages": ["invalid"]},
        {"profile": "invalid"},
        {"lyrics_provider": "invalid"},
        {"profile": "openrouter/custom", "custom_model": "invalid"},
        {"languages": ["en", "es", "fr", "de", "it", "pt"]},
    ],
)
def test_invalid_preferences_do_not_save(client, form):
    response = client.post("/preferences", data=form)
    assert response.headers["hx-retarget"] == "#notice"
    assert not main.PREFERENCES_PATH.exists()


def test_clear_all_languages(client):
    client.post("/preferences", data={"profile": main.DEFAULT_PROFILE})
    assert main.user_preferences["languages"] == []
    client.post("/demo")
    assert "at least one" in client.post("/translate").text


def test_cross_origin_mutation_rejected(client):
    assert client.post("/demo", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/demo", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_oauth_state_required(client):
    assert client.get("/callback?code=untrusted&state=bad").status_code == 400


def test_no_private_data_mount(client):
    for path in ["/data/preferences.json", "/data/cache/anything.json", "/.env", "/.cache"]:
        assert client.get(path).status_code == 404


def test_no_song_actions(client):
    assert client.get("/export").status_code == 400
    for endpoint in ["/translate", "/phonetics", "/refresh-lyrics"]:
        assert client.post(endpoint).headers["hx-retarget"] == "#notice"


def test_search_validates_and_escapes(client, monkeypatch):
    assert "Enter a song" in client.post("/search", data={"title": "a"}).text

    def fetch(song, provider):
        song.lyrics = demo_song().lyrics
        return song

    monkeypatch.setattr(main.spotify_service, "get_lyrics_for_song", fetch)
    response = client.post(
        "/search", data={"title": "<script>alert(1)</script>", "artist": "Someone"}
    )
    assert "&lt;script&gt;" in response.text
    assert "<script>" not in response.text


def test_translation_failure_preserves_lyrics(client, monkeypatch):
    client.post("/demo")
    main.active_song.demo = False
    monkeypatch.setattr(
        main.translation_service,
        "translate_lyrics",
        AsyncMock(side_effect=ValueError("Provider unavailable")),
    )
    response = client.post("/translate")
    assert response.headers["hx-retarget"] == "#notice"
    assert main.active_song.lyrics[0].original == "La lumière entre dans la pièce"


def test_search_failure_preserves_song(client, monkeypatch):
    client.post("/demo")

    def fail(*args):
        raise RuntimeError("private request details")

    monkeypatch.setattr(main.spotify_service, "get_lyrics_for_song", fail)
    response = client.post("/search", data={"title": "Missing", "artist": "Nobody"})
    assert "private request details" not in response.text
    assert main.active_song.demo


def test_translation_commits_titles_languages_and_lyrics_together(client, monkeypatch):
    from models import TranslationStats

    client.post("/demo")
    main.active_song.demo = False
    updated = main.active_song.model_copy(deep=True).lyrics
    updated[0].translations["en"] = "Updated translation"
    stats = [
        TranslationStats(
            language_name="English",
            duration_seconds=0.1,
            translated_word_count=2,
            translated_token_count=3,
        )
    ]
    monkeypatch.setattr(
        main.translation_service, "translate_lyrics", AsyncMock(return_value=(updated, stats))
    )
    monkeypatch.setattr(
        main.translation_service, "translate_text", AsyncMock(return_value={"en": "An open window"})
    )
    monkeypatch.setattr(
        main.translation_service, "detect_language", AsyncMock(return_value=["French"])
    )
    response = client.post("/translate")
    assert "Updated translation" in response.text
    assert "An open window" in response.text
    assert main.active_song.original_languages == ["French"]


def test_spotify_new_song_and_stopped_state(client, monkeypatch):
    song = demo_song()
    song.demo = False
    monkeypatch.setattr(main.spotify_service, "get_current_song_info", lambda: song)
    monkeypatch.setattr(main.spotify_service, "get_lyrics_for_song", lambda *args: song)
    assert "Une fenêtre ouverte" in client.get("/get-song-and-lyrics").text
    monkeypatch.setattr(main.spotify_service, "get_current_song_info", lambda: None)
    assert "Take it for a spin" in client.get("/get-song-and-lyrics").text
    assert main.active_song is None


def test_refresh_uses_selected_source_and_bypasses_cache(client, monkeypatch):
    client.post("/demo")
    main.active_song.demo = False

    def fetch(song, provider, refresh):
        assert provider == "auto"
        assert refresh is True
        song.lyrics[0].original = "Fresh lyric"
        return song

    monkeypatch.setattr(main.spotify_service, "get_lyrics_for_song", fetch)
    assert "Fresh lyric" in client.post("/refresh-lyrics").text
    assert main.selected_languages == []


def test_invalid_host_rejected(client):
    assert client.get("/", headers={"Host": "attacker.example"}).status_code == 400


def test_preferences_corruption_falls_back(client):
    main.PREFERENCES_PATH.write_text("{invalid")
    assert main.load_preferences()["translation_profile"] == main.DEFAULT_PROFILE


def test_websocket_rejects_cross_origin(client):
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws", headers={"Origin": "https://evil.example"}),
    ):
        pass


def test_websocket_sends_playback_state(client, monkeypatch):
    client.post("/demo")
    main.active_song.demo = False
    monkeypatch.setattr(
        main.spotify_service,
        "get_current_playback_state",
        lambda: {"track_id": "demo", "position": 1, "is_playing": True},
    )
    with client.websocket_connect("/ws") as socket:
        assert socket.receive_json()["position"] == 1


def test_websocket_disconnects_cleanly_without_song(client):
    with client.websocket_connect("/ws") as socket:
        socket.send_text("ping")


def test_openrouter_catalog_filters_structured_text_models(client, monkeypatch):
    import httpx

    async def get(self, url):
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "a/text",
                        "name": "Text",
                        "architecture": {"output_modalities": ["text"]},
                        "supported_parameters": ["structured_outputs"],
                    },
                    {
                        "id": "b/image",
                        "name": "Image",
                        "architecture": {"output_modalities": ["image"]},
                        "supported_parameters": ["structured_outputs"],
                    },
                    {
                        "id": "c/plain",
                        "name": "Plain",
                        "architecture": {"output_modalities": ["text"]},
                        "supported_parameters": [],
                    },
                ]
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    assert client.get("/models/openrouter").json() == {"models": [{"id": "a/text", "name": "Text"}]}


def test_openrouter_catalog_error(client, monkeypatch):
    import httpx

    async def get(*args, **kwargs):
        raise httpx.ConnectError("private request details")

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    response = client.get("/models/openrouter")
    assert response.status_code == 502
    assert "private request details" not in response.text


def test_oauth_valid_state_exchanges_code(client, monkeypatch):
    from unittest.mock import Mock

    auth = Mock()
    monkeypatch.setattr(main.spotify_service, "auth", auth)
    client.cookies.set("spotify_oauth_state", "valid-state")
    response = client.get("/callback?state=valid-state&code=synthetic-code", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/"
    auth.get_access_token.assert_called_once_with("synthetic-code", check_cache=False)


def test_oauth_error_does_not_exchange_code(client, monkeypatch):
    from unittest.mock import Mock

    auth = Mock()
    monkeypatch.setattr(main.spotify_service, "auth", auth)
    client.cookies.set("spotify_oauth_state", "valid-state")
    response = client.get("/callback?state=valid-state&error=access_denied")
    assert response.status_code == 400
    auth.get_access_token.assert_not_called()


def test_reloading_same_spotify_song_preserves_translations(client, monkeypatch):
    client.post("/demo")
    main.active_song.demo = False
    song = main.active_song.model_copy(deep=True)
    song.lyrics = []
    song.current_position = 20
    monkeypatch.setattr(main.spotify_service, "get_current_song_info", lambda: song)
    monkeypatch.setattr(
        main.spotify_service,
        "get_lyrics_for_song",
        lambda *args: pytest.fail("Existing lyrics should be retained"),
    )
    response = client.get("/get-song-and-lyrics")
    assert "The light comes into the room" in response.text
    assert main.active_song.current_position == 20
    assert main.selected_languages == ["en"]
