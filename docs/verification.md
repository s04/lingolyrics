# Verification — September 21–22, 2026

## Automated checks

- **87 Python tests passed**, **92% statement coverage** across application modules including the new source adapters (Python 3.12).
- **6 Playwright tests passed** across desktop Chromium and mobile Chromium emulation: repeated HTMX swaps, demo timer, translation/IPA visibility, focus mode, clipboard, downloads, language search, settings persistence, error preservation, and accessibility.
- Axe reported **no serious or critical violations** for the tested welcome and demo views. This is an automated check, not a complete manual accessibility audit.
- Ruff lint/format, djLint template lint/format, ESLint, Prettier, and `git diff --check` passed.
- `npm audit`: no known vulnerabilities. `pip-audit --disable-pip --no-deps -r requirements.txt`: no known vulnerabilities in the resolved runtime dependency set.
- Python tests emit two upstream deprecation warnings from Starlette's current test client integration with HTTPX/AnyIO; they do not indicate test failures.
- GitHub Actions is configured for Python 3.12 and 3.13. [Remote CI](https://github.com/s04/lingolyrics/actions/runs/35661882404) passed on both versions, including browser tests. Windows execution has not been observed in this session.

## Live integrations

| Integration | Observed result | Limit |
| --- | --- | --- |
| Direct LRCLIB | 30 synchronized lines for Imagine — John Lennon, around 0.4 seconds | One track; no catalog-wide guarantee |
| NetEase via isolated syncedlyrics | 28 synchronized lines for the same track, 1.8–3.5 seconds | Undocumented upstream service |
| Musixmatch, Megalobiz, Genius | No usable result for the same probe | Not proof of permanent provider failure |
| OpenRouter free router | One validated English translation, 59 completion tokens | Used original short sample text, not third-party lyrics |
| Spotify | Configured callback is correct; saved authorization failed | User must reconnect; live playback synchronization not verified end to end |
| Gemini | Deterministic adapter tests pass | No Gemini key configured, so no live request |

## Research-driven fixes included

The [research report](lyrics-research.md) established the OneTagger Musixmatch lineage and upstream indefinite token retry. The implementation now runs legacy adapters in short-lived subprocesses with a ten-second deadline. It also uses direct LRCLIB lookup, album/duration metadata, conservative search matching, and an explicit instrumental outcome. A separate syncedlyrics checkout was repaired and tested, then the user chose an independently implemented Go core with a Python wrapper: [lyricfetch](https://github.com/s04/lyricfetch). LingoLyrics can use it via `LYRICFETCH_BINARY`; its optional process integration forwards metadata and preserves typed outcomes.

The later three-song matrix confirmed Kugou and QQ Music synchronized retrieval, lyrics.ovh plain retrieval, and the new Go NetEase cloudsearch adapter without historical cookies. Musixmatch worked in one repaired-fork matrix but remains intermittent in the Go core; Genius/Megalobiz service failures remain unresolved. See [protocol evidence](https://github.com/s04/lyricfetch/blob/main/docs/sources.md) and [prior art](https://github.com/s04/lyricfetch/blob/main/docs/prior-art.md).

Remaining improvements include per-track offsets, local LRC import, manual candidate selection, short-lived negative caching, and broader multilingual live-provider probes. These are recommendations, not features claimed to be implemented.
