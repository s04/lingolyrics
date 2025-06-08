from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os
from dotenv import load_dotenv
from spotify_service import SpotifyService
from translation_service import TranslationService
import socket
import asyncio
import csv
import json
from typing import List

# Load environment variables
load_dotenv()

app = FastAPI()

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

# Only mount static files if directory exists
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
if os.path.exists("data"):
    app.mount("/data", StaticFiles(directory="data"), name="data")

templates = Jinja2Templates(directory="templates")

# In-memory store for user preferences for a single-user session.
# This replaces the JSON file-based storage.
user_preferences = {
    "languages": [],
    "translation_profile": "gemini-2.5-flash-preview-05-20_no_thinking"
}

def get_user_preferences() -> dict:
    """Loads user preferences from memory."""
    return user_preferences

def save_user_preferences(preferences: dict):
    """Saves user preferences to memory."""
    global user_preferences
    user_preferences.update(preferences)

def load_languages_from_csv(file_path: str) -> dict:
    languages = {}
    try:
        with open(file_path, mode='r', encoding='utf-8') as csv_file:
            # Clean up header whitespace
            reader = csv.reader(csv_file)
            header = [h.strip() for h in next(reader)]
            csv_reader = csv.DictReader(csv_file, fieldnames=header)
            
            for row in csv_reader:
                code = row.get('639-1')
                name = row.get('Language name')
                flag = row.get('Flag')
                if code and name:
                    languages[code] = {
                        "name": name.split(';')[0].split(',')[0].strip(),
                        "flag": flag.strip() if flag else ""
                    }
    except Exception as e:
        print(f"Error loading languages from CSV: {e}")
        # Fallback to a minimal list if CSV parsing fails
        return {
            "en": {"name": "English", "flag": "🇬🇧"}, 
            "es": {"name": "Spanish", "flag": "🇪🇸"}
        }
    return languages

# Use environment variables properly
spotify_service = SpotifyService(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI")
)

translation_service = TranslationService()

SUPPORTED_LANGUAGES = load_languages_from_csv("data/Languages.csv")

# Define our simplified model options
TRANSLATION_PROFILES = {
    "gemini-2.5-flash-preview-05-20_default": {
        "name": "gemini-2.5-flash-preview-05-20 (Default)",
        "model": "models/gemini-2.5-flash-preview-05-20",
        "thinking_mode": "default"
    },
    "gemini-2.5-flash-preview-05-20_no_thinking": {
        "name": "gemini-2.5-flash-preview-05-20 (No Thinking)",
        "model": "models/gemini-2.5-flash-preview-05-20",
        "thinking_mode": "no_thinking"
    },
    "gemini-2.5-pro-preview-06-05_default": {
        "name": "gemini-2.5-pro-preview-06-05",
        "model": "models/gemini-2.5-pro-preview-06-05",
        "thinking_mode": "default"
    },
    "gemini-2.0-flash_default": {
        "name": "gemini-2.0-flash",
        "model": "models/gemini-2.0-flash",
        "thinking_mode": "default"
    },
    "gemini-2.0-flash-lite_default": {
        "name": "gemini-2.0-flash-lite",
        "model": "models/gemini-2.0-flash-lite",
        "thinking_mode": "default"
    },
    "gemini-1.5-flash-8b_default": {
        "name": "gemini-1.5-flash-8b",
        "model": "models/gemini-1.5-flash-8b",
        "thinking_mode": "default"
    },
    "gemini-1.5-flash_default": {
        "name": "gemini-1.5-flash",
        "model": "models/gemini-1.5-flash",
        "thinking_mode": "default"
    }
}

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    user_prefs = get_user_preferences()
    user_languages = user_prefs.get('languages', [])
    
    # Sort languages to show selected ones first
    all_langs = list(SUPPORTED_LANGUAGES.items())
    all_langs.sort(key=lambda item: item[0] in user_languages, reverse=True)
    sorted_languages = dict(all_langs)
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request, 
            "languages": sorted_languages,
            "user_languages": user_languages,
            "translation_profiles": TRANSLATION_PROFILES,
            "user_profile": user_prefs.get('translation_profile', 'gemini-2.5-flash-preview-05-20_default'),
            "initial_message": "Translate a song to see stats here."
        }
    )

