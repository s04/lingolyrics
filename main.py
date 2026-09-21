"""Single-user local application. Run on a loopback interface."""

import asyncio
import csv
import json
import os
import re
import secrets
from contextlib import suppress
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from demo import demo_song
from lyrics_service import PROVIDERS, InstrumentalTrack
from model_catalog import DEFAULT_PROFILE, TRANSLATION_PROFILES
from models import Song
from spotify_service import SpotifyService
from translation_service import TranslationService

BASE_DIR = Path(__file__).resolve().parent
if os.getenv("LINGOLYRICS_LOAD_ENV", "1") != "0":
    load_dotenv(BASE_DIR / ".env")
PREFERENCES_PATH = Path(
    os.getenv("LINGOLYRICS_PREFERENCES", str(BASE_DIR / "data" / "preferences.json"))
)
app = FastAPI(title="LingoLyrics")
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"]
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
spotify_service = SpotifyService(
    os.getenv("SPOTIPY_CLIENT_ID"),
    os.getenv("SPOTIPY_CLIENT_SECRET"),
    os.getenv("SPOTIPY_REDIRECT_URI"),
)
translation_service = TranslationService()
# Serialize workspace changes: a slow translation must never overwrite a new song.
workspace_lock = asyncio.Lock()
active_song: Song | None = None
selected_languages: list[str] = []


def load_languages_from_csv(file_path):
    with open(file_path, encoding="utf-8") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        reader.fieldnames = [name.strip() for name in reader.fieldnames]
        return {
            row["639-1"].strip(): {
                "name": row["Language name"].split(";")[0].split(",")[0].strip(),
                "flag": row.get("Flag", "").strip(),
            }
            for row in reader
            if row.get("639-1") and row.get("Language name")
        }


SUPPORTED_LANGUAGES = load_languages_from_csv(BASE_DIR / "data" / "Languages.csv")


def load_preferences():
    defaults = {
        "languages": ["en"],
        "translation_profile": "openrouter/free"
        if os.getenv("OPENROUTER_API_KEY")
        and not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        else DEFAULT_PROFILE,
        "custom_model": "",
        "lyrics_provider": "auto",
    }
    try:
        saved = json.loads(PREFERENCES_PATH.read_text())
        if isinstance(saved, dict):
            defaults["languages"] = [
                code for code in saved.get("languages", []) if code in SUPPORTED_LANGUAGES
            ][:5]
            if saved.get("translation_profile") in TRANSLATION_PROFILES:
                defaults["translation_profile"] = saved["translation_profile"]
            if saved.get("lyrics_provider") in PROVIDERS:
                defaults["lyrics_provider"] = saved["lyrics_provider"]
            custom = saved.get("custom_model", "")
            if isinstance(custom, str) and re.fullmatch(r"[\w./:-]{0,160}", custom):
                defaults["custom_model"] = custom
    except (OSError, ValueError, TypeError):
        pass
    return defaults


user_preferences = load_preferences()


def save_user_preferences(preferences):
    updated = {**user_preferences, **preferences}
    temporary = PREFERENCES_PATH.with_suffix(".tmp")
    PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    temporary.replace(PREFERENCES_PATH)
    user_preferences.update(updated)


def profile():
    selected = TRANSLATION_PROFILES[user_preferences["translation_profile"]].copy()
    if user_preferences["translation_profile"] == "openrouter/custom":
        custom = user_preferences["custom_model"]
        if not custom or "/" not in custom:
            raise ValueError(
                "Enter an OpenRouter model ID, such as provider/model, and save settings."
            )
        selected["model"] = "openrouter:" + custom
    return selected


def fragment(name, request, **context):
    return templates.get_template(f"components/{name}.html").render(request=request, **context)


def error(request, message):
    return HTMLResponse(
        fragment("error", request, message=message),
        headers={"HX-Retarget": "#notice", "HX-Reswap": "innerHTML"},
    )


def render_workspace(request, stats=None):
    return HTMLResponse(
        fragment(
            "workspace",
            request,
            song=active_song,
            selected_languages={code: SUPPORTED_LANGUAGES[code] for code in selected_languages},
            stats=stats,
        )
    )


@app.middleware("http")
async def local_mutations(request: Request, call_next):
    # Reject browser requests from other sites to this local, single-user workspace.
    if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return PlainTextResponse("Cross-origin requests are not allowed.", status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return PlainTextResponse("Cross-site requests are not allowed.", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = (
        "no-store" if not request.url.path.startswith("/static/") else "public, max-age=3600"
    )
    return response


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "languages": dict(
                sorted(
                    SUPPORTED_LANGUAGES.items(),
                    key=lambda item: (
                        item[0] not in user_preferences["languages"],
                        item[1]["name"],
                    ),
                )
            ),
            "prefs": user_preferences,
            "translation_profiles": TRANSLATION_PROFILES,
            "providers": PROVIDERS,
            "spotify_configured": spotify_service.configured,
            "gemini_configured": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
            "openrouter_configured": bool(os.getenv("OPENROUTER_API_KEY")),
            "song": active_song,
            "selected_languages": {code: SUPPORTED_LANGUAGES[code] for code in selected_languages},
        },
    )


