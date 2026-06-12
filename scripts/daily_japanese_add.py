#!/usr/bin/env python3
"""
CLI for adding a Daily Japanese iKnow! card pair (V + S).

Thin wrapper around anki_vocab_lib.add_card_pair(). All the actual work —
TTS, image search, Anki media import, notes, sync, state — lives in the
library so it can be reused (tests, bulk import, cron jobs, etc.).

Deck policy (declared 2026-06-06 by kyo):
  Cards always go into the existing `Daily Japanese` deck. Never call
  `createDeck` for any other deck name. The `--ensure-deck` flag is the
  only exception: it (idempotently) ensures `Daily Japanese` itself exists,
  for the rare fresh-Anki-install case.

Usage:
  python3 daily_japanese_add.py \\
      --expression "やわらげる" \\
      --meaning "激しい感情を穏やかにする" \\
      --sentence "僕は奥さんの怒りを和らげた。" \\
      --reading-sentence "ぼく は おくさん の いかり を やわらげた。" \\
      --image-query "couple argument"

Notes:
  - --iKnowID is optional; if omitted the next available id is computed at
    runtime by querying Anki for the largest existing iKnowID (max + 1).
    No state file is read or written.
  - --no-image skips the image search entirely (saves ~5s of HTTP probes,
    and is the right call for words that have no iconic illustration).
  - --no-sync skips the final Anki sync (handy for batch runs that sync
    once at the end).
  - --ensure-deck calls createDeck + getDeckConfig probe to dodge the
    AnkiConnect deck-cache race. Only needed on a fresh Anki install
    where `Daily Japanese` doesn't exist yet.

Environment:
  - DAILY_JP_WORKSPACE: root dir holding scripts/
    (default: the skill's own directory)
  - ANKI_URL: AnkiConnect endpoint (default: http://localhost:8765)
"""
import argparse
import sys
from pathlib import Path

# Allow `python3 scripts/daily_japanese_add.py` from any cwd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import anki_vocab_lib as lib  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--expression", required=True,
                   help="vocabulary word/phrase (Japanese)")
    p.add_argument("--meaning", required=True,
                   help="simple Japanese explanation (N3 or below)")
    p.add_argument("--sentence", required=True,
                   help="example sentence (Japanese)")
    p.add_argument("--reading-sentence", required=True,
                   help="kana reading of the sentence with spaces between words")
    p.add_argument("--image-query", default=None,
                   help="search query for the illustration "
                        "(required unless --no-image is set)")
    p.add_argument("--iKnowID", type=int, default=None,
                   help="explicit iKnowID (else read from state)")
    p.add_argument("--no-image", action="store_true",
                   help="skip image search entirely (text-only card)")
    p.add_argument("--no-sync", action="store_true",
                   help="skip the final Anki sync")
    p.add_argument("--ensure-deck", action="store_true",
                   help="createDeck + getDeckConfig probe for `Daily Japanese` "
                        "before addNote. Only needed on a fresh Anki install.")
    args = p.parse_args()

    if not args.no_image and not args.image_query:
        p.error("--image-query is required unless --no-image is set")

    try:
        result = lib.add_card_pair(
            expression=args.expression,
            meaning=args.meaning,
            sentence=args.sentence,
            reading_sentence=args.reading_sentence,
            image_query=args.image_query,
            i_know_id=args.iKnowID,
            skip_image=args.no_image,
            ensure_deck_first=args.ensure_deck,
            sync_after=not args.no_sync,
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print("\n--- summary ---")
    for k, v in result.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
