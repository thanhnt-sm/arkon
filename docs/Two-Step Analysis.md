# Plan: Two-Step Analysis + User Contributions

## Context

Hai cải tiến lấy cảm hứng từ `llm_wiki-main`:

1. **Two-step Analysis → Generation**: Hiện tại agent bắt đầu "mù" — không biết gì về source trước khi dùng tools. Thêm một LLM call phân tích trước để agent có "bản đồ" (entities, concepts, pages cần update) trước khi vào vòng lặp. Cải thiện chất lượng wiki và giảm số tool calls lãng phí.

2. **User Contributions + Merge**: Người dùng cần chỉnh sửa/bổ sung wiki page trực tiếp (hiện chưa có API/UI). Khi source được re-ingest, nội dung user đóng góp KHÔNG được ghi đè — agent phải thấy và tích hợp vào content mới.

---

## Feature 1: Two-Step Analysis → Generation

### New file: `app/ai/wiki_analyzer.py`

Single async function `analyze_source()`:

```python
async def analyze_source(
    llm: LLMProvider,
    source_title: str,
    full_text: str,                      # capped at 30k chars
    existing_pages: list[dict],          # [{slug, title, page_type}]
    kt_name: Optional[str],
    kt_desc: Optional[str],
) -> Optional[dict]:                     # None = failed, caller falls back
```

- Single `llm.generate()` call (không dùng tools), `temperature=0.1`, max `2048` tokens
- Trả về JSON:

```json
{
  "document_type": "regulation|sop|report|technical_spec|other",
  "primary_language": "vi|en|...",
  "key_themes": ["..."],
  "named_entities": [{"name": "...", "type": "person|org|product|regulation", "significance": "..."}],
  "key_concepts": [{"name": "...", "suggested_slug": "concept/...", "description": "..."}],
  "existing_pages_to_update": [{"slug": "...", "reason": "..."}],
  "new_pages_to_create": [{"suggested_slug": "...", "page_type": "...", "title": "..."}],
  "source_page_slug": "source/...",
  "compilation_notes": "..."
}
```

- `existing_pages_to_update` được ground bằng danh sách pages thực tế → không hallucinate slug
- Mọi exception đều catch → return `None` → agent chạy bình thường không có analysis
- Strip markdown code fence nếu LLM wrap JSON trong backticks

### Modify `app/ai/wiki_agent.py`

Trong `compile_source_with_agent()`, trước khi khởi tạo `messages`:

1. Query wiki pages hiện tại (1 DB call, tương tự `read_wiki_index` tool)
2. Gọi `analyze_source(...)` — nếu fail thì `analysis_section = ""`
3. Format analysis thành markdown section, inject vào `INITIAL_USER_TEMPLATE` qua `{analysis_section}` placeholder (đặt sau `kt_context`, trước `source_excerpt`)

Analysis đặt trong **user message** (không phải system prompt) để tránh ảnh hưởng provider caching.

Thêm vào `SYSTEM_PROMPT`: hướng dẫn agent rằng "Pre-Analysis là advisory, cần verify bằng tools trước khi dùng".

---

## Feature 2: User Contributions + Merge on Re-ingest

### Phase A — DB Migration

**New file: `alembic/versions/xx_wiki_user_contributions.py`**

Thêm 4 cột vào `wiki_pages`:

```sql
user_contribution_md  TEXT        NULL
contributed_by_id     UUID        NULL FK → employees.id ON DELETE SET NULL
contributed_at        TIMESTAMPTZ NULL
contribution_note     TEXT        NULL   -- edit summary
```

**`app/database/models.py`** — thêm 4 `Mapped` columns vào `WikiPage`.

Existing rows: tất cả `NULL`, không cần data migration.

---

### Phase B — API Endpoint

**`app/routers/wiki.py`** — thêm:

```python
class WikiContributionRequest(BaseModel):
    user_contribution_md: str       # required, non-empty, max 50k chars
    contribution_note: Optional[str] = None

@router.patch("/wiki/pages/{slug:path}")
async def contribute_to_wiki_page(
    slug: str,
    body: WikiContributionRequest,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),   # any logged-in user
)
```

Logic:
1. Load page → 404 if not found; reject `_index`, `_log`
2. Set `user_contribution_md`, `contributed_by_id`, `contributed_at`, `contribution_note`
3. Bump `version`
4. Commit + append wiki log entry
5. Return extended `WikiPageDetail`

Extend `WikiPageDetail` Pydantic model:
```python
user_contribution_md: Optional[str] = None
contribution_note: Optional[str] = None
contributed_at: Optional[str] = None
contributed_by_name: Optional[str] = None   # join từ employees
```

---

### Phase C — Agent Awareness

**`app/ai/wiki_agent_tools.py`** — `read_wiki_page()` handler:

Khi page có `user_contribution_md`, embed trực tiếp vào `content_md` trả về agent:

```python
if page.user_contribution_md:
    content = (
        f"<!-- USER CONTRIBUTION (MUST be preserved/integrated) -->\n"
        f"<!-- Note: {page.contribution_note or 'no note'} -->\n"
        f"{page.user_contribution_md}\n"
        f"<!-- End of user contribution -->\n\n"
        f"<!-- Compiled content: -->\n"
        f"{page.content_md}"
    )
    result["content_md"] = content
    result["has_user_contribution"] = True
```

