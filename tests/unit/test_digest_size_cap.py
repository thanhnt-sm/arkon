"""
Unit tests for app/ai/mrp/digest.py:
  - _enforce_size_cap: recursion terminates at MAX_DEPTH=4
  - _validate_wiki_links: allowlist gates [[slug]] references
  - _strip_unsafe_html: <script>/<iframe>/etc removed

These are pure functions; no DB/network involved.
"""

import pytest

from app.ai.mrp.digest import (
    MAX_DEPTH,
    MAX_DIGEST_CHARS,
    _enforce_size_cap,
    _strip_unsafe_html,
    _validate_wiki_links,
)


# ---------------------------------------------------------------------------
# _enforce_size_cap
# ---------------------------------------------------------------------------

def test_size_cap_under_limit_unchanged():
    content = "short content under cap"
    assert _enforce_size_cap(content, max_chars=1000) == content


def test_size_cap_truncates_to_max():
    huge = "x" * 100_000
    result = _enforce_size_cap(huge, max_chars=1000)
    # Hard truncation marker added when no H1/H2/H3 boundaries present.
    assert len(result) <= 1000 + 200  # marker is ~80 chars VN
    assert result.startswith("x" * 1000)


def test_size_cap_recursion_terminates_on_flat_doc():
    """A 5M-char flat doc with no headings must NOT stack-overflow."""
    huge = "y" * 5_000_000
    result = _enforce_size_cap(huge, max_chars=10_000)
    # Should return truncated content + marker — no recursion explosion
    assert len(result) < 50_000


def test_size_cap_recursion_with_headings():
    """Content split by H1/H2 boundaries should split in halves down to MAX_DEPTH."""
    sections = []
    for i in range(8):
        sections.append(f"\n# Section {i}\n" + ("x" * 50_000))
    big = "intro\n" + "".join(sections)
    result = _enforce_size_cap(big, max_chars=80_000)
    # After halving, length should be bounded; no exception raised
    assert isinstance(result, str)
    assert len(result) > 0


def test_size_cap_respects_max_depth():
    """Even with deep splits available, depth caps at MAX_DEPTH then hard-truncates."""
    # Build content that always halves cleanly
    chunk = "# H\n" + ("z" * 1_000)
    big = (chunk * 200)  # ~204KB
    result = _enforce_size_cap(big, max_chars=500)
    # Either it converged via halving, or hit depth cap + truncation marker.
    assert len(result) <= 500 + 200


def test_max_digest_chars_default():
    """Default cap is MAX_DIGEST_CHARS (100k)."""
    assert MAX_DIGEST_CHARS == 100_000
    assert MAX_DEPTH == 4


# ---------------------------------------------------------------------------
# _validate_wiki_links
# ---------------------------------------------------------------------------

def test_validate_wiki_links_allowed():
    content = "See [[valid-slug]] and [[another-page]] for details."
    allowlist = ["valid-slug", "another-page"]
    result = _validate_wiki_links(content, allowlist)
    assert result == content


def test_validate_wiki_links_rejects_path_traversal():
    content = "Malicious [[../etc/passwd]] link"
    with pytest.raises(ValueError, match="unauthorized wiki-links"):
        _validate_wiki_links(content, allowlist=["valid-slug"])


def test_validate_wiki_links_rejects_unauthorized():
    content = "Random [[unknown-slug]] reference"
    with pytest.raises(ValueError, match="unauthorized"):
        _validate_wiki_links(content, allowlist=["other-slug"])


def test_validate_wiki_links_empty_content():
    """Empty content has no wiki-links to validate."""
    assert _validate_wiki_links("", allowlist=[]) == ""


def test_validate_wiki_links_no_links_present():
    content = "Plain markdown without any wiki links here."
    assert _validate_wiki_links(content, allowlist=[]) == content


def test_validate_wiki_links_with_pipe_alias():
    """[[slug|display]] form — slug part is what's validated."""
    content = "Check [[valid-slug|Display Name]] now."
    result = _validate_wiki_links(content, allowlist=["valid-slug"])
    assert result == content


# ---------------------------------------------------------------------------
# _strip_unsafe_html
# ---------------------------------------------------------------------------

def test_strip_unsafe_html_removes_script():
    """Script tags must be fully removed (incl. content)."""
    content = "Hello <script>alert('xss')</script> world"
    result = _strip_unsafe_html(content)
    assert "<script>" not in result
    assert "alert" not in result
    assert "Hello" in result
    assert "world" in result


def test_strip_unsafe_html_removes_iframe():
    content = "Pre <iframe src='evil.com'></iframe> post"
    result = _strip_unsafe_html(content)
    assert "<iframe" not in result
    assert "evil.com" not in result


def test_strip_unsafe_html_preserves_wiki_links():
    """[[wikilinks]] must survive HTML strip."""
    content = "See [[my-page]] and <span>boom</span>."
    result = _strip_unsafe_html(content)
    assert "[[my-page]]" in result
    assert "<span>" not in result


def test_strip_unsafe_html_removes_style():
    content = "before <style>.x{color:red}</style> after"
    result = _strip_unsafe_html(content)
    assert "<style>" not in result
    assert "color:red" not in result
