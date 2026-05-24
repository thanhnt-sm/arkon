"""
MAP phase prompt builder — structured extraction from a source chunk.

Output: strict JSON matching the extraction schema.
Sampling: temperature=0.2, top_p=0.9, top_k=40, min_p=0.05 (deterministic).
"""

from app.ai.local_orchestrator.prompt_templates import universal_system_vi
from app.ai.local_orchestrator.prompt_templates.few_shot_examples import (
    MAP_EXAMPLE_1,
    MAP_EXAMPLE_2,
)

_TASK = """\
[NHIỆM VỤ]
Trích xuất tri thức có cấu trúc từ đoạn văn bản nguồn (chunk) dưới đây.
Output là JSON tuân thủ schema — KHÔNG có markdown bọc ngoài, KHÔNG có giải thích trước/sau."""

_SCHEMA = """\
[SCHEMA]
{
  "entities": [{"name_vi": str, "name_en": str|null, "type": "concept|person|org|tech|event", "definition_vi": str}],
  "claims": [{"text_vi": str, "evidence_quote": str, "confidence": 0.0-1.0}],
  "relations": [{"subject": str, "predicate_vi": str, "object": str, "evidence_quote": str}],
  "open_questions": [str],
  "summary_vi": str
}"""


def build(
    chunk: str,
    rolling_summary: str,
    schema_json: str = "",
    include_examples: bool = True,
) -> str:
    """Build the MAP extraction prompt.

    Args:
        chunk: Raw source text to extract from.
        rolling_summary: ≤300-word summary of previously processed chunks.
        schema_json: Optional override schema JSON string. Uses built-in if empty.
        include_examples: Include few-shot examples (True for max mode).

    Returns:
        Full prompt string ready for user-turn submission (system prompt separate).
    """
    schema_block = schema_json.strip() if schema_json.strip() else _SCHEMA
    parts = [
        universal_system_vi.build(),
        "",
        _TASK,
        "",
        schema_block,
    ]

    if include_examples:
        parts += [
            "",
            "[FEW-SHOT EXAMPLES]",
            MAP_EXAMPLE_1,
            "",
            MAP_EXAMPLE_2,
        ]

    parts += [
        "",
        "[NGỮ CẢNH TRƯỚC — rolling context từ các chunk trước]",
        rolling_summary.strip() if rolling_summary.strip() else "(chưa có chunk nào trước đó)",
        "",
        "[SOURCE_CHUNK]",
        chunk.strip(),
        "",
        "[OUTPUT]",
    ]

    return "\n".join(parts)
