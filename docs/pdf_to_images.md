# PDF → JPG 拆分工具

把扫描版 PDF 拆分成单页 JPG 图像,适合 OCR(PaddleOCR / Tesseract)和 VLM(GPT-4V / Qwen-VL / Claude)阅读。

## 一、安装

只需一个依赖:`PyMuPDF`(纯 Python 绑定,不依赖 poppler / ghostscript 等系统命令)。

```bash
pip install pymupdf
```

如果你用 `uv` / `conda` 也可以:

```bash
uv pip install pymupdf
conda install -c conda-forge pymupdf
```

## 二、快速开始

```bash
# 最简单:把 input.pdf 拆成 JPG,默认输出到 ./input_images/
python pdf_to_images.py input.pdf
```

输出结构:

```
input_images/
  input_page_001.jpg
  input_page_002.jpg
  ...
```

## 三、常用场景

### 1. 给传统 OCR(PaddleOCR / Tesseract / EasyOCR)

OCR 需要清晰、较高的分辨率和单色通道:

```bash
python pdf_to_images.py input.pdf --dpi 300 --quality 90 --gray
```

参数含义:
- `--dpi 300`:300 DPI 是 OCR 业界事实标准
- `--quality 90`:JPEG 质量,90 在清晰度和体积间平衡好
- `--gray`:灰度模式,纯文字页面体积可减半,对识别精度无影响

### 2. 给 VLM(GPT-4V / Qwen-VL / Claude / Gemini)

VLM 受图像 token 配额限制,需要平衡清晰度与体积:

```bash
python pdf_to_images.py input.pdf --dpi 200 --quality 85 --max-side 1800
```

参数含义:
- `--dpi 200`:VLM 200 DPI 已足够
- `--quality 85`:画质略低于 90,但体积明显减小
- `--max-side 1800`:把最长边限制在 1800 像素内,符合多数 VLM 推荐的输入尺寸

### 3. 只拆部分页

```bash
# 只拆第 5 到第 10 页
python pdf_to_images.py input.pdf --start 5 --end 10
```

### 4. 指定输出目录和文件名前缀

```bash
python pdf_to_images.py input.pdf -o ./ocr_input --prefix scan
```

输出:`./ocr_input/scan_page_001.jpg`、`scan_page_002.jpg`...

## 四、完整参数表

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `pdf` | (必填) | 输入 PDF 路径 |
| `-o / --output` | `<PDF名>_images` | 输出目录 |
| `--dpi` | 250 | 渲染分辨率(72 DPI × zoom = 设置值) |
| `--quality` | 88 | JPEG 质量(1-95) |
| `--start` | 1 | 起始页(1-based) |
| `--end` | 0 | 结束页,0 表示到末页 |
| `--gray` | 否 | 输出灰度图 |
| `--prefix` | PDF 文件名 | 输出文件名前缀 |
| `--max-side` | 0 | 最长边像素上限,0 不限制 |

## 五、DPI / 质量参考表

按 A4 单页内容估算(中英文混排文档):

| DPI | 模式 | 单页大小 | 适用 |
|-----|------|---------|------|
| 150 | 彩色 | ~150 KB | 纯展示 / 缩略图 |
| 200 | 彩色 | ~250 KB | **VLM 推荐** |
| 250 | 彩色 | ~380 KB | 通用平衡(脚本默认) |
| 300 | 彩色 | ~550 KB | **传统 OCR 推荐** |
| 300 | 灰度 | ~280 KB | OCR + 体积敏感 |
| 400 | 彩色 | ~1 MB | 古籍 / 小字密集 |

> 💡 VLM 通常有 token 上限(单图按最长边 × 一定比例折算)。如果一页 PDF 在 300 DPI 下是 2500×3500,建议用 `--max-side 2048` 缩到 2048 以内,体积减半而模型识别几乎不变。

## 六、常见问题

**Q: 报错 `ModuleNotFoundError: No module named 'fitz'`**
A: 安装 PyMuPDF:`pip install pymupdf`(注意是 `pymupdf` 不是 `PyMuPDF`,新版已统一)。

**Q: PDF 是加密的怎么办?**
A: 脚本不支持加密 PDF。先用 PDF 阅读器解密后再运行。

**Q: 输出是 PDF 嵌入的文字怎么办?**
A: PyMuPDF 默认会矢量化文字层。本工具通过 `--dpi` 渲染成位图,这正是 OCR/VLM 想要的。但如果 PDF 本身是"双层 PDF"(扫描底图 + 可选文字层),也可以用其他工具如 `pdftoppm` / `ocrmypdf`。

**Q: 想保留 PNG 无损怎么办?**
A: 修改脚本里 `pix.save(...)` 的 `jpg=True` 改为 `jpg=False`,并把文件后缀改成 `.png` 即可。

## 七、配套建议

- 想直接把 PDF 喂给 OCR(不开图像文件),可以用 [`ocrmypdf`](https://github.com/ocrmypdf/OCRMypdf)。
- 想把多张 JPG 合并成 PDF 反向操作,用 PyMuPDF:`doc = fitz.open(); for img in imgs: doc.insert_pixmap(...)`。
