---
name: daily-japanese-anki
description: Add Vocab+Sentence (V+S) iKnow! flashcard pairs to the `Daily Japanese` Anki deck via AnkiConnect. Use whenever the user wants to add a Japanese word/phrase as a flashcard, build a vocabulary card from a sentence, run the daily-Japanese add-card pipeline, generate TTS audio for a Japanese word, fetch an illustration for a vocab card, or manage the `Daily Japanese` deck. Do NOT use for any deck other than `Daily Japanese` (one-deck policy). All card adds target the existing `Daily Japanese` deck only — never call `createDeck` for any other deck name. The `iKnow! Vocabulary` / `iKnow! Sentences` entries in `deckNames` are model names, not user decks.
compatibility: Requires Anki running locally with the AnkiConnect plugin installed (default port 8765).
---

# Daily Japanese Anki (iKnow! V+S)

This skill provides integration with [AnkiConnect](https://foosoft.net/projects/anki-connect/) for the **Daily Japanese iKnow! V+S pair workflow** — adding a Vocabulary card and a Sentence card that share a single iKnowID, with TTS audio and (best-effort) image.

## Deck: Daily Japanese (the only user deck)

**Deck policy (declared 2026-06-06):** one Japanese deck — `Daily Japanese` — for all iKnow! V+S cards. **NEVER call `createDeck`** and **NEVER add notes to any deck other than `Daily Japanese`**. No sub-decks, no new decks. `iKnow! Vocabulary` / `iKnow! Sentences` are **model names** (note types), not user decks.

If `Daily Japanese` is missing from `deckNames` (fresh Anki install, profile reset), STOP and ask before doing anything. The `--ensure-deck` flag in the CLI is the only sanctioned use of `createDeck`, and it targets `Daily Japanese` only.

Each new entry becomes **one Vocabulary card + one Sentence card** sharing a single iKnowID, with audio + (best-effort) image. `iKnowID` is computed at runtime by querying Anki for the largest existing value and adding 1 (no state file).

**Field schema (both models):**
| Field | Vocabulary | Sentences |
|---|---|---|
| `Expression` | the word/phrase | the example sentence |
| `Meaning` | simple Japanese explanation, N3 or below | empty (ignore) |
| `Reading` | auto-converted hiragana (kanji/katakana → hiragana via pykakasi) | kana with spaces between words (e.g. `じゅうぎょういん に ストレス を かけて`) |
| `Audio` | `[sound:iknow-<id>-vocab.mp3]` | `[sound:iknow-<id>-sentence.mp3]` |
| `Image_URI` | `<img src="iknow-<id>-image.png">` | same image as vocab (reuse); empty string if no image |
| `iKnowID` | max(existing iKnowID values in Anki) + 1, or 1 if none | same |
| `iKnowType` | `V` | `S` |
| `tags` | `[iKnowID as string]` | same |

**Numbering:** query Anki for the largest existing `iKnowID` (across both iKnow! models, all decks), use `max + 1` as the new `iKnowID`. No state file is read or written.

## The pipeline

The full workflow is wrapped in `scripts/anki_vocab_lib.py` (library) and exposed by `scripts/daily_japanese_add.py` (CLI). **Always use the CLI to add a card** — it handles the venv re-exec, id ordering, sync, and the V/S/V+S shapes. Reach into the library directly only for tests, bulk import, or cron. **Do not write a throwaway driver script for a single card** — the CLI already covers every shape (see below).

### Default recipe (CLI)

```bash
python3 ~/.agents/skills/daily-japanese-anki/scripts/daily_japanese_add.py \
  --expression "やわらげる" \
  --meaning "激しい感情を穏やかにする" \
  --sentence "僕は奥さんの怒りを和らげた。" \
  --reading-sentence "ぼく は おくさん の いかり を やわらげた。" \
  --image-query "couple argument"
```

When you already have a sentence audio URL (e.g. a native recording), pass `--sentence-audio-url` to download it instead of generating TTS for the sentence:

```bash
python3 ~/.agents/skills/daily-japanese-anki/scripts/daily_japanese_add.py \
  --expression "やわらげる" \
  --meaning "激しい感情を穏やかにする" \
  --sentence "僕は奥さんの怒りを和らげた。" \
  --reading-sentence "ぼく は おくさん の いかり を やわらげた。" \
  --sentence-audio-url "https://example.com/sentence.mp3" \
  --image-query "couple argument"
```

**Image resolution mirrors audio.** There are three states, and the default is *search*, not skip:

| You pass | Behavior |
|----------|----------|
| `--image-url URL` | download that exact image |
| `--image-query "..."` (no URL) | run the existing image-search tool and save the result |
| `--no-image` | skip the image (text-only card) |

So **if you don't pass an image URL, the image is still searched and saved via `--image-query`** — only `--no-image` skips it. `--image-url` makes `--image-query` optional. Example with a specific image:

```bash
python3 ~/.agents/skills/daily-japanese-anki/scripts/daily_japanese_add.py \
  --expression "芥川" \
  --meaning "文学や芸術で名声を得た人の名字。" \
  --image-url "https://upload.wikimedia.org/.../Akutagawa.jpg"
```

For visually-iconic words where the helper can't find an illustration, drop the image entirely:

```bash
python3 ~/.agents/skills/daily-japanese-anki/scripts/daily_japanese_add.py \
  --expression "折り返し" \
  --meaning "電話などで、かけ直すこと。" \
  --sentence "鈴木は、ただいま席を外しておりますので、戻り次第、折り返しご連絡いたします。" \
  --reading-sentence "すずきは、ただいませきを はずしておりますので、もどりしだい、おりかえし ご連絡 いたします。" \
  --no-image
```

**Card shape is auto-detected from which args you pass** — there is no mode flag. The same CLI does all three:

- **V only** — pass `--expression --meaning` (no sentence args):

```bash
python3 ~/.agents/skills/daily-japanese-anki/scripts/daily_japanese_add.py \
  --expression "芥川" \
  --meaning "芥川龍之介のように、文学や芸術の世界で名声を得た人の名字。" \
  --no-image
```

- **S only** — pass `--sentence --reading-sentence` (no vocab args):

```bash
python3 ~/.agents/skills/daily-japanese-anki/scripts/daily_japanese_add.py \
  --sentence "黒字と赤字の境界線となる損益分岐点を見極めることが重要だ。" \
  --reading-sentence "くろじ と あかじ の きょうかいせん と なる そんえきぶんきてん を みきわめる ことが じゅうようだ。" \
  --image-query "break even chart"
```

- **V + S** — pass all four (the examples above/below).

Each side must be a complete pair; passing one without its partner is an error. At least one complete card is required.

> ⚠️ **Never hand-roll a one-off driver script** (e.g. `python3 -c "import anki_vocab_lib..."` or a throwaway `add_*.py`) to add a card. This CLI already covers V-only, S-only, and V+S. An ad-hoc importer skips the venv re-exec (→ `No module named 'pykakasi'`), the pre-read + final Anki sync, and iKnowID ordering — every past breakage came from this. If you think you need a custom script, you don't.

For a fresh Anki install where `Daily Japanese` doesn't exist yet, add `--ensure-deck`:

```bash
python3 ~/.agents/skills/daily-japanese-anki/scripts/daily_japanese_add.py \
  --expression "やわらげる" \
  --meaning "激しい感情を穏やかにする" \
  --sentence "僕は奥さんの怒りを和らげた。" \
  --reading-sentence "ぼく は おくさん の いかり を やわらげた。" \
  --image-query "couple argument" \
  --ensure-deck
```

### What the recipe does (in order)

1. _(Optional, `--ensure-deck`)_ `ensure_deck()` — `createDeck("Daily Japanese")` (idempotent) followed by a `getDeckConfig` probe to dodge the AnkiConnect cache-flush race (pitfall #14). Only needed on a fresh Anki install.
2. **Resolve iKnowID** — query Anki for the largest existing `iKnowID` value, use `max + 1` (or 1 if none exist). No state file is read or written.
3. **TTS** for vocab and sentence via `scripts/tts-ja.sh -o ~/tts-output/iknow-<id>-vocab.mp3 "<Expression>"` and the same for the sentence. If `--sentence-audio-url` is given, the sentence audio is **downloaded** from that URL instead of TTS-generated (vocab audio is still TTS). The downloaded file is saved as `iknow-<id>-sentence.mp3`, so the note's `Audio` field is unchanged.
4. **Image search** via `scripts/image-search-download.sh`, trying each source in `IMAGE_SOURCE_ORDER = ["irasutoya", "commons", "pixabay", "pexels"]` until one returns a usable file. **Hard cap: 2 attempts.** After 2 consecutive failures the script logs a warning and proceeds with no image at all — do not retry endlessly, and do not stop the run. `--no-image` skips this step entirely.
5. **Media import** into Anki via `storeMediaFile`: image (if found) as `iknow-<id>-image.png`, then both `.mp3` files. Use `.png` extension to be safe even if the source is `.jpg`/`.webp`.
6. **addNote** for the V and S notes. `allowDuplicate=False`, `duplicateScope="deck"`.
7. **Sync once** at the end. (`--no-sync` to skip for batch runs.)

### Dependency scripts (bundled)

`scripts/anki_vocab_lib.py` resolves these scripts relative to the skill's own `scripts/` directory by default — no separate install step required:

- `scripts/tts-ja.sh` — Edge TTS wrapper, voice `ja-JP-NanamiNeural`
- `scripts/image-search-download.sh` — multi-source image search with `-s` / `-q` / `-d` flags

Both require the Python venv at `~/.venvs/edge-tts/` with `edge-tts`, `beautifulsoup4`, and `requests` installed (the `tts-ja.sh` script uses the `edge-tts` binary; `image-search-download.sh` uses the venv's `python` via `$PYTHON_BIN`).

If you want the scripts in a different location, override the workspace root with the `DAILY_JP_WORKSPACE` environment variable.

## Why this matters

- The V+S pair must share **one iKnowID** (not separate counters) and **one image** (don't re-fetch per note). Audio is two files, but they share the same id.
- **Don't re-import the same media file** if a card for the same iKnowID is being updated — `storeMediaFile` is idempotent but wastes a round-trip.
- **The image field accepts an empty string** — don't fabricate a URL just to fill it. An empty `Image_URI` is a valid card; it's how cards get added when image search fails.

## Pitfalls

1. **Don't re-prompt the user for every bash call.** opencode's permission rules handle this. Trust the pipeline; don't narrate each call as if it were a fresh approval.
2. **Don't store raw URLs in `Image_URI`** — import the image into Anki media first (so it syncs to AnkiWeb), then embed the local media filename with `<img src="..."">`. Storing only a URL breaks offline sync.
3. **Don't sync after every card.** Sync once at the end of the batch.
4. **Audio field uses `[sound:filename]` not `<audio>`** — that is the iKnow! model's convention. Brackets, not angle brackets.
5. **Don't reveal the count of "how many cards we have"** in the response — keep it terse.
6. **Image extension mismatch** — Anki's `storeMediaFile` does not auto-rename; if you save as `.png` but reference `.jpg` in `Image_URI`, the card shows a broken image. Pick a single extension and use it everywhere (we always use `.png`).
7. **If image search fails, do not halt the run.** Log it, set `Image_URI=""` for both notes, and proceed. A text-only card beats no card.
8. **`findNotes` with `deck:<name containing spaces>` can return `[]` right after `addNote`.** Don't conclude the card wasn't created. Verify with the note IDs from `addNote` via `findNotes` with a content or tag query.
9. **`addNotes` (plural) returns `null` on success, NOT the note IDs.** AnkiConnect bug distinct from the singular `addNote`. When `addNotes` returns `{"result": null, "error": null}` and the error list is empty, the notes were created — verify with `findNotes` instead of assuming failure and retrying. Retrying on a "null" success will trip `cannot create note because it is a duplicate`.
10. **NEVER call `createDeck` for any deck other than `Daily Japanese`.** The CLI's `--ensure-deck` flag is the ONLY sanctioned use of `createDeck`, and it targets `Daily Japanese` only.
11. **Decks may not exist yet — check first, create if missing.** On a fresh Anki install (or after a profile reset) `addNote` fails with `deck was not found`. Use the CLI's `--ensure-deck` flag, or call `lib.ensure_deck()` from a custom driver.
12. **`createDeck` is not immediately visible to `addNote` — race condition.** Even when `createDeck` returns a valid id and a subsequent `deckNames` lists the deck, the very next `addNote` can still fail with `deck was not found`. The fix is a `getDeckConfig(deck=...)` probe immediately before `addNote` — this forces the cache flush. The `lib.ensure_deck()` helper encapsulates this. Loop the probe 2–3 times with a short `sleep 0.2` if the first one doesn't unblock.
13. **Text-only is a valid card, not a failure mode.** For most new words the image search bails — irasutoya JS-renders banners, Pixabay/Pexels 403, and the irasutoya atom feed rarely has an exact match. Reaching for `--no-image` and shipping an audio-only card is the right call. Backfilling an image later is fine: re-upload the media via `storeMediaFile` and update the `Image_URI` field of an existing note via `updateNoteFields`.
14. **Skill files are shared with sibling subagents — re-read before each patch.** The skill directory is on a shared filesystem, and other agents (sibling subagents, kyo via the curator) can modify the same `SKILL.md`, `scripts/*.py`, and `templates/*.json` mid-task. For big multi-file rewrites of a skill, prefer a full re-read followed by a clean write of the complete new content over chained edits, so the last write wins cleanly.

## Templates and scripts

- `scripts/daily_japanese_add.py` — CLI for the `Daily Japanese` deck. Card shape (V / S / V+S) is **auto-detected** from which args you pass. Auto iKnowID from Anki; image is **searched by default** via `--image-query`, or pass `--image-url` for a specific image, or `--no-image` to skip; `--ensure-deck` for the rare fresh-install case. **Use this for every new iKnow! card — never write a throwaway driver script.**
- `scripts/anki_vocab_lib.py` — the library. One unified pipeline `add_cards(expression?, meaning?, sentence?, reading_sentence?, image_query?, image_url?, ...)` builds whichever of V/S is requested; `add_card_pair()`, `add_vocab_only()`, `add_sentence_only()` are thin wrappers over it. Also `find_image()`, `generate_audio()`, `download_audio()`, `download_image()`, `store_media()`, `ensure_deck()`, `build_vocab_note()`, `build_sentence_note()`, `next_iknow_id_from_anki()`, `_existing_iknow_ids()`. Import only for tests/bulk/cron — for a single card, use the CLI.
- `templates/note_vocab.json` and `templates/note_sentence.json` — exact field shapes to copy.
- `references/troubleshooting.md` — failure transcripts and detailed recovery recipes (irasutoya atom feed, ffmpeg resize, etc.).

## Quick library use (advanced)

```python
from scripts.anki_vocab_lib import add_card_pair

add_card_pair(
    expression="やわらげる",
    meaning="激しい感情を穏やかにする",
    sentence="僕は奥さんの怒りを和らげた。",
    reading_sentence="ぼく は おくさん の いかり を やわらげた。",
    image_query="couple argument",
    # i_know_id=None,            # auto from state
    # skip_image=False,          # True for text-only (pitfall #13)
    # ensure_deck_first=False,   # True on fresh Anki install (pitfall #12)
    # sync_after=True,           # False for batch runs
    # sentence_audio_url=None,   # download sentence audio instead of TTS
)
```

`add_card_pair` returns a small dict with `iKnowID`, `vocab_note_id`, `sentence_note_id`, and `image_media` (or `None` when the image search gave up). Exceptions are propagated.

## Manual / raw-AnkiConnect recipes (rare)

The CLI covers every standard case. **Only** when you need a flow the CLI doesn't cover
(custom field shapes, debugging, ad-hoc fixes, text-only via raw curl), see
`references/troubleshooting.md` → **"Manual recipe"** and **"Minimal recipe"** for the
full `curl` sequences (model probe → media dir → TTS → addNote ×2 → sync → verify).
All notes must still target `Daily Japanese`.
