# Dots OCR — Detailed Research Report

> Source: official model cards, GitHub README, arXiv papers, and HF model metadata.
> Compiled from public sources as of late 2025 / early 2026.

---

## TL;DR / Quick Facts

- **What it is:** RedNote's ("小红书 / Xiaohongshu") unified Vision-Language document parser.
- **Vendor:** `hi lab, Xiaohongshu Inc` (HF org `rednote-hilab`; the GitHub repo was moved to `studio-dots-ai/dots.ocr` and is now rebranded as `dots.mocr`).
- **Total parameters:** ≈3B (= 1.2B ViT vision encoder + 1.7B LLM decoder with tied embeddings). The 1.0 release was marketed as "1.7B-parameter LLM" but the full VLM is ~3B.
- **Architecture:** ViT-LLM (Qwen2-VL style). Vision encoder trained **from scratch** (not a fine-tune of an image-VLM encoder). LLM = **Qwen2.5-1.5B-base** with tied word embeddings → 1.7B.
- **License:** MIT (open weights).
- **Releases:**
  - **2025-07-30** — `dots.ocr` v1 (multilingual document parsing)
  - **2025-10-31** — `dots.ocr.base` (foundation VLM before SFT)
  - **Late 2025** — `dots.ocr-1.5` (added SVG generation, web/scene text, broader capabilities)
  - **2026-03-19** — `dots.ocr-1.5` **rebranded to `dots.mocr`** ("Multimodal OCR" — joint text + graphics parsing)
- **Papers:**
  - v1: arXiv **2512.02498** — *dots.ocr: Multilingual Document Layout Parsing in a Single Vision-Language Model* (Yumeng Li et al., hi lab, Xiaohongshu Inc.)
  - 1.5/mocr: arXiv **2603.13032** — *Multimodal OCR: Parse Anything from Documents* (Handong Zheng et al., HUST + hi lab)
- **Demos / code:** Live demo at https://dotsocr.xiaohongshu.com; code at https://github.com/rednote-hilab/dots.ocr (now studio-dots-ai/dots.ocr) and https://github.com/rednote-hilab/dots.mocr.

> Note on naming: the URLs the requester tried — `github.com/rednote-labs/DotsOCR` and `huggingface.co/rednote/DotsOCR` — 404. The correct orgs are `rednote-hilab` on Hugging Face and `studio-dots-ai`/`rednote-hilab` on GitHub. The mirror at `dots-studio/dots.ocr` is the community/maintained fork that became the upstream after the rebrand.

---

## 1. Basic Info

### 1.1 Release timeline

| Date | Event | Model |
|------|-------|-------|
| 2025-07-30 | Initial release | `dots.ocr` v1 (1.7B LLM, SOTA on OmniDocBench) |
| 2025-10-31 | Base model release | `dots.ocr.base` (foundation VLM pre-SFT) |
| ~Late 2025 | v1.5 release | `dots.ocr-1.5` (3B params, SVG generation, web parsing, scene text) |
| 2026-03-13/19 | Paper + rebrand | `dots.mocr` + `dots.mocr-svg` (rename of 1.5 with new paper) |

### 1.2 Architecture

From the arXiv paper (2512.02498 v4, §3.2) and HF `config.json`:

- **Vision encoder:** 1.2B-parameter ViT trained **entirely from scratch** (not a fine-tune of CLIP/SigLIP/Qwen-VL). Native high-resolution input up to **~11 million pixels** (uses NaViT-style processing). 42 layers, 12 heads, patch size 14, spatial merge 2, embed dim 1536.
- **Connector / merger:** lightweight multimodal connector.
- **LLM decoder:** **Qwen2.5-1.5B-base**, modified with **tied word embeddings**, giving **1.7B parameters**. Vocab 151,936; hidden 1536; 28 layers; 12 attention heads (with 2 KV heads, GQA); sliding window 131,072; RoPE θ 1,000,000; supports `flash_attention_2`.
- **Total:** ~3B parameters for v1; the 1.5/mocr release is also described as 3B (same encoder/decoder sizes, additional SFT data).

### 1.3 LLM backbone

