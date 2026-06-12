# Troubleshooting — AnkiConnect + Daily Japanese workflow

## Symptom: `addNote` fails with `deck was not found: iKnow! Vocabulary`

**Cause:** `iKnow! Vocabulary` and `iKnow! Sentences` are user-created decks (not built-in defaults). They only exist if `createDeck` was previously called for them.

**Fix:** Call `createDeck` for each missing deck before `addNote`. The call is idempotent — re-running it on an existing deck returns the existing deck ID with no error:

```bash
for d in "iKnow! Vocabulary" "iKnow! Sentences"; do
  curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' \
    --data "{\"action\":\"createDeck\",\"version\":6,\"params\":{\"deck\":\"$d\"}}"
done
```

In the CLI use `--ensure-deck`.

---

## Symptom: `image-search-download.sh -s irasutoya` produces only banner images

**Cause:** irasutoya's `/search?q=` results page renders the result grid client-side with JavaScript. Plain `curl` cannot extract the actual illustrations.

**Workaround:** Use commons as the primary image source. Commons gives you a real image URL via `-d`:

```bash
bash image-search-download.sh -s commons -q "stressed employee office" -d
# → ~/image-search-results/commons-stressed_employee_office-<ts>.jpg
```

---

## Symptom: `image-search-download.sh -s commons -q "..." -d` saves HTML but downloads no image (rc=1, no new file)

**Cause:** Wikimedia's MediaSearch results page no longer puts File: links in `<a href>` elements the script's selector matches. The script bails with rc=1.

**Manual recovery:**

1. Open the saved HTML and grep for candidate file pages:
   ```bash
   grep -oE 'commons\.wikimedia\.org/wiki/File:[^"]+\.jpg' \
     ~/image-search-results/commons-<query>-<ts>.html | head -5
   ```
2. Pick a File: page URL, fetch it:
   ```bash
   curl -L --silent -A 'Mozilla/5.0' \
     "https://commons.wikimedia.org/wiki/File:<title>.jpg" -o /tmp/argpage.html
   ```
3. Extract the full-res image URL (NOT the `/thumb/.../500px-...` variant):
   ```bash
   grep -oE 'https://upload\.wikimedia\.org/wikipedia/commons/[a-f0-9]/[a-f0-9]{2}/[^"]+\.jpg' \
     /tmp/argpage.html | sort -u | head -3
   ```
4. Download directly, then resize with `ffmpeg` (works without Pillow):
   ```bash
   curl -L --fail -A 'Mozilla/5.0' "<full-url>.jpg" -o iknow-<id>-image-source.jpg
   ffmpeg -y -i iknow-<id>-image-source.jpg -vf "scale=800:-1" -q:v 4 \
     iknow-<id>-image-resized.jpg
   ```

---

## Symptom: `find_image()` returns a "successful" path that is actually an old file from a previous run

**Cause:** The naive implementation picked the most recently modified image file in `~/image-search-results/`. If the script returned no new file but the directory already had an old image, the old file would silently win.

**Fix (already applied in `anki_vocab_lib.py:_try_one_image_source`):**
- Snapshot `time.time()` *before* the subprocess starts.
- After the subprocess returns, only consider files with `mtime >= pre_mtime - 0.5`.
- A run that produces no new file is now an honest "no image".

---

## Symptom: Anki `storeMediaFile` saves the image but the card shows a broken image icon

**Cause:** The filename passed to `storeMediaFile` and the `src=` in `Image_URI` use different extensions (e.g. saved as `.png`, referenced as `.jpg`).

**Fix:** Pick one extension (the recipe uses `.png`) and use it in BOTH places.

---

## Symptom: Audio doesn't play on the card

**Cause:** Used `<audio src="...">` instead of `[sound:...]` in the Audio field.

**Fix:** iKnow! models use Anki's `[sound:filename.mp3]` reference syntax. Brackets, not angle brackets.

---

## Symptom: State file increments but iKnowID is missing from notes

