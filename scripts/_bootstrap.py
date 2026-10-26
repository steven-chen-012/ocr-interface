"""Portable path helpers shared by every script in ``ocr/scripts``.

Design rules this module exists to enforce:

* **No hardcoded absolute paths.** Every location is derived from ``__file__``,
  an environment variable, or a CLI argument.
* **Graceful degradation.** If no venv is found we simply keep running on
  ``sys.executable`` — we never hard-fail because ``.venv`` is missing.
* **No exec loops.** The re-exec is guarded by ``$OCR_BOOTSTRAPPED``.

Import style used by the scripts::

    from scripts._bootstrap import reexec_in_venv, env_int, env_str

which works both when ``ocr/`` is on ``sys.path`` (source checkout, after
``pip install -e .``) and when a script is run directly by path.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: ``ocr/`` — the directory holding ``pyproject.toml``, ``dots_mocr/``, ``scripts/``.
PACKAGE_ROOT = Path(__file__).resolve().parents[1]

#: Directory that *contains* the ``ocr/`` package (the repo root in a checkout).
REPO_ROOT = PACKAGE_ROOT.parent

#: Name of the guard variable that stops the re-exec from recursing forever.
BOOTSTRAP_ENV = "OCR_BOOTSTRAPPED"

__all__ = [
    "BOOTSTRAP_ENV",
    "PACKAGE_ROOT",
    "REPO_ROOT",
    "ensure_import_path",
    "env_float",
    "env_int",
    "env_str",
    "reexec_in_venv",
    "venv_python",
]


def ensure_import_path() -> None:
    """Put ``ocr/`` on ``sys.path`` so ``dots_mocr`` and ``scripts`` import.

    ``dots_mocr`` is a *flat* top-level package whose modules self-reference as
    ``from dots_mocr.utils.consts import ...``, so its parent (``ocr/``) must be
    importable as a top-level directory. A no-op when already present.
    """
    root = str(PACKAGE_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def venv_python() -> Path | None:
    """Locate a project venv interpreter, or ``None`` when there is none.

    Search order (never hardcoded, all relative to this file):

    1. ``$OCR_VENV_PYTHON`` — explicit override, wins outright.
    2. ``<ocr>/.venv/bin/python`` — venv created inside the package.
    3. ``<repo-root>/.venv/bin/python`` — venv created at the repo root.

    Returns ``None`` when nothing is found; callers then stay on the current
    interpreter instead of failing.
    """
    override = os.environ.get("OCR_VENV_PYTHON")
    if override:
        candidate = Path(override).expanduser()
        return candidate if candidate.is_file() else None

    for base in (PACKAGE_ROOT, REPO_ROOT):
        candidate = base / ".venv" / "bin" / "python"
        if candidate.is_file():
            return candidate
    return None


def reexec_in_venv() -> None:
    """Re-exec the current script under the project venv when one exists.

    Silently does nothing (graceful degradation) when:

    * no venv is found — we keep the current interpreter;
    * we are already running inside that venv (no exec loop);
    * re-exec already happened once (``$OCR_BOOTSTRAPPED`` is set);
    * ``$OCR_NO_REEXEC=1`` is set (escape hatch);
    * ``sys.argv[0]`` does not point at a real file (e.g. ``-c``, frozen).

    ``argv[0]`` is passed through unchanged so relative ``sys.argv[0]``
    semantics and ``__file__``-relative resolution inside the child are
    preserved. Must run *before* any third-party import, because the system
    ``python3`` may lack Pillow / NumPy / PyMuPDF.
    """
    if os.environ.get("OCR_NO_REEXEC") or os.environ.get(BOOTSTRAP_ENV):
        return

    venv_py = venv_python()
    if venv_py is None:
        return  # no venv anywhere — stay on the current interpreter

    try:
        if Path(sys.executable).resolve() == venv_py.resolve():
            return  # already inside it
    except OSError:
        return

    script_argv0 = sys.argv[0] if sys.argv else ""
    try:
        script = Path(script_argv0).resolve()
    except OSError:
        return
    if not script.is_file():
        return  # -c / -m / interactive: nothing to re-run

    os.environ[BOOTSTRAP_ENV] = "1"
    os.environ["OCR_VENV_PYTHON"] = str(venv_py)
    os.execv(str(venv_py), [str(venv_py), script_argv0, *sys.argv[1:]])


def env_str(*names: str, default: str) -> str:
    """First non-empty environment variable among ``names``, else ``default``.

    Later names act as fallbacks for earlier ones, which is how ``LMSTUDIO_*``
    keeps priority over the newer ``OCR_*`` names.
    """
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def env_int(*names: str, default: int) -> int:
    """First parseable environment variable among ``names``, else ``default``.

    An unparseable value is skipped rather than fatal — a typo in an env var
    should not make the CLI unusable, it should just use the documented default.
    """
    for name in names:
        raw = os.environ.get(name)
        if raw:
            try:
                return int(raw)
            except ValueError:
                continue
    return default


def env_float(*names: str, default: float) -> float:
    """First parseable float environment variable among ``names``, else ``default``."""
    for name in names:
        raw = os.environ.get(name)
        if raw:
            try:
                return float(raw)
            except ValueError:
                continue
    return default