- **Qwen2.5-1.5B-base** (initialized from base, **not** the chat-tuned variant). Cited in both the arXiv paper and the modeling code.
- Custom modeling class `DotsOCRForCausalLM` (see `modeling_dots_ocr.DotsOCRForCausalLM` in `config.json`).

### 1.4 Training recipe (from paper §3 + blog)

- **Pretrain Stage 1** — Vision Encoder pre-training from scratch on image-text pairs.
- **Pretrain Stage 2** — VE continued pretraining with OCR/video/grounding data; aligned with frozen Qwen2.5-1.5B. Resulting encoder: `dots.vit`.
- **Pretrain Stage 3** — VLM specialization on pure OCR data; first frozen-VE then unfreeze-all for an additional 1/5 of the tokens. → `dots.ocr.base`.
- **SFT** — ~300k diverse samples (in-house manual annotations + synthetic tables/formulas/multilingual + open-source). AdamW, peak LR 5e-5, cosine decay. Three iterations of a human-in-the-loop "bad-case → re-train" flywheel on 15k multilingual layout samples.

For mocr the recipe adds two further pretraining stages (general vision → text-only OCR mixture → MOCR-heavy mixture with image-to-SVG) plus SVG-targeted SFT for the `-svg` variant.

---

## 2. Handwriting Recognition

**Honest answer: handwriting is *not* a primary target and no dedicated handwriting number is published.**

- The model is framed as a **printed/structured document** parser (PDFs, slides, scanned books, financial reports, magazines, academic papers, newspapers, notes). The closest "handwriting-adjacent" categories it touches:
  - **olmOCR-bench — "Old scans"**: dots.ocr = 40.9, dots.mocr = 48.2 (vs Mistral OCR 29.3, Marker 33.5, PaddleOCR-VL 37.8, olmOCR 47.7). "Old scans" are degraded historical scans, not handwriting per se.
  - **olmOCR-bench — "Long tiny text"**: dots.ocr = 81.2, dots.mocr = 81.6 (vs MonkeyOCR 80.1, Qwen2.5-VL 49.1).
  - **OmniDocBench "Notes" page type (handwritten-feel notes)**: dots.ocr = 0.109 text edit, vs MinerU 0.984 and GOT-OCR 0.388. (Lower = better.) So it is at least *much* better than the pipeline baselines on notes, but it isn't marketed as HTR.
- dots.ocr-1.5/mocr adds **scene-text spotting**, which is closer to handwriting than any benchmark the 1.0 release had.
- Community has used it for handwriting-style fine-tunes (e.g. `samaritan-ai/dots-ocr-samaritan-hebrew` is explicitly tagged `htr`).
- The model card explicitly **does not** list IAM, Bentham, CASIA, or any standard HTR benchmark.

**Takeaway:** dots.ocr is capable on degraded/scanned/notes-like inputs (and very strong there vs classical OCR pipelines), but the maintainers have not published numbers on standard handwriting benchmarks. Treat any HTR claim as "untested / plausible-but-unverified."

---

## 3. Figure / Diagram / Table / Formula Understanding — Output Format

For **dots.ocr v1** (within a document page), outputs are JSON then concatenated Markdown:

| Category | Output format | Native support |
|---|---|---|
| Text, Title, Section-header, List-item, Caption, Footnote, Page-header, Page-footer | Markdown | ✓ |
| **Table** | **HTML** | ✓ (e.g., `<table><tr><td>…</td></tr></table>`) |
| **Formula** | **LaTeX** | ✓ |
| **Picture / figure** | **Not parsed** (text field omitted in JSON; the bbox is reported but content is left as a raster crop) | ✗ in v1 |
| Reading order | implicit (elements serialized in human reading order) | ✓ |

For **dots.ocr-1.5 / dots.mocr**, the picture gap is closed:

| New task | Output | Notes |
|---|---|---|
| **Structured graphics** (charts, diagrams, icons, chemical formulas, logos, UI screenshots, scientific figures) | **SVG code** | Native, first-class output |
| **Webpage / UI** parsing | structured DOM-like / SVG | New prompt `prompt_web_parsing` |
| **Scene-text spotting** | text + bbox | New prompt `prompt_scene_spotting` |
| **Object grounding & counting** | bbox / count | Mentioned in iqr |

