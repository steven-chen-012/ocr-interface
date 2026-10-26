"""
check_imports.py — pre-flight check that every dots_mocr.* module imports
cleanly under your current interpreter.

Run BEFORE attempting any PDF parsing. If something is missing you'll see
every offender here in one shot instead of one-at-a-time during inference.

Usage:
    python ocr/scripts/check_imports.py             # real check (needs deps installed)
    python ocr/scripts/check_imports.py --no-stubs  # import the real openai SDK
    ocr-check-imports                               # after pip install -e .
"""
from __future__ import annotations

import argparse
import importlib
import sys
import types
from pathlib import Path

# 直接跑本文件时把包根目录加进 sys.path,`dots_mocr` 才找得到。
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts._bootstrap import ensure_import_path
except ImportError:  # pragma: no cover - 源码树不完整时的兜底
    def ensure_import_path() -> None:
        """找不到 scripts._bootstrap 时不额外处理 sys.path。"""
        return None

ensure_import_path()


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="check_imports",
        description="Pre-flight check that every dots_mocr.* module imports cleanly.",
    )
    ap.add_argument(
        "--no-stubs", action="store_true",
        help="don't stub `openai` — useful if you've installed it for real",
    )
    args = ap.parse_args()

    if not args.no_stubs:
        sys.modules.setdefault("openai", types.ModuleType("openai"))

    # Force a clean interpreter-side bytecode cache (cf. Python caching old
    # 'ImportError' results after a fresh pip install).
    importlib.invalidate_caches()

    modules = [
        "dots_mocr.utils.consts",
        "dots_mocr.utils.doc_utils",
        "dots_mocr.utils.image_utils",
        "dots_mocr.utils.layout_utils",
        "dots_mocr.utils.format_transformer",
        "dots_mocr.utils.output_cleaner",
        "dots_mocr.utils.svg_utils",
        "dots_mocr.utils.prompts",
        "dots_mocr.model.inference",
        "dots_mocr.parser",
    ]

    failed = 0
    for name in modules:
        try:
            importlib.import_module(name)
            print(f"  ok   {name}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {name}: {type(e).__name__}: {e}")

    if failed:
        print(
            f"\n{failed} module(s) failed to import. "
            "Install missing deps with:\n"
            "    pip install -r requirements.txt"
        )
        return 1
    print("\nall dots_mocr.* modules import cleanly ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
