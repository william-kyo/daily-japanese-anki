"""
Shared library for the Daily Japanese iKnow! card-pair workflow.

Pure-ish functions (no I/O at import time, all side effects explicit).
Used by `daily_japanese_add.py` and any future callers (e.g. bulk import,
test harnesses).

Deck policy (declared 2026-06-06 by kyo):
  - ONLY one user deck exists: `Daily Japanese`. NEVER call `createDeck` for
    any other deck name. NEVER add cards to any deck other than
    `Daily Japanese`. The `iKnow! Vocabulary` / `iKnow! Sentences` entries
    in `deckNames` are model names, not user decks — they exist as note-type
    targets within the `Daily Japanese` deck.
  - `ensure_deck` is the ONLY exception that may call `createDeck`, and only
    for the `Daily Japanese` deck itself. Use it when Anki starts up on a
    fresh profile where the deck is missing — but in the normal case the
    deck already exists, and the helper is idempotent.

Layout:
  - Anki:   json-rpc over HTTP to AnkiConnect
  - TTS:    wraps scripts/tts-ja.sh (Edge TTS, voice ja-JP-NanamiNeural)
  - Image:  wraps scripts/image-search-download.sh with 2-strike fallback
  - ID:     queries Anki for the largest existing iKnowID (no state file)
  - Notes:  builds V + S Anki note payloads

Environment overrides:
  - DAILY_JP_WORKSPACE: root directory holding scripts/
    (default: the skill's own directory)
  - ANKI_URL: AnkiConnect endpoint (default: http://localhost:8765)
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ANKI_URL = os.environ.get("ANKI_URL", "http://localhost:8765")
DECK = "Daily Japanese"

# Default workspace = the skill's own directory (so scripts/ is co-located).
# Users can override with DAILY_JP_WORKSPACE if they want a different layout.
SKILL_DIR = Path(__file__).resolve().parent.parent
WORKSPACE = Path(os.environ.get("DAILY_JP_WORKSPACE", str(SKILL_DIR))).expanduser()
TTS_SCRIPT = WORKSPACE / "scripts" / "tts-ja.sh"
IMG_SCRIPT = WORKSPACE / "scripts" / "image-search-download.sh"
TTS_OUT_DIR = Path("~/tts-output").expanduser()
IMG_OUT_DIR = Path("~/image-search-results").expanduser()

# Image-source search order. Per memory rule: irasutoya → commons → pixabay → pexels.
# Each is tried at most ONCE — if the first two fail we give up on the image
# and proceed without it.
IMAGE_SOURCE_ORDER = ["irasutoya", "commons", "pixabay", "pexels"]
MAX_IMAGE_ATTEMPTS = 2  # give up after this many failures (skip the rest)


# ---------------------------------------------------------------------------
# AnkiConnect
# ---------------------------------------------------------------------------
def anki(action: str, **params):
    """Single round-trip to AnkiConnect. Returns the parsed response dict."""
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(
        ANKI_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def store_media(filename: str, path: Path) -> str:
    """Import a local file into Anki's media collection, return the stored name."""
    b64 = base64.b64encode(path.read_bytes()).decode()
    res = anki("storeMediaFile", filename=filename, data=b64)
    if res.get("error") is not None:
        raise RuntimeError(f"storeMediaFile({filename}) failed: {res}")
    return res["result"]


def sync() -> None:
    """Trigger an Anki sync. Idempotent."""
    anki("sync")


