"""Opt-in live smoke check. Prints counts and timings, never lyric text."""

import argparse
import multiprocessing
import time


def probe(provider, queue):
    from lyrics_service import fetch_lyrics, parse_lyrics

    start = time.monotonic()
    try:
        text, source = fetch_lyrics("Imagine", "John Lennon", provider)
        lines, synced = parse_lyrics(text)
        queue.put(f"{source}: {len(lines)} lines, synced={synced}, {time.monotonic() - start:.1f}s")
    except Exception as exc:
        queue.put(f"{provider}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "providers", nargs="*", default=["lrclib", "NetEase", "Musixmatch", "Megalobiz", "Genius"]
    )
    args = parser.parse_args()
    for provider in args.providers:
        queue = multiprocessing.Queue()
        process = multiprocessing.Process(target=probe, args=(provider, queue))
        process.start()
        process.join(20)
        if process.is_alive():
            process.terminate()
            process.join()
            print(f"{provider}: timed out after 20s", flush=True)
        elif not queue.empty():
            print(queue.get(), flush=True)
        else:
            print(f"{provider}: worker failed", flush=True)
