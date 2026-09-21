# Contributing

Use Python 3.12 or newer. Follow the development commands in [README.md](README.md) before submitting a pull request.

- Keep external network calls out of ordinary tests; use synthetic provider responses and explicit live probes.
- Never include keys, tokens, private preferences, cache files, or complete third-party lyrics in fixtures, logs, screenshots, or pull requests.
- Keep provider requests bounded, and preserve the existing lyric sheet on failure.
- Exercise parser changes with both synchronized and plain lyrics. Test provider/model identity in cache keys.
- Keep the single-user loopback deployment assumption explicit. A hosted/multi-user deployment needs a separate design.
- Include behavior changes and validation in the PR description. Update setup docs when configuration changes.
- Run Ruff, djLint, ESLint, Prettier, pytest and Playwright. Frontend vendor files are excluded from formatting; retain their license notices.

The [lyrics research](docs/lyrics-research.md) records source provenance and known provider limitations. Recheck upstream changes before adopting code from a fork.