Lý do embed inline: agent không thể "miss" contribution — nó nằm ngay trong content đọc được.

**`app/services/wiki_service.py`** — `apply_update()`: **không thay đổi gì**. Columns contribution là separate, không bị ghi đè khi agent update `content_md`. Contribution tồn tại như audit record sau khi đã được merge vào content mới.

**`app/ai/wiki_agent.py`** — thêm vào `SYSTEM_PROMPT` section về user contributions:

> "Some pages contain USER CONTRIBUTION sections (marked with HTML comments). These represent expert input. When updating such pages: integrate their specific facts into the new content, do not silently discard them. If user contribution contradicts the source, keep both perspectives clearly labeled."

---

### Phase D — Frontend

**`frontend/src/types/wiki.ts`** — extend `WikiPageDetail` type với 4 contribution fields.

**New: `frontend/src/components/wiki/wiki-contribute-dialog.tsx`**
- Modal dialog (pattern: `Dialog` component, consistent với `contact-dialog.tsx`, `employee-dialog.tsx`)
- `Textarea` for contribution markdown
- `Input` for contribution note
- PATCH call on submit

**`frontend/src/app/(portal)/wiki/[...slug]/page.tsx`**
- Thêm "Contribute" button trong page header
- Hiển thị amber banner khi `user_contribution_md` tồn tại: "This page has user contributions that will be integrated on the next recompile."

---

### Phase E — MCP Tool

**`app/mcp/tools.py`** — thêm 1 tool mới `contribute_wiki_page`:

```python
@mcp.tool()
async def contribute_wiki_page(
    slug: str,
    user_contribution_md: str,
    contribution_note: Optional[str] = None,
) -> str:
    """
    Add or replace your contribution to an existing wiki page.

    Use this when you have domain knowledge, corrections, or additional context
    to add to a compiled wiki page. Your contribution will be preserved across
    re-ingests and integrated by the wiki compiler on the next recompile.

    Args:
        slug: Target page slug (e.g. "concept/fire-safety", "entity/pump-xyz").
              Use read_wiki_index() or search_wiki() to find the right slug.
        user_contribution_md: Your contribution in Markdown. Can include
              corrections, additional facts, procedures, or context.
        contribution_note: Optional one-line summary of what you added/changed.
    """
    identity, err = await _get_identity()
    if err:
        return err

    if not slug or not user_contribution_md.strip():
        return "Error: slug and user_contribution_md are required."
    if slug in ("_index", "_log"):
        return "Error: cannot contribute to reserved pages."

    async with async_session_factory() as session:
        page = (await session.execute(
            select(WikiPage).where(WikiPage.slug == slug)
        )).scalar_one_or_none()
        if not page:
            return f"Page '{slug}' not found. Use read_wiki_index() to browse available pages."

        page.user_contribution_md = user_contribution_md.strip()
        page.contributed_by_id = identity.employee_id
        page.contributed_at = datetime.now(timezone.utc)
        page.contribution_note = contribution_note
        page.version += 1
        await session.commit()

    return (
        f"Contribution saved to `{slug}`.\n\n"
        f"It will be integrated into the wiki on the next source recompile.\n"
        f"Note: {contribution_note or '(none)'}"
    )
```

- Follow đúng pattern hiện tại: `_get_identity()` → `async_session_factory` → return string
- `identity.employee_id` dùng làm `contributed_by_id` (MCP token → employee)
- Không cần scope filter vì đây là write, không phải read — mọi active employee đều có thể contribute (consistent với REST endpoint)

---

## Implementation Order

| # | File | Change |
|---|------|--------|
| 1 | `alembic/versions/009_wiki_user_contributions.py` | New migration |
| 2 | `app/database/models.py` | 4 new columns on WikiPage |
| 3 | `app/routers/wiki.py` | PATCH endpoint + extended WikiPageDetail |
| 4 | `app/mcp/tools.py` | `contribute_wiki_page` MCP tool |
| 5 | `app/ai/wiki_agent_tools.py` | read_wiki_page surfaces contributions |
| 6 | `app/ai/wiki_analyzer.py` | New file: analyze_source() |
| 7 | `app/ai/wiki_agent.py` | Inject analysis + system prompt updates |
| 8 | `frontend/src/types/wiki.ts` | Extend WikiPageDetail type |
| 9 | `frontend/src/components/wiki/wiki-contribute-dialog.tsx` | New component |
| 10 | `frontend/src/app/(portal)/wiki/[...slug]/page.tsx` | Contribute button + banner |

---

## Edge Cases

- **Force recompile deletes orphan pages** → contribution bị mất. Mitigation: trước khi xóa orphan có contribution, emit log entry với full contribution text.
- **Agent ignores contribution** → inline embed trong content_md làm cho điều này rất khó xảy ra.
- **Concurrent edits** → last-write-wins (acceptable for this phase).
- **Analysis call fails/slow** → fall back gracefully, log warning, agent chạy bình thường.

---

## Verification

1. Run alembic migration, check columns tồn tại trong DB
2. Upload `.doc`/`.pdf` source → check worker log có "Pre-Analysis" step
3. PATCH `/api/wiki/pages/{slug}` với test contribution → verify DB
4. Re-ingest source → verify `content_md` mới chứa user contribution content, `user_contribution_md` column không bị xóa
5. Frontend: Contribute button mở dialog, save thành công, amber banner hiện đúng