@app.get("/current-song", response_class=HTMLResponse)
def get_current_song(request: Request):
    try:
        print("Starting current song request")
        song = spotify_service.get_current_song_info()
        
        print(f"Song data received: {song.title if song else 'None'}")
        
        if not song:
            return templates.TemplateResponse(
                "components/no_song.html",
                {"request": request}
            )
            
        return templates.TemplateResponse(
            "components/song_header.html",
            {"request": request, "song": song}
        )
    except Exception as e:
        print(f"Error in get_current_song: {str(e)}")
        return templates.TemplateResponse(
            "components/error.html",
            {
                "request": request,
                "message": f"An error occurred: {str(e)}"
            }
        )

@app.get("/lyrics-loader", response_class=HTMLResponse)
def lyrics_loader(request: Request):
    return templates.TemplateResponse("components/lyrics_loader.html", {"request": request})

@app.get("/get-lyrics", response_class=HTMLResponse)
async def get_lyrics(request: Request):
    try:
        # Get current song from cache or fetch fresh
        song = spotify_service.current_song_cache
        if not song:
            song = spotify_service.get_current_song_info()
        
        if not song:
            return templates.TemplateResponse(
                "components/no_song.html",
                {"request": request}
            )
        
        # Fetch lyrics for the song
        song_with_lyrics = spotify_service.get_lyrics_for_song(song)
        
        if not song_with_lyrics or not song_with_lyrics.lyrics:
            return templates.TemplateResponse(
                "components/error.html",
                {
                    "request": request,
                    "message": "No lyrics found for this song. Some songs may not have synchronized lyrics available."
                }
            )
        
        # Detect language now that we have lyrics
        if not song_with_lyrics.original_languages:
            print(f"Lyrics found for {song_with_lyrics.title}, detecting language...")
            user_prefs = get_user_preferences()
            profile_key = user_prefs.get('translation_profile', 'gemini-2.5-flash-preview-05-20_default')
            profile = TRANSLATION_PROFILES[profile_key]
            
            langs = await translation_service.detect_language(
                song_with_lyrics.lyrics,
                song_with_lyrics.title,
                song_with_lyrics.artist,
                model_name=profile["model"],
                thinking_mode=profile["thinking_mode"]
            )
            song_with_lyrics.original_languages = langs
            print(f"Languages detected: {langs}")
        
        return templates.TemplateResponse(
            "components/lyrics.html",
            {"request": request, "song": song_with_lyrics, "selected_languages": []}
        )
        
    except Exception as e:
        print(f"Error getting lyrics: {str(e)}")
        return templates.TemplateResponse(
            "components/error.html",
            {
                "request": request,
                "message": f"Error fetching lyrics: {str(e)}"
            }
        )

@app.get("/get-song-and-lyrics", response_class=HTMLResponse)
async def get_song_and_lyrics(request: Request):
    try:
        # 1. Get song info
        song = spotify_service.get_current_song_info()
        
        if not song:
            no_song_html = templates.TemplateResponse("components/no_song.html", {"request": request}).body.decode()
            lyrics_placeholder = '<p class="text-gray-500 text-center">No song is currently playing on Spotify.</p>'
            
            return HTMLResponse(content=f"""
                <div id="song-container" hx-swap-oob="true">{no_song_html}</div>
                {lyrics_placeholder}
            """)

        # 2. Get lyrics
        song_with_lyrics = spotify_service.get_lyrics_for_song(song)
        
        song_header_template = templates.get_template("components/song_header.html")

        if not song_with_lyrics or not song_with_lyrics.lyrics:
            song_header_html = song_header_template.render({"request": request, "song": song})
            lyrics_error_html = templates.TemplateResponse(
                "components/error.html",
                {
                    "request": request,
                    "message": "No lyrics found for this song. Some songs may not have synchronized lyrics available."
                }
            ).body.decode()
            return HTMLResponse(content=f"""
                <div id="song-container" hx-swap-oob="true">{song_header_html}</div>
                {lyrics_error_html}
            """)

        # 3. Detect language
        if not song_with_lyrics.original_languages:
            print(f"Lyrics found for {song_with_lyrics.title}, detecting language...")
            user_prefs = get_user_preferences()
            profile_key = user_prefs.get('translation_profile', 'gemini-2.5-flash-preview-05-20_default')
            profile = TRANSLATION_PROFILES[profile_key]
            
            langs = await translation_service.detect_language(
                song_with_lyrics.lyrics,
                song_with_lyrics.title,
                song_with_lyrics.artist,
                model_name=profile["model"],
                thinking_mode=profile["thinking_mode"]
            )
            song_with_lyrics.original_languages = langs
            print(f"Languages detected: {langs}")
        
        # 4. Render templates
        song_header_html = song_header_template.render({"request": request, "song": song_with_lyrics})
        lyrics_template = templates.get_template("components/lyrics.html")
        lyrics_html = lyrics_template.render({"request": request, "song": song_with_lyrics, "selected_languages": []})
        
        return HTMLResponse(content=f"""
            <div id="song-container" hx-swap-oob="true">{song_header_html}</div>
            {lyrics_html}
        """)
        
    except Exception as e:
        print(f"Error in get_song_and_lyrics: {str(e)}")
        error_message_html = templates.TemplateResponse(
            "components/error.html",
            {
                "request": request,
                "message": f"An error occurred: {str(e)}"
            }
        ).body.decode()
        return HTMLResponse(content=f"""
            <div id="song-container" hx-swap-oob="true">{error_message_html}</div>
            {error_message_html}
        """)

