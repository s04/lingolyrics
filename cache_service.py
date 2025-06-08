import os
import json
import re
from typing import Optional, Any

CACHE_DIR = "data/cache"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def _sanitize_filename(name: str) -> str:
    """Sanitizes a string to be a valid filename."""
    name = name.lower()
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[-\s]+', '-', name).strip('-_')
    return name

def _get_cache_filepath(key: str) -> str:
    """Generates a filepath for a given cache key."""
    sanitized_key = _sanitize_filename(key)
    return os.path.join(CACHE_DIR, f"{sanitized_key}.json")

def get_from_cache(key: str) -> Optional[Any]:
    """Retrieves data from a cache file."""
    filepath = _get_cache_filepath(key)
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"Cache read error for key '{key}': {e}")
        return None

def save_to_cache(key: str, data: Any):
    """Saves data to a cache file."""
    filepath = _get_cache_filepath(key)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            print(f"Saved to cache: {filepath}")
    except IOError as e:
        print(f"Error saving to cache for key '{key}': {e}") 