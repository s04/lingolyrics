"""Curated text models. OpenRouter also accepts a custom model ID."""

DEFAULT_PROFILE = "gemini-3.1-flash-lite"
TRANSLATION_PROFILES = {
    model: {"name": name, "model": model, "provider": "gemini", "thinking_mode": "default"}
    for model, name in [
        ("gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite · economical"),
        ("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite"),
        ("gemini-3.5-flash", "Gemini 3.5 Flash"),
        ("gemini-3.6-flash", "Gemini 3.6 Flash"),
        ("gemini-3.7-flash", "Gemini 3.7 Flash"),
        ("gemini-3.8-flash", "Gemini 3.8 Flash"),
        ("gemini-3.1-pro-preview", "Gemini 3.1 Pro · preview"),
    ]
}
TRANSLATION_PROFILES.update(
    {
        "openrouter/free": {
            "name": "OpenRouter · free models",
            "model": "openrouter:openrouter/free",
            "provider": "openrouter",
            "thinking_mode": "default",
        },
        "openrouter/auto": {
            "name": "OpenRouter · auto (paid)",
            "model": "openrouter:openrouter/auto",
            "provider": "openrouter",
            "thinking_mode": "default",
        },
        "openrouter/custom": {
            "name": "OpenRouter · custom model",
            "model": "",
            "provider": "openrouter",
            "thinking_mode": "default",
        },
    }
)
