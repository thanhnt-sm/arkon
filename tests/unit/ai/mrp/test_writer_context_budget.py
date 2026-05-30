from __future__ import annotations

from types import SimpleNamespace

from app.ai.mrp.writer import _get_source_context_budget


def test_get_source_context_budget_uses_local_runtime_profile():
    llm = SimpleNamespace(
        config=SimpleNamespace(spec=None),
        runtime_profile=SimpleNamespace(context_length=8000, is_local=True),
    )

    assert _get_source_context_budget(llm) == 8000


def test_get_source_context_budget_uses_catalog_spec_without_profile():
    llm = SimpleNamespace(
        config=SimpleNamespace(spec=SimpleNamespace(context_window_tokens=32000)),
    )

    assert _get_source_context_budget(llm) == 76800
