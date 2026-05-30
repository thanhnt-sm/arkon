"""
Phase 3.5 — Comprehensive Source Digest.

Produces one `page_type='digest'` wiki page per source. Slug pattern:
`digest/<source-slug>`. Two narrative strategies:

  - outline: per-H1/H2 narrative loop (when source.outline_json is non-empty).
  - flat: TOC + plan.summary + first-N chars of sub-pages (no per-section LLM).

Hardening:
  - Wiki-link allowlist: only `[[slug]]` references in `plan.page_slugs` are
    accepted. Anything else triggers a ValueError before write
    (anti prompt-injection).
  - HTML/script strip on LLM output (defense-in-depth).
  - Size cap recursion terminates at `max_depth=4` even on 5M-char flat docs.
  - Failure isolated: digest error → log + `source.metadata.digest_failed=true`,
    but `source.status='ready'` is unaffected (digest is augmentation).
"""

from __future__ import annotations

import re
from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.mrp.contracts import CompilationPlanJson
from app.ai.providers.base import LLMProvider
from app.utils.text import slugify

# Caps + thresholds
MAX_DIGEST_CHARS = 100_000
MAX_OUTLINE_SECTIONS = 20
SECTION_EXCERPT_CHARS = 5_000
MAX_DEPTH = 4

# Truncation marker (Vietnamese first because UI is VN-first)
_TRUNC_MARKER = "\n\n*Nội dung bị cắt ngắn — xem source gốc để có đầy đủ.*"

DIGEST_SYSTEM = (
    "Bạn viết bản tổng hợp dài, mạch lạc của một tài liệu. "
    "Không sinh HTML thô, không emit <script>. "
    "Chỉ chèn [[wiki-links]] tới các slug có trong allowlist."
)

