"""Collision-resistant, atomic local JSON cache. Corrupt entries are misses."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / "data" / "cache"


def _get_cache_filepath(key: str) -> Path:
    return Path(CACHE_DIR) / (hashlib.sha256(key.encode()).hexdigest() + ".json")


def get_from_cache(key):
    try:
        return json.loads(_get_cache_filepath(key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_to_cache(key, data):
    temporary = None
    try:
        Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=CACHE_DIR, delete=False
        ) as handle:
            temporary = handle.name
            json.dump(data, handle, ensure_ascii=False)
        os.replace(temporary, _get_cache_filepath(key))
    except OSError:
        # Cache failures must not prevent a successful translation from displaying.
        pass
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
