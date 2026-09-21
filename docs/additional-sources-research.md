# Additional lyrics sources and provider recovery

Research date: 2026-09-21. Scope: public reference implementations and a small number of credential-free requests. No cookies, account credentials, proxy rotation, challenge solving, or authentication bypass were used. Only metadata, status and line counts are recorded; full retrieved lyrics are not committed.

## Recommended additions

**Kugou and current QQ Music CGI are working additional synchronized sources; lyrics.ovh is a working additional plain-text source.** All three were independently exercised during this research. Add them behind deadlines and result validation. This does not establish catalog-wide availability or guarantee that particular timings match the playing recording.

| Public request | Observed result |
| --- | --- |
| lyrics.ovh: John Lennon / Imagine | HTTP 200; 30 plain-text lines; approximately 0.2 seconds |
| lyrics.ovh: Stromae / Alors on danse | HTTP 200; 50 plain-text lines |
| Kugou search: `John Lennon - Imagine` | HTTP 200; matching John Lennon / Imagine candidates, duration 185704 ms |
| Kugou LRC download for a returned candidate | HTTP 200 and application status 200; 37 total lines, 32 timestamped lines |
| QQ Music smartbox: Imagine John Lennon | HTTP 200; three candidate records, including exact artist/title |
| QQ Music legacy lyric request for returned MID | HTTP 200 but application code `-1310`; no lyrics |
| QQ Music current `GetPlayLyricInfo`, same MID | HTTP 200, top-level and request codes 0; 37 total lines, 32 timed lines |

These are direct observations from the local research run, not guarantees from the reference projects. Tests ran with Python Requests using ordinary defaults and a 12-second request timeout.

## lyrics.ovh: documented API, plain lyrics

