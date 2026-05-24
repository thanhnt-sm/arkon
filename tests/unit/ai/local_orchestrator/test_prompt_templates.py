"""
Unit tests for app/ai/local_orchestrator/prompt_templates/

Coverage:
- Each template builder returns a non-empty str
- Universal VI system prompt substring appears in every phase output
- include_examples=False omits few-shot examples in map_extract / refine_write
- Snapshot (golden) tests for fixed inputs using normalised whitespace comparison
- digest_summary handles empty list gracefully
- vision_caption context_hint is conditional
"""

from __future__ import annotations

import re

import pytest

from app.ai.local_orchestrator.prompt_templates import universal_system_vi
from app.ai.local_orchestrator.prompt_templates.digest_summary import (
    build as build_digest,
)
from app.ai.local_orchestrator.prompt_templates.map_extract import (
    build as build_map,
)
from app.ai.local_orchestrator.prompt_templates.reduce_plan import (
    build as build_reduce,
)
from app.ai.local_orchestrator.prompt_templates.refine_write import (
    build as build_refine,
)
from app.ai.local_orchestrator.prompt_templates.verify_check import (
    build as build_verify,
)
from app.ai.local_orchestrator.prompt_templates.vision_caption import (
    build as build_vision,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SYSTEM_ANCHOR = "biên tập viên wiki kỹ thuật"  # stable substring of SYSTEM_PROMPT_VI


def _normalise(text: str) -> str:
    """Collapse runs of whitespace to a single space for snapshot comparison."""
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Shared fixture inputs
# ---------------------------------------------------------------------------

_CHUNK = "The Transformer model introduced by Vaswani et al. (2017) uses self-attention."
_ROLLING = "Đây là rolling summary từ chunk trước."
_CLAIMS = '{"entities": [], "claims": [{"text_vi": "Transformer ra đời 2017."}]}'
_PAGE_SPEC = "slug: transformer\ntitle_vi: Kiến trúc Transformer\ntype: overview"
_EVIDENCE = "[E1] Transformer introduced by Vaswani et al. (2017) — source_id=s001"
_RELATED = "- kien-truc-cnn: Mạng nơ-ron tích chập"
_DRAFT_MD = "# Kiến trúc Transformer\n\nTransformer ra đời năm 2017."

# ---------------------------------------------------------------------------
# 1. universal_system_vi
# ---------------------------------------------------------------------------


def test_universal_system_vi_build_no_extra():
    result = universal_system_vi.build()
    assert isinstance(result, str)
    assert len(result) > 100
    assert _SYSTEM_ANCHOR in result


def test_universal_system_vi_build_with_extra():
    extra = "Đây là chú thích thêm."
    result = universal_system_vi.build(extra)
    assert extra in result
    assert _SYSTEM_ANCHOR in result
    # extra must come after base prompt
    assert result.index(_SYSTEM_ANCHOR) < result.index(extra)


def test_universal_system_vi_build_empty_extra_no_double_newline():
    """Empty extra must not append trailing blank lines."""
    result = universal_system_vi.build("")
    assert not result.endswith("\n\n")


# ---------------------------------------------------------------------------
# 2. map_extract
# ---------------------------------------------------------------------------


def test_map_extract_returns_nonempty_string():
    result = build_map(_CHUNK, _ROLLING)
    assert isinstance(result, str) and len(result) > 50


def test_map_extract_contains_system_anchor():
    result = build_map(_CHUNK, _ROLLING)
    assert _SYSTEM_ANCHOR in result


def test_map_extract_contains_chunk():
    result = build_map(_CHUNK, _ROLLING)
    assert _CHUNK in result


def test_map_extract_with_examples_includes_few_shot():
    result = build_map(_CHUNK, _ROLLING, include_examples=True)
    assert "FEW-SHOT" in result or "few_shot" in result.lower() or "EXAMPLE" in result


def test_map_extract_without_examples_omits_few_shot():
    result = build_map(_CHUNK, _ROLLING, include_examples=False)
    # MAP_EXAMPLE_2 contains "Docker" — only present when examples included
    assert "Docker" not in result


def test_map_extract_empty_rolling_uses_placeholder():
    result = build_map(_CHUNK, "")
    assert "chưa có chunk nào" in result


# ---------------------------------------------------------------------------
# 3. reduce_plan
# ---------------------------------------------------------------------------


def test_reduce_plan_returns_nonempty_string():
    result = build_reduce(_CLAIMS)
    assert isinstance(result, str) and len(result) > 50


def test_reduce_plan_contains_system_anchor():
    result = build_reduce(_CLAIMS)
    assert _SYSTEM_ANCHOR in result


def test_reduce_plan_contains_claims_summary():
    result = build_reduce(_CLAIMS)
    assert _CLAIMS in result


# ---------------------------------------------------------------------------
# 4. refine_write
# ---------------------------------------------------------------------------


def test_refine_write_returns_nonempty_string():
    result = build_refine(_PAGE_SPEC, _EVIDENCE)
    assert isinstance(result, str) and len(result) > 50


def test_refine_write_contains_system_anchor():
    result = build_refine(_PAGE_SPEC, _EVIDENCE)
    assert _SYSTEM_ANCHOR in result


def test_refine_write_with_examples_includes_few_shot():
    result = build_refine(_PAGE_SPEC, _EVIDENCE, include_examples=True)
    # REFINE_EXAMPLE_1 contains "Kubernetes"
    assert "Kubernetes" in result


def test_refine_write_without_examples_omits_few_shot():
    result = build_refine(_PAGE_SPEC, _EVIDENCE, include_examples=False)
    assert "Kubernetes" not in result


def test_refine_write_related_kb_optional():
    without = build_refine(_PAGE_SPEC, _EVIDENCE, related_kb="")
    with_kb = build_refine(_PAGE_SPEC, _EVIDENCE, related_kb=_RELATED)
    assert _RELATED not in without
    assert _RELATED in with_kb


# ---------------------------------------------------------------------------
# 5. verify_check
# ---------------------------------------------------------------------------


def test_verify_check_returns_nonempty_string():
    result = build_verify(_DRAFT_MD, _EVIDENCE)
    assert isinstance(result, str) and len(result) > 50


def test_verify_check_contains_system_anchor():
    result = build_verify(_DRAFT_MD, _EVIDENCE)
    assert _SYSTEM_ANCHOR in result


def test_verify_check_contains_all_rule_ids():
    result = build_verify(_DRAFT_MD, _EVIDENCE)
    for rule in ("R1", "R2", "R3", "R4", "R5", "R6"):
        assert rule in result, f"Rule {rule} missing from verify_check output"


def test_verify_check_contains_draft_and_evidence():
    result = build_verify(_DRAFT_MD, _EVIDENCE)
    assert _DRAFT_MD.strip() in result
    assert _EVIDENCE in result


# ---------------------------------------------------------------------------
# 6. digest_summary
# ---------------------------------------------------------------------------


def test_digest_summary_returns_nonempty_string():
    result = build_digest(["Trang 1 nội dung.", "Trang 2 nội dung."])
    assert isinstance(result, str) and len(result) > 50


def test_digest_summary_contains_system_anchor():
    result = build_digest(["Trang 1."])
    assert _SYSTEM_ANCHOR in result


def test_digest_summary_empty_list_graceful():
    result = build_digest([])
    assert isinstance(result, str)
    assert "Không có trang nào" in result


def test_digest_summary_numbers_pages():
    result = build_digest(["Alpha", "Beta", "Gamma"])
    assert "Trang 1" in result
    assert "Trang 3" in result


# ---------------------------------------------------------------------------
# 7. vision_caption
# ---------------------------------------------------------------------------


def test_vision_caption_returns_nonempty_string():
    result = build_vision()
    assert isinstance(result, str) and len(result) > 20


def test_vision_caption_without_context_hint():
    result = build_vision()
    assert "NGỮ CẢNH TRANG" not in result


def test_vision_caption_with_context_hint():
    hint = "Ảnh minh hoạ kiến trúc Transformer."
    result = build_vision(hint)
    assert hint in result
    assert "NGỮ CẢNH TRANG" in result


# ---------------------------------------------------------------------------
# 8. Snapshot (golden) tests — normalised whitespace
# ---------------------------------------------------------------------------

_GOLDEN_MAP_NOEXAMPLE = (
    "[NHIỆM VỤ] Trích xuất tri thức có cấu trúc"
)

_GOLDEN_VERIFY_RULES = "R1 Trích dẫn (Citation)"


def test_snapshot_map_extract_no_examples_contains_golden():
    result = _normalise(build_map(_CHUNK, _ROLLING, include_examples=False))
    assert _GOLDEN_MAP_NOEXAMPLE in result


def test_snapshot_verify_check_contains_rule_golden():
    result = _normalise(build_verify(_DRAFT_MD, _EVIDENCE))
    assert _GOLDEN_VERIFY_RULES in result