@app.get("/get-song-lyrics-phonetics", response_class=HTMLResponse)
async def get_song_lyrics_phonetics(request: Request):
    try:
        # 1. Get song info
        song = spotify_service.get_current_song_info()
        
        if not song:
            no_song_html = templates.TemplateResponse("components/no_song.html", {"request": request}).body.decode()
            lyrics_placeholder = '<p class="text-gray-500 text-center">No song is currently playing on Spotify.</p>'
            
            return HTMLResponse(content=f"""
                <div id="song-container" hx-swap-oob="true">{no_song_html}</div>
                {lyrics_placeholder}
            """)

        # 2. Get lyrics
        song_with_lyrics = spotify_service.get_lyrics_for_song(song)
        
        song_header_template = templates.get_template("components/song_header.html")

        if not song_with_lyrics or not song_with_lyrics.lyrics:
            song_header_html = song_header_template.render({"request": request, "song": song})
            lyrics_error_html = templates.TemplateResponse(
                "components/error.html",
                {
                    "request": request,
                    "message": "No lyrics found for this song. Some songs may not have synchronized lyrics available."
                }
            ).body.decode()
            return HTMLResponse(content=f"""
                <div id="song-container" hx-swap-oob="true">{song_header_html}</div>
                {lyrics_error_html}
            """)

        # 3. Detect language & get model profile
        user_prefs = get_user_preferences()
        profile_key = user_prefs.get('translation_profile', 'gemini-2.5-flash-preview-05-20_default')
        profile = TRANSLATION_PROFILES[profile_key]
        model = profile["model"]
        thinking_mode = profile["thinking_mode"]

        if not song_with_lyrics.original_languages:
            print(f"Lyrics found for {song_with_lyrics.title}, detecting language...")
            langs = await translation_service.detect_language(
                song_with_lyrics.lyrics,
                song_with_lyrics.title,
                song_with_lyrics.artist,
                model_name=model,
                thinking_mode=thinking_mode
            )
            song_with_lyrics.original_languages = langs
            print(f"Languages detected: {langs}")
        
        # 4. Get Phonetics
        print(f"Fetching phonetics for {song_with_lyrics.title}...")
        song_with_lyrics.lyrics = await translation_service.get_phonetics(
            song_with_lyrics.title,
            song_with_lyrics.artist,
            song_with_lyrics.lyrics,
            song_with_lyrics.original_languages,
            model_name=model,
            thinking_mode=thinking_mode
        )
        print("Phonetics fetched.")

        # 5. Render templates
        song_header_html = song_header_template.render({"request": request, "song": song_with_lyrics})
        lyrics_template = templates.get_template("components/lyrics.html")
        lyrics_html = lyrics_template.render({"request": request, "song": song_with_lyrics, "selected_languages": {}})
        
        return HTMLResponse(content=f"""
            <div id="song-container" hx-swap-oob="true">{song_header_html}</div>
            {lyrics_html}
        """)
        
    except Exception as e:
        print(f"Error in get_song_lyrics_phonetics: {str(e)}")
        error_message_html = templates.TemplateResponse(
            "components/error.html",
            {"request": request, "message": f"An error occurred: {str(e)}"}
        ).body.decode()
        return HTMLResponse(content=f"""
            <div id="song-container" hx-swap-oob="true">{error_message_html}</div>
            {error_message_html}
        """)

