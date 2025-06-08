from pydantic import BaseModel
from typing import List, Dict, Optional

class TranslationStats(BaseModel):
    language_name: str
    duration_seconds: float
    translated_word_count: int
    translated_token_count: int
    from_cache: bool = False

class LyricLine(BaseModel):
    timestamp: str  # The LRC timestamp like [00:16.45]
    time_seconds: float  # Timestamp converted to seconds
    original: str
    phonetics: Optional[str] = None
    translations: Dict[str, str] = {}  # Language code -> translated text

class Song(BaseModel):
    title: str
    artist: str
    spotify_id: str
    current_position: float = 0  # Current playback position in seconds
    is_playing: bool = False
    lyrics: List[LyricLine] = []
    original_languages: List[str] = []
    translated_titles: Dict[str, str] = {} 