def ensure_deck() -> None:
    """Create the `Daily Japanese` deck (idempotent) and force AnkiConnect to
    refresh its internal deck map by probing getDeckConfig. Without the probe,
    the very next addNote can return `deck was not found` even though
    createDeck already succeeded (see pitfall #12 in SKILL.md).

    The deck name is hardcoded to `Daily Japanese` — the deck policy above
    forbids targeting any other deck.
    """
    anki("createDeck", deck=DECK)
    # The probe is intentionally redundant (we already know the deck exists
    # if createDeck returned an id) — its job is to flush the cache, not to
    # validate. Loop 2x with a short sleep because the flush is near-instant
    # but not synchronous with the prior createDeck call.
    for _ in range(2):
        anki("getDeckConfig", deck=DECK)
        time.sleep(0.2)


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------
def generate_audio(out_path: Path, text: str) -> Path:
    """Run tts-ja.sh to write a Japanese mp3 to out_path. Returns out_path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["bash", str(TTS_SCRIPT), "-o", str(out_path), text],
        check=True,
    )
    return out_path


def download_audio(url: str, out_path: Path) -> Path:
    """Download a pre-existing audio file to out_path. Returns out_path.

    Used when the caller already has a sentence audio URL (e.g. from a source
    that ships native recordings) and wants to skip TTS generation entirely.
    Raises on HTTP error or empty body so the failure is loud, not silent.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "daily-japanese-anki/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    if not data:
        raise RuntimeError(f"download_audio({url}) returned an empty body")
    out_path.write_bytes(data)
    return out_path


# ---------------------------------------------------------------------------
# Image search (with 2-strike fallback)
# ---------------------------------------------------------------------------
class ImageNotFoundError(Exception):
    """Raised when MAX_IMAGE_ATTEMPTS consecutive image sources fail."""


