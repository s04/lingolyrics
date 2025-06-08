import spotipy
from spotipy.oauth2 import SpotifyOAuth
import syncedlyrics
from models import Song, LyricLine
import re
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor
import time
import cache_service

class SpotifyService:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            scope="user-read-currently-playing user-read-playback-state",
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri
        ))
        self.current_song_cache = None
        self.lyrics_fetch_time = 0
        self.lyrics_timeout = 30  # Timeout after 30 seconds
        self.executor = ThreadPoolExecutor(max_workers=1)

    def parse_enhanced_lrc(self, lrc: str) -> List[LyricLine]:
        lyrics = []
        current_line = []
        current_timestamp = None
        
        for line in lrc.split('\n'):
            if not line.strip():
                continue
            
            # Find all timestamp-word pairs in the line
            matches = re.finditer(r'<(\d+:\d+\.\d+)>([^<]+)', line)
            for match in matches:
                timestamp, word = match.groups()
                if not current_timestamp:
                    current_timestamp = timestamp
                current_line.append(word.strip())
            
            # End of line - create LyricLine
            if current_line:
                # Convert timestamp to seconds
                minutes, seconds = map(float, current_timestamp.split(':'))
                total_seconds = minutes * 60 + seconds
                
                lyrics.append(LyricLine(
                    timestamp=f"[{current_timestamp}]",
                    time_seconds=total_seconds,
                    original=' '.join(current_line)
                ))
                current_line = []
                current_timestamp = None
            
        return lyrics

    def parse_regular_lrc(self, lrc: str) -> List[LyricLine]:
        lyrics = []
        for line in lrc.split('\n'):
            if line.strip():
                timestamp = re.search(r'\[([^\]]+)\]', line)
                text = re.sub(r'\[[^\]]+\]', '', line).strip()
                if timestamp and text:
                    time_str = timestamp.group(1)
                    minutes, seconds = map(float, time_str.split(':'))
                    total_seconds = minutes * 60 + seconds
                    
                    lyrics.append(LyricLine(
                        timestamp=timestamp.group(0),
                        time_seconds=total_seconds,
                        original=text
                    ))
        return lyrics

    def fetch_lyrics_with_timeout(self, song_title: str, song_artist: str) -> Optional[str]:
        current_time = time.time()
        
        # If we've recently tried and failed to fetch lyrics, don't try again yet
        if current_time - self.lyrics_fetch_time < self.lyrics_timeout:
            return None
            
        self.lyrics_fetch_time = current_time
        
        try:
            # Try enhanced lyrics first
            enhanced_lrc = syncedlyrics.search(f"{song_title} {song_artist}", enhanced=True)
            if enhanced_lrc:
                return enhanced_lrc
                
            # Fall back to plain lyrics
            plain_lrc = syncedlyrics.search(f"{song_title} {song_artist}", plain_only=True)
            return plain_lrc
            
        except Exception as e:
            print(f"Error fetching lyrics: {e}")
            raise e

    def get_current_song_info(self) -> Optional[Song]:
        """Get current song info without lyrics"""
        try:
            current_track = self.sp.current_user_playing_track()
            if not current_track:
                return None

            track = current_track['item']
            track_id = track['id']
            
            # Create song object without lyrics
            song = Song(
                title=track['name'],
                artist=track['artists'][0]['name'],
                spotify_id=track_id,
                current_position=current_track['progress_ms'] / 1000,
                is_playing=current_track['is_playing']
            )

            # Cache the new song (without lyrics)
            self.current_song_cache = song
            return song

        except Exception as e:
            print(f"Error getting current song: {e}")
            return None

    def get_lyrics_for_song(self, song: Song) -> Optional[Song]:
        """Fetch lyrics for a given song, using cache if available."""
        cache_key = f"{song.title}-{song.artist}-lyrics"
        cached_lyrics_data = cache_service.get_from_cache(cache_key)

        if cached_lyrics_data:
            print(f"Found cached lyrics for '{song.title}'")
            try:
                song.lyrics = [LyricLine.model_validate(line_data) for line_data in cached_lyrics_data]
                self.current_song_cache = song
                return song
            except Exception as e:
                print(f"Error loading lyrics from cache, refetching. Error: {e}")

        lrc = self.fetch_lyrics_with_timeout(song.title, song.artist)
        if lrc:
            if '<' in lrc:
                song.lyrics = self.parse_enhanced_lrc(lrc)
            else:
                song.lyrics = self.parse_regular_lrc(lrc)
            
            if song.lyrics:
                lyrics_to_cache = [line.model_dump() for line in song.lyrics]
                cache_service.save_to_cache(cache_key, lyrics_to_cache)
            
            self.current_song_cache = song
            return song
        return None

    def get_current_playback_state(self) -> Optional[dict]:
        try:
            playback = self.sp.current_playback()
            if not playback or not playback.get('item'):
                return {"is_playing": False, "position": 0, "timestamp": time.time()}

            return {
                "is_playing": playback['is_playing'],
                "position": playback['progress_ms'] / 1000,
                "timestamp": time.time()
            }
        except Exception as e:
            print(f"Error getting playback state: {e}")
            return None

    def get_current_song(self) -> Optional[Song]:
        try:
            current_track = self.sp.current_user_playing_track()
            if not current_track:
                return None

            track = current_track['item']
            track_id = track['id']
            
            # If we have the same song cached, just update the position
            if (self.current_song_cache and 
                self.current_song_cache.spotify_id == track_id):
                self.current_song_cache.current_position = current_track['progress_ms'] / 1000
                self.current_song_cache.is_playing = current_track['is_playing']
                return self.current_song_cache

            # Create new song object
            song = Song(
                title=track['name'],
                artist=track['artists'][0]['name'],
                spotify_id=track_id,
                current_position=current_track['progress_ms'] / 1000,
                is_playing=current_track['is_playing']
            )

            # Fetch lyrics
            lrc = self.fetch_lyrics_with_timeout(song.title, song.artist)
            if lrc:
                if '<' in lrc:  # Check if it's enhanced format
                    song.lyrics = self.parse_enhanced_lrc(lrc)
                else:
                    song.lyrics = self.parse_regular_lrc(lrc)

            # Cache the new song
            self.current_song_cache = song
            return song

        except Exception as e:
            print(f"Error getting current song: {e}")
            return None 