The project itself documents `GET https://api.lyrics.ovh/v1/{artist}/{title}` returning a JSON `lyrics` string or HTTP 404. URL-encode each path component independently. `/suggest/{query}` returns Deezer search suggestions, not synchronized lyrics. The README and current implementation describe multiple upstream text sources; this is an aggregator, not proof that direct Genius scraping has been repaired locally. [Official project README](https://github.com/NTag/lyrics.ovh), [implementation](https://github.com/NTag/lyrics.ovh/blob/main/lyrics.js).

Implementation recommendation: use as a late plain-text fallback, validate a nonempty string, cap response size, and retain `source=LyricsOvh` and `synced=false`. Do not invent timestamps. A 404 is a miss; a timeout, malformed body or 5xx is an unavailable provider. The code is MIT, and the repository metadata reports a June 20, 2026 push. [License](https://github.com/NTag/lyrics.ovh/blob/main/LICENSE), [repository metadata](https://api.github.com/repos/NTag/lyrics.ovh).

## Kugou: public candidate search followed by LRC download

A maintained public reference implements the candidate/search and base64-download flow. Its repository was pushed September 12, 2026; that is an activity observation, not a test result. The reference uses HTTP in this portion of its implementation; **the HTTPS equivalents were successfully tested here**. [musicdl Kugou implementation](https://github.com/CharlesPikachu/musicdl/blob/master/musicdl/modules/sources/kugou.py), [repository metadata](https://api.github.com/repos/CharlesPikachu/musicdl).

Observed working request shape:

```text
GET https://lyrics.kugou.com/search
    ?ver=1&man=yes&client=pc&keyword={artist - title}

GET https://lyrics.kugou.com/download
    ?ver=1&client=pc&id={candidate.id}
    &accesskey={candidate.accesskey}&fmt=lrc&charset=utf8
```

The search response exposes `candidates`, including `id`, `song`, `singer`, `duration` and a record-specific `accesskey`. Pass the key returned by the service for that candidate; it is not an account credential to guess or hard-code. The download response's `content` is base64-encoded UTF-8 LRC.

A preliminary search using `Imagine John Lennon` plus duration `183000` returned no candidates, whereas `John Lennon - Imagine` without the duration filter succeeded. Because both parameters changed, this does **not** isolate which caused the difference. Recommendation: search using structured artist/title, then score title/artist and duration locally rather than relying on an overly restrictive duration parameter.

Require successful HTTP and application statuses; validate candidate identity before downloading; handle invalid base64 and UTF-8 safely. Bound the number of candidates/downloads. Use line-level `fmt=lrc` initially rather than adding encrypted/compressed KRC handling. Reference code is evidence of protocol shape; do not copy it without reviewing its license. GitHub's detected license is `NOASSERTION`, which is not a permission grant.

## QQ Music: current public CGI works; legacy endpoint fails

The actively updated `L-1124/QQMusicApi` project defines public smartbox search at `https://c.y.qq.com/splcloud/fcgi-bin/smartbox_new.fcg` with `key={query}`. A live request with `format=json` returned records including song MID `000Eq2fc2uW9hE`, title Imagine, singer John Lennon. [Current search implementation](https://github.com/L-1124/QQMusicApi/blob/main/qqmusic_api/modules/search.py).

The legacy endpoint `https://i.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg`, called with that `songmid`, `format=json`, and `nobase64=1`, returned application code `-1310` and no lyric data. No attempt was made to defeat that response. An older project documents this legacy endpoint, while the current Python reference uses CGI module `music.musichallSong.PlayLyricInfo`, method `GetPlayLyricInfo`, with song ID/MID and lyric-format flags. A follow-up experiment successfully exercised the current route without account credentials, cookies, signatures or special headers. [Legacy reference](https://github.com/copws/qq-music-api), [current lyric implementation](https://github.com/L-1124/QQMusicApi/blob/main/qqmusic_api/modules/lyric.py).

The working request is `POST https://u.y.qq.com/cgi-bin/musicu.fcg` with this JSON body:

```json
{
  "comm": {"format": "json"},
  "req_0": {
    "module": "music.musichallSong.PlayLyricInfo",
    "method": "GetPlayLyricInfo",
    "param": {
      "songMid": "000Eq2fc2uW9hE",
      "crypt": 0,
      "lrc_t": 0,
      "qrc": 0,
      "qrc_t": 0,
      "roma": 0,
      "roma_t": 0,
      "trans": 0,
      "trans_t": 0,
      "needSingingAnnotations": false,
      "type": 1
    }
  }
}
```

The request envelope and transport URL follow the maintained reference's executor. The reference defaults to `crypt=1`; this experiment requested `crypt=0`, an output-format flag, and received base64 UTF-8 LRC rather than the reference's encrypted representation. This required no authentication/session manipulation. [Transport implementation](https://github.com/L-1124/QQMusicApi/blob/main/qqmusic_api/core/executor.py), [lyric request parameters](https://github.com/L-1124/QQMusicApi/blob/main/qqmusic_api/modules/lyric.py).

Observed response: top-level `code=0`, `req_0.code=0`, `req_0.data.songID=729151`, `crypt=0`, and a 1484-character base64 `lyric` value. Decoding produced 37 total lines and 32 timestamped lines. `songName` and `singerName` were empty, so retain the selected search result's metadata and check returned song ID when available. This validates one complete public search-to-lyrics path; broader catalog coverage remains unknown.

Recommendation: add a small QQ adapter using public smartbox discovery and this CGI route, with strict candidate matching and status/base64 validation. HTTP 200 alone must never count as provider success. Avoid pulling in an entire Android-session or account-login stack for this credential-free flow.

## Genius and Megalobiz: distinguish service access from parser repair

The implementation agent reports Genius search HTTP 403 and Megalobiz `/search/all` HTTP 500/503 in this session. Those observations were not redundantly probed here. They do not establish permanent closure, the cause of the failure, or a parser defect. No verified public endpoint replacement restoring either provider was found during this bounded research.

The current lyrics.ovh implementation uses Genius `/api/search/multi`, then extracts elements with `data-lyrics-container="true"`; this is a useful parser reference, **not evidence that another Genius URL will be accessible from this environment**. Do not cycle endpoint variants to circumvent an explicit access block. [Aggregator Genius implementation](https://github.com/NTag/lyrics.ovh/blob/main/lyrics.js).

Upstream syncedlyrics Megalobiz searches `/search/all`, selects `/lrc/maker/` links, and expects an element ID of `lrc_{id}_details`. Its query currently substitutes spaces manually, and missing containers are not guarded before `.get_text()`. Independently worthwhile fixes are proper query parameter encoding, HTTP status checks, missing-element handling, safe same-origin link validation, and parser fixtures. None repairs an upstream 500/503 response. [Megalobiz provider](https://github.com/moehmeni/syncedlyrics/blob/main/syncedlyrics/providers/megalobiz.py).

For both sources, return an explicit unavailable outcome promptly, preserve an opt-in diagnostic probe, and use the working alternatives. A truthful supported-provider list should distinguish “adapter included” from “live retrieval confirmed.”

## Acceptance checks for the new adapters

### NetEase follow-up: credential-free cloud search verified

On 2026-09-22, the new Go library's implementation agent reported application code `-462` from legacy `GET /api/search/pc` without syncedlyrics' historical cookie header. A maintained reference uses **POST `https://music.163.com/api/cloudsearch/pc`**, with URL-encoded form fields `s`, `type=1`, `limit` and `offset`. [Reference search implementation](https://github.com/CharlesPikachu/musicdl/blob/master/musicdl/modules/sources/netease.py).

A bounded local experiment with `s=Imagine John Lennon`, `type=1`, `limit=3`, `offset=0` returned HTTP 200/application code 200 and three candidates; the first was ID `1476431`, Imagine, artist John Lennon. `GET https://music.163.com/api/song/lyric?id=1476431&lv=1` then returned code 200 and 28 lines. A homepage request established zero cookies; a separate fresh search request with explicit user agent `lyricfetch/0.1`, no prior homepage visit and **no Cookie header** also returned three candidates. No copied session cookies, account credentials, request encryption, identity impersonation or challenge bypass were used.

The requested three-song follow-up matrix also passed using `User-Agent: lyricfetch/0.1` and no supplied cookies:

| Query | First matching candidate ID | Duration `dt` (ms) | Retrieved lines |
| --- | --- | --- | --- |
| Imagine / John Lennon | 1476431 | 185173 | 28 |
| Hello / Adele | 35847388 | 295502 | 53 |
| Alors on danse / Stromae | 19086497 | 206066 | 40 |

All six search/lyric responses were HTTP 200 with application code 200; every search returned three candidates. The first candidate's title and artist matched the requested song in each case. Confirmed metadata fields are `ar[].name`, `dt` in milliseconds and `al.name`; `artists` and `duration` were absent.

Recommendation: use this normal POST search flow and its current metadata schema. Continue strict application-status and identity validation. These three successful examples do not establish availability for all songs or regions.

### Shared acceptance criteria

1. Synthetic fixtures cover success, no candidates, mismatched candidate, service error inside HTTP 200, malformed JSON, invalid encoded content and empty lyrics.
2. Structured title/artist encoding handles punctuation and non-ASCII text without concatenating raw query strings.
3. All network operations have explicit timeouts and the complete fallback has a total deadline.
4. Plain results never take precedence over an available, correctly matched synchronized result solely because they arrive first.
5. Live checks remain small and opt-in, print only status/metadata/counts, and do not make ordinary CI depend on external provider uptime.

These acceptance criteria are engineering recommendations derived from the observed failure modes, not provider guarantees.
