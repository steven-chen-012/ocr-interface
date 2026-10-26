"""
smoke_test.py — verify the dots.ocr Mac pipeline loads and (optionally)
talks to your LM Studio server.

Usage:
    python scripts/smoke_test.py --check-only                 # imports + PDF render only
    python scripts/smoke_test.py path/to/sample.pdf           # also tries to call the server
    ocr-smoke-test --check-only                               # after pip install -e .

Environment:
    LMSTUDIO_IP / LMSTUDIO_PORT / LMSTUDIO_MODEL   (checked first, for backwards compat)
    OCR_HOST / OCR_PORT / OCR_MODEL                (new canonical names)
    OCR_DPI                                         (default 200)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 直接 `python ocr/scripts/smoke_test.py` 时,`ocr/` 不在 sys.path 里,
# `dots_mocr` 就 import 不到。`python -m scripts.smoke_test` 时已就位。
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts._bootstrap import env_int, env_str
except ImportError:  # pragma: no cover - 源码树不完整时的兜底
    import os

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

from dots_mocr.parser import DotsMOCRParser  # noqa: F401  (import-time smoke check)
from dots_mocr.utils.doc_utils import load_images_from_pdf
from dots_mocr.model.inference import inference_with_vllm


def check_imports() -> None:
    print("[ok] dots_mocr.parser imported")
    print("[ok] dots_mocr.utils.doc_utils imported")
    print("[ok] dots_mocr.model.inference imported")


def check_pdf_rendering(pdf_path: str, dpi: int = 200) -> None:
    pages = load_images_from_pdf(pdf_path, dpi=dpi)
    assert pages, "no pages rendered"
    first = pages[0]
    print(
        f"[ok] PDF rendered with fitz at {dpi} dpi: "
        f"{len(pages)} page(s), first page = {first.size}"
    )


def check_lmstudio(ip: str, port: int, model_name: str) -> None:
    print(f"[..] probing {ip}:{port} model='{model_name}'")
    text = inference_with_vllm(
        image=None,
        prompt="Reply with the single word: pong",
        ip=ip,
        port=port,
        model_name=model_name,
        max_completion_tokens=16,
    )
    print(f"[ok] server replied: {text!r}")


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="smoke_test",
        description="Smoke-test the dots.ocr Mac pipeline (imports, PDF render, model server).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("pdf", nargs="?", help="optional PDF for rendering check")
    ap.add_argument("--check-only", action="store_true",
                    help="import + render only, never call the model server")
    # LMSTUDIO_* 保持最高优先级(向后兼容),OCR_* 作为新的规范名兜底。
    ap.add_argument("--ip",   default=env_str("LMSTUDIO_IP", "OCR_HOST", default="127.0.0.1"))
    ap.add_argument("--port", type=int, default=env_int("LMSTUDIO_PORT", "OCR_PORT", default=1234))
    ap.add_argument("--model-name", default=env_str("LMSTUDIO_MODEL", "OCR_MODEL", default="model"))
    ap.add_argument("--dpi", type=int, default=env_int("OCR_DPI", default=200))
    args = ap.parse_args()

    check_imports()
    if args.pdf:
        check_pdf_rendering(args.pdf, dpi=args.dpi)
    if not args.check_only:
        check_lmstudio(args.ip, args.port, args.model_name)
    print("[done]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