@app.get("/models/openrouter")
async def openrouter_models():
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            models = response.json()["data"]
        return {
            "models": sorted(
                [
                    {"id": item["id"], "name": item["name"]}
                    for item in models
                    if "text" in item.get("architecture", {}).get("output_modalities", [])
                    and "structured_outputs" in item.get("supported_parameters", [])
                ],
                key=lambda item: item["name"],
            )
        }
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return JSONResponse({"error": "Model catalog unavailable."}, status_code=502)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "spotify_configured": spotify_service.configured,
        "gemini_configured": translation_service.configured(DEFAULT_PROFILE),
        "openrouter_configured": translation_service.configured("openrouter:openrouter/free"),
    }


@app.get("/auth/spotify")
def spotify_login(request: Request):
    if not spotify_service.auth:
        return error(
            request,
            "Add SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET and SPOTIPY_REDIRECT_URI to .env, then restart.",
        )
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(spotify_service.auth.get_authorize_url(state=state))
    response.set_cookie("spotify_oauth_state", state, httponly=True, samesite="lax", max_age=600)
    return response


@app.get("/callback")
async def spotify_callback(request: Request):
    expected = request.cookies.get("spotify_oauth_state")
    state = request.query_params.get("state", "")
    if not expected or not secrets.compare_digest(expected, state) or not spotify_service.auth:
        return PlainTextResponse(
            "Spotify sign-in expired. Return home and reconnect.", status_code=400
        )
    if request.query_params.get("error") or not request.query_params.get("code"):
        return PlainTextResponse(
            "Spotify sign-in was cancelled. Return home to try again.", status_code=400
        )
    try:
        await run_in_threadpool(
            spotify_service.auth.get_access_token, request.query_params["code"], check_cache=False
        )
    except Exception:
        return PlainTextResponse(
            "Spotify sign-in failed. Check the redirect URI and reconnect.", status_code=400
        )
    response = RedirectResponse("/")
    response.delete_cookie("spotify_oauth_state")
    return response


@app.post("/preferences")
@app.post("/preferences/profile")
async def preferences(request: Request):
    form = await request.form()
    languages = list(dict.fromkeys(form.getlist("languages")))
    chosen = form.get("profile", DEFAULT_PROFILE)
    provider = form.get("lyrics_provider", "auto")
    custom = str(form.get("custom_model", "")).strip()
    if len(languages) > 5 or any(code not in SUPPORTED_LANGUAGES for code in languages):
        return error(request, "Choose up to five supported languages.")
    if chosen not in TRANSLATION_PROFILES or provider not in PROVIDERS:
        return error(request, "Choose a valid model and lyrics source.")
    if not re.fullmatch(r"[\w./:-]{0,160}", custom) or (
        chosen == "openrouter/custom" and "/" not in custom
    ):
        return error(request, "Enter a valid OpenRouter model ID in provider/model format.")
    async with workspace_lock:
        try:
            save_user_preferences(
                {
                    "languages": languages,
                    "translation_profile": chosen,
                    "custom_model": custom,
                    "lyrics_provider": provider,
                }
            )
        except OSError:
            return error(
                request, "Settings could not be saved. Check write access to the data folder."
            )
    return HTMLResponse('<span class="success" role="status">Settings saved.</span>')


@app.post("/demo")
async def demo(request: Request):
    global active_song, selected_languages
    async with workspace_lock:
        active_song = demo_song()
        selected_languages = ["en"]
    return render_workspace(request)


@app.post("/search")
async def search(request: Request):
    global active_song, selected_languages
    form = await request.form()
    title, artist = str(form.get("title", "")).strip(), str(form.get("artist", "")).strip()
    if not title or not artist or max(len(title), len(artist)) > 200:
        return error(request, "Enter a song title and artist (up to 200 characters each).")
    async with workspace_lock:
        try:
            song = Song(title=title, artist=artist, spotify_id="")
            song = await asyncio.wait_for(
                run_in_threadpool(
                    spotify_service.get_lyrics_for_song, song, user_preferences["lyrics_provider"]
                ),
                timeout=60,
            )
            active_song, selected_languages = song, []
        except InstrumentalTrack as exc:
            return error(request, str(exc))
        except Exception:
            return error(
                request,
                "No lyrics could be loaded. Check the title and artist, try a different source, or retry shortly.",
            )
    return render_workspace(request)


