#!/usr/bin/env python3
"""
note_to_markdown.py — 手写笔记(手机照片 / 扫描 PDF)→ Markdown。

这是把之前写好的两段工具串起来的统一入口:

    pdf_to_images.py   PDF ──▶ JPG        (扫描件转图)
    dots_mocr.parser   JPG/PDF ──▶ JSON+MD (dots.mocr 版面解析)
    ───────────────────────────────
    note_to_markdown.py  手写照片/PDF ──▶ 一份干净的 Markdown

相比裸跑 dots_mocr,这里多了「手写专用预处理」这一步,这是手写识别成败的关键:
  1. deskew   —— 手机拍的手写纸几乎总是歪的,倾斜会让行检测和阅读顺序崩掉
  2. autocontrast —— 抹平拍照时的不均匀光照和阴影
  3. binarize —— dots.mocr 的视觉塔是拿「渲染/印刷文档」训出来的,
                  把手写笔画二值化能拉近到它的训练分布(可选,见 --preprocess)
  4. trim     —— 裁掉四周空白,让有效像素占满视觉分辨率配额

用法示例:
  # 单张手写照片
  python ocr/scripts/note_to_markdown.py note.jpg -o out/

  # 扫描版手写 PDF(逐页)
  python ocr/scripts/note_to_markdown.py notes.pdf -o out/

  # 一整个文件夹(按文件名排序当成连续多页)
  python ocr/scripts/note_to_markdown.py ./shots/ -o out/

  # 只要纯文本、不要版面 JSON(更稳,适合潦草字)
  python ocr/scripts/note_to_markdown.py note.jpg --prompt prompt_ocr

  # pip install -e . 之后
  ocr-note-to-markdown note.jpg -o out/

分辨率说明:
  默认 --dpi 150 + --scale 1.0 + --max-side 1600,整页落在 ~200 万像素以内。
  这是视觉塔的舒适区(约 2000²);再高只是多烧 token 和时间,识别不会更好。
  想让小字更清楚,优先调 --dpi 或 --max-side,而不是 --scale。

所有路径都从 __file__ / 环境变量 / 命令行参数推导,没有任何硬编码位置;
环境变量表见 README.md。
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── 自举 ────────────────────────────────────────────────────────────────────
# 两件事,顺序不能颠倒,而且都必须发生在任何第三方 import 之前:
#   1. 让 `ocr/` 目录进入 sys.path —— 直接 `python ocr/scripts/xxx.py` 跑时,
#      包根目录不在 sys.path 里,`dots_mocr` 就 import 不到。
#   2. 切到项目自带的 venv —— 系统 python3 里可能没装 pillow/numpy。
#      找不到 venv 就留在当前解释器(优雅降级),不报错。
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts._bootstrap import env_float, env_int, env_str, reexec_in_venv
except ImportError:  # pragma: no cover - 源码树不完整时的兜底
    import os

    def reexec_in_venv() -> None:
        """找不到 scripts._bootstrap 时跳过 venv 自举。"""
        return None

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

    def env_float(*names: str, default: float) -> float:
        """第一个能解析成 float 的环境变量,都没有就用 default。"""
        for name in names:
            raw = os.environ.get(name)
            if raw:
                try:
                    return float(raw)
                except ValueError:
                    continue
        return default

reexec_in_venv()

import argparse
import json
import re
import urllib.error
import urllib.request

try:
    import numpy as np
    from PIL import Image, ImageFilter, ImageOps
except ImportError as exc:  # pragma: no cover
    sys.stderr.write(f"[错误] 缺少依赖: {exc}\n请先 pip install -r requirements.txt\n")
    sys.exit(1)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
PREPROCESS_MODES = ("none", "gray", "enhance", "binarize")


# ── LM Studio 模型自动加载 ──────────────────────────────────────────────────
def _lm_studio_request(path: str, ip: str, port: int, payload: dict | None = None,
                       timeout: float = 120.0):
    url = f"http://{ip}:{port}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "replace")
    return json.loads(body) if body.strip() else {}


def ensure_model_loaded(ip: str, port: int, model_name: str, verbose: bool = True) -> bool:
    """LM Studio 会自动卸载闲置模型,这里检测到没加载就自动拉起来。

    用的是 LM Studio 原生 REST:GET /api/v0/models 看状态,
    POST /api/v1/models/load 触发加载(实测 ~5 秒)。
    """
    try:
        listing = _lm_studio_request("/api/v0/models", ip, port, timeout=10)
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        # 不是 LM Studio(比如 vLLM/Ollama),那就交给调用时的报错
        return False

    entries = listing.get("data") or []
    target = next(
        (m for m in entries
         if m.get("id") == model_name or m.get("id", "").split("/")[-1] == model_name),
        None,
    )
    if target is None:
        if verbose:
            print(f"[模型] 服务端没有 '{model_name}',可选: "
                  f"{[m.get('id') for m in entries]}")
        return False

    state = target.get("state")
    if state in ("loaded", "loading"):
        if verbose:
            print(f"[模型] '{model_name}' 已就绪 (state={state})")
        return True

    if verbose:
        print(f"[模型] '{model_name}' 处于 {state},正在自动加载…")
    try:
        _lm_studio_request("/api/v1/models/load", ip, port,
                           {"model": model_name}, timeout=300)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        if verbose:
            print(f"[模型] 自动加载失败: {exc}\n"
                  f"       请手动在 LM Studio 里加载 '{model_name}' 后重试。")
        return False

    if verbose:
        print(f"[模型] '{model_name}' 加载完成")
    return True


# ── 手写预处理 ──────────────────────────────────────────────────────────────
def estimate_skew(gray: Image.Image, max_angle: float = 6.0, step: float = 0.5) -> float:
    """投影方差法估计倾斜角。

    原理:文字行水平时,按行求和得到的墨迹投影曲线起伏最大(方差最大)。
    返回值是「把原图旋转多少度能摆正」,直接用即可。
    """
    small = gray
    w, h = small.size
    scale = min(1.0, 1000.0 / max(w, h))
    if scale < 1.0:
        small = small.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR)

    arr = np.asarray(small, dtype=np.float32)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + 1e-9, step):
        rot = Image.fromarray(arr).rotate(float(angle), resample=Image.BILINEAR, fillcolor=255)
        profile = (255.0 - np.asarray(rot, dtype=np.float32)).sum(axis=1)
        score = float(np.var(np.diff(profile)))
        if score > best_score:
            best_score, best_angle = score, float(angle)
    return best_angle


def otsu_threshold(gray: Image.Image) -> int:
    """Otsu 自适应阈值(纯 numpy 实现,免 scipy 依赖)。"""
    hist = np.asarray(gray.histogram(), dtype=np.float64)
    total = hist.sum()
    if total == 0:
        return 128
    weighted_total = float((np.arange(256) * hist).sum())

    weight_bg = 0.0
    sum_bg = 0.0
    best_var, best_t = -1.0, 128
    for t in range(256):
        weight_bg += hist[t]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += t * hist[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (weighted_total - sum_bg) / weight_fg
        between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if between > best_var:
            best_var, best_t = between, t
    return int(best_t)


def trim_whitespace(img: Image.Image, thresh: int = 245, pad: int = 16) -> Image.Image:
    """裁掉四周近白区域,让内容占满视觉塔的输入配额。"""
    gray = img.convert("L")
    mask = gray.point(lambda p: 255 if p < thresh else 0)
    box = mask.getbbox()
    if not box:
        return img
    left, top, right, bottom = box
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(img.width, right + pad)
    bottom = min(img.height, bottom + pad)
    return img.crop((left, top, right, bottom))


def preprocess(
    img: Image.Image,
    mode: str = "enhance",
    deskew: bool = True,
    scale: float = 1.0,
    trim: bool = True,
    max_side: int = 1600,
) -> tuple[Image.Image, str]:
    """返回 (处理后的 RGB 图, 人类可读的说明)。"""
    notes: list[str] = []

    if img.mode != "RGB":
        img = img.convert("RGB")

    if deskew:
        angle = estimate_skew(img.convert("L"))
        if abs(angle) >= 0.3:
            img = img.rotate(
                -angle, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255)
            )
            notes.append(f"deskew {angle:+.1f}°")
        else:
            notes.append("deskew 0.0°")

    if mode in ("gray", "enhance", "binarize"):
        gray = img.convert("L")
        if mode in ("enhance", "binarize"):
            gray = ImageOps.autocontrast(gray, cutoff=1)
            gray = gray.filter(ImageFilter.MedianFilter(size=3))
            notes.append("autocontrast+denoise")
        if mode == "binarize":
            thr = otsu_threshold(gray)
            gray = gray.point(lambda p: 0 if p < thr else 255)
            notes.append(f"binarize(Otsu={thr})")
        img = Image.merge("RGB", (gray, gray, gray))

    if trim:
        before = img.size
        img = trim_whitespace(img)
        if img.size != before:
            notes.append(f"trim {before[0]}×{before[1]}→{img.width}×{img.height}")

    if scale and abs(scale - 1.0) > 1e-3:
        img = img.resize(
            (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
            Image.LANCZOS,
        )
        notes.append(f"scale ×{scale:g}")

    # 分辨率上限:视觉塔在 ~2000² (400 万像素) 以内最舒服,
    # 超了只是白白多烧带宽和 token,识别不会更好。
    if max_side and max(img.size) > max_side:
        ratio = max_side / max(img.size)
        img = img.resize(
            (max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
            Image.LANCZOS,
        )
        notes.append(f"cap→{img.width}×{img.height}")

    return img, ", ".join(notes) if notes else "no-op"


# ── 输入加载 ────────────────────────────────────────────────────────────────
def _unescape_shell_path(raw: str) -> str:
    """还原终端里拖拽/粘贴带来的 shell 转义。

    macOS 终端把带空格的路径插入成 `扫描文稿\\ 2.pdf`(空格被反斜杠转义),
    直接当文件名用会找不到。这里把 `\\ `、`\\'`、`\\"` 还原成原字符。
    """
    return re.sub(r"\\([ '\"\\])", r"\1", raw)


def resolve_input(target: Path) -> Path:
    """把可能带 shell 转义的路径解析成真实存在的路径。"""
    if target.exists():
        return target

    candidates = [Path(_unescape_shell_path(str(target)))]
    for cand in candidates:
        if cand.exists():
            return cand

    # 兜底:在同一目录里找忽略空格、忽略大小写的匹配
    for cand in candidates:
        parent = cand.parent
        if not parent.is_dir():
            continue
        key = cand.name.replace(" ", "").lower()
        for item in parent.iterdir():
            if item.name.replace(" ", "").lower() == key:
                return item
    return target


def render_pdf_pages(pdf_path: Path, dpi: int) -> list[Image.Image]:
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz  # type: ignore

    pages: list[Image.Image] = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            pages.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    return pages


def load_inputs(target: Path, dpi: int) -> tuple[list[Image.Image], str]:
    """把目标(文件 / 目录 / PDF)统一变成一串页面图像。"""
    if target.is_dir():
        files = sorted(
            p for p in target.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES
        )
        if not files:
            sys.stderr.write(f"[错误] 目录里没有图片: {target}\n")
            sys.exit(1)
        return [Image.open(p).convert("RGB") for p in files], target.name

    if target.suffix.lower() == ".pdf":
        return render_pdf_pages(target, dpi), target.stem

    if target.suffix.lower() in IMAGE_SUFFIXES:
        return [Image.open(target).convert("RGB")], target.stem

    sys.stderr.write(f"[错误] 不支持的输入类型: {target}\n")
    sys.exit(1)


# ── 主流程 ──────────────────────────────────────────────────────────────────
def _parse_with_retry(parser, path: Path, pages_dir: Path, prompt: str,
                      ip: str, port: int, model_name: str):
    """解析单页;碰到「模型被卸载」就自动重新加载再重试一次。"""
    try:
        return parser.parse_file(
            str(path), output_dir=str(pages_dir), prompt_mode=prompt
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "unload" not in msg and "not loaded" not in msg:
            raise
        print("[重试] 模型被卸载了,正在重新加载…")
        ensure_model_loaded(ip, port, model_name)
        return parser.parse_file(
            str(path), output_dir=str(pages_dir), prompt_mode=prompt
        )


def parse_args() -> argparse.Namespace:
    # 相对默认(./note_md)按 CWD 解析 —— 没有任何绝对路径被写死。
    default_output = Path(env_str("OCR_OUTPUT_DIR", default="./note_md")).expanduser()
    default_host = env_str("OCR_HOST", "LMSTUDIO_IP", default="127.0.0.1")
    default_port = env_int("OCR_PORT", "LMSTUDIO_PORT", default=1234)
    default_model = env_str("OCR_MODEL", "LMSTUDIO_MODEL", default="dots.mocr")
    default_dpi = env_int("OCR_DPI", default=150)

    p = argparse.ArgumentParser(
        prog="note_to_markdown",
        description="手写笔记(照片 / 扫描 PDF)→ Markdown,走本地 dots.mocr。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("input", type=Path, help="输入: 图片 / PDF / 存放图片的目录")
    p.add_argument("-o", "--output", type=Path, default=default_output,
                   help="输出目录(默认 ./note_md,可用 $OCR_OUTPUT_DIR 覆盖)")
    p.add_argument("--dpi", type=int, default=default_dpi,
                   help="PDF 渲染分辨率(默认 150,A4≈1240×1754;可用 $OCR_DPI 覆盖)")
    p.add_argument("--preprocess", choices=PREPROCESS_MODES,
                   default=env_str("OCR_PREPROCESS", default="enhance"),
                   help="手写预处理强度:binarize 最接近印刷体,enhance 最保守")
    p.add_argument("--no-deskew", action="store_true", help="关闭自动纠偏")
    p.add_argument("--scale", type=float,
                   default=env_float("OCR_SCALE", default=1.0),
                   help="额外放大倍数(默认 1.0,即不放大)")
    p.add_argument("--max-side", type=int,
                   default=env_int("OCR_MAX_SIDE", default=1600),
                   help="最长边像素上限,0 不限制(视觉塔在 ~2000² 以内最舒服)")
    p.add_argument("--no-trim", action="store_true", help="关闭裁白边")
    p.add_argument("--prompt",
                   default=env_str("OCR_PROMPT", default="prompt_layout_all_en"),
                   help="dots.mocr 提示模式(prompt_ocr 只要纯文本更稳)")
    p.add_argument("--ip", default=default_host,
                   help="模型服务地址(默认 127.0.0.1,可用 $OCR_HOST 覆盖)")
    p.add_argument("--port", type=int, default=default_port,
                   help="模型服务端口(默认 1234,可用 $OCR_PORT 覆盖)")
    p.add_argument("--model-name", default=default_model,
                   help="模型名(默认 dots.mocr,可用 $OCR_MODEL 覆盖)")
    p.add_argument("--num-thread", type=int,
                   default=env_int("OCR_NUM_THREAD", default=1),
                   help="并发页数(LM Studio 串行,大于 1 基本没用)")
    p.add_argument("--keep-staging", action="store_true",
                   help="保留预处理后的中间图,便于排查")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    resolved = resolve_input(args.input)
    if not resolved.exists():
        sys.stderr.write(f"[错误] 找不到输入: {args.input}\n")
        parent = resolved.parent
        if parent.is_dir():
            sys.stderr.write("       同目录下有这些文件:\n")
            for item in sorted(parent.iterdir())[:20]:
                sys.stderr.write(f"         - {item.name}\n")
        return 2
    if resolved != args.input:
        print(f"[提示] 路径已修正: {args.input} → {resolved}")

    from dots_mocr.parser import DotsMOCRParser  # 延迟导入,便于先报错依赖

    out_dir = args.output.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    staging = out_dir / "_staging"
    staging.mkdir(exist_ok=True)

    images, stem = load_inputs(resolved.resolve(), args.dpi)
    print(f"[信息] 输入 {resolved} → {len(images)} 页,名目 '{stem}'")
    print(f"[信息] 预处理: {args.preprocess} (deskew={not args.no_deskew}, "
          f"scale={args.scale:g}, trim={not args.no_trim})")

    # ── Stage 1: 预处理 + 落盘 ──
    staged: list[Path] = []
    for idx, img in enumerate(images, start=1):
        processed, note = preprocess(
            img,
            mode=args.preprocess,
            deskew=not args.no_deskew,
            scale=args.scale,
            trim=not args.no_trim,
            max_side=args.max_side,
        )
        path = staging / f"{stem}_page_{idx:03d}.png"
        processed.save(path)
        staged.append(path)
        print(f"  ✓ 第 {idx} 页: {processed.width}×{processed.height}  [{note}]")

    # ── Stage 2: 调 dots.mocr ──
    ensure_model_loaded(args.ip, args.port, args.model_name)

    parser = DotsMOCRParser(
        protocol="http",
        ip=args.ip,
        port=args.port,
        model_name=args.model_name,
        num_thread=args.num_thread,
        dpi=args.dpi,
        output_dir=str(out_dir / "_pages"),
    )

    md_parts: list[str] = []
    for path in staged:
        results = _parse_with_retry(
            parser, path, out_dir / "_pages", args.prompt,
            args.ip, args.port, args.model_name,
        )
        for res in results:
            md_path = res.get("md_content_path")
            if md_path and Path(md_path).is_file():
                text = Path(md_path).read_text(encoding="utf-8").strip()
                page_no = res.get("page_no", 0)
                md_parts.append((page_no, text))

    if not md_parts:
        sys.stderr.write("[错误] 没有产出任何 Markdown\n")
        return 1

    md_parts.sort(key=lambda x: x[0])
    combined = out_dir / f"{stem}.md"
    with combined.open("w", encoding="utf-8") as fh:
        for i, (_, text) in enumerate(md_parts):
            if i:
                fh.write("\n\n---\n\n")
            fh.write(text)
            fh.write("\n")

    jsonl = out_dir / f"{stem}.jsonl"
    with jsonl.open("w", encoding="utf-8") as fh:
        for _, text in md_parts:
            fh.write(json.dumps({"markdown": text}, ensure_ascii=False) + "\n")

    print(f"\n[完成] Markdown → {combined}")
    print(f"[完成] 分页产物 → {out_dir / '_pages'}")

    if not args.keep_staging:
        for p in staged:
            p.unlink(missing_ok=True)
        try:
            staging.rmdir()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
