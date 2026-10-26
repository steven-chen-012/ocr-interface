# DeepSeek-OCR — Detailed Research Report

> Compiled from: arXiv:2510.18234 (Wei, Sun, Li — DeepSeek-AI, Oct 21 2025), the official GitHub & Hugging Face READMEs, and the follow-up DeepSeek-OCR‑2 repo. All numbers are quoted verbatim from those primary sources; nothing is invented. Where the primary sources are silent, the report says so.

---

## 1. Basic info

| Item | Value |
|---|---|
| Official name | **DeepSeek-OCR: Contexts Optical Compression** |
| Authors / org | Haoran Wei, Yaofeng Sun, Yukun Li — DeepSeek-AI |
| Release date | **2025-10-20** (model + paper). vLLM upstream support added **2025-10-23**. Follow-up "DeepSeek-OCR 2: Visual Causal Flow" announced **2026-01-27** (separate repo, separate model) |
| Paper | arXiv:2510.18234 (cs.CV), submitted 21 Oct 2025; CC-BY 4.0; [HTML](https://arxiv.org/html/2510.18234v1) |
| Model weights | [huggingface.co/deepseek-ai/DeepSeek-OCR](https://huggingface.co/deepseek-ai/DeepSeek-OCR) — MIT license, `transformers`-compatible, custom code, `image-text-to-text` pipeline tag |
| Total parameters | **≈ 3.4 B** (encoder ~380 M + decoder ~3 B), but **~950 M activated at inference** (380 M encoder + 570 M decoder) |
| Architecture | **Encoder–decoder VLM**. Encoder is the novel "DeepEncoder" (SAM-base + 16× conv compressor + CLIP-Large, serial). Decoder is **DeepSeek‑3B‑MoE** (a DeepSeekMoE) |
| Sequence length | 8 192 tokens (text-only training data and max generation length) |
| Supported input modalities | **Image only** (single image or PDF page). No native audio/video. Decoding is text. |
| Output modalities | Plain text, Markdown, HTML tables, chemical SMILES strings, geometry dictionaries, and free-form natural language. |

### 1.1 Architecture detail

- **DeepEncoder (≈ 380 M)** is the project's main contribution. It stacks three components in series:
  1. **SAM-base** (≈ 80 M, patch 16) — window-attention "perception" branch, takes 1024×1024 → 4096 patch tokens with acceptable activation.
  2. **2-layer conv "16× compressor"** (kernel 3, stride 2, padding 1; channels 256 → 1024; borrowed from Vary) — reduces the 4096 tokens to **256** tokens.
  3. **CLIP-Large** (≈ 300 M) with its patch-embedding layer removed — dense global-attention "knowledge" branch.
- **Decoder: DeepSeek-3B-MoE** with **64 routed experts + 2 shared experts**, activates **6 routed + 2 shared per token**, total activated params **≈ 570 M**, 12 transformer layers, AdamW step scheduler, init LR 3e-5.
- The decoder reconstructs text representation from compressed latent vision tokens: `f_dec : ℝ^{n × d_latent} → ℝ^{N × d_text}` with `n ≤ N`.

### 1.2 Multi-resolution modes (single model)

| Mode | Resolution | Vision tokens | Pre-process |
|---|---|---|---|
| Tiny | 512×512 | **64** | resize |
| Small | 640×640 | **100** | resize |
| Base | 1024×1024 | **256** | pad (keep aspect) |
| Large | 1280×1280 | **400** | pad (keep aspect) |
| Gundam (dynamic) | n × 640×640 tiles + 1 × 1024×1024 | **n·100 + 256** (n ∈ 2…9) | resize + pad |
| Gundam-M (continued-trained) | n × 1024×1024 tiles + 1 × 1280×1280 | n·256 + 400 | resize + pad |

For padded modes the *valid* vision token count is `N_valid = ⌈ N_actual · [1 − (max(w,h)−min(w,h))/max(w,h)] ⌉`.

### 1.3 Prompts (from official usage docs)

```python
# full document → markdown
"<image>\n<|grounding|>Convert the document to markdown."
# generic image OCR
"<image>\n<|grounding|>OCR this image."
# free-text no layout
"<image>\nFree OCR."
# figure-only parse
"<image>\nParse the figure."
# general describe
"<image>\nDescribe this image in detail."
# locate text in image (grounding/referring)
"<image>\nLocate <|ref|>xxxx<|/ref|> in the image."
```

The `<|grounding|>` token forces the model to emit bounding-box coordinates normalised into 1000 bins alongside the recognised text.

---

## 2. Handwriting recognition performance

**Bottom line: there are no published handwriting-specific numbers in the paper, README, or model card.** The paper does not list IAM, CASIA, IAM-HW, Bentham, RIMES, or any other handwriting corpus. I searched the paper text and the GitHub/Hugging Face README — none of them report handwriting CER/WRR.

What is reported for text recognition:

- **Document OCR data**: 30 M PDF pages covering ~100 languages (Chinese+English 25 M, others 5 M). Fine-annotated pages: 2 M Chinese + 2 M English with PP-DocLayout + MinerU + GOT-OCR2.0 labels. Minority languages get a "model flywheel" (train a GOT-OCR2.0 on small patches labelled by fitz) yielding 600 K samples. These are **mostly typeset printed text**, not handwriting.
- **Natural-scene OCR data**: 10 M Chinese (Wukong) + 10 M English (LAION), labelled with PaddleOCR. This data *may* incidentally contain handwritten signs/posters, but the paper does not isolate handwriting results.
- **No IAM, CASIA-HWDB, MNIST, CVL, ICDAR-HW, Bentham, etc. mentioned.** If you need handwriting numbers you would have to run the model yourself.

The prompt that would be used for handwritten scenes is the generic `"<image>\nFree OCR."` (no layout) or `"<image>\n<|grounding|>OCR this image."` (with bounding boxes). A user familiar with scene text recognition systems can probably get reasonable English/Chinese handwriting through the natural-scene branch, but **I cannot quote a benchmark** — none is published.

---

## 3. Figure / diagram / formula understanding

### 3.1 What the model can output for non-text content

| Visual content | Output format | Training data |
|---|---|---|
| **Charts** (line, bar, pie, composite) | **HTML `<table>`** representation | 10 M synthetic charts (pyecharts + matplotlib, following OneChart recipe) |
| **Chemical formulas** | **SMILES string** | 5 M image–SMILES pairs rendered with RDKit from PubChem |
| **Plane geometry figures** | **Dictionary** (line segments, endpoint coordinates, line-segment types) encoded with Slow Perception's perception-ruler | 1 M synthetic plane-geometry images |
| **Tables inside documents** | **HTML `<table>`** (improved by 3 M Word documents) | 3 M Word docs + open-source supplements |
| **Mathematical formulas** | LaTeX (via the 3 M Word data and standard OCR 1.0 pipeline) | implicit in document OCR + Word data |
| **Natural images** | free-form description / captions | LAION subset, 20 % of training mix |
| **Bounding-box localisation** | `<|ref|>…<|/ref|>` tokens with 1000-bin-normalised coords | included in fine annotations |

The paper explicitly states: *"We define chart parsing as **image-to-HTML-table** conversion task"* and that for plane geometry they convert the ground truth to a **dictionary** of line-segments, endpoint coordinates, and line-segment types — **not** SVG.

### 3.2 Performance on chart/formula/table parsing

The published evaluation is on **OmniDocBench** (edit-distance, lower is better). Headline numbers from the paper (Table 3, with my notes on truncation):

| Model | Tokens / page | EN overall | EN text | EN formula | EN table | ZH overall | ZH text | ZH formula | ZH table |
|---|---|---|---|---|---|---|---|---|---|
| Dolphin (pipeline) | — | 0.356 | 0.352 | 0.465 | 0.258 | 0.440 | 0.440 | 0.604 | 0.367 |
| Marker | — | 0.296 | 0.085 | 0.374 | 0.609 | 0.497 | 0.293 | 0.688 | 0.678 |
| Mathpix | — | 0.191 | 0.105 | 0.306 | 0.243 | 0.364 | 0.381 | 0.454 | 0.320 |
| MinerU-2.1.1 | — | 0.162 | 0.072 | 0.313 | 0.166 | 0.244 | 0.111 | 0.581 | 0.150 |
| MonkeyOCR-1.2B | — | 0.154 | 0.062 | 0.295 | 0.164 | 0.263 | 0.179 | 0.464 | 0.168 |
| PP-StructureV3 | — | 0.152 | 0.073 | 0.295 | 0.162 | 0.223 | 0.136 | 0.535 | 0.111 |
| Nougat | (truncated) | … | … | … | … | … | … | … | … |
| **DeepSeek-OCR (claimed)** | <800 (vs MinerU 6000+) | "surpasses GOT-OCR2.0 with only 100 tokens vs 256 tokens/page" and "outperforms MinerU2.0 with fewer than 800 vision tokens" — exact cells were truncated in my fetch of the HTML, but the abstract and Fig. 1(b) claim SOTA among end-to-end models with the **fewest** vision tokens. |

> Caveat: the OmniDocBench table cells for DeepSeek-OCR (and for end-to-end models Nougat/GOT-OCR2.0/Qwen-VL/InternVL) sit further down Table 3 and were cut off in every mirror I could fetch (arXiv HTML, ar5iv, HF, GitHub). The paper's prose claim — "surpasses GOT-OCR2.0 (256 tokens/page) using only 100 vision tokens, and outperforms MinerU2.0 (6000+ tokens/page on average) while utilizing fewer than 800 vision tokens" — is from the abstract and the caption of Fig. 1(b). **I therefore cannot quote per-column edit-distance numbers for DeepSeek-OCR on OmniDocBench.** Anyone who needs them should open `DeepSeek_OCR_paper.pdf` in the repo or the arXiv PDF directly.

### 3.3 Structured-format support summary

- ✅ **HTML** (charts, tables).
- ✅ **LaTeX-style math** (mathematical formulas inside documents; the README explicitly references this through the formula data).
- ✅ **Markdown** (full document conversion with grounding coords).
- ✅ **SMILES** (chemical structures).
- ✅ **JSON-like dictionaries** (plane geometry).
- ✅ **Bounding-box grounded text** (via `<|grounding|>` + `<|ref|>` tokens, coordinates in 1000-bin normalised form).
- ❌ **SVG / vector graphics output is not mentioned** anywhere in the paper, README, or HF card. See §4.

---

## 4. SVG generation

**No.** DeepSeek-OCR does not natively emit SVG. The chart branch outputs HTML `<table>` only, and the geometry branch outputs a Slow-Perception-style dictionary. The model's supported prompt list contains no SVG-specific instruction.

For images (general visual understanding) the prompt `"<image>\nDescribe this image in detail."` could *theoretically* be coaxed into outputting SVG text in an ad-hoc prompt, but (a) this is not advertised, (b) the official system isn't trained or tokenised with SVG keywords, and (c) no demo / example is provided in either repo.

If SVG-from-image is what you need, GOT-OCR2.0 has a `render` mode that ships with an explicit SVG output path — DeepSeek-OCR does not appear to have inherited or re-implemented that capability.

---

## 5. Speed / throughput

All numbers come from the paper or the official README.

| Setting | Throughput | Source |
|---|---|---|
| PDF processing, single A100-40G (vLLM) | **≈ 2 500 generated tokens / s** (≈ 200 K pages/day) | README, "concurrency ~2500tokens/s(an A100-40G)" |
| Single A100-40G data-generation throughput | **200 000+ pages/day** | arXiv abstract |
| 20 nodes × 8 × A100-40G | **33 million pages/day** (≈ 1.65 M pages/day/node) | arXiv §1 |
| Training (multimodal data) | **70 B tokens/day** | arXiv §3.5.2 |
| Training (text-only data) | **90 B tokens/day** | arXiv §3.5.2 |
| Fox compression study (Tiny mode 64 vis-tok) | 96.5 % precision @ 10.5× compression on 600–700-text-token pages | Table 2 |
| Fox compression study (Small mode 100 vis-tok) | 98.5 % precision @ 6.7× compression on 600–700-text-token pages | Table 2 |
| Fox compression study, worst bucket (1200–1300 text tokens, Tiny mode) | 59.1 % precision @ 19.7× compression | Table 2 |

What the paper does **not** publish:

- A clean **tokens/sec by resolution table** (Tiny/Small/Base/Large/Gundam). The README mentions "streaming output" mode but no per-mode throughput.
- A clean **pages/sec** figure for non-PDF batch inference. Only the 2 500 tok/s and 200 K pages/day numbers are given.
- Latency / time-to-first-token numbers.

If you need those, you'd run `run_dpsk_ocr_image.py` and `run_dpsk_ocr_pdf.py` on your own hardware. The codebase ships vLLM recipes that include an `NGramPerReqLogitsProcessor` (ngram_size=30, window_size=90, whitelisting `<td>`/`</td>` token IDs 128821/128822) which is used to keep `<td>` tags balanced inside HTML tables.

---

## 6. Known limitations & strengths vs. traditional OCR

### 6.1 Stated and implied strengths

1. **Single end-to-end VLM** replaces the classical pipeline (text-detection → text-recognition → table-extraction → formula-recognition). No separate detection/recognition experts.
2. **Massive token compression** with competitive accuracy: 97 % decoding precision at <10× compression, ~90 % at 10–12×, ~60 % at 20× (Fox benchmark, paper §1, Table 2).
3. **State-of-the-art on OmniDocBench among end-to-end models with the fewest vision tokens** — beats GOT-OCR2.0 with 100 vs 256 tokens, beats MinerU2.0 with <800 vs 6000+ tokens (abstract + Fig. 1(b)).
4. **Multi-resolution in one model** (Tiny → Large → Gundam dynamic), with the smallest mode using just **64 vision tokens** for a 512×512 image — enables cheap high-throughput inference.
5. **Structured output beyond text**: HTML tables, SMILES, plane-geometry dictionaries, LaTeX math, grounded bounding boxes.
6. **Strong multilingual coverage**: ~100 languages in training data; explicit Chinese + English specialisation for natural-scene OCR.
7. **Very high data-generation throughput** for LLM/VLM pretraining pipelines: 33 M pages/day on a 20×8 A100-40G cluster, 200 K pages/day on a single A100-40G.
8. **Native vLLM support** (since 2025-10-23) and **Hugging Face `transformers` support** with `trust_remote_code=True`.

### 6.2 Stated and implied limitations / caveats

1. **The paper frames itself as a "preliminary proof-of-concept for vision-text compression"**, not a SOTA OCR engine. Many claims are about compression ratios, not absolute top accuracy.
2. **OCR precision collapses at extreme compression**: ~60 % at 20×; ~59 % in the worst bucket (Tiny mode on 1200–1300 text-token pages). Pick the mode accordingly.
3. **Not a general VLM**: only ~20 % of training data is general vision; the model is tuned for OCR/document parsing. General QA, instruction-following, etc. are explicitly out-of-scope.
4. **No handwriting benchmarks** — natural-scene branch exists but the paper never isolates handwriting. If you need IAM/CASIA-style numbers, you must evaluate yourself.
5. **No SVG output**. Charts → HTML tables; geometry → dict; no vector-graphics generation path.
6. **Single-image input only.** Multi-image / multi-page reasoning has to be done by the caller (e.g. by feeding pages one-by-one through the model).
7. **Sequence length is 8 192** for both training text and generation. Very long documents need streaming / chunking; the paper does not discuss how to handle a >8 K-token page.
8. **Padded-base / padded-large modes waste tokens** for very elongated aspect ratios — the model ships a `N_valid` correction but it still costs FLOPs.
9. **Hardware floor is high**: an A100-40G is referenced throughout (training used 20 nodes × 8 A100-40G = 160 GPUs). Smaller GPUs are not benchmarked.
10. **Decoder is only 570 M activated parameters**, so on truly exotic outputs (long Chinese paragraphs, complex chemistry, dense math) the model may not match a much larger general LLM-VLM. The paper explicitly notes it is suitable as a "domain-centric (OCR for us) VLM".
11. **Relative to GOT-OCR2.0 and MinerU2.0** DeepSeek-OCR wins on the *vision-token budget* but the per-column edit-distance numbers I was able to fetch are partial — anyone needing apples-to-apples per-benchmark numbers should pull Table 3 directly from the PDF.
12. **Compared to traditional OCR (Tesseract / PaddleOCR / EasyOCR)**: those are CPU-friendly, deterministic, character-level, well-understood, and easy to ship. DeepSeek-OCR is GPU-only, non-deterministic by default (temperature in vLLM recipe is 0.0 but the decoder is still a generative LM), requires a CUDA + flash-attn + vLLM stack, and trades the determinism of a classical recogniser for the flexibility of an LLM that can also emit structured markup. It is therefore best viewed as a **document-parsing model**, not a drop-in Tesseract replacement.

### 6.3 Quick "use it if / don't use it if"

- ✅ Use it for: high-volume PDF/image-to-Markdown pipelines, multilingual print OCR (≈ 100 languages), chart/table/figure parsing, formula extraction, batch synthetic-data generation for LLM/VLM training.
- ⚠️ Evaluate first for: handwriting-heavy archives, very low-quality scans, real-time latency-sensitive workloads, CPU-only deployments, SVG-from-image tasks (no support).

---

## 7. Source URLs

- arXiv abstract: https://arxiv.org/abs/2510.18234
- arXiv HTML: https://arxiv.org/html/2510.18234v1
- GitHub repo: https://github.com/deepseek-ai/DeepSeek-OCR
- GitHub raw README: https://raw.githubusercontent.com/deepseek-ai/DeepSeek-OCR/main/README.md
- Hugging Face model card: https://huggingface.co/deepseek-ai/DeepSeek-OCR
- HF raw README: https://huggingface.co/deepseek-ai/DeepSeek-OCR/raw/main/README.md
- HF papers page: https://huggingface.co/papers/2510.18234
- vLLM recipe: https://docs.vllm.ai/projects/recipes/en/latest/DeepSeek/DeepSeek-OCR.html
- Follow-up DeepSeek-OCR 2: https://github.com/deepseek-ai/DeepSeek-OCR-2 (separate repo, separate weights, arXiv:2601.20552, Visual Causal Flow)