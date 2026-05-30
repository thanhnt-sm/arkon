from __future__ import annotations

from types import SimpleNamespace

from app.ai.mrp.reducer import _build_fallback_pages


def test_build_fallback_pages_uses_claim_subjects_and_source_page():
    source = SimpleNamespace(id="source-id", title="Sample Source", file_name=None)
    entities = [{"name": "Vy", "aliases": [], "mention_count": 3}]
    concepts = [{"term": "Can thiệp sớm", "mention_count": 2}]
    claims = [
        {"subject": "Vy", "statement": "Vy duoc chan doan"},
        {"subject": "Can thiệp sớm", "statement": "Can thiep giup tre"},
        {"subject": "Can thiệp sớm", "statement": "Can thiep can lap lai"},
    ]

    pages = _build_fallback_pages(source, "standard", entities, concepts, claims)

    assert pages[0]["page_type"] == "source"
    assert pages[0]["slug"] == "source/sample-source"
    assert any(page["title"] == "Can thiệp sớm" for page in pages)
    assert all(page["entity_names"] for page in pages)