@app.post("/translate")
async def translate_song(request: Request):
    try:
        form = await request.form()
        language_codes = form.getlist("languages")
        
        if not language_codes:
            # If no languages are selected in the form, use the user's saved preferences
            user_prefs = get_user_preferences()
            saved_languages = user_prefs.get('languages', [])
            if saved_languages:
                print(f"No languages selected, using saved preferences: {saved_languages}")
                language_codes = saved_languages
            else:
                return templates.TemplateResponse(
                    "components/error.html",
                    {"request": request, "message": "Please select at least one language or save your preferences."}
                )
        
        # Use cached song with lyrics
        song = spotify_service.current_song_cache
        if not song:
            return templates.TemplateResponse(
                "components/error.html",
                {"request": request, "message": "No song loaded. Please get a song and lyrics first."}
            )
        
        if not song.lyrics:
            return templates.TemplateResponse(
                "components/error.html",
                {"request": request, "message": "No lyrics found. Please get lyrics first."}
            )
        
        languages_to_translate = {
            code: SUPPORTED_LANGUAGES[code]["name"] 
            for code in language_codes if code in SUPPORTED_LANGUAGES
        }
        
        user_prefs = get_user_preferences()
        profile_key = user_prefs.get('translation_profile', 'gemini-2.5-flash-preview-05-20_default')
        profile = TRANSLATION_PROFILES[profile_key]
        model = profile["model"]
        thinking_mode = profile["thinking_mode"]

        # Translate lyrics and title in parallel
        lyrics_task = translation_service.translate_lyrics(
            song.title,
            song.artist,
            song.lyrics,
            languages_to_translate,
            song.original_languages,
            model_name=model,
            thinking_mode=thinking_mode
        )
        
        title_task = translation_service.translate_text(
            song.title,
            languages_to_translate,
            model_name=model,
            thinking_mode=thinking_mode
        )

        results = await asyncio.gather(lyrics_task, title_task)

        song.lyrics, translation_stats = results[0]
        song.translated_titles = results[1]
        
        selected_languages_details = {
            code: SUPPORTED_LANGUAGES[code] for code in language_codes if code in SUPPORTED_LANGUAGES
        }
        
        # Render all components
        lyrics_template = templates.get_template("components/lyrics.html")
        lyrics_html = lyrics_template.render({
            "request": request, 
            "song": song, 
            "selected_languages": selected_languages_details
        })

        song_header_template = templates.get_template("components/song_header.html")
        song_header_html = song_header_template.render({
            "request": request,
            "song": song
        })

        stats_template = templates.get_template("components/stats_card.html")
        stats_html = stats_template.render({
            "request": request,
            "stats": translation_stats
        })
        
        return HTMLResponse(content=f"""
            <div id="song-container" hx-swap-oob="true">{song_header_html}</div>
            <div id="stats-container" hx-swap-oob="true">{stats_html}</div>
            {lyrics_html}
        """)
        
    except Exception as e:
        print(f"Translation error: {str(e)}")
        return templates.TemplateResponse(
            "components/error.html",
            {"request": request, "message": f"Error: {str(e)}"}
        )

@app.post("/preferences")
async def save_language_preferences(request: Request):
    form = await request.form()
    selected_languages = form.getlist("languages")
    
    prefs = get_user_preferences()
    prefs['languages'] = selected_languages
    save_user_preferences(prefs)
    
    # Sort languages to show selected ones first for the re-rendered component
    all_langs = list(SUPPORTED_LANGUAGES.items())
    all_langs.sort(key=lambda item: item[0] in selected_languages, reverse=True)
    sorted_languages = dict(all_langs)
    
    # Return an updated fragment of the languages UI
    return templates.TemplateResponse(
        "components/language_list.html",
        {
            "request": request,
            "languages": sorted_languages,
            "user_languages": prefs['languages']
        }
    )

@app.post("/preferences/profile")
async def save_profile_preference(request: Request):
    form = await request.form()
    selected_profile = form.get("profile")

    prefs = get_user_preferences()
    if selected_profile in TRANSLATION_PROFILES:
        prefs['translation_profile'] = selected_profile
    else:
        prefs['translation_profile'] = 'gemini-2.5-flash-preview-05-20_default' # Fallback
    save_user_preferences(prefs)
    
    return HTMLResponse(status_code=204)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket connection accepted.")
    try:
        while True:
            # Handle client-side ping to keep connection alive
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                if data == 'ping':
                    continue
            except asyncio.TimeoutError:
                pass # No data from client is fine, proceed to send server state

            playback_state = spotify_service.get_current_playback_state()
            if playback_state:
                await websocket.send_json(playback_state)
            
            # Send updates roughly every second
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        print("Client disconnected from WebSocket.")
    except Exception as e:
        print(f"Error in WebSocket: {e}")
    finally:
        print("Closing WebSocket connection.")

if __name__ == "__main__":
    import uvicorn
    
    # Find an available port starting from 8000
    port = 8000
    while is_port_in_use(port) and port < 8010:
        print(f"Port {port} is in use, trying next port...")
        port += 1
    
    if port >= 8010:
        raise RuntimeError("No available ports found between 8000 and 8009")
    
    print(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port) 