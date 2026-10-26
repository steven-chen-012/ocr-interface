"""Command-line entry points for the ``ocr`` package.

Each module in here works two ways:

* ``python -m ocr.scripts.note_to_markdown ...`` (package install or repo root on
  ``sys.path``)
* ``python ocr/scripts/note_to_markdown.py ...`` (direct run from a clone)

Both paths resolve through :mod:`ocr`, so there is no hardcoded location.
"""

from __future__ import annotations

__all__: list[str] = []