"""
REFINE phase prompt builder — long-form Vietnamese wiki page writing.

Most critical phase: produces the final markdown page with frontmatter,
citations [E#], internal links [[slug|title]], and H2/H3 structure.
Sampling: temperature=0.7, repeat_penalty=1.1, top_p=0.9, min_p=0.05.
"""

from app.ai.local_orchestrator.prompt_templates import universal_system_vi
from app.ai.local_orchestrator.prompt_templates.few_shot_examples import (
    REFINE_EXAMPLE_1,
    REFINE_EXAMPLE_2,
)

_ROLE_EXTRA = """\
Bạn đang viết một trang wiki cụ thể trong bộ wiki lớn. \
Output là markdown đầy đủ với frontmatter YAML."""

_WRITING_RULES = """\
[QUY TẮC VIẾT]
1. Mở bài (2-3 câu): định nghĩa + ngữ cảnh + tầm quan trọng.
2. Thân bài: theo outline, mỗi section 200–400 từ, có heading ## (tiếng Việt).
3. Trích dẫn: dạng [E#] đặt SAU câu (không sau từng cụm từ).
4. Heading: dùng tiếng Việt; thuật ngữ trong tiêu đề kèm (English / ABBR).
5. Internal link: [[related-slug|Tiêu đề tiếng Việt]] khi nhắc trang khác.
6. KHÔNG copy nguyên văn từ evidence — paraphrase + cite.
7. Code/command/path: giữ trong backtick, không dịch."""

_OUTPUT_FORMAT = """\
[ĐỊNH DẠNG OUTPUT]
---
slug: {slug}
title_vi: {title_vi}
page_type: {page_type}
citations: [E1, E2, ...]
---

# {title_vi}

{nội dung markdown đầy đủ}"""


def build(
    page_spec: str,
    evidence_block: str,
    related_kb: str = "",
    include_examples: bool = True,
) -> str:
    """Build the REFINE wiki-writing prompt.

    Args:
        page_spec: Structured page spec (slug, title_vi, type, outline, word count).
        evidence_block: Top-K retrieved evidence lines formatted as [E1] ... [E2] ...
        related_kb: Optional list of related wiki pages for internal links.
        include_examples: Include few-shot paragraph examples (True for max mode).

    Returns:
        Full prompt string for the REFINE LLM call.
    """
    parts = [
        universal_system_vi.build(_ROLE_EXTRA),
        "",
        "[PAGE_SPEC]",
        page_spec.strip(),
        "",
        "[EVIDENCE — top-K từ retrieval]",
        evidence_block.strip(),
    ]

    if related_kb and related_kb.strip():
        parts += [
            "",
            "[RELATED_KB — link đến trang khác trong wiki]",
            related_kb.strip(),
        ]

    parts += [
        "",
        _WRITING_RULES,
    ]

    if include_examples:
        parts += [
            "",
            "[FEW-SHOT EXAMPLES — đoạn wiki mẫu]",
            REFINE_EXAMPLE_1,
            "",
            REFINE_EXAMPLE_2,
        ]

    parts += [
        "",
        _OUTPUT_FORMAT,
    ]

    return "\n".join(parts)