def _try_one_image_source(query: str, source: str) -> Optional[Path]:
    """Run image-search-download.sh for one source. Returns a downloaded file
    path if a usable image was produced, else None.

    To avoid the "old file from a previous run" trap, we only consider files
    written *during* this call: snapshot mtime before the subprocess starts,
    then pick the freshest image file with mtime >= that snapshot.
    """
    IMG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    pre_mtime = time.time()
    cmd = ["bash", str(IMG_SCRIPT), "-s", source, "-q", query]
    if source == "commons":
        cmd.append("-d")  # only commons supports auto-download
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"[image] {source} CLI failed (rc={e.returncode})")
        return None
    candidates = sorted(
        [
            p
            for p in IMG_OUT_DIR.iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
            and p.stat().st_mtime >= pre_mtime - 0.5  # 0.5s clock skew tolerance
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    return candidates[0]


def find_image(query: str) -> Optional[Path]:
    """Try IMAGE_SOURCE_ORDER up to MAX_IMAGE_ATTEMPTS times. Returns a path
    on success, or None if every attempt failed. Never raises."""
    if MAX_IMAGE_ATTEMPTS <= 0:
        return None
    tried = 0
    for source in IMAGE_SOURCE_ORDER:
        if tried >= MAX_IMAGE_ATTEMPTS:
            break
        print(f"[image] trying source {source!r} for {query!r} "
              f"(attempt {tried + 1}/{MAX_IMAGE_ATTEMPTS})")
        tried += 1
        try:
            result = _try_one_image_source(query, source)
        except Exception as e:
            print(f"[image] {source} raised: {e}")
            result = None
        if result is not None:
            print(f"[image] success via {source}: {result}")
            return result
        print(f"[image] {source} returned no usable image")
    print(f"[image] giving up after {tried} attempt(s); proceeding without image")
    return None


# ---------------------------------------------------------------------------
# Hiragana conversion (kanji / katakana → hiragana, for the Vocab Reading field)
# ---------------------------------------------------------------------------
_KAKASI = None


def _import_pykakasi():
    """Import pykakasi, self-healing when the active interpreter lacks it.

    pykakasi is installed in the skill's venv (default ~/.venvs/edge-tts, see
    install.sh). The CLI entrypoint re-execs under that venv, but ad-hoc callers
    that `import anki_vocab_lib` under a bare system python3 don't get that
    protection. Rather than fail with `No module named 'pykakasi'`, we locate
    the venv's site-packages and add it to sys.path, then retry. Honors
    EDGE_TTS_VENV. This makes the library safe to import from ANY interpreter.
    """
    try:
        import pykakasi  # type: ignore
        return pykakasi
    except ModuleNotFoundError:
        pass
    import glob
    import sys
    venv = Path(os.environ.get("EDGE_TTS_VENV", "~/.venvs/edge-tts")).expanduser()
    # CPython lays site-packages out as lib/pythonX.Y/site-packages.
    for site in sorted(glob.glob(str(venv / "lib" / "python*" / "site-packages"))):
        if site not in sys.path:
            sys.path.append(site)
    try:
        import pykakasi  # type: ignore
        return pykakasi
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            f"pykakasi not importable and not found under {venv}. "
            f"Run install.sh, or set EDGE_TTS_VENV to the venv that has it."
        ) from e


def _get_kakasi():
    """Lazy-init pykakasi (the conversion is JIT-expensive)."""
    global _KAKASI
    if _KAKASI is None:
        pykakasi = _import_pykakasi()
        _KAKASI = pykakasi.kakasi()
    return _KAKASI


def to_hiragana(text: str) -> str:
    """Convert kanji + katakana in `text` to hiragana. Pass-through for already-
    hiragana or non-Japanese text. Used to populate the Vocabulary card's
    Reading field so the Anki reviewer shows the kana form."""
    if not text:
        return text
    k = _get_kakasi()
    return "".join(token["hira"] for token in k.convert(text))


# ---------------------------------------------------------------------------
# iKnowID resolution (queried from Anki, not stored in a state file)
# ---------------------------------------------------------------------------
def _existing_iknow_ids() -> list[int]:
    """Return all iKnowID values currently in Anki (across all decks, both
    iKnow! models), as a sorted list of ints. Empty list if none exist."""
    # Query the iKnowID field directly. Anki's search treats field values as
    # strings, but `iKnowID:*` matches anything non-empty, then we filter to
    # digit-only values via notesInfo.
    res = anki("findNotes", query='"iKnowID:*"')
    note_ids = res.get("result") or []
    if not note_ids:
        return []
    # notesInfo is a heavier call but it's the only way to get actual field
    # values. Batch in chunks of 100 (AnkiConnect's notesInfo limit).
    ids: list[int] = []
    for chunk_start in range(0, len(note_ids), 100):
        chunk = note_ids[chunk_start:chunk_start + 100]
        info_res = anki("notesInfo", notes=chunk)
        for n in info_res.get("result") or []:
            fields = n.get("fields", {}) or {}
            raw = fields.get("iKnowID", {}).get("value", "")
            raw = (raw or "").strip()
            if raw.isdigit():
                ids.append(int(raw))
    return sorted(set(ids))


def next_iknow_id_from_anki() -> int:
    """Return max(existing iKnowIDs in Anki) + 1, or 1 if none exist.

    Syncs Anki first so that iKnowIDs created on other devices are pulled in
    before we compute the next id. Without this, a note added on another device
    (but not yet synced locally) would be invisible here, and we'd reuse its id
    and collide. The sync is best-effort: if it fails (e.g. offline, no sync
    configured) we fall back to the local collection rather than blocking.
    """
    try:
        print("[sync] syncing Anki before reading iKnowIDs...")
        sync()
    except Exception as e:  # noqa: BLE001 - best-effort, never block id lookup
        print(f"[sync] pre-read sync failed ({e}); using local collection")
    ids = _existing_iknow_ids()
    nxt = (max(ids) + 1) if ids else 1
    print(f"[id] queried Anki: {len(ids)} existing iKnowID(s), next = {nxt}")
    return nxt


def next_iknow_id(explicit: Optional[int] = None) -> int:
    """Return the iKnowID to use. If `explicit` is provided, use it. Otherwise
    query Anki for the largest existing iKnowID and return max + 1."""
    if explicit is not None:
        return explicit
    return next_iknow_id_from_anki()


# ---------------------------------------------------------------------------
# Note builders (V + S)
# ---------------------------------------------------------------------------
def build_vocab_note(
    iknow_id: int,
    expression: str,
    meaning: str,
    image_media: Optional[str],
) -> dict:
    audio = f"[sound:iknow-{iknow_id}-vocab.mp3]"
    image_field = f'<img src="{image_media}">' if image_media else ""
    return {
        "deckName": DECK,
        "modelName": "iKnow! Vocabulary",
        "fields": {
            "Expression": expression,
            "Meaning": meaning,
            "Reading": to_hiragana(expression),  # kanji/katakana → hiragana
            "Audio": audio,
            "Image_URI": image_field,
            "iKnowID": str(iknow_id),
            "iKnowType": "V",
        },
        "tags": [str(iknow_id)],
        "options": {"allowDuplicate": False, "duplicateScope": "deck"},
    }


def build_sentence_note(
    iknow_id: int,
    sentence: str,
    reading: str,
    image_media: Optional[str],
) -> dict:
    audio = f"[sound:iknow-{iknow_id}-sentence.mp3]"
    image_field = f'<img src="{image_media}">' if image_media else ""
    return {
        "deckName": DECK,
        "modelName": "iKnow! Sentences",
        "fields": {
            "Expression": sentence,
            "Meaning": "",
            "Reading": reading,
            "Audio": audio,
            "Image_URI": image_field,
            "iKnowID": str(iknow_id),
            "iKnowType": "S",
        },
        "tags": [str(iknow_id)],
        "options": {"allowDuplicate": False, "duplicateScope": "deck"},
    }


def add_note(note: dict) -> int:
    """Add one note, return its id, raising on error."""
    res = anki("addNote", note=note)
    if res.get("error") is not None:
        raise RuntimeError(f"addNote failed: {res}")
    return res["result"]


# ---------------------------------------------------------------------------
# Top-level pipeline
# ---------------------------------------------------------------------------
def add_cards(
    expression: Optional[str] = None,
    meaning: Optional[str] = None,
    sentence: Optional[str] = None,
    reading_sentence: Optional[str] = None,
    image_query: Optional[str] = None,
    i_know_id: Optional[int] = None,
    skip_image: bool = False,
    ensure_deck_first: bool = False,
    sync_after: bool = True,
    sentence_audio_url: Optional[str] = None,
) -> dict:
    """Unified end-to-end pipeline for ALL three card shapes under one iKnowID:

      - V only:  pass `expression` + `meaning`
      - S only:  pass `sentence` + `reading_sentence`
      - V + S:   pass all four

    Steps: optional ensure-deck → TTS (per requested side) → image (shared,
    2-strike fallback) → media → notes → sync. Whatever isn't requested is
    simply skipped — there is one code path, so V/S/V+S never drift.

    Returns a summary dict with `vocab_note_id` / `sentence_note_id` set to the
    new note id, or None for a side that wasn't built.

    Args:
      - `skip_image=True` bypasses image search entirely (text-only card).
      - `ensure_deck_first=True` runs `ensure_deck()` (idempotent) to create
        `Daily Japanese` and flush AnkiConnect's deck cache. Rarely needed.
      - `sentence_audio_url` (when set) downloads the sentence audio from that
        URL instead of TTS. Only meaningful when a sentence is requested.

    Raises ValueError if neither a complete V nor a complete S is specified.
    """
    want_v = bool(expression) and bool(meaning)
    want_s = bool(sentence) and bool(reading_sentence)
    if not want_v and not want_s:
        raise ValueError(
            "add_cards needs at least one complete card: a V (expression+meaning) "
            "or an S (sentence+reading_sentence)."
        )
    if sentence_audio_url and not want_s:
        raise ValueError("sentence_audio_url given but no sentence card requested.")

    shape = "V+S" if (want_v and want_s) else ("V" if want_v else "S")
    iknow_id = next_iknow_id(i_know_id)
    print(f"[id] using iKnowID={iknow_id} (shape={shape})")

    if ensure_deck_first:
        print(f"[deck] ensure_deck({DECK!r})")
        ensure_deck()

    # 1. Audio — vocab is always TTS; sentence is downloaded when a URL is
    #    supplied, otherwise TTS-generated. Only the requested sides run.
    vocab_mp3 = TTS_OUT_DIR / f"iknow-{iknow_id}-vocab.mp3"
    sent_mp3 = TTS_OUT_DIR / f"iknow-{iknow_id}-sentence.mp3"
    if want_v:
        assert expression is not None
        print("[tts] generating vocab audio...")
        generate_audio(vocab_mp3, expression)
    if want_s:
        assert sentence is not None
        if sentence_audio_url:
            print(f"[audio] downloading sentence audio from {sentence_audio_url}")
            download_audio(sentence_audio_url, sent_mp3)
        else:
            print("[tts] generating sentence audio...")
            generate_audio(sent_mp3, sentence)

    # 2. Image (shared by both notes)
    image_media: Optional[str] = None
    if skip_image or not image_query:
        print("[image] skipped (no image query or --no-image)")
    else:
        img_path = find_image(image_query)
        if img_path is not None:
            print(f"[image] importing {img_path}")
            image_media = store_media(f"iknow-{iknow_id}-image.png", img_path)
        else:
            print(f"[image] no image for {image_query!r}; cards will have no image")

    # 3. Audio media
    print("[media] importing audio...")
    if want_v:
        store_media(f"iknow-{iknow_id}-vocab.mp3", vocab_mp3)
    if want_s:
        store_media(f"iknow-{iknow_id}-sentence.mp3", sent_mp3)

    # 4. Notes
    print("[notes] adding cards...")
    v_id: Optional[int] = None
    s_id: Optional[int] = None
    if want_v:
        assert expression is not None and meaning is not None
        v_id = add_note(build_vocab_note(iknow_id, expression, meaning, image_media))
    if want_s:
        assert sentence is not None and reading_sentence is not None
        s_id = add_note(build_sentence_note(iknow_id, sentence, reading_sentence, image_media))
    print(f"[notes] vocab id={v_id}, sentence id={s_id}")

    # 5. Sync
    if sync_after:
        print("[sync] syncing Anki...")
        sync()

    return {
        "iKnowID": iknow_id,
        "vocab_note_id": v_id,
        "sentence_note_id": s_id,
        "image_media": image_media,
    }


# Backward-compatible thin wrappers over add_cards(). Existing callers and the
# documented `add_card_pair()` entry keep working unchanged.
def add_card_pair(
    expression: str,
    meaning: str,
    sentence: str,
    reading_sentence: str,
    image_query: str,
    i_know_id: Optional[int] = None,
    skip_image: bool = False,
    ensure_deck_first: bool = False,
    sync_after: bool = True,
    sentence_audio_url: Optional[str] = None,
) -> dict:
    """Add a V + S card pair. Thin wrapper over `add_cards()`."""
    return add_cards(
        expression=expression, meaning=meaning,
        sentence=sentence, reading_sentence=reading_sentence,
        image_query=image_query, i_know_id=i_know_id, skip_image=skip_image,
        ensure_deck_first=ensure_deck_first, sync_after=sync_after,
        sentence_audio_url=sentence_audio_url,
    )


def add_vocab_only(
    expression: str,
    meaning: str,
    image_query: Optional[str] = None,
    i_know_id: Optional[int] = None,
    skip_image: bool = False,
    ensure_deck_first: bool = False,
    sync_after: bool = True,
) -> dict:
    """Add a Vocabulary (V) card only. Thin wrapper over `add_cards()`."""
    return add_cards(
        expression=expression, meaning=meaning, image_query=image_query,
        i_know_id=i_know_id, skip_image=skip_image,
        ensure_deck_first=ensure_deck_first, sync_after=sync_after,
    )


def add_sentence_only(
    sentence: str,
    reading_sentence: str,
    image_query: Optional[str] = None,
    i_know_id: Optional[int] = None,
    skip_image: bool = False,
    ensure_deck_first: bool = False,
    sync_after: bool = True,
    sentence_audio_url: Optional[str] = None,
) -> dict:
    """Add a Sentence (S) card only. Thin wrapper over `add_cards()`."""
    return add_cards(
        sentence=sentence, reading_sentence=reading_sentence,
        image_query=image_query, i_know_id=i_know_id, skip_image=skip_image,
        ensure_deck_first=ensure_deck_first, sync_after=sync_after,
        sentence_audio_url=sentence_audio_url,
    )