**Cause:** Forgot to write the same iKnowID into BOTH the vocab and sentence note's `iKnowID` field, and as the `tags` array element.

**Fix:** Always derive both notes from a single `iknow_id` variable; never type it twice.

---

## Symptom: When you need an irasutoya illustration and the helper script can't get one

**Manual workaround (~3 minutes, beats the helper):** Use the Blogger atom feed that backs `irasutoya.com`. Plain Atom XML, no JS, no anti-bot.

1. **Page through the feed** (150-post chunks via `start-index`):
   ```bash
   mkdir -p /tmp/ir
   for start in 1 151 301 451 601 751 901 1051 1201 1351 1501 1651 1801; do
     curl -sS -A "Mozilla/5.0" \
       "https://www.irasutoya.com/feeds/posts/default?alt=atom&max-results=150&start-index=$start" \
       -o /tmp/ir/feed_${start}.xml
     [ "$(wc -c < /tmp/ir/feed_${start}.xml)" -lt 1000 ] && break
   done
   ```

2. **Filter titles locally** (the feed's `?q=` is broken):
   ```python
   import re, glob
   for f in sorted(glob.glob('/tmp/ir/feed_*.xml')):
       for t in re.findall(r"<title type='text'>(.*?)</title>", open(f).read(), re.S):
           if any(k in t for k in ["電話","内線","取り次","受付"]):
               print(t.strip()[:80])
   ```

3. **Map title → URL** and **extract `<img>` from post page** with a targeted `grep -oE`.

4. **Bump `s450` → `s800`** in the Blogger URL segment for a larger version.

5. **Vision-verify** the illustration matches the concept before committing.

---

## Symptom: `addNotes` returns `{"result": null, "error": null}` and you think it failed

**Cause:** AnkiConnect's `addNotes` (plural) has a known bug where it returns `null` instead of the array of new note IDs on success.

**Fix:** Treat `{"result": null, "error": null}` as SUCCESS when the error list is empty. Verify with a content-based `findNotes` query (e.g. `"\"<expression>\""` or `"tag:<id>"`). **Do not retry** — the second attempt will fail with `cannot create note because it is a duplicate`.

---

## Symptom: `findNotes` with `deck:Daily Japanese` returns `[]` immediately after `addNote`

**Cause:** Query-engine quirk with deck names containing spaces, not a missing note.

**Fix:** Search the expression text or the shared tag instead — both are reliable:
```bash
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' \
  --data '{"action":"findNotes","version":6,"params":{"query":"\"やわらげる\""}}'
# → [<vocab_id>, <sentence_id>]
```

---

## Manual recipe (any case the CLI doesn't cover)

The CLI (`daily_japanese_add.py`) covers the standard V+S pair. For unusual flows
(custom field shapes, debugging, ad-hoc fixes), drop down to the AnkiConnect API
directly. All notes must still target `Daily Japanese`.

### 1. Confirm the model exists

```bash
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' \
  --data '{"action":"modelNames","version":6}'
# → look for "iKnow! Vocabulary" and "iKnow! Sentences"
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' \
  --data '{"action":"modelFieldNames","version":6,"params":{"modelName":"iKnow! Vocabulary"}}'
# → ["Expression","Meaning","Reading","Audio","Image_URI","iKnowID","iKnowType"]
```

### 2. Locate the Anki media directory

```bash
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' \
  --data '{"action":"getMediaDirPath","version":6}'
```

### 3. Generate TTS

```bash
TTS=$HOME/.agents/skills/daily-japanese-anki/scripts/tts-ja.sh
$TTS -o /tmp/audio_voc.mp3  "やわらげる"
$TTS -o /tmp/audio_sent.mp3 "ぼく は おくさん の いかり を やわらげた。"
```

### 4. Copy media into the Anki media directory

Use the `iknow-<id>-{vocab,sentence}.mp3` naming convention. If `Daily Japanese` is
missing, call `createDeck` first followed by a `getDeckConfig` probe.

### 5. addNote twice (V + S), then sync once

`Audio` = `[sound:filename.mp3]`. `Image_URI` = `<img src="filename.png">` (or `""` if
no image). `iKnowType` = `V` / `S`. `iKnowID` is the integer resolved from Anki. Tags
include the iKnowID as a string for easy filtering.

```bash
IKNOWID=8
AUDIO_VOC="iknow-${IKNOWID}-vocab.mp3"
AUDIO_SENT="iknow-${IKNOWID}-sentence.mp3"

curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' --data "{
  \"action\":\"addNote\",\"version\":6,
  \"params\":{\"note\":{
    \"deckName\":\"Daily Japanese\",\"modelName\":\"iKnow! Vocabulary\",
    \"fields\":{
      \"Expression\":\"やわらげる\",
      \"Meaning\":\"激しい感情を穏やかにする\",
      \"Reading\":\"やわらげる\",
      \"Audio\":\"[sound:${AUDIO_VOC}]\",
      \"Image_URI\":\"\",
      \"iKnowID\":\"${IKNOWID}\",
      \"iKnowType\":\"V\"},
    \"tags\":[\"${IKNOWID}\"]}}}
"

curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' --data "{
  \"action\":\"addNote\",\"version\":6,
  \"params\":{\"note\":{
    \"deckName\":\"Daily Japanese\",\"modelName\":\"iKnow! Sentences\",
    \"fields\":{
      \"Expression\":\"僕は奥さんの怒りを和らげた。\",
      \"Meaning\":\"\",
      \"Reading\":\"ぼく は おくさん の いかり を やわらげた。\",
      \"Audio\":\"[sound:${AUDIO_SENT}]\",
      \"Image_URI\":\"\",
      \"iKnowID\":\"${IKNOWID}\",
      \"iKnowType\":\"S\"},
    \"tags\":[\"${IKNOWID}\"]}}}
"

curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' \
  --data '{"action":"sync","version":6}'
# → {"result":null,"error":null} means success; AnkiConnect returns no positive ack.
```

### 6. Verify with `findNotes` on expression text (NOT `deck:`)

Search the expression text or the shared tag instead — `deck:` queries can return `[]`
immediately after a new `addNote`:

```bash
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' \
  --data '{"action":"findNotes","version":6,"params":{"query":"\"やわらげる\""}}'
# → [<vocab_id>, <sentence_id>]

# Or by tag — works regardless of deck-name spacing
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' \
  --data '{"action":"findNotes","version":6,"params":{"query":"tag:8"}}'
```

---

## Minimal recipe (text-only fallback, no TTS / no image)

```bash
# 1. Ensure Daily Japanese exists (idempotent + probe) — skip if deck is already present
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' \
  --data '{"action":"createDeck","version":6,"params":{"deck":"Daily Japanese"}}'
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' \
  --data '{"action":"getDeckConfig","version":6,"params":{"deck":"Daily Japanese"}}'

# 2. addNote once for the vocab
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' --data '{
  "action":"addNote","version":6,
  "params":{"note":{
    "deckName":"Daily Japanese","modelName":"iKnow! Vocabulary",
    "fields":{"Expression":"取り次ぎ","Meaning":"電話や来客を、担当の人に渡すこと","Reading":"とりつぎ"},
    "tags":["toritsugi"],
    "options":{"allowDuplicate":false}}}}'
```

For multiple notes at once, use `addNotes` (plural) — but expect `{"result": null, "error": null}` even on success.

---

## AnkiConnect quick reference (JSON-RPC v6, http://localhost:8765)

```python
def anki(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request("http://localhost:8765", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

# Common actions
anki("deckNames")
anki("modelNames")
anki("modelFieldNames", modelName="iKnow! Vocabulary")
anki("findNotes", query='"deck:Daily Japanese" iKnowID:3')
anki("addNote", note={...})
anki("updateNoteFields", id=..., fields={...})
anki("deleteNotes", notes=[...])
anki("storeMediaFile", filename="...", data="<base64>")
anki("sync")
```
