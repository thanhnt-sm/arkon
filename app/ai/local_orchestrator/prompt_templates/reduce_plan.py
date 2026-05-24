"""
REDUCE phase prompt builder — compile MAP extracts into a wiki structure plan.

Output: strict JSON with wiki title, description, and per-page outline.
Sampling: temperature=0.3, top_p=0.9, top_k=40, min_p=0.05.
"""

from app.ai.local_orchestrator.prompt_templates import universal_system_vi

_ROLE_EXTRA = "Bạn là editor tổng hợp, xây dựng cấu trúc wiki từ nhiều chunk extracts."

_TASK = """\
[NHIỆM VỤ]
Dựa trên các extracts từ MAP phase, đề xuất cấu trúc wiki tối ưu: danh sách trang con, \
entities chính và sequence sections cho từng trang. Output JSON theo schema — \
KHÔNG có markdown bọc ngoài, KHÔNG có giải thích."""

_DEFAULT_SCHEMA = """\
[SCHEMA]
{
  "wiki_title_vi": str,
  "wiki_description_vi": str,
  "pages": [{
    "slug": str,
    "title_vi": str,
    "type": "overview|deep_dive|reference|tutorial",
    "section_outline_vi": [str],
    "primary_entities": [str],
    "target_word_count": int
  }],
  "dependency_order": [str]
}

Lưu ý:
- slug: kebab-case, ký tự Latin không dấu (ví dụ: "kien-truc-transformer").
- target_word_count: 500–2000 từ mỗi trang.
- dependency_order: thứ tự slug nên viết (trang overview trước)."""


def build(claims_summary: str, outline_schema: str = "") -> str:
    """Build the REDUCE planning prompt.

    Args:
        claims_summary: Aggregated MAP-phase extracts/claims (JSON or plain text).
        outline_schema: Optional override schema. Uses built-in if empty.

    Returns:
        Full prompt string for the REDUCE LLM call.
    """
    schema_block = outline_schema.strip() if outline_schema.strip() else _DEFAULT_SCHEMA

    parts = [
        universal_system_vi.build(_ROLE_EXTRA),
        "",
        _TASK,
        "",
        schema_block,
        "",
        "[INPUT — aggregated extracts từ MAP phase]",
        claims_summary.strip(),
        "",
        "[OUTPUT]",
    ]

    return "\n".join(parts)
