"""Original sample text, written for this project; no external calls."""

from models import LyricLine, Song


def demo_song():
    pairs = [
        (
            "La lumière entre dans la pièce",
            "The light comes into the room",
            "la ly.mjɛʁ ɑ̃tʁ dɑ̃ la pjɛs",
        ),
        ("Et le jour commence doucement", "And the day begins softly", "e lə ʒuʁ kɔ.mɑ̃s du.sə.mɑ̃"),
        (
            "Une chanson traverse la ville",
            "A song travels through the city",
            "yn ʃɑ̃.sɔ̃ tʁa.vɛʁs la vil",
        ),
        (
            "Je la garde avec moi un instant",
            "I keep it with me for a moment",
            "ʒə la ɡaʁd a.vɛk mwa œ̃.n‿ɛ̃.stɑ̃",
        ),
        ("Chaque mot ouvre une fenêtre", "Every word opens a window", "ʃak mo u.vʁ‿yn fə.nɛtʁ"),
        (
            "Sur un monde que je découvre",
            "Onto a world I am discovering",
            "syʁ œ̃ mɔ̃d kə ʒə de.kuvʁ",
        ),
    ]
    return Song(
        title="Une fenêtre ouverte",
        artist="LingoLyrics · original demo",
        spotify_id="demo",
        demo=True,
        lyrics_source="Original sample",
        original_languages=["French"],
        lyrics=[
            LyricLine(
                timestamp=f"[00:{i * 6:02d}.00]",
                time_seconds=i * 6,
                original=original,
                phonetics=ipa,
                translations={"en": translated},
            )
            for i, (original, translated, ipa) in enumerate(pairs)
        ],
    )
