"""
VERIFY phase prompt builder — audit pass on a drafted wiki page.

Deterministic (temperature=0.0, top_k=1): finds rule violations without
modifying the draft. Output is a JSON list of violation objects.

R1 = citations     R2 = Vietnamese format   R3 = pronouns
R4 = tense         R5 = hallucination        R6 = length
"""

from app.ai.local_orchestrator.prompt_templates import universal_system_vi

_ROLE_EXTRA = "Bạn là kiểm duyệt viên. KHÔNG sửa bài viết. Chỉ liệt kê lỗi vi phạm."

_TASK = """\
[NHIỆM VỤ]
Kiểm tra trang wiki bên dưới theo danh sách kiểm tra (checklist). \
Output là JSON array — mỗi item là một vi phạm. \
Nếu không có vi phạm, trả về mảng rỗng []. \
KHÔNG có markdown bọc ngoài."""

_CHECKLIST = """\
[CHECKLIST]
R1 Trích dẫn (Citation): mọi claim factual phải có [E#] trong cùng câu.
R2 Định dạng tiếng Việt: thuật ngữ kỹ thuật phải có (English / ABBR) ở lần xuất hiện đầu tiên.
R3 Đại từ nhân xưng: không có "tôi/bạn/chúng ta/của bạn".
R4 Nhất quán thì (tense consistency): không pha trộn thì trong cùng đoạn.
R5 Bịa đặt (Hallucination): claim không khớp evidence — vi phạm CRITICAL.
R6 Độ dài (Length): nội dung nằm trong ±20% target_word_count."""

_SCHEMA = """\
[OUTPUT SCHEMA]
[
  {
    "rule_id": "R1"|"R2"|"R3"|"R4"|"R5"|"R6",
    "severity": "critical"|"high"|"medium"|"low",
    "location": str,
    "quote": str,
    "suggestion": str
  },
  ...
]"""


def build(page_markdown: str, evidence_block: str) -> str:
    """Build the VERIFY audit prompt.

    Args:
        page_markdown: Full markdown content of the drafted wiki page.
        evidence_block: Complete evidence bag used during REFINE (for R5 check).

    Returns:
        Full prompt string for the VERIFY LLM call.
    """
    parts = [
        universal_system_vi.build(_ROLE_EXTRA),
        "",
        _TASK,
        "",
        _CHECKLIST,
        "",
        _SCHEMA,
        "",
        "[DRAFT — trang wiki cần kiểm tra]",
        page_markdown.strip(),
        "",
        "[EVIDENCE BAG — dùng để xác minh R5]",
        evidence_block.strip(),
        "",
        "[OUTPUT]",
    ]

    return "\n".join(parts)