The output schema is driven by the **prompt**: `prompt_layout_all_en`, `prompt_layout_only_en`, `prompt_ocr`, `prompt_grounding_ocr`, `prompt_web_parsing`, `prompt_scene_spotting`, `prompt_image_to_svg`, plus a general QA path — all in a single VLM with the same weights.

---

## 4. SVG Generation (the big question)

**Yes — fully native, but only from v1.5 (Oct/Nov 2025) onward, not in v1.**

- **Releases with SVG:**
  - `rednote-hilab/dots.ocr-1.5` — primary model, supports SVG plus everything else.
  - `rednote-hilab/dots.ocr-1.5-svg` — special variant, further fine-tuned for image-to-SVG.
  - `rednote-hilab/dots.mocr` and `rednote-hilab/dots.mocr-svg` — rebranded names (Mar 2026).
- **Demos:** the HF model card and the live demo at `dotsocr.xiaohongshu.com` both ship "Examples for image parsing" showing SVG outputs of charts, UI screens, scientific figures, chemical diagrams, etc. Six SVG showcase images are visible in the README:
  `assets/showcase_dots_ocr_1_5/result/svg_{1,2,4,5,6}.png`
- **Code path:** `python3 ./demo/demo_vllm_svg.py --prompt_mode prompt_image_to_svg`
- **Architecture for SVG:** SVG generation is **not** a separate module — the same VLM is conditioned with a different prompt (`prompt_image_to_svg`), giving it SVG code as the payload. The `-svg` checkpoint is the same VLM with the SVG share up-weighted during SFT (the paper describes this in §3.3).
- **SVG benchmarks** (from the v1.5/mocr model card). Higher is better; metric is ISVGEN from UniSVG, plus native benchmarks.

| Model | UniSVG Low-Level | UniSVG High-Level | UniSVG Score | Chartmimic | Design2Code | Genexam | SciGen | ChemDraw |
|---|---|---|---|---|---|---|---|---|
| OCRVerse | 0.632 | 0.852 | 0.763 | 0.799 | – | – | – | 0.881 |
| Gemini 3 Pro | 0.563 | 0.850 | 0.735 | 0.788 | 0.760 | 0.756 | 0.783 | 0.839 |
| **dots.mocr / dots.ocr-1.5** | **0.850** | **0.923** | **0.894** | 0.772 | 0.801 | 0.664 | 0.660 | 0.790 |
| **dots.mocr-svg / dots.ocr-1.5-svg** | **0.860** | **0.931** | **0.902** | **0.905** | **0.834** | **0.800** | **0.797** | **0.901** |

So the `-svg` variant **beats Gemini 3 Pro** on every SVG benchmark reported and is dramatically better on low-level reconstruction.

- **Important limitation (from paper §3.1 and README):** SVG generation and full-page document parsing are **two separate passes** — the model is not yet a single one-pass system that emits both the page text layout *and* inline SVG for every figure. To get a full MOCR parse you run page-level text parsing + region-level image-to-SVG sequentially.
- **Failure modes (from the paper and model card):** complex natural-photo images and arbitrary raster pictures are intentionally **not** converted to SVG (the paper explicitly says "complex real-world imagery … lack a compact programmatic description, are retained as raster content"). Demos focus on chart/diagram/UI/chemical-figure style inputs.
- **v1 does NOT do SVG.** It only emits Markdown / JSON for the page; figures are skipped. So if a user is on v1, "SVG" won't appear at all.

---

## 5. Benchmark Numbers (specifics)

### 5.1 OmniDocBench v1 (end-to-end; lower = better, except Table TEDS)

