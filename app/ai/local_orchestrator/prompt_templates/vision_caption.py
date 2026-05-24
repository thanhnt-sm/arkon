"""
VISION phase prompt builder — image description for wiki pages.

Not prepended with universal_system_vi (vision model gets its own minimal
role instruction in Vietnamese). Output: 2–4 Vietnamese sentences.
Sampling: temperature=0.2, top_p=0.9.
"""

_BASE_ROLE = """\
Bạn mô tả hình ảnh kỹ thuật bằng tiếng Việt để chú thích trong wiki."""

_RULES = """\
[QUY ƯỚC MÔ TẢ]
1. Viết 2–4 câu tiếng Việt súc tích.
2. Nếu ảnh có chữ tiếng Việt: trích lại nguyên văn (verbatim).
3. Nếu ảnh là sơ đồ/biểu đồ: mô tả các thành phần chính và quan hệ giữa chúng.
4. Nếu ảnh có code: trích đoạn code chính trong backtick.
5. Thuật ngữ tiếng Anh trên ảnh: "Tiếng Việt (English)" lần đầu xuất hiện.
6. KHÔNG đoán thông tin không thể quan sát được từ ảnh.
7. KHÔNG dùng "tôi thấy" hay "hình ảnh cho thấy" — mô tả trực tiếp."""


def build(context_hint: str = "") -> str:
    """Build the VISION caption prompt (system turn for vision model).

    Args:
        context_hint: Optional sentence describing the page/section context
                      where this image appears (helps model frame the caption).

    Returns:
        System prompt string for the vision LLM call.
        The caller attaches the image in the user turn separately.
    """
    parts = [_BASE_ROLE, "", _RULES]

    if context_hint and context_hint.strip():
        parts += [
            "",
            "[NGỮ CẢNH TRANG]",
            context_hint.strip(),
        ]

    parts += ["", "[CAPTION]"]

    return "\n".join(parts)
