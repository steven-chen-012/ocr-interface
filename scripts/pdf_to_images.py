#!/usr/bin/env python3
"""
pdf_to_images.py — 把扫描版 PDF 拆分为适合 OCR / VLM 阅读的 JPG 图像。

设计目标:
  - 单页输出,每页一张 JPG,便于 OCR(VL 模型/传统 OCR 都按页读)。
  - 分辨率兼顾 OCR 精度与 VLM 文件大小(默认 250 DPI,可在 --dpi 调整)。
  - 零依赖外部命令行工具,只依赖 PyMuPDF(`pip install pymupdf`)。

用法示例:
  python ocr/scripts/pdf_to_images.py input.pdf
  python ocr/scripts/pdf_to_images.py input.pdf -o ./images --dpi 300 --quality 90
  python ocr/scripts/pdf_to_images.py input.pdf --dpi 200 --quality 85 --prefix scan
  python ocr/scripts/pdf_to_images.py input.pdf --start 5 --end 10        # 只拆 5~10 页
  python ocr/scripts/pdf_to_images.py input.pdf --gray                     # 灰度,适合纯文字 OCR

  pip install -e . 之后
  ocr-pdf-to-images input.pdf --dpi 300 --gray

输出目录默认是 PDF 同级的 <PDF 名>_images/;可用 -o 或 $OCR_IMAGES_DIR 覆盖。
详见 docs/pdf_to_images.md。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts._bootstrap import env_int, env_str
except ImportError:  # pragma: no cover - 源码树不完整时的兜底

    def env_str(*names: str, default: str) -> str:
        """第一个非空的环境变量,都没有就用 default。"""
        for name in names:
            value = os.environ.get(name)
            if value:
                return value
        return default

    def env_int(*names: str, default: int) -> int:
        """第一个能解析成 int 的环境变量,都没有就用 default。"""
        for name in names:
            raw = os.environ.get(name)
            if raw:
                try:
                    return int(raw)
                except ValueError:
                    continue
        return default

try:
    import fitz  # PyMuPDF
except ImportError:
    try:
        import pymupdf as fitz  # PyMuPDF >= 1.24 推荐的模块名
    except ImportError:
        sys.stderr.write(
            "[错误] 缺少依赖 PyMuPDF。请先运行: pip install pymupdf\n"
        )
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    default_output = env_str("OCR_IMAGES_DIR", default="")
    p = argparse.ArgumentParser(
        prog="pdf_to_images",
        description="将扫描版 PDF 拆分为 JPG 图像,适合 OCR / VLM 阅读。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("pdf", type=Path, help="输入 PDF 文件路径")
    p.add_argument(
        "-o", "--output",
        type=Path,
        default=Path(default_output) if default_output else None,
        help="输出目录(默认: <PDF 名>_images/<PDF 名>_page_NNN.jpg;可用 $OCR_IMAGES_DIR 覆盖)",
    )
    p.add_argument(
        "--dpi",
        type=int,
        default=env_int("OCR_DPI", default=150),
        help="渲染分辨率。VLM 150 平衡画质与体积,OCR 建议 300。",
    )
    p.add_argument(
        "--quality",
        type=int,
        default=env_int("OCR_QUALITY", default=80),
        help="JPEG 质量(1-95)。数值越高画质越好、体积越大。VLM 80 左右。",
    )
    p.add_argument(
        "--start", type=int, default=1, help="起始页码(1-based,含)"
    )
    p.add_argument(
        "--end", type=int, default=0, help="结束页码(1-based,含,0 表示到末页)"
    )
    p.add_argument(
        "--gray", action="store_true", help="输出灰度图(适合纯文字 OCR,体积更小)"
    )
    p.add_argument(
        "--prefix", default=None,
        help="输出文件名前缀(默认使用 PDF 文件名)",
    )
    p.add_argument(
        "--max-side", type=int, default=env_int("OCR_MAX_SIDE", default=1280),
        help="限制最长边像素(0 不限制)。Qwen-VL 推荐 1280,其他 VLM 可设 1568。",
    )
    return p.parse_args()


def render_pdf(
    pdf_path: Path,
    output_dir: Path,
    dpi: int,
    quality: int,
    start: int,
    end: int,
    gray: bool,
    prefix: str,
    max_side: int,
) -> int:
    if not pdf_path.is_file():
        sys.stderr.write(f"[错误] 找不到 PDF: {pdf_path}\n")
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    total = doc.page_count
    end = end if end and end <= total else total
    start = max(1, min(start, total))
    if start > end:
        sys.stderr.write(f"[错误] 起始页 {start} 大于结束页 {end}\n")
        doc.close()
        return 2

    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    cs = fitz.csGRAY if gray else fitz.csRGB
    saved = 0

    print(f"[信息] PDF: {pdf_path}")
    print(f"[信息] 总页数: {total} | 本次处理: 第 {start}-{end} 页 | DPI: {dpi} | 灰度: {gray} | max-side: {max_side}")
    print(f"[信息] 输出目录: {output_dir}")

    for i in range(start - 1, end):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=matrix, colorspace=cs, alpha=False)

        # 如需限制最长边
        if max_side > 0 and max(pix.width, pix.height) > max_side:
            scale = max_side / max(pix.width, pix.height)
            pix = page.get_pixmap(
                matrix=fitz.Matrix(zoom * scale, zoom * scale),
                colorspace=cs,
                alpha=False,
            )

        name = f"{prefix}_page_{i + 1:03d}.jpg"
        out_path = output_dir / name
        # PyMuPDF 1.28+:靠文件后缀名识别格式,质量用 jpg_quality
        pix.save(str(out_path), jpg_quality=quality)
        saved += 1
        print(f"  ✓ {name}  ({pix.width}x{pix.height})")

    doc.close()
    print(f"[完成] 共生成 {saved} 张 JPG 图像 → {output_dir}")
    return 0


def main() -> int:
    args = parse_args()
    pdf_path = args.pdf.resolve()
    output_dir = args.output or pdf_path.with_name(
        f"{pdf_path.stem}_images"
    ).resolve()
    prefix = args.prefix or pdf_path.stem

    return render_pdf(
        pdf_path=pdf_path,
        output_dir=output_dir,
        dpi=args.dpi,
        quality=args.quality,
        start=args.start,
        end=args.end,
        gray=args.gray,
        prefix=prefix,
        max_side=args.max_side,
    )


if __name__ == "__main__":
    sys.exit(main())
