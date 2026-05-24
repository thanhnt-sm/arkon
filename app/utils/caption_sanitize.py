"""Sanitize VLM caption outputs.

Local VLMs (paddleocr-vl, deepseek-ocr-2, qwen-vl) frequently emit:
- Hallucination loops — single caption running 5-10KB of repeated phrases.
- Refusals — "The image is a graphic design and does not contain..."
- Chinese character leak — when reading Vietnamese text the OCR backbone
  proposes plausible-looking CJK glyphs.
- Empty / near-empty strings on photo-only frames.

This module is a defensive layer: it does NOT re-call the model (caller
decides whether to retry). It returns a cleaned caption + warns on
issues so the caller can decide retry policy.
"""

from __future__ import annotations

import re
from typing import Final

from loguru import logger

# Length bounds. Captions outside these are flagged as suspicious but the
# value is still returned (truncated for over-long).
MIN_USEFUL_CHARS: Final[int] = 15
MAX_USEFUL_CHARS: Final[int] = 2_000

# CJK (Chinese/Japanese/Korean) Unicode blocks — flag leak when the source
# document is expected to be Vietnamese/English.
_CJK_PATTERN: Final[re.Pattern] = re.compile(
    r"[぀-ゟ゠-ヿ一-鿿豈-﫿]"
)

# Known refusal/filler openers from local VLMs.
_REFUSAL_PATTERNS: Final[tuple[re.Pattern, ...]] = (
    re.compile(r"^the image is a (graphic design|photo|picture) and does not", re.IGNORECASE),
    re.compile(r"^i cannot (extract|describe|analyze|see)", re.IGNORECASE),
    re.compile(r"^sorry,? i (can'?t|cannot)", re.IGNORECASE),
    re.compile(r"^based on the (image|picture)", re.IGNORECASE),
)


def _strip_filler_prefix(text: str) -> str:
    """Drop a leading filler clause like 'Based on the image, X' → 'X'."""
    m = re.match(r"^(based on the (image|picture|photo)[^,.]*[,.]\s*)(.+)", text, re.IGNORECASE)
    if m:
        return m.group(3).strip()
    return text


def sanitize_caption(raw: str | None, *, expected_cjk: bool = False) -> str:
    """Clean a VLM caption. Returns a possibly-empty string.

    `expected_cjk=True` disables the CJK-leak warning (use when ingesting
    Chinese/Japanese sources).
    """
    if not raw:
        return ""

    text = raw.strip()

    # Drop leading filler.
    text = _strip_filler_prefix(text)

    # Hallucination-loop detection: caption far larger than the prompt's
    # 1-3 sentence target → truncate at MAX_USEFUL_CHARS. Better than the
    # current 10KB outliers consuming downstream token budget.
    if len(text) > MAX_USEFUL_CHARS:
        logger.warning(
            f"caption_sanitize: truncating likely-hallucinated caption "
            f"({len(text)} → {MAX_USEFUL_CHARS} chars)"
        )
        text = text[:MAX_USEFUL_CHARS].rstrip()

    # Refusal detection: collapse to empty so downstream MRP ignores the
    # marker. (Keeping a refusal string pollutes the source.full_text fed
    # to the LLM during MAP.)
    for pat in _REFUSAL_PATTERNS:
        if pat.search(text):
            logger.info(f"caption_sanitize: dropped refusal/filler caption: {text[:80]!r}")
            return ""

    # CJK leak detection — informational only.
    if not expected_cjk:
        cjk_hits = _CJK_PATTERN.findall(text)
        if cjk_hits:
            logger.info(
                f"caption_sanitize: {len(cjk_hits)} CJK char(s) in non-CJK caption "
                f"(possible OCR leak): {text[:120]!r}"
            )

    # Min-length check — informational; empty captions are valid downstream.
    if 0 < len(text) < MIN_USEFUL_CHARS:
        logger.info(f"caption_sanitize: very short caption ({len(text)} chars): {text!r}")

    return text
