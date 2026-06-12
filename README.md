# daily-japanese-anki

A [Claude Code Agent Skill](https://docs.claude.com/en/docs/claude-code/skills) that adds **Vocab + Sentence (V+S)** iKnow!-style flashcard pairs to a single `Daily Japanese` Anki deck via [AnkiConnect](https://foosoft.net/projects/anki-connect/) — with auto-generated reading (kanji → hiragana), Japanese TTS audio, and a best-effort illustration.

Each entry becomes **one Vocabulary card + one Sentence card** sharing a single `iKnowID`. See [`SKILL.md`](SKILL.md) for the full field schema and pipeline, and [`docs/usage.zh.md`](docs/usage.zh.md) for a Chinese walkthrough.

## Requirements

| Dependency | Why | Notes |
|---|---|---|
| [Anki](https://apps.ankiweb.net/) + [AnkiConnect](https://ankiweb.net/shared/info/2055492159) | card/media storage | must be running, port `8765` |
| Python 3.9+ | scripts | a venv is created by `install.sh` |
| `edge-tts`, `pykakasi`, `beautifulsoup4`, `requests` | TTS / reading / image search | see `requirements.txt` |

## Install

```bash
git clone https://github.com/<you>/daily-japanese-anki.git \
  ~/.agents/skills/daily-japanese-anki
cd ~/.agents/skills/daily-japanese-anki
./install.sh
```

`install.sh` creates a venv at `~/.venvs/edge-tts` (override with `EDGE_TTS_VENV=/path ./install.sh`), installs the Python deps, and checks that AnkiConnect is reachable.

Claude Code auto-discovers any skill folder under `~/.agents/skills/` or `~/.claude/skills/`, so once cloned the skill is available — just make sure Anki is open.

## Usage

```bash
python3 scripts/daily_japanese_add.py \
  --expression "やわらげる" \
  --meaning "激しい感情を穏やかにする" \
  --sentence "僕は奥さんの怒りを和らげた。" \
  --reading-sentence "ぼく は おくさん の いかり を やわらげた。" \
  --image-query "couple argument"
```

Useful flags: `--no-image` (skip illustration), `--ensure-deck` (create `Daily Japanese` on a fresh Anki install). Run `--help` for the full list.

> **One-deck policy:** all cards go into the existing `Daily Japanese` deck only. The skill never creates other decks.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `EDGE_TTS_VENV` | `~/.venvs/edge-tts` | venv used by the shell helpers |
| `ANKI_URL` | `http://localhost:8765` | AnkiConnect endpoint |
| `TTS_OUT_DIR` | `~/tts-output` | TTS scratch dir |
| `IMG_OUT_DIR` | `~/image-search-results` | image scratch dir |

## License

[MIT](LICENSE)