@app.get("/get-song-and-lyrics")
@app.get("/current-song")
async def get_song_and_lyrics(request: Request):
    global active_song, selected_languages
    async with workspace_lock:
        try:
            song = await run_in_threadpool(spotify_service.get_current_song_info)
            if not song:
                active_song, selected_languages = None, []
                return render_workspace(request)
            if active_song and active_song.spotify_id == song.spotify_id and active_song.lyrics:
                active_song.current_position = song.current_position
                active_song.is_playing = song.is_playing
                return render_workspace(request)
            song = await asyncio.wait_for(
                run_in_threadpool(
                    spotify_service.get_lyrics_for_song,
                    song.model_copy(deep=True),
                    user_preferences["lyrics_provider"],
                ),
                timeout=60,
            )
            active_song, selected_languages = song, []
        except ValueError as exc:
            return error(request, str(exc))
        except Exception:
            return error(
                request,
                "Spotify or the lyrics source could not be reached. Reconnect Spotify or try another lyrics source.",
            )
    return render_workspace(request)


@app.post("/refresh-lyrics")
async def refresh_lyrics(request: Request):
    global active_song, selected_languages
    async with workspace_lock:
        if not active_song or active_song.demo:
            return error(request, "Load a song from Spotify or search before refreshing lyrics.")
        try:
            active_song = await asyncio.wait_for(
                run_in_threadpool(
                    spotify_service.get_lyrics_for_song,
                    active_song.model_copy(deep=True),
                    user_preferences["lyrics_provider"],
                    True,
                ),
                timeout=60,
            )
            active_song.original_languages = []
            active_song.translated_titles = {}
            selected_languages = []
        except Exception:
            return error(
                request,
                "Lyrics could not be refreshed. Your existing lyrics are still here. Try another source.",
            )
    return render_workspace(request)


@app.post("/translate")
async def translate_song(request: Request):
    global selected_languages
    async with workspace_lock:
        if not active_song or not active_song.lyrics:
            return error(request, "Load a song first, then translate its lyrics.")
        if not user_preferences["languages"]:
            return error(request, "Choose at least one language and save your settings.")
        if active_song.demo:
            return error(
                request,
                "The demo includes an English translation and IPA. Search for a song to try your chosen AI model.",
            )
        try:
            selected = profile()
            languages = {
                code: SUPPORTED_LANGUAGES[code]["name"] for code in user_preferences["languages"]
            }
            # Keep title and lyric updates atomic if any provider request fails.
            lyric_result, titles, detected = await asyncio.gather(
                translation_service.translate_lyrics(
                    active_song.title,
                    active_song.artist,
                    active_song.lyrics,
                    languages,
                    model_name=selected["model"],
                ),
                translation_service.translate_text(
                    active_song.title, languages, model_name=selected["model"]
                ),
                translation_service.detect_language(
                    active_song.lyrics,
                    active_song.title,
                    active_song.artist,
                    model_name=selected["model"],
                ),
            )
            lyrics, stats = lyric_result
            active_song.lyrics = lyrics
            active_song.translated_titles = titles
            active_song.original_languages = detected
            selected_languages = list(languages)
        except ValueError as exc:
            return error(request, str(exc))
    return render_workspace(request, stats)


@app.post("/phonetics")
async def phonetics(request: Request):
    async with workspace_lock:
        if not active_song or not active_song.lyrics:
            return error(request, "Load lyrics before adding pronunciation.")
        if not active_song.demo:
            try:
                selected = profile()
                active_song.lyrics = await translation_service.get_phonetics(
                    active_song.title,
                    active_song.artist,
                    active_song.lyrics,
                    active_song.original_languages,
                    model_name=selected["model"],
                )
            except ValueError as exc:
                return error(request, str(exc))
    return render_workspace(request)


@app.get("/export")
def export_lyrics():
    if not active_song or not active_song.lyrics:
        return PlainTextResponse("Load lyrics before exporting.", status_code=400)
    lines = [
        f"{active_song.title} — {active_song.artist}",
        f"Source: {active_song.lyrics_source}",
        "",
    ]
    for line in active_song.lyrics:
        lines.append(f"{line.timestamp} {line.original}".strip())
        if line.phonetics:
            lines.append(line.phonetics)
        lines.extend(
            f"{code}: {line.translations[code]}"
            for code in selected_languages
            if code in line.translations
        )
        lines.append("")
    return PlainTextResponse(
        "\n".join(lines), headers={"Content-Disposition": 'attachment; filename="lingolyrics.txt"'}
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin and origin.removeprefix("http://").removeprefix("https://") != websocket.headers.get(
        "host"
    ):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            if active_song and active_song.spotify_id and not active_song.demo:
                try:
                    state = await run_in_threadpool(spotify_service.get_current_playback_state)
                    await websocket.send_json(state)
                except Exception:
                    await websocket.send_json({"error": "Playback unavailable. Reconnect Spotify."})
            with suppress(TimeoutError):
                await asyncio.wait_for(websocket.receive_text(), timeout=3)
    except (WebSocketDisconnect, RuntimeError):
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
