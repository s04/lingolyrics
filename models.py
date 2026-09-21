from pydantic import BaseModel, Field


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
    phonetics: str | None = None
    translations: dict[str, str] = Field(default_factory=dict)  # Language code -> translated text


class Song(BaseModel):
    title: str
    artist: str
    spotify_id: str
    current_position: float = 0  # Current playback position in seconds
    is_playing: bool = False
    lyrics: list[LyricLine] = Field(default_factory=list)
    original_languages: list[str] = Field(default_factory=list)
    translated_titles: dict[str, str] = Field(default_factory=dict)
    synced: bool = True
    lyrics_source: str = ""
    demo: bool = False
    album: str = ""
    duration: float | None = None
    primary_artist: str = ""
