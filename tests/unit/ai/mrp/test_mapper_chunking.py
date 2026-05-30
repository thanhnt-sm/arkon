from __future__ import annotations

from app.ai.mrp.mapper import build_chunks


def test_build_chunks_uses_runtime_target_for_sliding_windows():
    full_text = "x" * 12_500

    chunks = build_chunks(full_text, outline_json=None, strategy="standard", target_chars=5_000)

    assert [c.end_char - c.start_char for c in chunks] == [5_000, 5_000, 2_500]


def test_build_chunks_uses_runtime_target_for_outline_groups():
    full_text = "x" * 12_000
    outline = [
        {"level": 1, "title": "A", "char_start": 0, "char_end": 4_000},
        {"level": 1, "title": "B", "char_start": 4_000, "char_end": 8_000},
        {"level": 1, "title": "C", "char_start": 8_000, "char_end": 12_000},
    ]

    chunks = build_chunks(full_text, outline_json=outline, strategy="standard", target_chars=5_000)

    assert [(c.start_char, c.end_char) for c in chunks] == [
        (0, 4_000),
        (4_000, 8_000),
        (8_000, 12_000),
    ]