| Model | Overall Edit EN ↓ | Overall Edit ZH ↓ | Text EN ↓ | Text ZH ↓ | Formula EN ↓ | Formula ZH ↓ | Table TEDS EN ↑ | Table TEDS ZH ↑ | Read Order EN ↓ | Read Order ZH ↓ |
|---|---|---|---|---|---|---|---|---|---|---|
| GOT-OCR | 0.287 | 0.411 | 0.189 | 0.315 | 0.360 | 0.528 | 53.2 | 47.2 | 0.141 | 0.280 |
| MinerU 2 | 0.139 | 0.240 | 0.047 | 0.109 | 0.297 | 0.536 | 82.5 | 79.0 | 0.069 | 0.118 |
| MonkeyOCR-pro-3B | 0.138 | 0.206 | 0.067 | 0.107 | **0.246** | 0.421 | 81.5 | 87.5 | 0.100 | 0.185 |
| GPT-4o | 0.233 | 0.399 | 0.144 | 0.409 | 0.425 | 0.606 | 72.0 | 62.9 | 0.128 | 0.251 |
| Qwen2.5-VL-72B | 0.214 | 0.261 | 0.092 | 0.180 | 0.315 | 0.434 | 82.9 | 83.9 | 0.106 | 0.168 |
| Gemini 2.5 Pro | 0.148 | 0.212 | 0.055 | 0.168 | 0.356 | 0.439 | 85.8 | 86.4 | 0.049 | 0.121 |
| doubao-1-5-thinking-vision-pro-250428 | 0.140 | 0.162 | 0.043 | 0.085 | 0.295 | **0.384** | 83.3 | **89.3** | 0.058 | 0.094 |
| **dots.ocr (v1)** | **0.125** | **0.160** | **0.032** | **0.066** | 0.329 | 0.416 | **88.6** | 89.0 | **0.040** | **0.067** |

### 5.2 OmniDocBench v1.5 (newer; reported in v1.5/mocr release)

| Model | Size | Text Edit ↓ | Read Order Edit ↓ | pdf-parse-bench |
|---|---|---|---|---|
| Gemini 2.5 Pro | – | 0.075 | 0.097 | 9.06 |
| Qwen3-VL-235B-A22B | 235B | 0.069 | 0.068 | **9.71** |
| Gemini 3 Pro | – | 0.066 | 0.079 | 9.68 |
| DeepSeek-OCR | 3B | 0.073 | 0.086 | 8.26 |
| MonkeyOCR-pro-3B | 3B | 0.075 | 0.128 | – |
| OCRVerse | 4B | 0.058 | 0.071 | – |
| MinerU 2.5 | 1.2B | 0.047 | 0.044 | – |
| PaddleOCR-VL | 0.9B | 0.035 | 0.043 | 9.51 |
| PaddleOCR-VL-1.5 | 0.9B | 0.035 | 0.042 | – |
| HunyuanOCR | 0.9B | 0.042 | – | – |
| GLM-OCR | 0.9B | 0.040 | 0.043 | – |
| **dots.ocr** | 3B | 0.048 | 0.053 | 9.29 |
| **dots.mocr / dots.ocr-1.5** | 3B | **0.031** | **0.029** | 9.54 |

