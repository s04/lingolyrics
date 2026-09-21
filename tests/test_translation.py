import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

import cache_service
from models import LyricLine
from translation_service import TranslationService


def lines():
    return [LyricLine(timestamp="[00:01]", time_seconds=1, original="Bonjour")]


def test_missing_key_has_actionable_error():
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        asyncio.run(
            TranslationService().translate_to_language(
                lines(), "English", model_name="openrouter:openrouter/free"
            )
        )


def test_openrouter_payload_and_response(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")

    async def post(self, url, **kwargs):
        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer test-only"
        assert kwargs["json"]["model"] == "provider/model"
        assert kwargs["json"]["response_format"]["json_schema"]["strict"] is True
        assert kwargs["json"]["provider"]["require_parameters"] is True
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"translations": ["Hello"]})}}],
                "usage": {"completion_tokens": 7},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    translated, stats = asyncio.run(
        TranslationService().translate_to_language(
            lines(), "English", model_name="openrouter:provider/model"
        )
    )
    assert translated == ["Hello"]
    assert stats.translated_token_count == 7


@pytest.mark.parametrize("status", [401, 402, 429, 503])
def test_openrouter_errors_do_not_expose_response(monkeypatch, status):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-test-value")

    async def post(*args, **kwargs):
        return httpx.Response(status, text="secret-test-value")

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    with pytest.raises(ValueError, match=f"HTTP {status}") as caught:
        asyncio.run(
            TranslationService().translate_to_language(
                lines(), "English", model_name="openrouter:x/y"
            )
        )
    assert "secret-test-value" not in str(caught.value)


def test_gemini_response_without_usage(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    service = TranslationService()
    generate = AsyncMock(
        return_value=SimpleNamespace(text='{"translations":["Hello"]}', usage_metadata=None)
    )
    service.client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    )
    result, stats = asyncio.run(service.translate_to_language(lines(), "English"))
    assert result == ["Hello"]
    assert stats.translated_token_count == 0


def test_line_mismatch_does_not_mutate_or_cache(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    service = TranslationService()
    generate = AsyncMock(
        return_value=SimpleNamespace(text='{"translations":[]}', usage_metadata=None)
    )
    service.client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    )
    original = lines()
    with pytest.raises(ValueError, match="wrong number"):
        asyncio.run(service.translate_lyrics("Title", "Artist", original, {"en": "English"}))
    assert original[0].translations == {}
    assert not cache_service.CACHE_DIR.exists()


def test_cache_varies_by_content_model_and_operation():
    service = TranslationService()
    keys = {
        service._cache_key(operation, content, model, "default")
        for operation in ["lyrics", "phonetics"]
        for content in ["a", "b"]
        for model in ["gemini-test", "openrouter:x/y"]
    }
    assert len(keys) == 8


def test_cached_translation_does_not_call_ai(monkeypatch):
    service = TranslationService()
    source = lines()
    key = service._cache_key("lyrics", ["Title", "Artist", ["Bonjour"], "en"], None, None)
    cache_service.save_to_cache(key, {"translations": ["Hello"]})
    generate = AsyncMock(side_effect=AssertionError("must not call API"))
    monkeypatch.setattr(service, "_generate", generate)
    result, stats = asyncio.run(
        service.translate_lyrics("Title", "Artist", source, {"en": "English"})
    )
    assert result[0].translations == {"en": "Hello"}
    assert source[0].translations == {}
    assert stats[0].from_cache


def test_phonetics_line_count_and_cache(monkeypatch):
    from translation_service import PhoneticsResponse

    service = TranslationService()
    generate = AsyncMock(return_value=(PhoneticsResponse(phonetics=["bɔ̃.ʒuʁ"]), 0))
    monkeypatch.setattr(service, "_generate", generate)
    for _ in range(2):
        result = asyncio.run(service.get_phonetics("Title", "Artist", lines(), ["French"]))
        assert result[0].phonetics == "bɔ̃.ʒuʁ"
    assert generate.await_count == 1


def test_bad_phonetics_preserves_input(monkeypatch):
    from translation_service import PhoneticsResponse

    service = TranslationService()
    monkeypatch.setattr(
        service, "_generate", AsyncMock(return_value=(PhoneticsResponse(phonetics=[]), 0))
    )
    original = lines()
    with pytest.raises(ValueError, match="wrong number"):
        asyncio.run(service.get_phonetics("Title", "Artist", original, ["French"]))
    assert original[0].phonetics is None


def test_title_and_detection_caching(monkeypatch):
    from translation_service import LanguageDetectionResponse, SimpleTranslationResponse

    service = TranslationService()
    generate = AsyncMock(
        side_effect=[
            (SimpleTranslationResponse(translation="Hello"), 0),
            (LanguageDetectionResponse(languages=["French"]), 0),
        ]
    )
    monkeypatch.setattr(service, "_generate", generate)
    for _ in range(2):
        assert asyncio.run(service.translate_text("Bonjour", {"en": "English"})) == {"en": "Hello"}
        assert asyncio.run(service.detect_language(lines(), "Title", "Artist")) == ["French"]
    assert generate.await_count == 2


def test_corrupt_cached_translation_regenerates(monkeypatch):
    from translation_service import TranslationResponse

    service = TranslationService()
    key = service._cache_key("lyrics", ["Title", "Artist", ["Bonjour"], "en"], None, None)
    cache_service.save_to_cache(key, {"translations": ["Too", "many"]})
    monkeypatch.setattr(
        service,
        "_generate",
        AsyncMock(return_value=(TranslationResponse(translations=["Hello"]), 3)),
    )
    result, stats = asyncio.run(
        service.translate_lyrics("Title", "Artist", lines(), {"en": "English"})
    )
    assert result[0].translations["en"] == "Hello"
    assert not stats[0].from_cache


@pytest.mark.parametrize(
    "text", ["not json", '{"translations":[3]}', '{"translations":["Hello"],"unexpected":true}']
)
def test_malformed_ai_response(monkeypatch, text):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only")
    service = TranslationService()
    service.client = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(
                generate_content=AsyncMock(
                    return_value=SimpleNamespace(text=text, usage_metadata=None)
                )
            )
        )
    )
    with pytest.raises(ValueError, match="invalid response"):
        asyncio.run(service.translate_to_language(lines(), "English"))
