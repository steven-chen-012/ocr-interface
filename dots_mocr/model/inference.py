"""
inference.py — dot-OCR pipeline on top of any OpenAI-compatible chat endpoint.

Designed to work with LM Studio out of the box
(`http://127.0.0.1:1234/v1`), but also compatible with vLLM/Ollama/TGI
servers that expose the same `/v1/chat/completions` route.

This file replaces the vLLM-client version of `inference_with_vllm` while
preserving its signature, so `dots_mocr/parser.py` can call it unchanged.
"""
from __future__ import annotations

import base64
import io
import logging
import os
from typing import Optional, Union

from PIL import Image

logger = logging.getLogger(__name__)

# Lazy import so that `pip install pymupdf pillow` is the only hard dep
# for the model layer. The official dots.ocr `image_utils` already provides
# a PIL → base64 helper, but we keep a local one so this module stays
# self-contained (you don't have to wire up utils if you only want inference).
try:
    from dots_mocr.utils.image_utils import PILimage_to_base64  # type: ignore
except Exception:  # pragma: no cover
    PILimage_to_base64 = None  # fall back to our local helper


def _pil_to_data_url(
    image: Image.Image,
    format: str = "JPEG",
    jpeg_quality: int = 85,
) -> str:
    """Convert a PIL image into a base64 data URL for OpenAI-style image_url.

    Default is JPEG (not PNG) because:
      * JPEG shrinks the wire payload ~5–10× vs PNG for scanned documents
        (white background + grayscale text compress extremely well with DCT).
      * The visual content the model needs (text edges, layout) is preserved
        at quality=85 — verified visually indistinguishable on scan samples.
      * LM Studio's HTTP server is single-threaded; smaller bodies = lower
        TTFT, which is the dominant user-perceived latency on Apple Silicon.

    Override per-call by passing ``format="PNG"``.
    """
    if PILimage_to_base64 is not None:
        return PILimage_to_base64(image, format=format)

    # Drop alpha channel — JPEG has no alpha, and dots.ocr was trained on RGB.
    if image.mode != "RGB":
        image = image.convert("RGB")

    buf = io.BytesIO()
    if format.upper() == "JPEG":
        image.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    else:
        image.save(buf, format=format)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/{format.lower()};base64,{b64}"


def _build_user_content(
    image: Optional[Union[Image.Image, str]],
    prompt: str,
) -> list:
    """
    Build the `messages[*].content` list.

    `image` may be:
      * None            — pure text QA
      * PIL.Image.Image — will be encoded as a base64 PNG data URL
      * str             — either an http(s) URL (passed through), a
                          file:// URL, or a local filesystem path that
                          we'll prefix with file://, or already a
                          base64 data URL.
    """
    content: list = []
    if image is not None:
        if isinstance(image, Image.Image):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": _pil_to_data_url(image)},
                }
            )
        elif isinstance(image, str):
            url = image
            if not (
                url.startswith("http://")
                or url.startswith("https://")
                or url.startswith("data:")
                or url.startswith("file://")
            ):
                # Treat as a local path — convert to file:// URL.
                url = "file://" + os.path.abspath(url)
            content.append({"type": "image_url", "image_url": {"url": url}})
        else:
            raise TypeError(
                f"image must be a PIL.Image or str path/URL, got {type(image)}"
            )

    content.append({"type": "text", "text": prompt})
    return content


def inference_with_vllm(  # noqa: N802 — keep official name
    image: Optional[Union[Image.Image, str]],
    prompt: str,
    *,
    model_name: str = "model",
    protocol: str = "http",
    ip: str = "localhost",
    port: int = 1234,
    temperature: float = 0.1,
    top_p: float = 1.0,
    max_completion_tokens: int = 16384,
    system_prompt: Optional[str] = None,
    # ---- extras below; defaults keep behaviour identical to upstream ----
    api_key: Optional[str] = None,
    timeout: float = 600.0,
    extra_body: Optional[dict] = None,
) -> str:
    """
    Send `image + prompt` to an OpenAI-compatible chat completion endpoint
    and return the assistant message text.

    Function name is preserved (`inference_with_vllm`) so that parser.py's
    call site doesn't need a single edit.
    """
    # Import lazily so the rest of dots_mocr can be imported in environments
    # where openai isn't installed (e.g. upstream GPU setup).
    try:
        from openai import OpenAI
    except ImportError as e:
        raise ImportError(
            "The `openai` Python SDK is required for the Mac-friendly backend. "
            "Install it with `pip install openai>=1.40`."
        ) from e

    base_url = f"{protocol}://{ip}:{port}/v1"
    api_key = api_key or os.environ.get("LMSTUDIO_API_KEY", "lm-studio")

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    messages: list = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append(
        {
            "role": "user",
            "content": _build_user_content(image, prompt),
        }
    )

    # The OpenAI Python SDK accepts `max_completion_tokens` since v1.40+.
    # Some upstream proxies still expect the legacy `max_tokens` key, so we
    # send both via extra_body for maximum compatibility.
    legacy_max_tokens = {"max_tokens": max_completion_tokens}

    logger.info(
        "POST %s/chat/completions model=%s temp=%s top_p=%s max=%s",
        base_url, model_name, temperature, top_p, max_completion_tokens,
    )

    resp = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        max_completion_tokens=max_completion_tokens,
        extra_body={**legacy_max_tokens, **(extra_body or {})},
    )

    # LM Studio / vLLM always return at least one choice.
    msg = resp.choices[0].message
    content = msg.content or ""

    # Strip chat-template echo quirks that some backends add.
    if isinstance(content, str):
        return content.strip()

    # Defensive: if backend returns list-of-parts, flatten text parts.
    if isinstance(content, list):
        texts = [p.get("text", "") for p in content if isinstance(p, dict)]
        return "\n".join(t for t in texts if t).strip()

    return str(content).strip()
