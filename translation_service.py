import asyncio
from typing import List, Optional, Tuple
from pydantic import BaseModel
from google import genai
from google.genai import types
from models import LyricLine, TranslationStats
import os
import json
import cache_service
import time

class TranslationResponse(BaseModel):
    translations: List[str]

class SimpleTranslationResponse(BaseModel):
    translation: str

class LanguageDetectionResponse(BaseModel):
    languages: List[str]

class PhoneticsResponse(BaseModel):
    phonetics: List[str]

class TranslationService:
    def __init__(self):
        # The google-genai SDK uses the GOOGLE_API_KEY environment variable by default.
        # Ensure it is set in the .env file.
        # main.py calls load_dotenv() before initializing this service.
        try:
            self.client = genai.Client()
        except Exception as e:
            raise RuntimeError(
                "Failed to initialize Google GenAI Client. "
                "Please ensure the GOOGLE_API_KEY environment variable is set in your .env file. "
                f"Original error: {e}"
            )

    def _build_thinking_config(self, model_name: Optional[str], thinking_mode: Optional[str]) -> Optional[types.ThinkingConfig]:
        """Builds the thinking configuration based on the selected mode and model."""
        if not model_name or not thinking_mode or thinking_mode == "default":
            return None

        if thinking_mode == "no_thinking":
            # Only Flash models fully support disabling thinking with budget=0
            if "flash" in model_name.lower():
                return types.ThinkingConfig(thinking_budget=0)
            else:
                # For Pro models, 'no_thinking' is not supported. Fallback to default.
                print(f"Warning: 'No Thinking' mode is not supported for '{model_name}'. Using default thinking.")
                return None
        
        return None

    async def translate_lyrics(self, song_title: str, song_artist: str, lyrics: List[LyricLine], languages_to_translate: dict[str, str], original_languages: Optional[List[str]] = None, model_name: Optional[str] = None, thinking_mode: Optional[str] = None) -> Tuple[List[LyricLine], List[TranslationStats]]:
        if not lyrics or not languages_to_translate:
            return lyrics, []

        tasks = []
        lang_order_for_api = []
        stats_list = []
        
        for lang_code, lang_name in languages_to_translate.items():
            cache_key = f"{song_title}-{song_artist}-{lang_code}-translation"
            cached_data = cache_service.get_from_cache(cache_key)

            if cached_data and isinstance(cached_data, dict) and 'translations' in cached_data and 'stats' in cached_data:
                print(f"Found cached translation for '{song_title}' to {lang_name}")
                cached_translations = cached_data['translations']
                cached_stats = cached_data['stats']

                for line_idx, translation_text in enumerate(cached_translations):
                    lyrics[line_idx].translations[lang_code] = translation_text

                stats = TranslationStats.model_validate(cached_stats)
                stats.from_cache = True
                stats_list.append(stats)
            else:
                print(f"No cache for '{song_title}' to {lang_name}. Will call API.")
                tasks.append(self.translate_to_language(lyrics, lang_name, original_languages, model_name=model_name, thinking_mode=thinking_mode))
                lang_order_for_api.append((lang_code, lang_name))

        if not tasks:
            return lyrics, stats_list

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, (lang_code, lang_name) in enumerate(lang_order_for_api):
            result = results[i]
            if isinstance(result, Exception):
                print(f"Translation error for {lang_name}: {str(result)}")
                error_msg = f"Translation error: {str(result)}"
                for line in lyrics:
                    line.translations[lang_code] = error_msg
            else:
                translations, stats = result
                stats_list.append(stats)
                
                cache_key = f"{song_title}-{song_artist}-{lang_code}-translation"
                data_to_cache = {
                    "translations": translations,
                    "stats": stats.model_dump()
                }
                cache_service.save_to_cache(cache_key, data_to_cache)
                
                for line_idx, translation in enumerate(translations):
                    lyrics[line_idx].translations[lang_code] = translation
        
        return lyrics, stats_list
        
    async def get_phonetics(self, song_title: str, song_artist: str, lyrics: List[LyricLine], original_languages: List[str], model_name: Optional[str] = None, thinking_mode: Optional[str] = None) -> List[LyricLine]:
        if not lyrics:
            return lyrics
        
        cache_key = f"{song_title}-{song_artist}-phonetics"
        cached_phonetics = cache_service.get_from_cache(cache_key)

        if cached_phonetics and isinstance(cached_phonetics, list) and len(cached_phonetics) == len(lyrics):
            print(f"Found cached phonetics for '{song_title}'")
            for i, phonetic_text in enumerate(cached_phonetics):
                lyrics[i].phonetics = phonetic_text
            return lyrics
        
        print(f"No cache for phonetics for '{song_title}'. Will call API.")
        try:
            lines_to_process = [line.original for line in lyrics]
            num_lines = len(lines_to_process)
            content_to_process = "\n".join(lines_to_process)
            
            lang_info = f"The lyrics are in {', '.join(original_languages)}. " if original_languages and "Detection Failed" not in original_languages else ""

            system_instruction = (
                f"You are a linguistic expert specializing in phonetics. Your task is to provide the International Phonetic Alphabet (IPA) transcription for each line of the provided song lyrics. "
                f"{lang_info}"
                "The user's text consists of song lyrics separated by newlines. "
                f"There are exactly {num_lines} lines of input. "
                "Your response must be a JSON object that adheres to the provided schema. "
                f"The 'phonetics' list must contain exactly {num_lines} strings, one for each line of input text, containing the IPA transcription. "
                "Maintain a one-to-one correspondence between input lines and phonetic transcriptions. "
                "If a line is purely instrumental or cannot be transcribed, return an empty string for that line."
            )

            model_to_use = model_name or 'models/gemini-1.5-flash-latest'
            
            thinking_config = self._build_thinking_config(model_to_use, thinking_mode)
            generate_config = types.GenerateContentConfig(
                    response_mime_type='application/json',
                    response_schema=PhoneticsResponse,
                    system_instruction=system_instruction,
                    thinking_config=thinking_config,
                )

            response = await self.client.aio.models.generate_content(
                model=model_to_use,
                contents=content_to_process,
                config=generate_config,
            )
            
            parsed_response = PhoneticsResponse.model_validate_json(response.text)
            phonetics_list = parsed_response.phonetics

            if len(phonetics_list) != num_lines:
                raise Exception(f"Model returned {len(phonetics_list)} phonetic lines, but {num_lines} were expected.")
            
            phonetics_to_cache = []
            for i, phonetic_text in enumerate(phonetics_list):
                lyrics[i].phonetics = phonetic_text
                phonetics_to_cache.append(phonetic_text)
            
            cache_service.save_to_cache(cache_key, phonetics_to_cache)

            return lyrics

        except Exception as e:
            print(f"Phonetics generation error: {str(e)}")
            for line in lyrics:
                line.phonetics = "Phonetics generation failed."
            return lyrics
            
    async def detect_language(self, lyrics: List[LyricLine], title: str, artist: str, model_name: Optional[str] = None, thinking_mode: Optional[str] = None) -> List[str]:
        if not lyrics:
            return []

        cache_key = f"{title}-{artist}-language"
        cached_languages = cache_service.get_from_cache(cache_key)
        if cached_languages and isinstance(cached_languages, list):
            print(f"Found cached language detection for '{title}'")
            return cached_languages
            
        try:
            # Use a sample of the lyrics for detection
            sample_lyrics = "\n".join([line.original for line in lyrics[:10]])
            
            model_to_use = model_name or 'models/gemini-1.5-flash-latest'
            
            thinking_config = self._build_thinking_config(model_to_use, thinking_mode)
            generate_config = types.GenerateContentConfig(
                    response_mime_type='application/json',
                    response_schema=LanguageDetectionResponse,
                    system_instruction=(
                        f"You are a language detection expert. Your task is to identify the primary language(s) of the song '{title}' by '{artist}'. "
                        "The user's text consists of lines of song lyrics. Sometimes songs are in multiple languages. "
                        "Your response must be a JSON object that adheres to the provided schema, containing a 'languages' field "
                        "with a list of detected language names (e.g., ['English', 'Spanish']). If only one language is detected, return a list with a single string."
                    ),
                    thinking_config=thinking_config,
                )

            response = await self.client.aio.models.generate_content(
                model=model_to_use,
                contents=sample_lyrics,
                config=generate_config,
            )
            
            parsed_response = LanguageDetectionResponse.model_validate_json(response.text)
            
            # Cache the result
            cache_service.save_to_cache(cache_key, parsed_response.languages)
            
            return parsed_response.languages
            
        except Exception as e:
            print(f"Language detection error: {str(e)}")
            return ["Detection Failed"]
        
    async def translate_to_language(self, lyrics: List[LyricLine], target_lang_name: str, original_languages: Optional[List[str]] = None, model_name: Optional[str] = None, thinking_mode: Optional[str] = None) -> Tuple[List[str], TranslationStats]:
        try:
            lines_to_translate = [line.original for line in lyrics]
            num_lines = len(lines_to_translate)
            content_to_translate = "\n".join(lines_to_translate)
            
            source_lang_info = ""
            if original_languages and "Detection Failed" not in original_languages:
                source_lang_info = f" from {', '.join(original_languages)}"

            system_instruction = (
                f"You are a translation expert. Translate the user's text{source_lang_info} to {target_lang_name}. "
                "The user's text consists of song lyrics separated by newlines. "
                f"There are exactly {num_lines} lines of input. "
                "Your response must be a JSON object that adheres to the provided schema. "
                f"The 'translations' list must contain exactly {num_lines} translated strings, "
                "one for each line of input text, in the same order. "
                "Do not merge, split, or omit any lines. Maintain a one-to-one correspondence between input lines and translated lines."
            )

            model_to_use = model_name or 'models/gemini-1.5-flash-latest'
            
            thinking_config = self._build_thinking_config(model_to_use, thinking_mode)
            generate_config = types.GenerateContentConfig(
                    response_mime_type='application/json',
                    response_schema=TranslationResponse,
                    system_instruction=system_instruction,
                    thinking_config=thinking_config,
                )

            start_time = time.time()
            response = await self.client.aio.models.generate_content(
                model=model_to_use,
                contents=content_to_translate,
                config=generate_config
            )
            duration = time.time() - start_time

            # The response.text will be a JSON string matching the schema.
            parsed_response = TranslationResponse.model_validate_json(response.text)
            
            translations = parsed_response.translations
            if len(translations) != len(lyrics):
                # This indicates the model didn't follow instructions.
                raise Exception(f"Model returned {len(translations)} translations, but {len(lyrics)} were expected.")
            
            translated_text = " ".join(translations)
            translated_word_count = len(translated_text.split())

            stats = TranslationStats(
                language_name=target_lang_name,
                duration_seconds=duration,
                translated_word_count=translated_word_count,
                translated_token_count=response.usage_metadata.candidates_token_count
            )

            return translations, stats

        except Exception as e:
            print(f"Translation error for {target_lang_name}: {str(e)}")
            raise e

    async def _translate_single_text(self, text: str, target_lang_name: str, model_name: Optional[str] = None, thinking_mode: Optional[str] = None) -> str:
        try:
            system_instruction = (
                f"You are a translation expert. Translate the user's text to {target_lang_name}. "
                "The user's text is a song title. "
                "Your response must be a JSON object that adheres to the provided schema. "
                "The 'translation' field must contain the single translated string."
            )

            model_to_use = model_name or 'models/gemini-1.5-flash-latest'
            
            thinking_config = self._build_thinking_config(model_to_use, thinking_mode)
            generate_config = types.GenerateContentConfig(
                    response_mime_type='application/json',
                    response_schema=SimpleTranslationResponse,
                    system_instruction=system_instruction,
                    thinking_config=thinking_config,
                )

            response = await self.client.aio.models.generate_content(
                model=model_to_use,
                contents=text,
                config=generate_config,
            )

            parsed_response = SimpleTranslationResponse.model_validate_json(response.text)
            return parsed_response.translation

        except Exception as e:
            print(f"Single text translation error for {target_lang_name}: {str(e)}")
            raise e

    async def translate_text(self, text_to_translate: str, languages_to_translate: dict[str, str], model_name: Optional[str] = None, thinking_mode: Optional[str] = None) -> dict[str, str]:
        if not text_to_translate or not languages_to_translate:
            return {}

        tasks = []
        lang_order_for_api = []
        translated_titles = {}

        for lang_code, lang_name in languages_to_translate.items():
            cache_key = f"{text_to_translate}-{lang_code}-title-translation"
            cached_translation = cache_service.get_from_cache(cache_key)

            if cached_translation and isinstance(cached_translation, str):
                print(f"Found cached title translation for '{text_to_translate}' to {lang_name}")
                translated_titles[lang_code] = cached_translation
            else:
                print(f"No cache for title '{text_to_translate}' to {lang_name}. Will call API.")
                tasks.append(self._translate_single_text(text_to_translate, lang_name, model_name=model_name, thinking_mode=thinking_mode))
                lang_order_for_api.append((lang_code, lang_name))

        if not tasks:
            return translated_titles

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, (lang_code, lang_name) in enumerate(lang_order_for_api):
            result = results[i]
            if isinstance(result, Exception):
                print(f"Title translation error for {lang_name}: {str(result)}")
                translated_titles[lang_code] = "Translation Error"
            else:
                translated_titles[lang_code] = result
                cache_key = f"{text_to_translate}-{lang_code}-title-translation"
                cache_service.save_to_cache(cache_key, result)

        return translated_titles 