# OCR — dots.ocr / dots.mocr for macOS

A minimal Mac-friendly version of the official [dots.ocr / dots.mocr](https://github.com/rednote-hilab/dots.mocr)
pipeline. Only the **PDF → image rendering, prompt construction, JSON / Markdown / layout-image post-processing** parts
are kept; the local HuggingFace inference path has been removed and replaced with a thin
OpenAI-compatible HTTP client.

The official `dots_mocr/parser.py` is reused almost verbatim — the inference call site
points at this fork's `inference_with_vllm()` which now talks to any `/v1/chat/completions`
endpoint (LM Studio by default).

On top of that parser, this repo ships a small toolchain: split a PDF into page images,
preprocess handwriting so it reads better, and merge everything into one clean Markdown file.

**No hardcoded paths anywhere.** Every location comes from `__file__`, an environment
variable, or a CLI argument, so the repo works wherever you clone it.

---

## 中文速查

**最省事的办法:交互式面板(常驻)。** 一屏显示所有当前设置,用斜杠命令改任意一项。
面板不会自己退出 —— 你可以把文件一个个拖进终端窗口,它就一个个转,全部弄完再关掉。

```bash
# 装好之后
ocr-shell                 # 交互面板
# 或者不装,直接跑
./ocr/bin/ocr             # 启动器(自带找解释器的逻辑)
python3 scripts/ocr_shell.py
```

**流水线用法:**

1. 先设一次输出目录:`/output` → 选「手动输入路径」

   (不设也行 —— 第一次拖进去时面板会问「输出到哪儿」,选一次就固定了)

2. 把文件**拖进终端窗口**,路径会出现在提示符上,回车
3. 面板自动开始转,跑完回到面板,输出目录和设置都还在
4. 再拖下一个,继续
5. 全部弄完,`/quit` 退出

想双击运行:Finder 里双击 `bin/OCR交互式外壳.command`。

常用命令:

```
/input      设置输入(手输路径 / 浏览目录 / 整个文件夹)
/output     设置输出目录(可设成「每次都问」)
/set        设置页(分组菜单:DPI、预处理、提示模式、服务器……)
/preset     预设(手写笔记 / 印刷文档 / 快速 / 高精度,也能存自己的)
/task       切换任务
/run        执行
/print-argv 只打印将要执行的命令,不真的跑
/save       立即保存设置        /reload  丢弃改动重新载入
/history    命令历史            /help    全部命令
```

命令可以省略 `/`(写 `run` 等价于 `/run`);空回车只是重画面板;
`↑`/`↓` 翻历史,`Ctrl-R` 反向搜索;主提示符上按 `Ctrl-C` 直接退出(设置会保存),
子提示里按 `Ctrl-C` 只取消当前操作,`Ctrl-D` 也能退出。

**设置会被记住**:退出时自动存到 `~/.config/ocr/session.json`(纯 JSON,可自己编辑),
下次打开自动恢复。想每次都用全新默认值就加 `--no-session`。

---

三步装好,然后就能把手写照片 / 扫描 PDF 转成 Markdown:

```bash
# 1. 建 venv 并装依赖(在 ocr/ 目录下)
cd ocr
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 在 LM Studio 里加载 dots.mocr 模型,启动本地服务(默认 127.0.0.1:1234,
#    Context Length 至少调到 32768)

# 3. 转换
python scripts/note_to_markdown.py 我的笔记.jpg -o 输出目录/
```

也可以一步装成命令行工具(推荐):

```bash
pip install -e .
ocr-note-to-markdown 我的笔记.jpg -o 输出目录/
```

想直接双击运行(Finder 里把图片/PDF 拖到图标上),用 `bin/手写笔记转Markdown.command`。
输出目录默认是当前目录下的 `note_md/`,也可以用 `$OCR_OUTPUT_DIR` 改。

常用环境变量:`OCR_HOST`、`OCR_PORT`、`OCR_MODEL`、`OCR_DPI`、`OCR_OUTPUT_DIR`,
完整表格见下面的 [Environment variables](#environment-variables)。

---

## The tool chain

```
┌───────────────┐  pdf_to_images.py   ┌────────────┐   OpenAI SDK   ┌──────────────┐
│  PDF / image  │ ──────────────────▶ │ PIL image  │ ─────────────▶ │  LM Studio   │
└───────────────┘   (PyMuPDF, per page)│  per page  │   base64 img   │ (your model) │
        │                              └────────────┘ ◀────────────── └──────────────┘
        │                                        layout JSON
        │                                              │
        ▼                                              ▼
 note_to_markdown.py                        JSON + .md + layout.jpg
 (handwriting preprocess)                          │
        │  deskew → autocontrast → binarize → trim  │
        └───────────────▶ merged .md + .jsonl ◀─────┘
```

`note_to_markdown.py` is the single entry point for the common case; the other two
pieces are usable independently.

### Why the preprocessing step matters

Handwriting is the hard case, and this is where recognition usually wins or loses:

1. **deskew** — a phone photo of paper is almost never straight, and a tilt breaks
   line detection and reading order.
2. **autocontrast** — flattens the uneven lighting and shadows from photographing
   a page.
3. **binarize** (optional) — the vision tower was trained on rendered/printed
   documents; thresholding handwritten strokes pulls the input closer to that
   distribution. See `--preprocess`.
4. **trim** — crops the surrounding whitespace so real content fills the vision
   resolution budget.

Resolution: the defaults (`--dpi 150`, `--scale 1.0`, `--max-side 1600`) keep a
page under ~2 megapixels, which is the vision tower's comfort zone (~2000²).
Going higher only burns tokens and time. For small text, raise `--dpi` or
`--max-side` rather than `--scale`.

---

## Install

```bash
# Option A — venv (no conda needed, ~30 seconds on Apple Silicon)
git clone https://github.com/chenhaiwen/ai.git
cd ai/ocr
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
# Option B — install as a package, which also gives you the console commands
cd ai/ocr
python3 -m venv .venv
source .venv/bin/activate
pip install -e .          # then: ocr-note-to-markdown, ocr-pdf-to-images, ...
```

```bash
# Option C — conda (recommended if PyMuPDF has trouble building)
conda create -n dots_ocr python=3.12
conda activate dots_ocr
conda install -c conda-forge pymupdf pillow tqdm pydantic numpy requests
pip install openai
```

> **No `torch` / `transformers` / `vllm` / `flash-attn` are required.**
> Those deps are what makes the upstream install slow on macOS; we don't need them.

### Console entry points

After `pip install -e .`:

| Command | Module | What it does |
|---|---|---|
| `ocr-shell` | `scripts.ocr_shell:main` | **interactive menu** — pick input, output and every parameter |
| `ocr-note-to-markdown` | `scripts.note_to_markdown:main` | handwriting photo/PDF → Markdown |
| `ocr-pdf-to-images` | `scripts.pdf_to_images:main` | PDF → per-page JPG |
| `ocr-check-imports` | `scripts.check_imports:main` | verify every `dots_mocr.*` imports |
| `ocr-smoke-test` | `scripts.smoke_test:main` | end-to-end check incl. model server |

### Running without installing

Every script self-bootstraps `sys.path` from `__file__`, so a plain clone works
with no install step at all:

```bash
python3 ocr/scripts/note_to_markdown.py note.jpg -o out/   # from the repo root
python3 scripts/note_to_markdown.py note.jpg -o out/       # from inside ocr/
```

---

## Interactive panel

`ocr-shell` is a **panel**, in the style of Claude Code: one screen shows every
current setting at once, and you change any of them with a slash command. No
endless chain of questions.

It is also a **persistent application** — it stays alive between jobs, so you
can keep dropping files into it, and your settings are remembered between
sessions.

```bash
ocr-shell                       # installed console script
./ocr/bin/ocr                   # launcher, works without installing
python3 ocr/scripts/ocr_shell.py # works from a plain clone
```

Or double-click `ocr/bin/OCR交互式外壳.command` in Finder.

### The pipeline: drop a file, it runs

Leave the panel open. Drag a file into the terminal window — the path lands at
the prompt — and hit enter. The panel treats it as *"run this file with my
current settings"*:

```
> /Users/me/Desktop/扫描文稿 2.pdf
[已设置] 输入 → /Users/me/Desktop/扫描文稿 2.pdf
[流水线] 立即执行这次转换。
[运行] 正在执行:
  ...
```

When it finishes you are back at the panel, output directory and all other
settings untouched, ready for the next file. Drop the next one in. When you're
done, `/quit` closes it.

The output directory is remembered too: set it once with `/output` and every
later file goes there without asking. On the very first run the panel asks
where to send the output — pick one and it sticks. To go back to being asked
every time, use `/output` → "每次都问(不定死目录)".

### The panel

```
╭──────────────────────────────────────────────────────────────╮
│  OCR 工具链 · 交互式面板                                     │
╰──────────────────────────────────────────────────────────────╯

  任务      note_to_markdown      手写笔记 / 图片 / PDF → Markdown
  输入      (未设置, /input 指定)
  输出      note_md
  ────────────────────────────────────────────────────────────

  DPI       150                         scale     1
  预处理    enhance                     max-side  1600
  纠偏      开                          裁白边    开
  中间图    不留
  ────────────────────────────────────────────────────────────

  服务      127.0.0.1:1234              模型      dots.mocr
  提示模式  prompt_layout_all_en        并发      1

  可用命令:
    /task        切换任务           /set         设置页(分组菜单)
    /input       设置输入           /preset      预设(内置 + 自定义)
    /output      设置输出目录       /run         执行当前配置
    /dpi         渲染分辨率         /print-argv  只打印命令不执行
    /quality     JPEG 质量          /save        立即保存会话到文件
    /start       起始页码           /reload      丢弃改动,重新载入会话
    /end         结束页码(0=到末页) /history     查看命令历史
    /preprocess  预处理强度         /reset       恢复默认
    /prompt      提示模式           /preflight   依赖 + 模型服务预检
    /deskew      自动纠偏开关       /config      查看环境变量与默认值
    /trim        裁白边开关         /help        命令帮助
    /staging     保留中间图开关     /quit        退出
    /scale       放大倍数

  最近命令:
    /dpi
    /run

  会话: ~/.config/ocr/session.json (已载入)
  提示: 命令可省略 `/`;直接拖入一个存在的路径 = 设输入并立即执行。

>
```

Type a command, hit enter, and the panel redraws with the new value:

```
> /dpi
PDF 渲染分辨率 --dpi [当前 150, 范围 1-1200]: 300
[已设置] DPI → 300
```

`↑` / `↓` recall previous commands (`Ctrl-R` does a reverse search).

### Commands

| Command | What it does |
|---|---|
| `/task` | switch the task — `note_to_markdown` / `pdf_to_images` / `parser` |
| `/input` | set the input: type a path, browse, pick a whole folder, or clear it |
| `/output` | set the output directory — fixed, or "ask me every time" |
| `/set` | **the settings screen** — grouped menu, see below |
| `/preset` | apply, save, or delete presets |
| `/dpi` `/quality` `/start` `/end` `/max-side` `/num-thread` | numeric, validated against a range |
| `/scale` | float, validated |
| `/preprocess` | numbered menu — `none` / `gray` / `enhance` / `binarize`, each explained |
| `/prompt` | numbered menu of the real modes read from `dots_mocr/utils/prompts.py` |
| `/deskew` `/trim` `/staging` `/gray` | y/n toggles |
| `/server` | host / port / model; the model list is auto-detected from the server's `/v1/models` |
| `/prefix` | output file prefix |
| `/run` | execute the current configuration (asks first) |
| `/print-argv` | print the command that *would* run, without running it |
| `/save` | save the session to disk now |
| `/reload` | discard changes and reload from the session file |
| `/history` | show the command history |
| `/reset` | reset everything to defaults |
| `/preflight` | dependency check + model server probe |
| `/config` | show the resolved environment variables and defaults |
| `/help` | command help |
| `/quit` | leave (`quit` / `exit` / Ctrl-D also work) |

Conventions:

- The leading `/` is optional — `run` and `/run` are the same.
- Typing a path that exists sets the input **and runs it** (the pipeline).
- An empty line just redraws the panel.
- `Ctrl-C` at the main prompt exits (settings are saved); inside a sub-prompt it
  cancels just that operation and returns to the panel.
- `Ctrl-D` exits as well.
- An unknown command prints the full command list.

### The settings screen

`/set` groups everything into one place, so you don't have to remember which
command sets what:

```
=== 设置 ===
  1. 输出与输入
  2. 图片质量(DPI / 缩放 / 最长边)
  3. 预处理
  4. 提示模式
  5. 模型服务
  6. 任务与页码
  7. 预设
  0. 返回
```

Each group opens a sub-menu showing that group's current values, and you pick
which one to change.

### Presets

A preset sets several settings at once. Four are built in:

| Preset | What it does |
|---|---|
| `handwriting` | binarize + 300 DPI + `prompt_ocr` — for messy handwriting |
| `document` | no preprocessing + 200 DPI + full layout — for printed scans |
| `fast` | gray + 120 DPI + `prompt_ocr` — a quick look, low resolution |
| `precise` | enhance + 400 DPI + full layout — slow but most accurate |

`/preset` applies one, saves the current settings as your own, deletes one, or
loads one from a JSON file. Applying a preset tells you exactly what changed:

```
[已套用] 预设 handwriting
[预设] 改了 4 项:
    preprocess   enhance → binarize
    dpi          150 → 300
    max_side     1600 → 2000
    prompt       prompt_layout_all_en → prompt_ocr
```

Your own presets live in the session file and survive restarts.

### Your settings are remembered

The panel saves its settings when it exits and loads them when it starts, so
it always comes up the way you left it.

| Where | Path |
|---|---|
| `$OCR_SESSION_FILE` | if set, used as-is |
| `$XDG_CONFIG_HOME/ocr/session.json` | if `XDG_CONFIG_HOME` is set |
| `~/.config/ocr/session.json` | otherwise |

The file is plain JSON — read it, edit it, copy it between machines:

```json
{
  "version": 1,
  "config": {
    "task": "note_to_markdown",
    "dpi": 300,
    "preprocess": "binarize",
    "prompt": "prompt_ocr",
    "host": "127.0.0.1",
    "port": 1234,
    "model": "dots.mocr"
  },
  "output_fixed": false,
  "presets": {},
  "history": ["/dpi", "/run"]
}
```

CLI flags:

| Flag | Effect |
|---|---|
| `--session PATH` | use a specific session file |
| `--no-session` | neither load nor save — fresh defaults every time |

A corrupt session file produces a warning and is ignored; it never crashes the
panel.

### Setting the input

`/input` offers four ways:

```
请选择设置输入的方式:
   1. 手动输入路径 (当前)
   2. 浏览目录挑选
   3. 就用一整个文件夹
   4. 清空输入
```

Browsing shows a numbered list of the images and PDFs in the current directory,
lets you descend into a subfolder, go back up with `..`, and pick a whole
folder as the input. Typed paths may be relative, absolute, `~`-prefixed, or
macOS shell-escaped (`扫描文稿\ 2.pdf`).

### Scriptable / non-interactive mode

The shell is also a plain command runner, so it is usable from CI and scripts:

```bash
# run a target directly, bypassing the panel
ocr-shell --exec note_to_markdown -- note.jpg -o out/
ocr-shell --exec pdf_to_images   -- doc.pdf -o imgs/
ocr-shell --exec parser          -- doc.pdf
ocr-shell --exec check_imports   --
ocr-shell --exec smoke_test      -- --check-only

# print the argv that *would* run, without running it
ocr-shell --exec note_to_markdown --dry-run -- note.jpg -o out/

# list the available prompt modes
ocr-shell --list-prompts
```

> `--dry-run` must come **before** the `--` separator. Anything after `--` is
> passed through to the target script untouched.

When **stdin is not a terminal** (piped, or running in CI) the shell refuses to
open the panel and exits with code **2** — this is deliberate, so a pipeline can
never hang waiting for input. Use `--exec` in that situation.

### Environment variables

| Variable | Effect |
|---|---|
| `OCR_SHELL_YES=1` | Skip the confirmation prompt and run straight away. |
| `OCR_SHELL_FORCE_TTY=1` | Treat stdin as interactive even when it is a pipe. Useful for testing the panel. |
| `OCR_SESSION_FILE` | Path to the session file. |
| `OCR_NO_SESSION=1` | Don't load or save a session file. |
| `OCR_SHELL_NO_CLEAR=1` | Don't clear the screen between redraws (also `--no-clear`). |

### Tests

`ocr/scripts/test_ocr_shell.py` drives the panel, the session persistence and
the non-interactive mode through a pipe, and asserts on the argv they produce.
It needs no model server:

```bash
python ocr/scripts/test_ocr_shell.py
```

---

In LM Studio:

1. Search & load **`dots.mocr`** (or **dots.ocr**) — quantized GGUF works on Apple Silicon.
2. Start the local server (Developer tab). It listens on `http://127.0.0.1:1234/v1`.
3. **Bump the context length** to at least 32768 (Settings → Context Length). dots.ocr
   generates long JSON outputs.
4. Note the exact model identifier LM Studio shows in the server log
   (e.g. `dots.mocr@q4_k_m` or whatever you've loaded).

If you're using Ollama instead of LM Studio, just point `--port` at its
`11434` and use `--model-name dots.mocr`.

---

## Run

### Handwriting → Markdown

```bash
# Single photo
python3 ocr/scripts/note_to_markdown.py note.jpg -o out/

# Scanned handwriting PDF (page by page)
python3 ocr/scripts/note_to_markdown.py notes.pdf -o out/

# A folder of shots (sorted by filename, treated as consecutive pages)
python3 ocr/scripts/note_to_markdown.py ./shots/ -o out/

# Plain text only, no layout JSON — more robust for messy handwriting
python3 ocr/scripts/note_to_markdown.py note.jpg --prompt prompt_ocr

# Nearest to printed text; try this if recognition is poor
python3 ocr/scripts/note_to_markdown.py note.jpg --preprocess binarize
```

Or via the launcher, which needs no venv activation:

```bash
./ocr/bin/nmd note.jpg -o out/
```

Or double-click `ocr/bin/手写笔记转Markdown.command` in Finder and drag your file in.

### PDF → images

```bash
python3 ocr/scripts/pdf_to_images.py input.pdf
python3 ocr/scripts/pdf_to_images.py input.pdf -o ./images --dpi 300 --quality 90
python3 ocr/scripts/pdf_to_images.py input.pdf --dpi 200 --quality 85 --prefix scan
python3 ocr/scripts/pdf_to_images.py input.pdf --start 5 --end 10   # pages 5–10 only
python3 ocr/scripts/pdf_to_images.py input.pdf --gray              # grayscale, for plain-text OCR
```

Full parameter reference and DPI/quality guidance: [`docs/pdf_to_images.md`](docs/pdf_to_images.md).

### The dots.mocr parser directly

```bash
# Whole-PDF layout + recognition (one JSON per page + a stitched MD)
python3 -m dots_mocr.parser path/to/file.pdf \
    --ip 127.0.0.1 --port 1234 \
    --model_name "dots.mocr" \
    --num_thread 4 \
    --prompt prompt_layout_all_en \
    --output ./output

# Single page, layout detection only
python3 -m dots_mocr.parser path/to/file.pdf \
    --ip 127.0.0.1 --port 1234 \
    --model_name "dots.mocr" \
    --prompt prompt_layout_only_en

# A quick smoke test (just one rendered page, raw OCR text)
python3 -m dots_mocr.parser path/to/file.pdf \
    --ip 127.0.0.1 --port 1234 \
    --model_name "dots.mocr" \
    --prompt prompt_ocr \
    --num_thread 1

# Image (non-PDF) input
python3 -m dots_mocr.parser path/to/file.jpg \
    --model_name "dots.mocr"
```

Per-PDF outputs land in `output/<pdf_name>/`:

| File | Contents |
|---|---|
| `<name>_page_<i>.json` | Bbox + category + text for page _i_ |
| `<name>_page_<i>.md` | Markdown with page-header/footer included |
| `<name>_page_<i>_nohf.md` | Same MD without page-header/footer (for benchmarks) |
| `<name>_page_<i>.jpg` | Original page with detected bboxes drawn on top |
| `<name>.jsonl` | Index across all pages |

### Programmatic use

```python
from dots_mocr.parser import DotsMOCRParser

parser = DotsMOCRParser(
    ip="127.0.0.1", port=1234, model_name="dots.mocr",
    num_thread=4, dpi=150,
)
results = parser.parse_file(
    "demo.pdf",
    output_dir="./output",
    prompt_mode="prompt_layout_all_en",
)
for r in results:
    print(r["page_no"], "→", r["md_content_path"])
```

---

## Environment variables

Every default below can be set in the environment instead of passed as a flag.
**Command-line flags win over environment variables**, which win over the
built-in defaults. Nothing here is required — the defaults work standalone.

| Variable | Default | Used by | Meaning |
|---|---|---|---|
| `OCR_VENV_PYTHON` | *(auto)* | `note_to_markdown` | Absolute path to a venv interpreter. Overrides the `.venv` search. |
| `OCR_NO_REEXEC` | *(unset)* | `note_to_markdown` | Set to `1` to never re-exec into a venv. |
| `OCR_HOST` | `127.0.0.1` | `note_to_markdown`, `smoke_test` | Model server host. |
| `OCR_PORT` | `1234` | `note_to_markdown`, `smoke_test` | Model server port. |
| `OCR_MODEL` | `dots.mocr` | `note_to_markdown`, `smoke_test` | Model identifier. |
| `OCR_DPI` | `150` (`200` in `smoke_test`) | all | PDF render resolution. |
| `OCR_OUTPUT_DIR` | `./note_md` | `note_to_markdown`, `bin/手写笔记转Markdown.command` | Output directory. Relative to CWD. |
| `OCR_IMAGES_DIR` | *(PDF name)*`_images` | `pdf_to_images` | Output directory for split images. |
| `OCR_PREPROCESS` | `enhance` | `note_to_markdown` | `none` / `gray` / `enhance` / `binarize`. |
| `OCR_MAX_SIDE` | `1600` (`1280` in `pdf_to_images`) | `note_to_markdown`, `pdf_to_images` | Longest-edge pixel cap, `0` = unlimited. |
| `OCR_SCALE` | `1.0` | `note_to_markdown` | Extra upscale factor. |
| `OCR_PROMPT` | `prompt_layout_all_en` | `note_to_markdown` | dots.mocr prompt mode. |
| `OCR_NUM_THREAD` | `1` | `note_to_markdown` | Concurrent pages. |
| `OCR_QUALITY` | `80` | `pdf_to_images` | JPEG quality, 1–95. |
| `LMSTUDIO_IP` / `LMSTUDIO_PORT` / `LMSTUDIO_MODEL` | — | `smoke_test` | **Legacy names, checked first** for backwards compatibility. |
| `OCR_SHELL_YES` | *(unset)* | `ocr_shell` | Set to `1` to skip the confirmation prompt and run immediately. |
| `OCR_SHELL_FORCE_TTY` | *(unset)* | `ocr_shell` | Set to `1` to treat piped stdin as interactive (for testing the menus). |
| `OCR_FONT_PATH` | *(auto)* | `dots_mocr` | Absolute path to a TrueType font for the SVG label renderer. Auto-detected per platform otherwise. |

Example:

```bash
export OCR_HOST=192.168.1.20 OCR_PORT=11434 OCR_MODEL=dots.mocr
export OCR_OUTPUT_DIR=~/Documents/notes
ocr-note-to-markdown note.jpg
```

---

## Output layout

`note_to_markdown.py -o out/` produces:

```
out/
├─ note.md              # all pages merged, `---` between pages  ← the deliverable
├─ note.jsonl           # one {"markdown": "..."} per page, for batch pipelines
└─ _pages/
   └─ note_page_001/
      ├─ note_page_001.json      # raw layout JSON (bbox + category + text)
      ├─ note_page_001.md        # page Markdown incl. header/footer
      ├─ note_page_001_nohf.md   # page Markdown without header/footer
      └─ note_page_001.jpg       # page image with bboxes drawn on top
```

A `_staging/` directory holds the preprocessed images during a run and is removed
afterwards. Pass `--keep-staging` to keep them for debugging.

Sample outputs are **not committed** — this repository ships code only. Run the
toolchain yourself to produce the same artefacts (see [Run](#run)): every run
writes a `note_md/` directory holding one `*.jsonl` per page, a
`_pages/<name>_page_<i>/` folder per page (layout JSON + Markdown + annotated
JPEG) and a concatenated Markdown file. Generated output is ignored by git.

---

## Layout

```
ocr/
├─ README.md                  # this file
├─ LICENSE                    # MIT
├─ pyproject.toml             # package metadata + console entry points
├─ requirements.txt
├─ .gitignore
├─ scripts/
│  ├─ _bootstrap.py           # portable path helpers (venv lookup, env vars)
│  ├─ ocr_shell.py            # interactive menu shell + scriptable runner
│  ├─ test_ocr_shell.py       # smoke tests for the shell (no model server needed)
│  ├─ note_to_markdown.py     # handwriting photo/PDF → Markdown
│  ├─ pdf_to_images.py        # PDF → per-page JPG
│  ├─ check_imports.py        # pre-flight: does every dots_mocr.* import?
│  └─ smoke_test.py           # end-to-end check, incl. the model server
├─ bin/
│  ├─ ocr                     # interactive shell launcher
│  ├─ nmd                     # one-line launcher: ./bin/nmd note.jpg
│  ├─ OCR交互式外壳.command    # Finder double-click → interactive shell
│  └─ 手写笔记转Markdown.command  # Finder double-click / drag-and-drop
├─ dots_mocr/
│  ├─ parser.py               # CLI entrypoint, mostly upstream code
│  ├─ model/
│  │  └─ inference.py         # OpenAI-SDK replacement for the vLLM client
│  └─ utils/
│     ├─ consts.py
│     ├─ doc_utils.py         # PyMuPDF / fitz
│     ├─ image_utils.py       # smart_resize, fetch_image
│     ├─ layout_utils.py      # bbox post-processing + draw_layout_on_image
│     ├─ format_transformer.py
│     ├─ output_cleaner.py
│     ├─ prompts.py
│     └─ svg_utils.py
├─ docs/                      # research reports + tool references
│  ├─ deepseek_ocr_report.md
│  ├─ dots_ocr_report.md
│  ├─ got_ocr2_report.md
│  └─ pdf_to_images.md
```

`dots_mocr` is deliberately a **flat top-level package**: its modules
self-reference absolutely (`from dots_mocr.utils.consts import ...`), so it must
not be nested under another package name.

### Research reports

`docs/` holds background reading on the OCR landscape this toolchain was built
from — comparisons of dots.ocr, DeepSeek-OCR, and GOT-OCR2:

- [`docs/deepseek_ocr_report.md`](docs/deepseek_ocr_report.md)
- [`docs/dots_ocr_report.md`](docs/dots_ocr_report.md)
- [`docs/got_ocr2_report.md`](docs/got_ocr2_report.md)

---

## What changed vs. the upstream repo

| File | Change |
|---|---|
| `dots_mocr/model/inference.py` | **Rewritten.** `inference_with_vllm` now uses the `openai` Python SDK instead of the vLLM Python client. Signature preserved so `parser.py` calls it unchanged. |
| `dots_mocr/utils/{doc,image}_utils.py` + `layout_utils.py` | One-line swap: `import fitz` → `try: import pymupdf as fitz / except: import fitz`. Compatible with PyMuPDF ≥1.24. |
| `dots_mocr/parser.py` | Default port changed to `1234` (LM Studio); HF backend removed; CLI `--use_hf` is now `store_true` (instead of the upstream broken `type=bool`). |
| `dots_mocr/utils/{consts,prompts,format_transformer,svg_utils}.py` | **Unchanged.** |
| `scripts/`, `bin/` | New — the handwriting preprocessing + PDF splitting toolchain. |
| `requirements.txt`, `pyproject.toml` | New. Trimmed to `openai`, `pymupdf`, `Pillow`, `tqdm`, `pydantic`, `numpy`, `requests`. |

---

## Troubleshooting

**`ModuleNotFoundError` after installing**

Python caches failed imports. Run:

```bash
find . -name __pycache__ -type d -exec rm -rf {} +
```

…then re-run. This commonly happens right after the first `pip install`, before
all transitive deps are resolved.

**`No module named 'dots_mocr'`**

You are running from the wrong directory, or `ocr/` is not on `sys.path`. Either
run the script by its full path (`python3 ocr/scripts/note_to_markdown.py`, which
self-bootstraps) or install the package (`pip install -e .`).

**`[错误] 缺少依赖: No module named 'numpy'`** (or `PIL`, `fitz`)

The script tried to use the system `python3`, which lacks the dependencies.
Either activate the venv, or let the bootstrap find it — it looks for
`$OCR_VENV_PYTHON`, then `ocr/.venv/bin/python`, then `<repo>/.venv/bin/python`.
If none exists it stays on the current interpreter and tells you to
`pip install -r requirements.txt`.

**`[..] probing 127.0.0.1:1234` then a connection error**

The model server isn't running. Start it in LM Studio's Developer tab. Use
`ocr-smoke-test --check-only` to confirm the local side is fine first.

**Model not found on the server**

The script prints the available model IDs if it can't find yours — check that
`--model-name` / `$OCR_MODEL` matches exactly what LM Studio reports.

**Recognition quality is poor**

Try, in order: `--preprocess binarize` (closest to printed text), a higher
`--dpi`, and `--prompt prompt_ocr` (plain text, skips layout JSON — more robust
for messy handwriting). Open the `_pages/*.jpg` files: if the detected bboxes
look wrong, the problem is preprocessing, not the model.

**`--num_thread` doesn't speed things up**

That's expected. LM Studio serves one request at a time, so multi-page processing
is essentially sequential regardless of thread count.

**The SVG prompt needs a different model**

`prompt_image_to_svg` requires **`dots.mocr-svg`** loaded on the server, not the
plain `dots.ocr` weights.

---

## Caveats

- **First request is slow** — LM Studio may take 30–90 s for the first token while
  it loads the GGUF into memory. Subsequent pages are fast.
- **Speed on Mac**: expect ~3–10 s per A4 page for the full layout+recognition
  prompt, depending on the prompt length, quantization and context.

## License

MIT — see [LICENSE](LICENSE).