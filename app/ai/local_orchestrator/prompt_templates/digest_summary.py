"""
DIGEST phase prompt builder — multi-page rollup summary for admin review.

Output: 3-paragraph Vietnamese markdown (300–500 words total).
Sampling: temperature=0.5, top_p=0.9, top_k=40, min_p=0.05.
"""

from app.ai.local_orchestrator.prompt_templates import universal_system_vi

_ROLE_EXTRA = (
    "Bạn tổng hợp digest cho toàn bộ source (300–500 từ) để admin review "
    "sau khi bộ wiki đã được tạo."
)

_TASK = """\
[NHIỆM VỤ]
Viết digest 3 đoạn bằng tiếng Việt dựa trên tóm tắt các trang wiki đã cung cấp.
Đoạn 1: Source nói về gì (tổng quan nội dung gốc).
Đoạn 2: Wiki bao phủ những gì + cấu trúc trang (số trang, chủ đề chính).
Đoạn 3: Lỗ hổng / câu hỏi mở còn tồn tại (nếu không có, ghi "Không có câu hỏi mở.").
Tổng độ dài: 300–500 từ. KHÔNG dùng heading hay bullet list."""


def build(page_markdowns: list[str]) -> str:
    """Build the DIGEST rollup prompt.

    Args:
        page_markdowns: List of per-page markdown strings (or their summaries).
                        Caller should trim to fit context window before passing.

    Returns:
        Full prompt string for the DIGEST LLM call.
    """
    if not page_markdowns:
        page_summaries_block = "(Không có trang nào được cung cấp.)"
    else:
        numbered = [
            f"[Trang {i + 1}]\n{md.strip()}" for i, md in enumerate(page_markdowns)
        ]
        page_summaries_block = "\n\n".join(numbered)

    parts = [
        universal_system_vi.build(_ROLE_EXTRA),
        "",
        _TASK,
        "",
        f"[INPUT — {len(page_markdowns)} trang wiki]",
        page_summaries_block,
        "",
        "[OUTPUT — digest 3 đoạn, 300–500 từ]",
    ]

    return "\n".join(parts)
