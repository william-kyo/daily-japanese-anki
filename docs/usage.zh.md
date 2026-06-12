# daily-japanese-anki Skill 使用文档

## 这是什么

`daily-japanese-anki` 是 opencode 的一个 skill，用于通过 AnkiConnect REST API 把日语单词和例句批量加入你的 Anki 卡片库，专门服务于 **iKnow! V+S 配对卡片**（Vocab 词卡 + Sentence 句卡共用同一个 iKnowID，自动配 TTS 音频、可选配图片）。

所有卡片**只能**进入 `Daily Japanese` 这一个 deck —— 这是硬性 deck 政策。

## 目录位置

```
~/.agents/skills/daily-japanese-anki/   # skill 本体（脚本也在这里）
├── SKILL.md
├── scripts/
│   ├── anki_vocab_lib.py      # 核心库
│   ├── daily_japanese_add.py  # CLI 入口
│   ├── tts-ja.sh              # Edge TTS 日语语音合成
│   └── image-search-download.sh  # 多源图片搜索（commons/irasutoya/...）
├── templates/                 # note payload 模板
├── references/                # 故障排查
└── docs/                      # 中文使用文档
```

## 前置条件

1. **Anki 在本地运行**（装了 AnkiConnect 插件，监听 `http://localhost:8765`）
2. **Anki 里已经创建了 `iKnow! Vocabulary` 和 `iKnow! Sentences` 两个 note type**（如果没装，CLI 提供 `--ensure-deck` 自动建）
3. **Anki 里已经创建了 `Daily Japanese` 这个 deck**
4. **Python 3.10+**，且 `~/.venvs/edge-tts/bin/python` 这个 venv 里已经装了 `beautifulsoup4` 和 `requests`（初始化时已装好）
5. **Edge TTS 已安装** 在 `~/.venvs/edge-tts/bin/edge-tts`（已装好）

如果以上都满足，skill 可以直接用。

## 触发方式

opencode skill 是**语义触发**的 —— 你用自然语言说出相关意图，opencode 会自动加载这个 skill。常用的触发句式：

- "帮我把这个词加到 Anki 卡片里：やわらげる"
- "把'折り返し'做一个 V+S 配对卡片"
- "运行 daily japanese 卡片添加流程"
- "给这个日语单词生成 TTS 和图片并加入 Anki"

也会在以下场景自动触发：
- 用户提到日语单词想做成 Anki 卡片
- 用户想管理 `Daily Japanese` deck
- 用户想跑 iKnow! V+S 配对流水线

**不会**触发的场景（防止误触发）：
- 非日语内容
- 其他 deck（`Business Japanese`、`Japanese::N2` 等都不行）
- 只想要 TTS 文件、不进 Anki
- 通用 Anki 操作（这些走 opencode 自带的 `anki-mcp_*` 工具）

## 三种使用方式

### 方式 1：直接调 CLI（最常见）

```bash
python3 ~/.agents/skills/daily-japanese-anki/scripts/daily_japanese_add.py \
  --expression "やわらげる" \
  --meaning "激しい感情を穏やかにする" \
  --sentence "僕は奥さんの怒りを和らげた。" \
  --reading-sentence "ぼく は おくさん の いかり を やわらげた。" \
  --image-query "couple argument"
```

**参数说明：**

| 参数 | 必填 | 说明 |
|---|---|---|
| `--expression` | ✓ | 单词/短语（Japanese） |
| `--meaning` | ✓ | 简单日语解释，N3 难度以内 |
| `--sentence` | ✓ | 例句（Japanese） |
| `--reading-sentence` | ✓ | 例句的假名读音，词与词之间用空格分隔 |
| `--image-query` | 条件必填 | 配图搜索关键词；和 `--no-image` 二选一 |
| `--iKnowID` | ✗ | 显式指定 iKnowID（默认从 state 文件读下一个） |
| `--no-image` | ✗ | 跳过图片搜索，纯文字卡 |
| `--no-sync` | ✗ | 跑完不立即 sync（批量跑最后再 sync 一次） |
| `--ensure-deck` | ✗ | 首次安装时用：`createDeck` + `getDeckConfig` 探测 |

### 方式 2：作为 Python 库调用

适合批量导入、自动化脚本、测试：

```python
import sys
sys.path.insert(0, "/Users/kyo/.agents/skills/daily-japanese-anki/scripts")
import anki_vocab_lib as lib

result = lib.add_card_pair(
    expression="やわらげる",
    meaning="激しい感情を穏やかにする",
    sentence="僕は奥さんの怒りを和らげた。",
    reading_sentence="ぼく は おくさん の いかり を やわらげた。",
    image_query="couple argument",
    # skip_image=False,         # True 跳过图片
    # ensure_deck_first=False,  # True 在全新 Anki 安装时用
    # sync_after=True,          # False 用于批量场景
)

print(result)
# → {"iKnowID": 8, "vocab_note_id": 1780..., "sentence_note_id": 1780..., "image_media": "iknow-8-image.png"}
```

