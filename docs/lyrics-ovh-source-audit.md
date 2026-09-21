# lyrics.ovh source audit for a standalone lyrics library

Audited 2026-09-21 from local clone `lyrics-ovh-reference`, exact commit **`44cf73f2576ab0c6857076de75d6bb4a13175e34`**. Scope: source inspection and a few public HTTP requests; no account sessions, challenge solving, fingerprint impersonation or repeated attempts against denied endpoints. This is an implementation audit, not an assertion of provider uptime or a legal review of each website's terms.

## What the service actually does

It is a JavaScript/Express service with **six plain-text website adapters**, not a synchronized lyrics engine. `findLyrics(title, artist)` starts all six, returns the first fulfilled result, and caches that text. LyricsMania internally starts two URL patterns, so one ordinary lookup starts seven requests before any two-stage searches or query variations. The public wrapper exposes `/v1/:artist/:title`; the separate `/suggest/:term` route forwards Deezer search results. **Deezer supplies suggestions, not the lyrics.** [Pinned provider source](https://github.com/NTag/lyrics.ovh/blob/44cf73f2576ab0c6857076de75d6bb4a13175e34/lyrics.js), [pinned HTTP wrapper](https://github.com/NTag/lyrics.ovh/blob/44cf73f2576ab0c6857076de75d6bb4a13175e34/index.js).

### All six underlying sources

| Source | Actual lookup flow | Extraction |
| --- | --- | --- |
| Genius | `/api/search/multi?q={artist title}` → song section → filter title → choose smallest artist edit distance → returned result URL | `[data-lyrics-container="true"]`, preserving `<br>` as newline |
| AZLyrics | Construct `/lyrics/{artist}/{title}.html`; ASCII letters/digits only, remove initial `the` from artist | First unnamed div longer than 100 characters inside `.col-xs-12.col-lg-8.text-center` |
| Paroles.net | Construct `/{artist}/paroles-{title}` with accent-stripped ASCII hyphen slugs | `.song-text`; remove headings and nested divs with IDs/classes |
| LyricsMania | Race `/{title}_lyrics_{artist}.html` and `/{title}_{artist}.html`, using underscore slugs | `.lyrics-body` |
| Letras.mus.br | Construct `/{artist}/{title}/` with hyphen slugs | `.lyric-original p, .lyric-tra p` |
| Lyrics.com | `/serp.php?st={title artist}&stype=1` → title-filtered `.sec-lyric.clearfix` records → nearest artist → detail URL | `#lyric-body-text` |

These are the implemented flows, not official API contracts. [Pinned implementation](https://github.com/NTag/lyrics.ovh/blob/44cf73f2576ab0c6857076de75d6bb4a13175e34/lyrics.js).

## Small public probes: two useful direct sources

Requests used ordinary Python Requests defaults and ten-second timeouts. No full lyrics were logged or saved. A status 200 alone is not considered success.

| Source / sample | Local observation | Interpretation |
| --- | --- | --- |
| LyricsMania / Imagine — John Lennon | HTTP 200, no redirect; exactly one `.lyrics-body` containing 637 non-whitespace-trimmed text characters | Good candidate for a direct plain-text adapter. Still needs metadata validation and fixtures. |
| Letras / Imagine — John Lennon | HTTP 200 after redirect from `/john-lennon/imagine/` to `/john-lennon/90/`; title `Imagine - John Lennon - LETRAS.MUS.BR`; matching canonical URL; five `.lyric-original p` elements, no translated paragraphs | Working direct page with a legitimate same-host canonical redirect. Upstream's blanket redirect rejection would discard it. |
| Paroles.net / Alors on danse — Stromae | HTTP 200, no redirect; zero `.song-text` matches | Not verified working. Could be changed markup or a non-song response; cause not established. |
| AZLyrics / Imagine — John Lennon | HTTP 200 after redirect; zero expected container matches | Not verified working. Do not treat this as lyrics or repeatedly probe for a way around restrictions. |

The Genius 403 observed earlier was not reprobed. Lyrics.com was not live-tested in this bounded audit. Earlier lyrics.ovh aggregate success does not identify which of its providers answered. These outcomes are independent local observations, not claims made by NTag.

## Behaviors worth improving rather than translating literally

The following findings come from static inspection of the pinned source; recommendations are this audit's engineering judgments.

* **Provenance is lost:** only a string survives the race and cache. Return provider name, final source URL, matched metadata and synchronization type from the new library.
* **First response need not be the best match:** title substring acceptance can be too permissive, and nearest artist is selected without a minimum artist-confidence threshold. Use explicit identity thresholds; do not let a fast wrong song win.
* **Plain providers should not race synchronized providers indiscriminately:** first search validated synchronized catalogs, then use plain text according to the caller's preference.
* **Redirect policy is too broad in some sources and too loose in others:** it rejects all redirects for Letras, LyricsMania and Paroles.net, while following returned links elsewhere. Validate HTTPS scheme and permitted host at every hop, limit hops, and verify the final song identity. The Letras probe supplies a concrete positive redirect fixture.
* **Language can be mixed accidentally:** Letras selects both original and translated paragraph classes. Prefer original content; expose translation separately if explicitly requested.
* **ASCII slugging is not general title normalization:** non-Latin names may collapse to empty strings, and removing every initial `the` can damage artist names that merely start with those letters. Keep provider-specific slugs separate from Unicode-aware matching.
* **Edition markers disappear:** removing bracketed/parenthesized suffixes can confuse live, remix or alternate-language recordings. Preserve the original query and make simplified queries bounded alternatives, never replacements for identity checks.
* **Network work survives a successful race:** `Promise.any` does not cancel the remaining requests. Query variants recursively fan out, and concurrent identical requests are not coalesced before completion. Use a small provider budget, deduplicate variants, and stop further work after success.
* **Five seconds is a per-fetch timeout, not a global deadline:** two-stage providers and fallback variants need a shared total budget. Limit response size before HTML parsing.
* **All upstream failures become public 404:** distinguish no match, denied access, timeout and malformed response so callers can make informed retry decisions.
* **The cache has an entry-count limit but no TTL:** avoid permanent stale matches and unbounded total text size. A library can make caching caller-owned or implement a small TTL cache with separate transient-failure handling.
* **Cleanup is heuristic:** the implementation rejects very short text and some short placeholder messages, but a long error/consent message can pass. Require a recognized song container and confirmed metadata; parse HTML using a parser rather than generic regex tag stripping.

[Pinned provider implementation](https://github.com/NTag/lyrics.ovh/blob/44cf73f2576ab0c6857076de75d6bb4a13175e34/lyrics.js), [failure mapping in wrapper](https://github.com/NTag/lyrics.ovh/blob/44cf73f2576ab0c6857076de75d6bb4a13175e34/index.js).

## Tests and dependencies

The upstream test file contains live positive and negative examples. Positive assertions check that a returned string exceeds 50 characters; they do not assert song identity, source, language or exact structure. The tests were inspected, not run, to avoid a broad fan-out of live scraping. A standalone package should use synthetic HTML/JSON fixtures for parsers and matching, with live probes opt-in. Include wrong-artist results, canonical redirects, consent pages, original/translation separation and Unicode names. [Pinned tests](https://github.com/NTag/lyrics.ovh/blob/44cf73f2576ab0c6857076de75d6bb4a13175e34/lyrics.test.js).

`package.json` declares version 2.0.0 with Cheerio, Express and CORS dependencies. This is a web app whose retrieval function is exported internally, not a reason to add Node to the Python app. A small Python HTTP client plus HTML parser can implement the useful providers without the server/frontend. [Pinned package metadata](https://github.com/NTag/lyrics.ovh/blob/44cf73f2576ab0c6857076de75d6bb4a13175e34/package.json).

## License and provenance

The audited repository explicitly grants an **MIT software license**, copyright Basile Bruneau. It requires retaining the copyright and permission notice in copies or substantial portions. If the new library ports substantial adapter/cleanup logic, include that notice in a third-party notice file and describe the source and pinned commit. Changing language does not erase attribution requirements. [Pinned license](https://github.com/NTag/lyrics.ovh/blob/44cf73f2576ab0c6857076de75d6bb4a13175e34/LICENSE).

The inspected files do not establish any right to redistribute the underlying song lyrics or any negotiated permission from the six providers. No additional third-party adapter attribution was found in `lyrics.js`; that is a limited observation about the inspected file, not a complete history/provenance audit. Record the source relationship accurately and keep licensed software distinct from externally fetched content.

## Concrete recommendation for the new library

Build the first version around the already demonstrated direct structured sources **LRCLIB, NetEase, Kugou and QQ Music**, plus the documented **lyrics.ovh** aggregate as an optional plain fallback. For independent plain adapters, **LyricsMania and Letras** have the strongest fresh evidence in this audit. Add them with explicit source attribution, source URL, fixture tests and bounded requests. Keep Genius, AZLyrics, Paroles.net and Lyrics.com marked unverified/unavailable until a normal public request and parser can be demonstrated; adapter code existing upstream is not proof of working retrieval.

The minimal public API should accept structured title/artist and optional duration, return one typed result or a typed failure, and allow provider selection. Separate parsing/matching from transport so provider contracts can be tested without network access. Avoid inheriting an Express server, browser UI, Android authentication stack or recursive fan-out simply to fetch a lyric.