SECTION_NARRATIVE_PROMPT = """\
Bạn đang viết phần "{heading}" trong bản tổng hợp đầy đủ của tài liệu.

Yêu cầu:
- Chỉ dùng [[wiki-links]] với các slug trong allowlist: {page_slugs}
- Giữ lại chi tiết quan trọng, không tóm lược quá đà
- Dùng markdown tự nhiên (list, sub-heading) khi hợp lý
- KHÔNG được emit <script>, <iframe>, hoặc HTML thô

Trích đoạn nguồn:
{excerpt}

Hãy viết phần narrative này (≤2000 từ):"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _anchor(text: str) -> str:
    return slugify(text)


def _flatten_outline(nodes: list, depth: int = 0) -> list[dict]:
    flat: list[dict] = []
    for n in nodes or []:
        flat.append({**n, "_depth": depth})
        if n.get("children"):
            flat.extend(_flatten_outline(n["children"], depth + 1))
    return flat


def _enforce_size_cap(text: str, max_chars: int = MAX_DIGEST_CHARS, depth: int = 0) -> str:
    """
    Cap markdown content at `max_chars`. Recursively halves on H1/H2/H3
    boundaries up to `MAX_DEPTH`; hard-truncates with a marker otherwise so
    we cannot stack-overflow on a 5M-char flat doc.
    """
    if len(text) <= max_chars:
        return text
    if depth >= MAX_DEPTH:
        return text[:max_chars] + _TRUNC_MARKER
    for level_marker in ("\n# ", "\n## ", "\n### "):
        parts = text.split(level_marker)
        if len(parts) > 2:
            half = len(parts) // 2
            left = level_marker.join(parts[:half])
            return _enforce_size_cap(left, max_chars, depth + 1)
    return text[:max_chars] + _TRUNC_MARKER


def _strip_unsafe_html(content: str) -> str:
    """Remove <script>/<style> blocks and any other raw HTML tags."""
    content = re.sub(
        r"<(script|style|iframe|object|embed)\b[^>]*>.*?</\1>",
        "",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Strip remaining naked tags (keep `[[wikilinks]]`).
    content = re.sub(r"<[^>]+>", "", content)
    return content


def _validate_wiki_links(content_md: str, allowlist: list[str]) -> str:
    """Reject any [[slug]] not in the allowlist (anti prompt-injection)."""
    raw_slugs = re.findall(r"\[\[([^\]\|]+)", content_md)
    bad = [s for s in raw_slugs if s.strip() not in allowlist]
    if bad:
        raise ValueError(f"Digest contains unauthorized wiki-links: {bad[:5]}")
    return content_md


def _inject_related_pages(content_md: str, page_slugs: list[str]) -> str:
    if not page_slugs:
        return content_md
    section = ["", "## Các trang liên quan", ""]
    section.extend(f"- [[{s}]]" for s in page_slugs[:30])
    return content_md + "\n" + "\n".join(section) + "\n"


def _draft_pages_by_slug(page_drafts: list[dict]) -> dict[str, dict]:
    """Return fresh REFINE drafts keyed by slug.

    Flat digest runs before COMMIT, so reading WikiPage rows can pull stale
    content from the previous run. Prefer plan_json._page_drafts when present.
    """
    by_slug: dict[str, dict] = {}
    for draft in page_drafts or []:
        if not isinstance(draft, dict):
            continue
        slug = (draft.get("slug") or "").strip()
        content_md = draft.get("content_md") or ""
        if not slug or not content_md:
            continue
        by_slug[slug] = {
            "title": draft.get("title") or slug,
            "content_md": content_md,
        }
    return by_slug


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

async def _digest_with_outline(
    source, plan: CompilationPlanJson, sections: list, llm: LLMProvider, profile
) -> str:
    """Outline strategy — per-H1/H2 narrative loop."""
    flat = [
        s for s in _flatten_outline(sections)
        if s.get("level", 99) <= 2 and "char_start" in s and "char_end" in s
    ]
    flat.sort(key=lambda s: s["char_start"])
    full_text = source.full_text or ""
    title = source.title or source.file_name or "Untitled"

    out: list[str] = [f"# {title} — Tổng quan đầy đủ", ""]
    out.append(f"> Bản tổng hợp comprehensive. Catalog: [[source/{slugify(title)}]]")
    out.append("")
    out.append("## Mục lục")
    for s in flat[:MAX_OUTLINE_SECTIONS]:
        out.append(f"- [{s.get('title', '')}](#{_anchor(s.get('title', ''))})")
    out.append("")
    out.append("## Nội dung")

    writer_timeout = getattr(profile, "writer_timeout_s", 180) if profile else 180

    for s in flat[:MAX_OUTLINE_SECTIONS]:
        heading = s.get("title", "")
        cs = int(s.get("char_start") or 0)
        ce = int(s.get("char_end") or cs)
        excerpt = full_text[cs:ce][:SECTION_EXCERPT_CHARS]

        prompt = SECTION_NARRATIVE_PROMPT.format(
            heading=heading,
            excerpt=excerpt,
            page_slugs=", ".join(plan.page_slugs[:40]),
        )
        try:
            import asyncio
            narrative = await asyncio.wait_for(
                llm.generate(
                    prompt,
                    system=DIGEST_SYSTEM,
                    temperature=0.15,
                    max_tokens=2_000,
                ),
                timeout=writer_timeout,
            )
        except Exception as exc:
            logger.warning(f"[digest] section narrative failed for '{heading}': {exc}")
            narrative = excerpt[:1_500] + " …"

        narrative = _strip_unsafe_html(narrative)
        out.append("")
        out.append(f"### {heading}")
        out.append("")
        out.append(narrative)

    return "\n".join(out)


async def _digest_flat_narrative(
    source,
    plan: CompilationPlanJson,
    llm: LLMProvider,
    profile,
    db: AsyncSession,
    page_drafts: Optional[list[dict]] = None,
) -> str:
    """Flat strategy — TOC of sub-pages + plan summary + first-N chars per page."""
    from app.database.models import WikiPage
    from sqlalchemy import select

    title = source.title or source.file_name or "Untitled"
    out = [
        f"# {title} — Tổng quan đầy đủ",
        "",
        f"> Tài liệu nguồn không có outline; bản digest này tổng hợp từ các sub-page do MRP sinh ra.",
        "",
    ]
    if plan.summary:
        out.append("## Tóm tắt tài liệu")
        out.append("")
        out.append(plan.summary)
        out.append("")

    out.append("## Mục lục các sub-page")
    for sl in plan.page_slugs[:50]:
        out.append(f"- [[{sl}]]")
    out.append("")

    if plan.page_slugs:
        out.append("## Trích đoạn từ các sub-page")
        drafts_by_slug = _draft_pages_by_slug(page_drafts or [])
        rendered_slugs: set[str] = set()

        for slug in plan.page_slugs[:30]:
            draft = drafts_by_slug.get(slug)
            if not draft:
                continue
            snippet = (draft.get("content_md") or "")[:1_200]
            out.append("")
            out.append(f"### {draft.get('title') or slug}")
            out.append("")
            out.append(snippet)
            rendered_slugs.add(slug)

        missing_slugs = [s for s in plan.page_slugs[:30] if s not in rendered_slugs]
        if missing_slugs:
            rows = (
                await db.execute(
                    select(WikiPage).where(WikiPage.slug.in_(missing_slugs))
                )
            ).scalars().all()
            rows_by_slug = {page.slug: page for page in rows}
            for slug in missing_slugs:
                page = rows_by_slug.get(slug)
                if not page:
                    continue
                snippet = (page.content_md or "")[:1_200]
                out.append("")
                out.append(f"### {page.title}")
                out.append("")
                out.append(snippet)

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_digest_phase(
    session: AsyncSession,
    source,
    compilation_plan,
    llm: LLMProvider,
    profile=None,
) -> Optional[str]:
    """
    Generate `page_type='digest'` page for the given source. Idempotent —
    overwrites existing digest slug. Returns the digest slug on success or
    None on failure (callers must not gate `source.status` on this).
    """
    from app.services import wiki_service

    try:
        plan_data = CompilationPlanJson.model_validate(compilation_plan.plan_json or {})
    except Exception as exc:
        logger.warning(f"[digest] plan_json failed validation, defaulting: {exc}")
        plan_data = CompilationPlanJson()

    sections = source.outline_json if isinstance(source.outline_json, list) else []

    if sections:
        content_md = await _digest_with_outline(source, plan_data, sections, llm, profile)
    else:
        page_drafts = []
        try:
            page_drafts = list((compilation_plan.plan_json or {}).get("_page_drafts") or [])
        except Exception:
            page_drafts = []
        content_md = await _digest_flat_narrative(
            source, plan_data, llm, profile, session, page_drafts=page_drafts
        )

    content_md = _strip_unsafe_html(content_md)
    content_md = _validate_wiki_links(content_md, plan_data.page_slugs)
    content_md = _inject_related_pages(content_md, plan_data.page_slugs)
    content_md = _enforce_size_cap(content_md)

    title = source.title or source.file_name or "Untitled"
    digest_slug = f"digest/{slugify(title)}"
    summary = content_md[:300].replace("\n", " ").strip()

    # Resolve scope same way as commit phase (Source.scope_type/scope_id).
    scope_type = source.scope_type or "global"
    scope_id = source.scope_id

    existing = await wiki_service.get_page_by_slug(
        session, digest_slug, scope_type=scope_type, scope_id=scope_id
    )
    if existing is not None:
        await wiki_service.apply_update(
            session,
            slug=digest_slug,
            new_content_md=content_md,
            summary=summary,
            title=f"{title} — Tổng quan đầy đủ",
            add_source_id=source.id,
            scope_type=scope_type,
            scope_id=scope_id,
        )
    else:
        await wiki_service.apply_create(
            session,
            slug=digest_slug,
            title=f"{title} — Tổng quan đầy đủ",
            page_type="digest",
            content_md=content_md,
            summary=summary,
            knowledge_type_slugs=[],
            source_ids=[source.id],
            scope_type=scope_type,
            scope_id=scope_id,
        )

    await session.flush()
    logger.info(f"[digest] wrote {digest_slug} ({len(content_md)} chars) for source={source.id}")
    return digest_slug