库导出的函数：
- `add_card_pair(...)` — 端到端流水线（TTS + 图片 + 媒体 + 笔记 + sync + 状态）
- `find_image(query)` — 图片搜索（带 2 次失败 fallback）
- `generate_audio(out_path, text)` — TTS
- `store_media(filename, path)` — 导入媒体到 Anki
- `ensure_deck()` — 创建 `Daily Japanese` + 刷缓存
- `build_vocab_note(...)` / `build_sentence_note(...)` — 构造 note payload
- `read_state()` / `write_state(next_id)` — iKnowID 计数器

### 方式 3：直接 curl 调 AnkiConnect（绕过 skill 库）

适合调试或特殊场景。详见 `~/.agents/skills/daily-japanese-anki/SKILL.md` 末尾的 "Manual recipe" 章节。

## 一次完整运行的内部流程

调用 `add_card_pair()` 后会发生这些事（按顺序）：

1. **读 iKnowID**（如果没显式传）：实时查 Anki 里的 `iKnow!` 笔记字段，取最大 iKnowID + 1
2. **（可选）创建 deck**：如果传了 `ensure_deck_first=True`，先 `createDeck("Daily Japanese")` + `getDeckConfig` 探测刷缓存
3. **TTS 生成音频**：
   - 单词 → `~/tts-output/iknow-<id>-vocab.mp3`
   - 例句 → `~/tts-output/iknow-<id>-sentence.mp3`
   - 用 `tts-ja.sh`（Edge TTS，ja-JP-NanamiNeural 声音）
4. **搜索配图**（如果没传 `--no-image`）：
   - 按顺序试 `irasutoya → commons → pixabay → pexels`
   - **最多试 2 次**，2 次都失败就用纯文字卡（不卡流程）
   - 找到后下载到 `~/image-search-results/`
5. **导入媒体到 Anki**：
   - 图片（如有）→ `iknow-<id>-image.png`
   - 两个 mp3 → `iknow-<id>-vocab.mp3` / `iknow-<id>-sentence.mp3`
6. **创建两个 note**：
   - Vocabulary 卡（model: `iKnow! Vocabulary`）
   - Sentences 卡（model: `iKnow! Sentences`）
   - 共享同一个 iKnowID 和 tag
7. **（可选）sync**：如果没传 `--no-sync`，调一次 Anki sync
8. **写状态**：把 `nextIknowId` 增 1，更新 `lastUpdated`（Asia/Tokyo 日期）

## 关键字段映射

每张 Vocabulary 卡的字段：

| 字段 | 值 |
|---|---|
| `Expression` | 你传的 `--expression` |
| `Meaning` | 你传的 `--meaning` |
| `Reading` | 自动转换的平假名（汉字/片假名 → 平假名，用 pykakasi） |
| `Audio` | `[sound:iknow-<id>-vocab.mp3]` |
| `Image_URI` | `<img src="iknow-<id>-image.png">` 或空字符串 |
| `iKnowID` | 这次分配的整数（实时从 Anki 查 max+1，也是 tag） |
| `iKnowType` | `V` |

每张 Sentences 卡的字段：

| 字段 | 值 |
|---|---|
| `Expression` | 你传的 `--sentence` |
| `Meaning` | 空（iKnow! Sentences 不需要） |
| `Reading` | 你传的 `--reading-sentence` |
| `Audio` | `[sound:iknow-<id>-sentence.mp3]` |
| `Image_URI` | 和 Vocabulary 共享同一张图（不重新抓） |
| `iKnowID` | 同上 |
| `iKnowType` | `S` |

## 常见操作示例

### 1. 全新 Anki 安装后第一次跑

```bash
python3 ~/.agents/skills/daily-japanese-anki/scripts/daily_japanese_add.py \
  --expression "やわらげる" \
  --meaning "激しい感情を穏やかにする" \
  --sentence "僕は奥さんの怒りを和らげた。" \
  --reading-sentence "ぼく は おくさん の いかり を やわらげた。" \
  --image-query "couple argument" \
  --ensure-deck
```

`--ensure-deck` 会确保 `Daily Japanese` 存在并刷新 AnkiConnect 缓存。

### 2. 没有合适配图的词（用 `--no-image`）

