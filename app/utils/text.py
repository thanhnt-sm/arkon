import json
import re
import unicodedata
from typing import Any


def strip_code_fence(raw: str) -> str:
    """
    Remove a surrounding ```json ... ``` (or plain ``` ... ```) fence from an
    LLM response. Unlike `str.strip("```json")`, which strips any of those
    characters and can corrupt valid JSON, this matches the fence as a substring.
    """
    s = raw.strip()
    # Leading fence
    s = re.sub(r"^```(?:json|JSON)?\s*\n?", "", s)
    # Trailing fence
    s = re.sub(r"\n?```\s*$", "", s)
    return s.strip()


def _clean_json_from_llm(s: str) -> str:
    """
    Fix common JSON defects produced by local/fine-tuned LLMs:
      - JS single-line comments: // ...
      - JS multi-line comments: /* ... */
      - Trailing commas before } or ]
    """
    # Remove /* ... */ block comments
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
    # Remove // line comments (avoid stripping URLs like https://)
    s = re.sub(r'(?<!:)//[^\n]*', "", s)
    # Remove trailing commas before } or ]
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s


def parse_json_loose(raw: str) -> Any:
    """
    Parse a JSON value from an LLM response that may be wrapped in a code fence,
    have trailing prose, or contain JS-style defects (comments, trailing commas).
    """
    cleaned = strip_code_fence(raw)

    # First attempt: strict parse on cleaned text
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Second attempt: fix JS-style defects
    fixed = _clean_json_from_llm(cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Final fallback: truncate at last closing bracket (handles trailing prose)
    last = max(fixed.rfind("}"), fixed.rfind("]"))
    if last != -1:
        return json.loads(fixed[: last + 1])
    raise json.JSONDecodeError("No valid JSON found", cleaned, 0)


def slugify(text: str) -> str:
    """
    Convert text to a URL-friendly slug.
    Supports Vietnamese characters by removing diacritics.
    """
    if not text:
        return ""
    
    # Convert to lowercase
    text = text.lower()
    
    # Remove Vietnamese diacritics
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    
    # Replace non-alphanumeric characters with hyphens
    text = re.sub(r'[^a-z0-9]+', '-', text)
    
    # Remove leading/trailing hyphens
    text = text.strip('-')
    
    return text