(The paper's own prose reports dots.ocr at **87.5 EN / 84.0 ZH** overall on OmniDocBench v1 — these are composite "page score" style numbers distinct from the Edit-distance columns above.)

### 5.3 olmOCR-Bench

| Model | ArXiv | Old scans math | Tables | Old scans | H&F | Multi-col | Long tiny | Base | **Overall** |
|---|---|---|---|---|---|---|---|---|---|
| Mistral OCR | 77.2 | 67.5 | 60.6 | 29.3 | 93.6 | 71.3 | 77.1 | 99.4 | 72.0±1.1 |
| MinerU 2.5.4 | 76.6 | 54.6 | 84.9 | 33.7 | 96.6 | 78.2 | 83.5 | 93.7 | 75.2±1.1 |
| Marker 1.10.1 | 83.8 | 66.8 | 72.9 | 33.5 | 86.6 | 80.0 | 85.7 | 99.3 | 76.1±1.1 |
| DeepSeek-OCR | 77.2 | 73.6 | 80.2 | 33.3 | 96.1 | 66.4 | 79.4 | 99.8 | 75.7±1.0 |
| Nanonets-OCR2-3B | 75.4 | 46.1 | 86.8 | 40.9 | 32.1 | 81.9 | 93.0 | 99.6 | 69.5±1.1 |
| PaddleOCR-VL* | 85.7 | 71.0 | 84.1 | 37.8 | 97.0 | 79.9 | 85.7 | 98.5 | 80.0±1.0 |
| olmOCR v0.4.0 | 83.0 | 82.3 | 84.9 | 47.7 | 96.1 | 83.7 | 81.9 | 99.7 | 82.4±1.1 |
| Chandra OCR 0.1.0* | 82.2 | 80.3 | 88.0 | 50.4 | 90.8 | 81.2 | 92.3 | 99.9 | 83.1±0.9 |
| MonkeyOCR-pro-3B | **83.8** | 68.8 | 74.6 | 36.1 | 91.2 | 76.6 | 80.1 | 95.3 | 75.8±1.0 |
| Infinity-Parser 7B* | 84.4 | 83.8 | 85.0 | **47.9** | 88.7 | 84.2 | 86.4 | 99.8 | 82.5 |
| **dots.ocr (v1)** | 82.1 | 64.2 | 88.3 | 40.9 | 94.1 | 82.4 | 81.2 | 99.5 | 79.1±1.0 |
| **dots.mocr / dots.ocr-1.5** | **85.9** | **85.5** | **90.7** | 48.2 | 94.0 | **85.3** | 81.6 | 99.7 | **83.9±0.9** |

### 5.4 Elo leaderboard (Gemini-3-Flash judged)

| Model | olmOCR-Bench | OmniDocBench v1.5 | XDocParse | Average |
|---|---|---|---|---|
| MonkeyOCR-pro-3B | 895.0 | 811.3 | 637.1 | 781.1 |
| GLM-OCR | 884.2 | 972.6 | 820.7 | 892.5 |
| PaddleOCR-VL-1.5 | 897.3 | 997.9 | 866.4 | 920.5 |
| HuanyuanOCR | 997.6 | 1003.9 | 951.1 | 984.2 |
| dots.ocr | 1041.1 | 1027.2 | 1190.3 | 1086.2 |
| **dots.mocr / dots.ocr-1.5** | **1104.4** | **1059.0** | **1210.7** | **1124.7** |
| Gemini 3 Pro | 1180.4 | 1128.0 | 1323.7 | 1210.7 |

(The paper notes these match the [ocrarena.ai](https://www.ocrarena.ai/battle) rankings.)

### 5.5 Layout detection (dots.ocr-bench, 100 languages, 1,493 pages)

| Method | F1@IoU=.50:.05:.95 (overall) | F1@IoU=.50 |
|---|---|---|
| DocLayout-YOLO-DocStructBench | 0.733 | 0.806 |
| dots.ocr (parse all) | 0.831 | 0.922 |
| **dots.ocr (detection only)** | **0.845** | **0.930** |

### 5.6 General-vision tasks (v1.5/mocr)

| Model | CharXiv_desc | CharXiv_reason | OCR_Reasoning | InfoVQA | DocVQA | ChartQA | OCRBench | AI2D | CountBenchQA | RefCOCO |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3-VL-2B | 62.3 | 26.8 | – | 72.4 | 93.3 | – | 85.8 | 76.9 | 88.4 | – |
| Qwen3-VL-4B | 76.2 | 39.7 | – | 80.3 | 95.3 | – | 88.1 | 84.1 | 84.9 | – |
| **dots.mocr / dots.ocr-1.5** | **77.4** | **55.3** | 22.85 | 73.76 | 91.85 | 83.2 | 86.0 | 82.16 | **94.46** | 80.03 |

### 5.7 Notes on benchmarks the requester asked about

- **OmniDocBench** — extensively covered above. dots.ocr/dots.mocr is **state of the art** on v1 among non-cloud models; on v1.5 it tops the open-source list at Text 0.031 / Read Order 0.029, behind only Gemini 3 Pro (and only just behind Qwen3-VL-235B).
- **Fox-1 / Fox benchmark** — *not mentioned anywhere* in the README, paper, or model card. I could not find a Fox-1 OCR number for dots.ocr.
- **MMVet** — *not mentioned*. dots.ocr is a specialized document parser, not a general-purpose chat VLM, so MMVet-style instruction-following numbers are not reported. The closest analogues are OCRBench (86.0), CharXiv, and the general-VLM columns above.
- **XDocParse** — RedNote's *new* multilingual benchmark (126 languages) released alongside the v1 paper; dots.ocr is +7.4 points over the next competitor, and dots.mocr pushes that further to Elo 1210.7.

---

## 6. Speed / Throughput

**The official docs do NOT publish a pages/sec or tokens/sec number.** Concrete facts available:

- Recommended inference stack: **vLLM ≥ 0.9.1** for v1; **vLLM ≥ 0.11.0** for dots.mocr (DotsOCR is officially integrated into vLLM as of v0.11.0).
- Default launch: 1 GPU, tensor-parallel-size 1, gpu-memory-utilization 0.95 (v1) / 0.9 (1.5/mocr), flash-attention-2, bf16.
- For PDF batch: `--num_threads 64` recommended for large PDFs (parallel vLLM requests).
- Max new tokens per call: 24,000 (set in the HF demo script).
- Resolution: accepts images up to **~11,289,600 pixels** (cap); best results when rendered at ~200 DPI per the recipe (`tikz_preprocess`).
- The maintainers explicitly call out: *"Despite its 1.7B parameter LLM foundation, dots.ocr is not yet optimized for high-throughput processing of large PDF volumes."* (v1 README Limitation section). The 1.5/mocr README echoes this as *"parsing failures may still occur occasionally."*
- HF repo stats: `dots-studio/dots.ocr` (the mirrored v1) had **888,620 downloads** and **1,341 likes** as of the snapshot I pulled, indicating very heavy real-world use despite the lack of an official speed claim.
- A **CPU inference** path is documented in the issue tracker (`https://github.com/rednote-hilab/dots.ocr/issues/1#issuecomment-3148962536`).

**Bottom line:** speed is *not* a published headline metric. Expect a 3B VLM on a single A100/H100 with vLLM to behave like a typical 3B VLM; no specific `pages/sec` number exists in any official source I could find.

---

## 7. Comparison with Competitors (qualitative)

The paper + model card rank the *open-source* and *closed-API* OCR systems as follows (numbers from OmniDocBench v1 and olmOCR-Bench above):

| Competitor | Class | Size | vs dots.ocr / dots.mocr |
|---|---|---|---|
| **DeepSeek-OCR** | Specialized VLM (end-to-end) | 3B | Dots.mocr is **better** on olmOCR-Bench (83.9 vs 75.7) and on OmniDocBench v1.5 Text/Read Order; DeepSeek-OCR is conceptually closest in approach (deepseek-ai's encoder-decoder) but dots.mocr is the current SOTA open model. |
| **GOT-OCR** | Specialist VLM | ~0.8B | dots.ocr beats it handily on OmniDocBench (0.125 vs 0.287 EN) and olmOCR (79.1 vs 48.3). |
| **MinerU / MinerU 2 / MinerU 2.5** | Pipeline (YOLO + DB + …) | <1.2B | dots.ocr beats MinerU 2 (0.125 vs 0.139) and ties with MinerU 2.5; dots.mocr now slightly edges MinerU 2.5 on Text/Read Order. MinerU 2.5 is competitive at lower parameter count. |
| **Marker** | Pipeline (heuristic + OCR) | – | dots.ocr / mocr dominate on every benchmark. |
| **MonkeyOCR-pro-3B** | Specialist VLM (modular pipeline) | 3B | Strong on formulas (0.246 EN, the only model below dots.ocr here) but trails on overall/text/tables. dots.mocr beats it on olmOCR-Bench 83.9 vs 75.8 and on Elo. |
| **olmOCR (AllenAI)** | Specialist VLM (anchored) | 7B | dots.mocr (3B) beats olmOCR v0.4.0 (82.4) on olmOCR-Bench 83.9. |
| **Qwen2.5-VL-72B / Qwen3-VL-235B** | General VLM | 72–235B | dots.mocr (3B) beats Qwen2.5-VL-72B on OmniDocBench v1 (overall) and beats Qwen3-VL-235B on v1.5 Text/Read Order (0.031/0.029 vs 0.069/0.068), but Qwen3-VL-235B wins on pdf-parse-bench (9.71 vs 9.54). |
| **PaddleOCR-VL / PaddleOCR-VL-1.5** | Specialist VLM | 0.9B | PaddleOCR-VL-1.5 (0.035 Text Edit on v1.5) edges dots.mocr slightly on raw Text Edit but trails on Read Order and olmOCR-Bench. |
| **HunyuanOCR / GLM-OCR / OCRVerse** | Specialist VLM | 0.9–4B | All trail dots.mocr on Elo and olmOCR-Bench. |
| **Chandra OCR 0.1.0** | Specialist VLM (7B) | 7B | Better than dots.ocr v1 (83.1 vs 79.1) but **worse than dots.mocr** (83.9). |
| **Infinity-Parser 7B** | Specialist VLM | 7B | Comparable to dots.mocr (82.5 vs 83.9 olmOCR-Bench), trails on Elo. |
| **GPT-4o** | General VLM | – | dots.ocr beats GPT-4o on OmniDocBench (0.125 vs 0.233 EN) and on pdf-parse-bench in dots.mocr's favor. |
| **Gemini 2.5 Pro / Gemini 3 Pro** | Closed frontier | – | dots.mocr is **second only to Gemini 3 Pro** on the OCR Arena Elo leaderboard; on SVG generation, dots.mocr-svg beats Gemini 3 Pro. |
| **Mistral OCR** | Closed | – | Loses on every metric. |
| **Nougat / Nougat-style** | Specialist VLM | – | Very outdated; dots.ocr wins by 2–4×. |
| **Nanonets-OCR2-3B / Docling / Pix2Text / Unstructured / OpenParse / PPStruct-V3 / SmolDocling-256M / Dolphin / OCRFlux** | Various | various | dots.ocr beats all of these on OmniDocBench v1. |
| **Mathpix** | Commercial OCR API | – | dots.ocr (0.125 EN overall) beats Mathpix (0.191). |

**Positioning summary (RedNote's own framing):** dots.mocr is the best open OCR/document-parsing model as of early 2026, ranking below only Gemini 3 Pro on the OCR Arena Elo leaderboard, and is the leading open model on SVG generation. The main *practical* strengths RedNote claims over competitors: (1) it is one VLM handling text + graphics + reading order + (now) SVG, vs the pipeline cascade most rivals use; (2) strong multilingual (126-lang XDocParse) and low-resource-language coverage; (3) same weights for OCR, layout detection, web parsing, scene text, and image-to-SVG.

**Practical weaknesses the team admits:** complex tables/formulas and arbitrary raster photos; occasional parsing failures on long ellipses/underscores; not optimized for high-throughput PDF batch.

---

## 8. Community / Distribution Notes

- **Mirrors/forks** because the official Hugging Face org had a re-org:
  - `dots-studio/dots.ocr` (v1.0) — still the most-downloaded mirror (888k+ downloads).
  - `kristaller486/dots.ocr-1.5`, `kristaller486/dots.ocr-1.5-svg` — re-uploads from ModelScope after HF takedown, by community member.
  - `dots-studio/dots.mocr`, `dots-studio/dots.mocr-svg` — mocr lineage.
- **Quantizations:** GGUF, AWQ 4-bit, MLX 4/5/6/8-bit, bnb 4-bit, NVFP4, MXFP4/8, CoreML, Apple MLX — maintained by the community.
- **Fine-tunes spotted on HF (representative):**
  - `wjbmattingly/old-church-slavonic-dots-ocr` (Old Church Slavonic)
  - `samaritan-ai/dots-ocr-samaritan-hebrew` (Samaritan Hebrew, tagged HTR)
  - `baohuynhbk14/dotsocr_du_multi_lang_v4.*` (multi-language)
  - `prithivMLmods/Dots.OCR-Latest-BF16` (community "latest" snapshot)
  - Several `ritu-kumari07/DotsOCR_*` PEFT/LoRA experiments.
- **Demo:** https://dotsocr.xiaohongshu.com/ (live, free).
- **Docker image:** `rednotehilab/dots.ocr` and `rednotehilab/dots1` on Docker Hub.

---

## 9. Citations

```bibtex
@misc{li2025dotsocrmultilingualdocumentlayout,
  title={dots.ocr: Multilingual Document Layout Parsing in a Single Vision-Language Model},
  author={Yumeng Li and Guang Yang and Hao Liu and Bowen Wang and Colin Zhang},
  year={2025},
  eprint={2512.02498},
  archivePrefix={arXiv},
  primaryClass={cs.CV},
  url={https://arxiv.org/abs/2512.02498}
}

@misc{zheng2026multimodalocrparsedocuments,
  title={Multimodal OCR: Parse Anything from Documents},
  author={Handong Zheng and Yumeng Li and Kaile Zhang and Liang Xin and Guangwei Zhao and Hao Liu and Jiayu Chen and Jie Lou and Jiyu Qiu and Qi Fu and Rui Yang and Shuo Jiang and Weijian Luo and Weijie Su and Weijun Zhang and Xingyu Zhu and Yabin Li and Yiwei Ma and Yu Chen and Zhaohui Yu and Guang Yang and Colin Zhang and Lei Zhang and Yuliang Liu and Xiang Bai},
  year={2026},
  eprint={2603.13032},
  archivePrefix={arXiv},
  primaryClass={cs.CV},
  url={https://arxiv.org/abs/2603.13032}
}
```

---

## 10. Primary Sources

- HF model cards (raw README files I read):
  - https://huggingface.co/rednote-hilab/dots.ocr — primary v1
  - https://huggingface.co/rednote-hilab/dots.mocr — current rebrand
  - https://huggingface.co/dots-studio/dots.ocr — community mirror
  - https://huggingface.co/kristaller486/dots.ocr-1.5 — community v1.5 mirror
  - https://huggingface.co/kristaller486/dots.ocr-1.5-svg — community v1.5-svg mirror
- HF API: `https://huggingface.co/api/models?search=DotsOCR` (60+ derived community models).
- HF config: `https://huggingface.co/dots-studio/dots.ocr/raw/main/config.json` (architecture details).
- GitHub: `https://github.com/rednote-hilab/dots.ocr` (now redirected under studio-dots-ai/dots.ocr).
- Blog (mirrored on GitHub): `https://raw.githubusercontent.com/rednote-hilab/dots.ocr/master/assets/blog.md`.
- arXiv abstracts (fetched): https://arxiv.org/abs/2512.02498 (dots.ocr v1) and https://arxiv.org/abs/2603.13032 (dots.mocr v1.5).
- Related: https://arxiv.org/abs/2506.05767 (RedNote's earlier **dots.llm1** 142B MoE — *not* the OCR model, but same vendor).
- Live demo: https://dotsocr.xiaohongshu.com/.

---

## Bottom Line for the requester

- DotsOCR is a real, well-documented RedNote product line: **dots.ocr** (2025-07, document parser) → **dots.ocr-1.5** (added SVG + web + scene text) → **dots.mocr** (2026-03 rebrand of 1.5, with a published paper).
- **Architecture:** 1.2B from-scratch ViT + 1.7B Qwen2.5-1.5B-base decoder (tied embeddings) = ~3B total.
- **SVG: yes, but only from v1.5 / dots.mocr onward**; v1 does not emit SVG. The dedicated `-svg` variant beats Gemini 3 Pro on every SVG benchmark reported (UniSVG, Chartmimic, Design2Code, Genexam, SciGen, ChemDraw).
- **Tables/Formulas:** native in v1 (HTML for tables, LaTeX for formulas).
- **Handwriting:** not a tested/claimed feature; only "old scans" and "notes" pages (likely handwritten-feeling but not labeled as such) are benchmarked.
- **Speed:** no official pages/sec or tokens/sec; deploy with vLLM ≥ 0.11.0 on one GPU.
- **Fox-1 and MMVet:** not reported anywhere I could find.
- **Positioning:** open-source SOTA on OmniDocBench v1/v1.5, olmOCR-Bench, XDocParse, layout detection, and image-to-SVG; second only to Gemini 3 Pro on the OCR Arena Elo leaderboard.