```bash
python3 ~/.agents/skills/daily-japanese-anki/scripts/daily_japanese_add.py \
  --expression "折り返し" \
  --meaning "電話などで、かけ直すこと。" \
  --sentence "鈴木は、ただいま席を外しておりますので、戻り次第、折り返しご連絡いたします。" \
  --reading-sentence "すずきは、ただいませきを はずしておりますので、もどりしだい、おりかえし ご連絡 いたします。" \
  --no-image
```

走纯文字 + 音频路线，节省 5 秒左右的图片搜索。

### 3. 批量导入 10 个词

写个 shell 循环：

```bash
#!/bin/bash
set -e
CLI=~/.agents/skills/daily-japanese-anki/scripts/daily_japanese_add.py

python3 "$CLI" --expression "単語1" --meaning "..." --sentence "..." --reading-sentence "..." --no-image --no-sync
python3 "$CLI" --expression "単語2" --meaning "..." --sentence "..." --reading-sentence "..." --no-image --no-sync
# ... 共 10 个
# 全部跑完后再 sync 一次
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' \
  --data '{"action":"sync","version":6}'
```

`--no-sync` 是关键：避免每次都触发 Anki 同步。

### 4. 修改某张已存在卡的图片

skill 不会自动 backfill 已有卡片。要补图片/音频：

```bash
# 1. 上传新图片
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' --data '{
  "action":"storeMediaFile","version":6,
  "params":{"filename":"iknow-8-image.png","data":"<base64>"}}
'

# 2. 找到 note id
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' \
  --data '{"action":"findNotes","version":6,"params":{"query":"tag:8"}}'

# 3. 改 Image_URI 字段
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' --data '{
  "action":"updateNoteFields","version":6,
  "params":{"note":{"id":<note_id>,"fields":{"Image_URI":"<img src=\"iknow-8-image.png\">"}}}}
'
```

## 验证卡片是否真的写进去了

`addNote` 之后立刻 `findNotes` 可能返回 `[]`（query engine 对含空格的 deck 名有延迟）。**用 expression 文本或 tag 查**：

```bash
# 用表达式文本
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' \
  --data '{"action":"findNotes","version":6,"params":{"query":"\"やわらげる\""}}'

# 用 iKnowID tag
curl -sS -X POST http://127.0.0.1:8765 -H 'Content-Type: application/json' \
  --data '{"action":"findNotes","version":6,"params":{"query":"tag:8"}}'
```

应该返回 2 个 id：第一个是 Vocabulary，第二个是 Sentence。

## 常见坑（必读）

完整 14 条 pitfalls 见 `~/.agents/skills/daily-japanese-anki/SKILL.md`，这里挑 5 个最常踩的：

1. **找不到 deck 报错** `deck was not found`：第一次跑要加 `--ensure-deck`
2. **`addNotes` 批量接口返回 `null` 不代表失败** —— 那是 AnkiConnect 的 bug，null + 错误列表为空 = 成功；别重试
3. **图片扩展名要统一** —— 上传用 `.png`，`Image_URI` 里也写 `.png`，否则显示破图
4. **Audio 字段是 `[sound:...]` 不是 `<audio>`** —— iKnow! 模板的语法
5. **图片搜索 2 次失败就放弃** —— irasutoya 是 JS 渲染的、pixabay/pexels 经常 403，纯文字卡也是合法卡

## 故障排查

如果出问题，先翻 `~/.agents/skills/daily-japanese-anki/references/troubleshooting.md` —— 里面按症状分类写了 8 个具体 case 的复现和修法（irasutoya atom feed 手动方案、commons 抓取失败、ffmpeg 缩图、`addNotes` null、permission 拦截等等）。

## 配置文件位置

| 用途 | 路径 |
|---|---|
| skill 本体 | `~/.agents/skills/daily-japanese-anki/` |
| TTS / 图片脚本 | `~/.agents/skills/daily-japanese-anki/scripts/` |
| iKnowID 计数器 | （已删除）实时从 Anki 查最大 iKnowID + 1 |
| Edge TTS venv | `~/.venvs/edge-tts/` |

**环境变量覆盖：**
- `DAILY_JP_WORKSPACE` — 覆盖 workspace 根目录
- `ANKI_URL` — 覆盖 AnkiConnect 端点（默认 `http://localhost:8765`）
- `PYTHON_BIN` — 覆盖 image-search-download.sh 里用的 python（默认 `~/.venvs/edge-tts/bin/python`）

## 何时不要用这个 skill

- 你的卡片不是日语
- 你想加到非 `Daily Japanese` 的 deck（不允许）
- 你只想生成 TTS 文件不导入 Anki
- 你想做通用 Anki 操作（增删改查非 iKnow! 模型的卡片）—— 这种用 opencode 自带的 `anki-mcp_*` 工具更合适
