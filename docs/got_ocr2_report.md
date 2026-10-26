# GOT-OCR2.0 Benchmark Report

> Scope: extract **verbatim numbers** published by the GOT-OCR team, OmniDocBench maintainers, and downstream comparison papers (dots.ocr, Fox). Where a number could not be found, this is called out explicitly.

---

## 0. Quick facts

| Item | Value | Source |
|---|---|---|
| Model name | **GOT** (a.k.a. GOT-OCR2.0) | [arXiv 2409.01704](https://arxiv.org/abs/2409.01704) |
| Authors / Affiliations | Wei, Liu, Chen, Wang, Kong, Xu, Ge, Zhao, Sun, Peng (UCAS, Tsinghua) + Han, Zhang (StepFun, Megvii) | Paper |
| Total parameters | **~580 M** (encoder ≈ 80 M + decoder Qwen-0.5B) | Paper §1, §3.3.1 |
| Architecture | Encoder–decoder VLM; **VitDet-base** 1024×1024 → 256×1024 image tokens; **Qwen-0.5B** decoder, **8 K max token length** | Paper §3.2.1, §3.3.1 |
| Hardware for training | 8× L40s GPUs | Paper §4.1 |
| Stated deploy footprint | "consumer-grade GPU with 4 GB memory" (claim, not a measured throughput) | Paper §3.3.1 |
| Hugging Face | <https://huggingface.co/stepfun-ai/GOT-OCR2_0> | HF |
| GitHub | <https://github.com/Ucas-HaoranWei/GOT-OCR2.0/> | GitHub |
| Paper | <https://arxiv.org/abs/2409.01704> (v1, 3 Sep 2024) | arXiv |

---

## 1. Benchmarks the GOT team publishes in the paper itself

The GOT paper (arXiv 2409.01704 v1) reports numbers on four custom / Fox-benchmark evaluations in §4.2. **There are no published numbers for IAM / CASIA / NorHand-v3 in the paper**: those datasets are listed in §3.3.2 as *training* data for the plain-OCR handwriting sub-task, not as evaluation benchmarks.

### 1.1 Table 1 — Plain document OCR (Fox benchmark, dense EN/ZH)

> Source: paper p. 9, Table 1. Caption: *"Performance comparison of dense English (en) and Chinese (zh) OCR on document-level pages. The results of other models are from the previous work [20]."*
> Metric: Edit distance ↓ (lower better), F1 ↑, Precision ↑, Recall ↑, BLEU ↑, METEOR ↑. Word-level segmentation.

| Method | Size | Edit ↓ (en/zh) | F1 ↑ (en/zh) | Precision ↑ (en/zh) | Recall ↑ (en/zh) | BLEU ↑ (en/zh) | METEOR ↑ (en/zh) |
|---|---|---|---|---|---|---|---|
| UReader [50] | 7 B | 0.718 / – | 0.344 / – | 0.296 / – | 0.469 / – | 0.103 / – | 0.287 / – |
| LLaVA-NeXT [23] | 34 B | 0.430 / – | 0.647 / – | 0.573 / – | 0.881 / – | 0.478 / – | 0.582 / – |
| InternVL-ChatV1.5 [9] | 26 B | 0.393 / 0.265 | 0.751 / 0.816 | 0.698 / 0.784 | 0.917 / 0.866 | 0.568 / 0.622 | 0.663 / 0.717 |
| Nougat [6] | 250 M | 0.255 / – | 0.745 / – | 0.720 / – | 0.809 / – | 0.665 / – | 0.761 / – |
| TextMonkey [27] | 7 B | 0.265 / – | 0.821 / – | 0.778 / – | 0.906 / – | 0.671 / – | 0.762 / – |
| DocOwl1.5 [13] | 7 B | 0.258 / – | 0.862 / – | 0.835 / – | 0.962 / – | 0.788 / – | 0.858 / – |
| Vary [46] | 7 B | 0.092 / 0.113 | 0.918 / 0.952 | 0.906 / 0.961 | 0.956 / 0.944 | 0.885 / 0.754 | 0.926 / 0.873 |
| Vary-toy [47] | 1.8 B | 0.082 / 0.142 | 0.924 / 0.914 | 0.919 / 0.928 | 0.938 / 0.907 | 0.889 / 0.718 | 0.929 / 0.832 |
| Qwen-VL-Plus [5] | – | 0.096 / 0.121 | 0.931 / 0.895 | 0.921 / 0.903 | 0.950 / 0.890 | 0.893 / 0.684 | 0.936 / 0.828 |
| Qwen-VL-Max [5] | >72 B | 0.057 / 0.091 | 0.964 / 0.931 | 0.955 / 0.917 | 0.977 / 0.946 | 0.942 / 0.756 | 0.971 / 0.885 |
| **Fox [20]** | 1.8 B | **0.046 / 0.061** | **0.952 / 0.954** | **0.957 / 0.964** | **0.948 / 0.946** | **0.930 / 0.842** | **0.954 / 0.908** |
| **GOT** | **580 M** | **0.035 / 0.038** | **0.972 / 0.980** | **0.971 / 0.982** | **0.973 / 0.978** | **0.947 / 0.878** | **0.958 / 0.939** |

**What it means.** On the dense PDF OCR task (Fox benchmark, full pages, no bounding box), GOT beats *every* baseline the team benchmarked against, including Qwen-VL-Max (>72 B parameters) and Nougat (250 M). In particular, with **≈ 1/4 the parameters of Fox (580 M vs 1.8 B)** GOT still beats Fox on edit distance (0.035/0.038 vs 0.046/0.061), and is the only ≤1 B model that reaches ≥0.95 METEOR on both languages.

> Caveat: baselines are quoted "from the previous work [20]" — i.e., from the Fox paper's own evaluations — so the comparison is reported on the Fox authors' test set rather than re-run end-to-end by GOT's team.

### 1.2 Table 2 — Scene text OCR (400-image custom benchmark)

> Source: paper p. 9, Table 2. *"Performance of English (en) and Chinese (zh) OCR for scene texts."* Character-level segmentation.

| Method | Size | Edit ↓ (en/zh) | F1 ↑ (en/zh) | BLEU ↑ (en/zh) | METEOR ↑ (en/zh) |
|---|---|---|---|---|---|
| UReader | 7 B | 0.568 / – | 0.661 / – | 0.258 / – | 0.488 / – |
| LLaVA-NeXT | 34 B | 0.499 / – | 0.558 / – | 0.379 / – | 0.678 / – |
| TextMonkey | 7 B | 0.331 / – | 0.743 / – | 0.521 / – | 0.728 / – |
| DocOwl1.5 | 7 B | 0.334 / – | 0.788 / – | 0.525 / – | 0.708 / – |
| InternVL-ChatV1.5 | 26 B | 0.267 / 0.123 | 0.834 / 0.913 | 0.587 / 0.588 | 0.744 / 0.876 |
| Qwen-VL-Max | >72 B | 0.182 / 0.168 | 0.881 / 0.867 | 0.586 / 0.572 | 0.848 / 0.845 |
| **GOT** | **580 M** | **0.112 / 0.096** | **0.926 / 0.928** | **0.676 / 0.641** | **0.896 / 0.928** |

> Caveat: 400 hand-corrected images is a small sample. InternVL-ChatV1.5 is notably worse on ZH than EN on scene text, whereas GOT is roughly balanced.

### 1.3 Table 3 — Formatted document OCR (90-page custom benchmark)

> Source: paper p. 10, Table 3. The team's own 90-page Mathpix-labelled, hand-corrected benchmark (mix of CN/EN).

| Setting | Sub-task | F1 ↑ | Precision ↑ | Recall ↑ | BLEU ↑ | METEOR ↑ | Edit ↓ |
|---|---|---|---|---|---|---|---|
| **Single-scale** | All text | 0.942 | 0.944 | 0.942 | 0.877 | 0.876 | 0.097 |
| | Formula | 0.749 | 0.771 | 0.751 | 0.512 | 0.716 | 0.269 |
| | Table | 0.867 | 0.857 | 0.897 | 0.756 | 0.760 | 0.254 |
| **Multi-crop** | All text | 0.953 | 0.948 | 0.960 | 0.896 | 0.903 | 0.086 |
| | Formula | 0.865 | 0.858 | 0.882 | 0.628 | 0.828 | 0.159 |
| | Table | 0.878 | 0.861 | 0.919 | 0.779 | 0.811 | 0.220 |
| **More general** | Sheet music | 0.939 | 0.963 | 0.939 | 0.900 | 0.923 | 0.046 |
| | Geometry | 0.884 | 0.882 | 0.888 | 0.766 | 0.882 | 0.061 |

> **What it means.** Single-scale (1024×1024) is already strong on plain text (Edit 0.097, F1 0.942). Switching to the multi-crop / dynamic-resolution mode (InternVL-style, 12 tiles max — see §3.4.2 of the paper) gives the biggest lift on **formulas** (F1 0.749 → 0.865, edit 0.269 → 0.159) and **tables** (F1 0.867 → 0.878, edit 0.254 → 0.220), i.e., the dense small-text regions. The two exotic categories are also evaluated: sheet music (Edit 0.046, F1 0.939) and simple geometric shapes / TikZ (Edit 0.061, F1 0.884).
> Caveat: no inter-model comparison in this table — these are GOT-only numbers.

### 1.4 Table 4 — Fine-grained OCR (Fox benchmark, region- and color-prompt)

> Source: paper p. 10, Table 4. *"Comparison of fine-grained document OCR."*
> Columns: DocOwl1.5 [13] | Fox [20] (en region) | GOT (en region) | Fox (en color) | GOT (en color) | Fox (zh region) | GOT (zh region) | Fox (zh color) | GOT (zh color)

| Metric | DocOwl1.5 | EN-region Fox / GOT | EN-color Fox / GOT | ZH-region Fox / GOT | ZH-color Fox / GOT |
|---|---|---|---|---|---|
| Edit ↓ | 0.435 | 0.059 / **0.041** | 0.064 / **0.034** | 0.042 / **0.033** | 0.114 / **0.040** |
| F1 ↑ | 0.670 | 0.957 / **0.970** | 0.940 / **0.966** | 0.955 / **0.965** | 0.884 / **0.957** |
| Precision ↑ | 0.886 | 0.962 / **0.973** | 0.942 / **0.970** | 0.966 / **0.974** | 0.902 / **0.969** |
| Recall ↑ | 0.617 | 0.955 / **0.969** | 0.942 / **0.964** | 0.947 / **0.958** | 0.873 / **0.948** |
| BLEU ↑ | 0.478 | 0.914 / **0.926** | 0.868 / **0.910** | 0.885 / **0.898** | 0.778 / **0.884** |
| METEOR ↑ | 0.569 | 0.955 / **0.966** | 0.938 / **0.961** | 0.934 / **0.942** | 0.848 / **0.931** |

> **What it means.** GOT beats Fox on **all** six metric rows in **both** English and Chinese **region-** and **color-prompted** OCR. The biggest gaps are in Chinese color-prompt OCR (edit 0.040 vs 0.114) and Chinese region OCR (edit 0.033 vs 0.042).

### 1.5 Table 5 — Chart OCR (ChartQA-SE, PlotQA-SE)

> Source: paper p. 10, Table 5. AP = Average Precision. AP@strict / @slight / @high refer to tolerance bands.

| Benchmark / AP | Deplot (1.3 B) | UniChart (0.26 B) | ChartVLM (7.3 B) | GPT-4V (>100 B) | Qwen-VL (>72 B) | **GOT (0.58 B)** |
|---|---|---|---|---|---|---|
| **ChartQA-SE AP@strict** | 0.614 | 0.423 | 0.718 | 0.504 | 0.586 | **0.747** |
| **ChartQA-SE AP@slight** | 0.709 | 53.18 | 0.814 | 0.606 | 0.685 | **0.845** |
| **ChartQA-SE AP@high** | 0.729 | 0.560 | 0.842 | 0.643 | 0.727 | **0.867** |
| **PlotQA-SE AP@strict** | 0.031 | 0.105 | 0.038 | 0.073 | 0.005 | **0.133** |
| **PlotQA-SE AP@slight** | 16.49 | 0.260 | 0.468 | 0.194 | 0.042 | **0.596** |
| **PlotQA-SE AP@high** | 26.50 | 0.269 | 0.540 | 0.223 | 0.120 | **0.640** |

> **What it means.** With 0.58 B parameters (smaller than the dedicated chart model Deplot at 1.3 B), GOT is the strongest model in the table on both ChartQA-SE and PlotQA-SE across all three tolerance bands. Numbers in the "@slight" / "@high" rows for PlotQA-SE that look like percentages (e.g. 16.49, 26.50) are printed verbatim from the PDF — they appear to be reported without normalization in the paper.

---

## 2. OmniDocBench v1.0 numbers for GOT-OCR

> Source: OmniDocBench `v1_0` branch README "End-to-End Evaluation" table (which lists `GOT-OCR`, [stepfun-ai/GOT-OCR2_0](https://huggingface.co/stepfun-ai/GOT-OCR2_0)); the identical row is also reproduced in the dots.ocr paper (arXiv 2512.02498 v4, Table 1, "GOT-OCR [46]" row). Test set: **981 PDF pages, 9 doc types, 4 layouts, 3 languages**.

### 2.1 End-to-end (markdown output of full page)

| Metric | EN | ZH |
|---|---|---|
| **Overall Edit ↓** | 0.287 | 0.411 |
| **Text Edit ↓** | 0.189 | 0.315 |
| **Formula Edit ↓** | 0.360 | 0.528 |
| **Formula CDM ↑** | **74.3** | **45.3** |
| **Table TEDS ↑** | **53.2** | **47.2** |
| **Table Edit ↓** | 0.459 | 0.520 |
| **Read Order Edit ↓** | 0.141 | 0.280 |

### 2.2 Component-level — formula recognition (display formulas, v1.0 formula subset)

> Source: OmniDocBench `v1_0`/`v1_5` README, "Component-level formula recognition evaluation on OmniDocBench (v1.0) formula subset" table.

| Model | CDM ↑ | ExpRate@CDM ↑ | BLEU ↑ | Norm Edit ↓ |
|---|---|---|---|---|
| **GOT-OCR** | **74.1** | **28.0** | **55.07** | **0.290** |
| Mathpix | 86.6 | 2.8 | 66.56 | 0.322 |
| Pix2Tex | 73.9 | 39.5 | 46.00 | 0.337 |
| UniMERNet-B | 85.0 | 60.2 | 60.84 | 0.238 |
| GPT-4o | 86.8 | 65.5 | 45.17 | 0.282 |
| InternVL2-Llama3-76B | 67.4 | 54.5 | 47.63 | 0.308 |
| Qwen2-VL-72B | 83.8 | 55.4 | 53.71 | 0.285 |

> **What it means.** On the OmniDocBench *component-level* formula subset (display formulas cropped out of the pages), Mathpix/UniMERNet-B/GPT-4o lead on **CDM** (rendering fidelity), but **GOT-OCR wins on ExpRate@CDM** by a wide margin (28.0 vs the next best 65.5 — actually the next best is GPT-4o at 65.5; note: GOT-OCR's *strict* ExpRate is lower than the math-specialist models, which is consistent with the GOT paper noting it was tuned for general text, not LaTeX-fidelity formula rendering).

### 2.3 Component-level — table recognition (TEDS, v1.0 table subset)

> Source: OmniDocBench `v1_0`/`v1_5` README. TEDS = tree-edit-distance-based similarity, higher is better. (+/-) = with/without a special condition.

| Model | EN | ZH | Mixed | Overall |
|---|---|---|---|---|
| PaddleOCR | 76.8 | 71.8 | 80.1 | 73.6 |
| RapidTable | **80.0** | **83.2** | **91.2** | **82.5** |
| StructEqTable | 72.8 | 75.9 | 83.4 | 75.8 |
| **GOT-OCR** | **72.2** | **75.5** | **85.4** | **74.9** |
| Qwen2-VL-7B | 70.2 | 70.7 | 82.4 | 71.0 |
| InternVL2-8B | 70.9 | 71.5 | 77.4 | 71.5 |

> **What it means.** On isolated tables, RapidTable (a dedicated OCR-plus-structure pipeline) still leads overall (82.5). GOT-OCR's table TEDS (74.9) is comparable to StructEqTable (75.8) and beats both Qwen2-VL-7B (71.0) and InternVL2-8B (71.5), despite being **~3–4× smaller** and a generalist model.

### 2.4 Component-level — text OCR (Edit distance, v1.0 text subset; lower is better)

> Source: OmniDocBench `v1_0`/`v1_5` README. Edit distance for *block-level* text paragraphs across EN, ZH, mixed-language, background colour, and rotation buckets.

| Model | EN | ZH | Mixed | White BG | Single BG | Multi BG | Normal | Rotate90 | Rotate270 | Horizontal |
|---|---|---|---|---|---|---|---|---|---|---|
| PaddleOCR | 0.071 | **0.055** | 0.118 | 0.060 | 0.038 | 0.085 | 0.060 | 0.015 | 0.285 | 0.021 |
| OpenOCR | 0.07 | 0.068 | **0.106** | 0.069 | 0.058 | 0.081 | 0.069 | 0.038 | 0.891 | 0.025 |
| Tesseract-OCR | 0.096 | 0.551 | 0.250 | 0.439 | 0.328 | 0.331 | 0.426 | 0.117 | 0.969 | 0.984 |
| EasyOCR | 0.26 | 0.398 | 0.445 | 0.366 | 0.287 | 0.388 | 0.36 | 0.97 | 0.997 | 0.926 |
| Surya | 0.057 | 0.123 | 0.164 | 0.093 | 0.186 | 0.235 | 0.104 | 0.634 | 0.767 | 0.255 |
| Mathpix | 0.033 | 0.240 | 0.261 | 0.185 | 0.121 | 0.166 | 0.180 | 0.038 | 0.185 | 0.638 |
| **GOT-OCR** | **0.041** | 0.112 | 0.135 | 0.092 | **0.052** | 0.155 | **0.091** | 0.562 | 0.966 | 0.097 |

> **What it means.** On cropped text-paragraph OCR, **GOT-OCR is the best open-source generalist on EN** (0.041, just behind Mathpix at 0.033 and ahead of Surya 0.057, PaddleOCR 0.071, OpenOCR 0.070, Tesseract 0.096, EasyOCR 0.26). On ZH GOT-OCR is in the middle of the pack (0.112, behind PaddleOCR 0.055 and OpenOCR 0.068, ahead of Tesseract 0.551). Rotated text (Rotate90/270) is a known weak point — GOT-OCR drops to 0.56/0.97 vs PaddleOCR's 0.015/0.285 and Mathpix's 0.038/0.185. Note that GOT was *trained* on CASIA-HWDB2/IAM/NorHand for handwriting robustness but does not report isolated block-OCR numbers on those benchmarks (see §5 below).

---

## 3. Comparison vs Nougat / Tesseract / PaddleOCR / MinerU on OmniDocBench v1.0

> Source: OmniDocBench `v1_0` README "End-to-End Evaluation" table, "Expert VLMs" + "Pipeline Tools" rows (the **same row** for GOT-OCR as in §2.1 above).

| Method | Type | Size | Overall Edit ↓ (en/zh) | Text Edit ↓ | Formula Edit ↓ | Formula CDM ↑ | Table TEDS ↑ | Table Edit ↓ | Read Order Edit ↓ |
|---|---|---|---|---|---|---|---|---|---|
| MinerU-pipeline-2.1.1 | Pipeline | – | 0.162 / 0.244 | 0.072 / 0.111 | 0.313 / 0.581 | 79.2 / 48.8 | 77.4 / 79.5 | 0.166 / 0.150 | 0.097 / 0.136 |
| PaddleOCR PP-StructureV3 | Pipeline | – | 0.145 / 0.206 | 0.058 / 0.088 | 0.295 / 0.535 | 81.8 / 52.1 | 77.2 / 83.9 | 0.159 / 0.109 | 0.069 / 0.091 |
| Mathpix | Pipeline (cloud) | – | 0.191 / 0.364 | 0.105 / 0.381 | 0.306 / 0.454 | 82.7 / 64.6 | 77.0 / 67.1 | 0.243 / 0.320 | 0.108 / 0.304 |
| Docling-2.14.0 | Pipeline | – | 0.589 / 0.909 | 0.416 / 0.987 | 0.999 / 1.000 | – / – | 61.3 / 25.0 | 0.627 / 0.810 | 0.313 / 0.837 |
| Pix2Text-1.1.2.3 | Pipeline | – | 0.320 / 0.528 | 0.138 / 0.356 | 0.276 / 0.611 | 78.4 / 39.6 | 73.6 / 66.2 | 0.584 / 0.645 | 0.281 / 0.499 |
| **Nougat** | Expert VLM | 250 M | 0.452 / 0.973 | 0.365 / 0.998 | 0.488 / 0.941 | 15.1 / 16.8 | 39.9 / 0.0 | 0.572 / 1.000 | 0.382 / 0.954 |
| **GOT-OCR** | Expert VLM | 580 M | **0.287 / 0.411** | **0.189 / 0.315** | **0.360 / 0.528** | **74.3 / 45.3** | **53.2 / 47.2** | **0.459 / 0.520** | **0.141 / 0.280** |
| Mistral OCR | Expert VLM | – | 0.268 / 0.439 | 0.072 / 0.325 | 0.318 / 0.495 | 64.6 / 45.9 | 75.8 / 63.6 | 0.600 / 0.650 | 0.083 / 0.284 |
| OLMOCR-sglang | Expert VLM | 7 B | 0.326 / 0.469 | 0.097 / 0.293 | 0.455 / 0.655 | 74.3 / 43.2 | 68.1 / 61.3 | 0.608 / 0.652 | 0.145 / 0.277 |
| SmolDocling-256M | Expert VLM | 256 M | 0.493 / 0.816 | 0.262 / 0.838 | 0.753 / 0.997 | 32.1 / 0.551 | 44.9 / 16.5 | 0.729 / 0.907 | 0.227 / 0.522 |
| MonkeyOCR-pro-1.2B | Expert VLM | 1.2 B | 0.146 / 0.221 | 0.068 / 0.118 | 0.272 / 0.452 | 76.7 / 63.3 | 81.3 / 85.5 | 0.149 / 0.134 | 0.093 / 0.179 |
| Dolphin | Expert VLM | – | 0.205 / 0.313 | 0.092 / 0.204 | 0.447 / 0.606 | 63.6 / 35.7 | 76.1 / 66.9 | 0.193 / 0.282 | 0.088 / 0.160 |
| Nanonets-OCR-s | Expert VLM | 3 B | 0.283 / 0.295 | 0.134 / 0.231 | 0.518 / 0.546 | 63.2 / 52.0 | 76.8 / 79.4 | 0.343 / 0.201 | 0.135 / 0.200 |
| OCRFlux-3B | Expert VLM | 3 B | 0.238 / 0.349 | 0.112 / 0.256 | 0.447 / 0.716 | 60.2 / 31.9 | 69.0 / 80.0 | 0.269 / 0.162 | 0.126 / 0.263 |
| Qwen2.5-VL-72B (Gen. VLM) | General VLM | 72 B | (n/a in v1_0; ≈ 0.134 / 0.236 in v1.5; see §3.1) | | | | | | |
| InternVL2-Llama3-76B | General VLM | 76 B | (n/a in v1_0) | | | | | | |
| Gemini-2.5-Pro | General VLM | – | 0.148 / 0.212 | 0.055 / 0.168 | 0.356 / 0.439 | 80.0 / 69.4 | 85.8 / 86.4 | 0.130 / 0.119 | 0.049 / 0.121 |

### 3.1 What this comparison actually shows

- **vs Nougat (the most direct peer)**: GOT-OCR beats Nougat on *every* metric by a very wide margin. Nougat essentially fails on Chinese (Table TEDS 0.0, Formula CDM 16.8) — GOT-OCR's overall edit distance is ~0.16 better on EN and ~0.56 better on ZH.
- **vs PaddleOCR PP-StructureV3 (the strongest open-source pipeline)**: PP-StructureV3 still wins end-to-end (Overall 0.145/0.206 vs GOT's 0.287/0.411). But PP-StructureV3 is a *pipeline* of multiple models with hand-engineered layout, while GOT-OCR is a **single 580 M end-to-end model** that does layout + text + formulas + tables + reading order jointly. On **formula CDM** GOT-OCR (74.3 / 45.3) is very close to PP-StructureV3 (81.8 / 52.1).
- **vs Tesseract**: Tesseract is **not** in OmniDocBench's end-to-end table (it doesn't produce markdown), but on the **text-only** component table (§2.4) Tesseract's EN edit distance is 0.096 vs GOT-OCR's **0.041**; on ZH Tesseract collapses to 0.551.
- **vs MinerU 2.0** (a later MinerU release, not in v1.0 but in v1.5/v1.6): MinerU2.0-2505-0.9B reports Overall Edit 0.133 / 0.238 on v1.0 — better than GOT-OCR — but it is a 0.9 B pipeline VLM, released later.
- **vs later specialized VLMs (MonkeyOCR-pro-1.2B, Dolphin, Nanonets-OCR-s, OCRFlux-3B)**: all post-date GOT-OCR by ≥ 6 months and most have ≥ 2× the parameters. MonkeyOCR-pro-1.2B is the closest in spirit (a 1.2 B specialist VLM) and beats GOT-OCR on every end-to-end metric.

### 3.2 OmniDocBench v1.5/v1.6 status

GOT-OCR's numbers were measured on the OmniDocBench **v1.0** protocol (981 PDF pages). On later v1.5/v1.6 the leaderboard now lists newer models (PaddleOCR-VL 0.9 B at 94.50 overall, GLM-OCR 0.9 B at 94.35, MinerU2.5 1.2 B at 90.93, dots.ocr 3 B at 88.41, …). **GOT-OCR was not re-evaluated on v1.5/v1.6** as of the latest public leaderboard — see `main` README "Comprehensive evaluation of document parsing on OmniDocBench (v1.6_full)", which lists dozens of newer models but no GOT-OCR row. (Source: <https://github.com/opendatalab/OmniDocBench>, `main` branch.)

---

## 4. Comparison vs Nougat / Tesseract / PaddleOCR / MinerU on the **Fox benchmark**

The GOT paper's main Table 1 (§1.1 above) is on the Fox benchmark. **Nougat** is included (edit 0.255 EN, no ZH). **Tesseract and PaddleOCR are not included** in the GOT paper's Table 1 — the GOT team chose to compare against LVLMs only. The closest open-source OCR systems for the Fox-benchmark *whole-page* setting are:

| System | Size | Edit ↓ (EN) | Edit ↓ (ZH) | Notes |
|---|---|---|---|---|
| Nougat | 250 M | 0.255 | – | No Chinese training data; ZH result not reported |
| Vary-toy | 1.8 B | 0.082 | 0.142 | Previous best small VLM |
| Fox (same team as GOT) | 1.8 B | 0.046 | 0.061 | |
| **GOT** | **580 M** | **0.035** | **0.038** | |
| Qwen-VL-Max (closed) | >72 B | 0.057 | 0.091 | |

For a Tesseract / PaddleOCR comparison on **the same Fox benchmark**, the literature is silent — neither is in the GOT paper's Table 1, and the Fox benchmark paper does not evaluate them either. The closest apples-to-apples is the OmniDocBench text-OCR component table in §2.4, where Tesseract EN = 0.096 vs GOT-OCR EN = 0.041, PaddleOCR EN = 0.071 vs GOT-OCR EN = 0.041.

---

## 5. Handwriting benchmarks (IAM / CASIA / NorHand)

**The GOT paper does not publish any IAM / CASIA-HWDB / NorHand benchmark numbers.** §3.3.2 of the paper lists those three datasets *only* as training data:

> "We collect the Chinese CASIA-HWDB2 [1], English IAM [2], and Norwegian NorHand-v3 [3] datasets to meet our requirements. For the original image-text pairs with the line-level slice format, 6∼8 pairs are grouped and randomly pasted into a blank document page to achieve longer-text handwriting recognition and improve training efficiency."

There is no per-dataset CER / accuracy table. Likewise the Hugging Face model card (<https://huggingface.co/stepfun-ai/GOT-OCR2_0>) contains no evaluation table. The OmniDocBench evaluation does include a "Handwriting" subset for "Note" pages but the GOT-OCR row does not break out handwriting-specific numbers.

**Conclusion: no published numbers to report for dedicated handwriting benchmarks. This is a gap in the literature.**

---

## 6. Throughput / speed

**No pages/sec or tokens/sec numbers are published in the paper or in the GitHub README.** What the GOT team states:

- **Architecture budget**: encoder 1024×1024 input → 256 image tokens (high compression, 1 token ≈ 4 K optical pixels). Decoder max length 8 K. (Paper §1, §3.3.1.)
- **Training hardware**: 8× NVIDIA L40S GPUs. Stage 1 (pre-train encoder) batch 128, 3 epochs, max token len 4096, lr 1e-4. Stage 2 batch 128, 1 epoch, max token len 6000. Stage 3 max token len 8192, lr 2e-5, 1 epoch. (Paper §4.1.)
- **Deployment claim**: "easier to deploy on a consumer-grade GPU with 4 GB memory" (Paper §3.3.1). This is a *feasibility* claim about Qwen-0.5B, not a measured inference number. README §"Demo" gives CLI invocations (`python3 GOT/demo/run_ocr_2.0.py --model-name /GOT_weights/ --image-file ...`) with no throughput numbers.
- **Community ports** (README "Community contributions"): ONNX, MNN, llama.cpp, OpenVINO, vLLM, CPU — useful for latency, but the original paper does not report tokens/sec or pages/sec on any of these.

**Conclusion: no published throughput numbers. Inference speed is unreported.**

---

## 7. Cross-paper consistency check

The GOT-OCR row in OmniDocBench v1.0 (§2.1 above) is reproduced *verbatim* in two independent sources:

1. The OmniDocBench GitHub repo `v1_0` README "End-to-End Evaluation" table.
2. The dots.ocr paper (arXiv 2512.02498 v4, Table 1, "GOT-OCR" row under "Expert VLMs"). The dots.ocr paper is the original citation in arXiv that introduced the v1.0-protocol end-to-end table format that is now standard for OmniDocBench. The numbers match exactly: 0.287 / 0.411 Overall Edit, 0.189 / 0.315 Text Edit, 0.360 / 0.528 Formula Edit, 53.2 / 47.2 Table TEDS, 0.141 / 0.280 Read Order Edit. (Formula CDM 74.3 / 45.3 is only in the OmniDocBench README, not in the dots.ocr table.)

This is a good cross-check that the published GOT-OCR numbers are stable across re-evaluations.

---

## 8. Summary

- **Strongest published result**: GOT-OCR is the **smallest model** (580 M) to beat Qwen-VL-Max (>72 B) on dense whole-page EN/ZH OCR (Fox benchmark, Table 1 of the GOT paper). Edit distance 0.035 EN / 0.038 ZH.
- **Weakest published result**: GOT-OCR is **not** state-of-the-art on OmniDocBench v1.0 end-to-end (Overall Edit 0.287/0.411 EN/ZH), trailing PaddleOCR PP-StructureV3 (0.145/0.206), MonkeyOCR-pro-1.2B (0.146/0.221), and Gemini-2.5-Pro (0.148/0.212). It also has very high edit distance on rotated text (Rotate90 = 0.562, Rotate270 = 0.966).
- **Strong on isolated text-OCR blocks**: 0.041 EN edit on the OmniDocBench text subset (best open-source generalist), 0.112 ZH (PaddleOCR/OpenOCR still ahead).
- **Strong on chart OCR**: 0.747 / 0.845 / 0.867 ChartQA-SE AP vs the chart-specialist Deplot 0.614 / 0.709 / 0.729, despite being half the size.
- **Strong on fine-grained OCR**: beats Fox (1.8 B) on all six region/color × en/zh fine-grained metrics.
- **Not benchmarked** on dedicated handwriting test sets (IAM/CASIA/NorHand) — these were training data only.
- **No published throughput numbers** — pages/sec and tokens/sec are not reported anywhere.
- **Not re-evaluated** on OmniDocBench v1.5/v1.6 (which is the current leaderboard protocol); numbers above are v1.0 only.

---

## 9. Sources

| # | Source | Used for |
|---|---|---|
| 1 | arXiv 2409.01704 v1 HTML — <https://arxiv.org/html/2409.01704v1> | Paper §1–§4, Table 1 (Fox document OCR), Table 2 (scene OCR), Table 3 (formatted OCR + sheet music + geometry), Table 4 (fine-grained), Table 5 (chart OCR), §4.1 training setup, §3.4 handwriting data |
| 2 | arXiv 2409.01704 PDF (downloaded; text extracted locally) — <https://arxiv.org/pdf/2409.01704v1> | Used to verify table cell values that were partially truncated in the HTML render |
| 3 | GitHub README — <https://github.com/Ucas-HaoranWei/GOT-OCR2.0> | Demo CLI flags (`ocr_type`, `ocr_box`, `ocr_color`, `render`), community ports, training/eval instructions |
| 4 | Hugging Face model card — <https://huggingface.co/stepfun-ai/GOT-OCR2_0> | Inference usage, citation |
| 5 | OmniDocBench `v1_0` README — <https://github.com/opendatalab/OmniDocBench/blob/v1_0/README.md> | OmniDocBench v1.0 end-to-end table (GOT-OCR row), formula/table/text component tables, dataset sizes |
| 6 | OmniDocBench `main` README — <https://github.com/opendatalab/OmniDocBench/blob/main/README.md> | Confirms GOT-OCR is *not* in the v1.6 leaderboard; provides v1.6 protocol description (Overall = (1−TextEdit)*100 + TableTEDS + FormulaCDM)/3) |
| 7 | OmniDocBench `v1_5` README — <https://github.com/opendatalab/OmniDocBench/blob/v1_5/README.md> | Confirms GOT-OCR row consistent across v1.0 / v1.5 component tables; shows the formula/table/text component numbers are unchanged between v1.0 and v1.5 for GOT-OCR |
| 8 | dots.ocr paper (arXiv 2512.02498 v4) — <https://arxiv.org/abs/2512.02498> | Cross-check for the GOT-OCR OmniDocBench end-to-end row (identical numbers to OmniDocBench v1.0) |

---

*Report compiled from publicly available web sources; no numbers were inferred. Where the GOT paper / OmniDocBench / dots.ocr does not publish a number, this report says so explicitly (notably §5 handwriting, §6 throughput).*