# Lyrics retrieval research

> Follow-up, September 22: after the clone/repair experiments, the owner chose a small standalone Go library with a Python wrapper. [lyricfetch](https://github.com/s04/lyricfetch) now implements the verified public APIs independently. The original recommendation below is the first-round assessment; [current protocol evidence](https://github.com/s04/lyricfetch/blob/main/docs/sources.md) and [prior-art comparison](https://github.com/s04/lyricfetch/blob/main/docs/prior-art.md) incorporate the later work.

Research date: 2026-09-21. Primary sources checked: repository source, GitHub API commit comparisons, package registry metadata, and provider documentation. Repository activity is a snapshot, not a reliability guarantee. Recommendations below are engineering judgments; they are not claims that every provider was tested.

## Decision

Keep a small, directly tested LRCLIB adapter as the primary provider. Preserve optional providers behind a bounded fallback interface. Do not adopt a fork or add a Rust runtime solely to retrieve lyrics: the underlying remote service, metadata matching, and failure handling matter more than the implementation language.

## The Rust connection is real

The **Musixmatch provider specifically**, rather than the entire Python package, explicitly credits OneTagger's Rust implementation and says much of it was converted from Rust to Python. Its source links the originating OneTagger commit. This answers the suspected lineage directly; no evidence was found that all of syncedlyrics originated in Rust. [Python provider with attribution](https://github.com/moehmeni/syncedlyrics/blob/3c8a318d9a8df26855bdc3a5d23f7fd2b99ade2e/syncedlyrics/providers/musixmatch.py), [original Rust provider](https://github.com/Marekkon5/onetagger/blob/0654131188c4df2b4b171ded7cdb927a4369746e/crates/onetagger-platforms/src/musixmatch.rs).

LRCLIB is also a Rust server, and LRCGET is its official desktop client, built using Tauri. These are separate relationships, not evidence that syncedlyrics is a binding to either project. [LRCLIB repository](https://github.com/tranxuanthang/lrclib), [LRCGET repository](https://github.com/tranxuanthang/lrcget).

## Is syncedlyrics maintained?

The latest default-branch commit is `3c8a318` from **2024-07-28**; PyPI's latest release is **1.0.1**, uploaded that same day. The GitHub repository is not archived. Thus the concern about two years without a release is justified, while “archived” would be inaccurate. GitHub's `updated_at` can change without a code update; use commit/release dates. [Commit history API](https://api.github.com/repos/moehmeni/syncedlyrics/commits?per_page=5), [PyPI metadata](https://pypi.org/pypi/syncedlyrics/json), [repository metadata](https://api.github.com/repos/moehmeni/syncedlyrics).

The upstream README identifies Deezer as no longer working and Lyricsify as blocked by Cloudflare; Genius supplies plain lyrics. The Spotify provider in the tree is a stub whose methods raise `NotImplementedError`, not an additional working engine. [Provider list](https://github.com/moehmeni/syncedlyrics#providers), [Spotify source](https://github.com/moehmeni/syncedlyrics/blob/3c8a318d9a8df26855bdc3a5d23f7fd2b99ade2e/syncedlyrics/providers/spotify.py).

## Forks: substantive changes exist, but no demonstrated replacement

The public forks endpoint was inspected, followed by comparisons for recently pushed candidates. This is a scoped survey, not a claim to have audited every branch of every fork. [Fork listing](https://api.github.com/repos/moehmeni/syncedlyrics/forks?sort=newest&per_page=100).

| Candidate | Verified changes versus upstream `main` | Assessment |
| --- | --- | --- |
| [yanus/syncedlyrics](https://github.com/moehmeni/syncedlyrics/compare/main...yanus:main) | Three commits on September 18, 2026: prefer synced results, switch Musixmatch to its mobile endpoint, support richer search parameters | Most relevant patch set found. Review matching changes independently. Mobile endpoint behavior has not been live-validated here; this remains an unofficial endpoint and is not proof of restored reliable service. |
| [dddevid/syncedlyrics](https://github.com/moehmeni/syncedlyrics/compare/main...dddevid:main) | Seven commits in October 2025: TypeScript migration, test files and package versions through 1.0.4 | Potential reference for a JS application; changing this Python app's runtime does not inherently repair provider access. Tests were not executed in this research. |
| [Kristerley/syncedlyrics](https://github.com/moehmeni/syncedlyrics/compare/main...Kristerley:main) | Three June 2026 commits concerning extraction of search terms from paths | Addresses a different input use case, not demonstrated provider repair. |
| [nxllvxxd/syncedlyrics](https://github.com/moehmeni/syncedlyrics/compare/main...nxllvxxd:main) | One `.gitignore` change | Recent push date is not meaningful evidence of lyrics improvements. |

The `yanus` source uses `apic-appmobile.musixmatch.com` and a mobile application identifier. It should not silently become this app's default on the strength of a recent commit. [Fork provider source](https://github.com/yanus/syncedlyrics/blob/main/syncedlyrics/providers/musixmatch.py).

## Alternatives and adoption cost

| Option | What it contributes | Recommendation |
| --- | --- | --- |
| [LRCLIB HTTP API](https://lrclib.net/docs) | Structured track metadata and plain/synced lyrics, independent of client language | Primary adapter. Small integration surface; keep matching and parsing under local tests. |
| [LRCGET](https://github.com/tranxuanthang/lrcget) | Official LRCLIB desktop client for bulk local-library lyrics retrieval | Useful behavior/reference implementation, not a new independent catalog or necessary runtime dependency. |
| [OneTagger](https://github.com/Marekkon5/onetagger) | Rust music tagger with Musixmatch and rich synchronization handling | Read for lineage and provider behavior. Integrating the application is substantially more work than a direct adapter. |
| [SyncLyrics](https://github.com/AnshulJ999/SyncLyrics) | Separate Python application with lyrics providers, word synchronization and playback integrations | Useful feature comparison; not a drop-in library. Its license includes Commons Clause restrictions, so do not casually copy code into this public project. |
| [librespot](https://github.com/librespot-org/librespot) | Spotify client library; README states Premium accounts are required | Not a standalone general lyrics catalog. Adding Spotify playback infrastructure does not address LRCLIB matching or failed scrape providers. |
| [Official Musixmatch API](https://www.postman.com/musixmatch-dev/musixmatch-apis/collection/pqm8o6w/lyrics-api) | Documented, authenticated commercial-provider integration | Evaluate separately if licensed coverage is desired; do not assume desktop/mobile private API behavior represents this API's contract. |

## Concrete reliability findings

* Upstream Musixmatch token acquisition recursively retries after a ten-second sleep on response status 401, with no attempt limit. A per-request socket timeout does **not** bound this provider's total execution. OneTagger's current implementation also retains recursive token retry, so moving back to Rust does not automatically fix it. Isolate or disable this fallback until a total deadline is enforced. [Python implementation](https://github.com/moehmeni/syncedlyrics/blob/3c8a318d9a8df26855bdc3a5d23f7fd2b99ade2e/syncedlyrics/providers/musixmatch.py), [Rust implementation](https://github.com/Marekkon5/onetagger/blob/master/crates/onetagger-platforms/src/musixmatch.rs).
* Upstream LRCLIB chooses the first fuzzy-sorted track, then makes a second request for that ID. It does not implement the commented-out search for another candidate with synchronized lyrics. A plain-only top candidate can therefore hide a usable synchronized candidate. [LRCLIB adapter](https://github.com/moehmeni/syncedlyrics/blob/3c8a318d9a8df26855bdc3a5d23f7fd2b99ade2e/syncedlyrics/providers/lrclib.py).
* NetEase uses a hard-coded historical cookie header and undocumented service endpoints. Its successful result in a smoke test does not establish long-term operational stability. [NetEase implementation](https://github.com/moehmeni/syncedlyrics/blob/3c8a318d9a8df26855bdc3a5d23f7fd2b99ade2e/syncedlyrics/providers/netease.py).
* LRCLIB's current server source supports structured title, artist, optional album and duration lookup, with an explicit `instrumental` field. Search returns metadata and lyrics together. Server overload handling includes 503 with `Retry-After`; distinguish this from an actual missing track. Repository code can be ahead of the hosted deployment. [Metadata route](https://github.com/tranxuanthang/lrclib/blob/main/server/src/routes/get_lyrics_by_metadata.rs), [search route](https://github.com/tranxuanthang/lrclib/blob/main/server/src/routes/search_lyrics.rs).

## Evidence from this improvement session

The implementation session reported one live probe for **Imagine — John Lennon**: direct LRCLIB returned 30 synchronized lines in approximately 0.4 seconds; syncedlyrics 1.0.1 NetEase returned 28 in approximately 3.5 seconds; Musixmatch, Megalobiz and Genius yielded no usable result. These are local observations supplied by the implementation agent, not independent repetitions by this research agent. They establish that at least one direct retrieval path worked, not catalog-wide coverage, timing correctness, or permanent provider failure. No complete copyrighted lyrics are reproduced in this report.

## Ranked improvements after the first pass

1. **Bound failures before expanding providers.** Apply a total provider deadline, limited concurrency, bounded retries for transient errors, and cooldown after repeated failure. A thread timeout alone can leave the original operation running. Never retry indefinitely on authentication errors.
2. **Improve identity matching.** Carry Spotify title, all artists, album, duration and track ID through the service. Try structured lookup first. Rank fallback candidates by title/artist agreement and duration, preserve live/remix distinctions, and prefer synchronized lyrics only among plausible matches. Reject unrelated candidates rather than presenting an incorrect lyric as success.
3. **Represent outcomes explicitly.** Preserve source, provider record ID, synchronization type, instrumental status and retrieval time. Separate not-found, provider-unavailable and parse-error states. Keep short negative-cache lifetimes; transient outages must not become permanent missing-lyrics entries.
4. **Add deterministic provider contracts.** Use synthetic response fixtures for plain-only first candidates, mismatched artists, duplicate timestamps, malformed JSON, empty bodies, 429/503, and instrumental tracks. Test retry ceilings and total deadlines. Keep live probes opt-in or scheduled and report metadata/status only; one provider outage should not make every pull request fail.
5. **Give users a repair path.** Candidate selection, source display, per-track timing offset and local LRC import are useful when automatic matching fails. Store corrections by stable track identity. Do not manufacture synchronization for plain lyrics without clearly identifying it as estimated.
6. **Only then consider maintaining a fork.** Forking is justified if multiple provider fixes are needed by other consumers and maintainers will own releases, security updates, adapters and contract tests. For this app, independently implemented direct adapters plus narrow upstream contributions are a smaller ongoing obligation.

## Licensing facts and remaining unknowns

syncedlyrics declares MIT; OneTagger declares GPL-3.0, and the Python file explicitly acknowledges translation from its Rust code. That is a concrete provenance question to review before copying or republishing that provider; this research does not determine whether the authors obtained separate permission or whether a violation occurred. [syncedlyrics license](https://github.com/moehmeni/syncedlyrics/blob/main/LICENSE), [OneTagger license](https://github.com/Marekkon5/onetagger/blob/master/LICENSE).

SyncLyrics includes a Commons Clause condition excluding the right to sell the software as defined by that license; treating it as ordinary unrestricted MIT would be inaccurate. LRCLIB and LRCGET have MIT code licenses. These code licenses alone do not answer what rights attach to a particular retrieved lyric. This research has not established catalog-wide redistribution or translation rights, nor audited provider terms for a hosted commercial deployment. [SyncLyrics license](https://github.com/AnshulJ999/SyncLyrics/blob/main/LICENSE), [LRCLIB license](https://github.com/tranxuanthang/lrclib/blob/main/LICENSE), [LRCGET license](https://github.com/tranxuanthang/lrcget/blob/main/LICENSE).
