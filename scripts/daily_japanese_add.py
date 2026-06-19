#!/usr/bin/env python3
"""
CLI for adding Daily Japanese iKnow! cards (V only, S only, or V + S).

Thin wrapper around anki_vocab_lib.add_cards(). All the actual work —
TTS, image search, Anki media import, notes, sync, state — lives in the
library so it can be reused (tests, bulk import, cron jobs, etc.).

Card shape is auto-detected from which args you pass — there is no mode flag:
  - V only:  --expression --meaning
  - S only:  --sentence --reading-sentence
  - V + S:   all four
This CLI covers every shape. Do NOT hand-roll a one-off driver script to add
a card — that path skips the venv re-exec, the Anki sync, and id ordering.

Deck policy (declared 2026-06-06 by kyo):
  Cards always go into the existing `Daily Japanese` deck. Never call
  `createDeck` for any other deck name. The `--ensure-deck` flag is the
  only exception: it (idempotently) ensures `Daily Japanese` itself exists,
  for the rare fresh-Anki-install case.

Usage (V + S):
  python3 daily_japanese_add.py \\
      --expression "やわらげる" \\
      --meaning "激しい感情を穏やかにする" \\
      --sentence "僕は奥さんの怒りを和らげた。" \\
      --reading-sentence "ぼく は おくさん の いかり を やわらげた。" \\
      --image-query "couple argument"

Usage (V only):
  python3 daily_japanese_add.py \\
      --expression "横ばい" \\
      --meaning "数値や状態が上にも下にも動かず、ほぼ同じ水準で続くこと。" \\
      --no-image

Usage (S only):
  python3 daily_japanese_add.py \\
      --sentence "黒字と赤字の境界線を見極める。" \\
      --reading-sentence "くろじ と あかじ の きょうかいせん を みきわめる。" \\
      --no-image

Notes:
  - --iKnowID is optional; if omitted the next available id is computed at
    runtime by querying Anki for the largest existing iKnowID (max + 1).
    No state file is read or written.
  - --sentence-audio-url downloads the sentence audio from the given URL
    instead of generating it via TTS (the vocab audio is still TTS-generated).
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
import os
import sys


def _ensure_venv_interpreter() -> None:
    """Re-exec under the skill's venv when runtime deps aren't importable here.

    The documented entrypoint is `python3 daily_japanese_add.py`, but deps like
    pykakasi live in the venv created by install.sh (default ~/.venvs/edge-tts).
    Run under a bare system python3 that lacks them, this transparently re-execs
    with the venv's interpreter instead of failing with
    `No module named 'pykakasi'`. Honors EDGE_TTS_VENV; guards against re-exec
    loops via DAILY_JP_REEXEC.
    """
    try:
        import pykakasi  # noqa: F401
        return  # current interpreter already has what we need
    except ModuleNotFoundError:
        pass
    if os.environ.get("DAILY_JP_REEXEC") == "1":
        return  # already re-exec'd once; let the real import fail clearly
    venv = os.path.expanduser(os.environ.get("EDGE_TTS_VENV", "~/.venvs/edge-tts"))
    venv_py = os.path.join(venv, "bin", "python")
    if os.path.exists(venv_py) and os.path.realpath(venv_py) != os.path.realpath(sys.executable):
        os.environ["DAILY_JP_REEXEC"] = "1"
        os.execv(venv_py, [venv_py, os.path.abspath(__file__), *sys.argv[1:]])


_ensure_venv_interpreter()

import argparse  # noqa: E402
from pathlib import Path  # noqa: E402

# Allow `python3 scripts/daily_japanese_add.py` from any cwd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import anki_vocab_lib as lib  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--expression", default=None,
                   help="vocabulary word/phrase (Japanese). Pair with --meaning "
                        "to build a V card.")
    p.add_argument("--meaning", default=None,
                   help="simple Japanese explanation (N3 or below). Pair with "
                        "--expression to build a V card.")
    p.add_argument("--sentence", default=None,
                   help="example sentence (Japanese). Pair with --reading-sentence "
                        "to build an S card.")
    p.add_argument("--reading-sentence", default=None,
                   help="kana reading of the sentence with spaces between words. "
                        "Pair with --sentence to build an S card.")
    p.add_argument("--image-query", default=None,
                   help="search query for the illustration "
                        "(required unless --no-image is set)")
    p.add_argument("--iKnowID", type=int, default=None,
                   help="explicit iKnowID (else read from state)")
    p.add_argument("--sentence-audio-url", default=None,
                   help="URL of a pre-existing sentence audio file. When set, "
                        "the sentence audio is downloaded from this URL instead "
                        "of generated via TTS (vocab audio is still TTS).")
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

    # Card shape is auto-detected from which args are supplied. Each side must
    # be given as a complete pair; at least one complete card is required.
    if bool(args.expression) != bool(args.meaning):
        p.error("--expression and --meaning must be given together (V card)")
    if bool(args.sentence) != bool(args.reading_sentence):
        p.error("--sentence and --reading-sentence must be given together (S card)")
    want_v = bool(args.expression) and bool(args.meaning)
    want_s = bool(args.sentence) and bool(args.reading_sentence)
    if not want_v and not want_s:
        p.error("provide a V card (--expression --meaning), an S card "
                "(--sentence --reading-sentence), or both")
    if args.sentence_audio_url and not want_s:
        p.error("--sentence-audio-url requires --sentence/--reading-sentence")

    try:
        result = lib.add_cards(
            expression=args.expression,
            meaning=args.meaning,
            sentence=args.sentence,
            reading_sentence=args.reading_sentence,
            image_query=args.image_query,
            i_know_id=args.iKnowID,
            skip_image=args.no_image,
            ensure_deck_first=args.ensure_deck,
            sync_after=not args.no_sync,
            sentence_audio_url=args.sentence_audio_url,
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
