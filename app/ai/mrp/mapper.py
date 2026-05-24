"""
Phase 0 (Triage) + Phase 1 (MAP) of the MRP pipeline.

Phase 0: classify_strategy() — decides single_pass / standard / hierarchical
         based on full_text length.

Phase 1: build_chunks() — splits document into ~20k-char chunks along section
         boundaries from outline_json. Each chunk is then sent to extract_chunk()
         in parallel (up to MAX_MAP_CONCURRENCY concurrent LLM calls).
         Results are persisted to SourceChunkExtract rows immediately so the
         pipeline can resume from a crash without re-doing completed chunks.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.base import LLMProvider
from app.utils.progress import ProgressTracker

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHUNK_TARGET_CHARS = 20_000
OVERLAP_CHARS = 1_000
MAX_MAP_CONCURRENCY = 6
EXTRACT_TIMEOUT = 120  # seconds per extraction call
OVERLAP_SEPARATOR = "[…context from previous section…]\n"

# Abort-early threshold: if first-round MAP success rate < this, skip the
# sequential retry phase. The retry costs ~len(failed) × timeout (e.g. 7 × 180s
# = 21min). When the model is unresponsive/crashed, retry can't recover —
# better to fail fast and surface the error so ops can fix the LLM.
MIN_FIRST_ROUND_SUCCESS_RATE = 0.30

# Pipeline-shape thresholds (D3). Sub-cases inside `single_pass` decide
# whether to stuff (no MRP), single-MAP (no refine/resolve), or full MRP.
STUFF_THRESHOLD_CHARS = 8_000
SINGLE_MAP_THRESHOLD_CHARS = 20_000


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class DocumentChunk:
    index: int
    start_char: int       # absolute offset in full_text (does NOT include overlap prefix)
    end_char: int         # absolute offset in full_text
    section_path: str     # e.g. "Chapter 2 > Section 2.1"
    text: str             # chunk body (may be prefixed with OVERLAP_SEPARATOR + overlap text)
    overlap_prefix_len: int = field(default=0)
    # Length of the overlap prefix prepended to `text` (chars before the separator newline).
    # local_offset values from LLM output must be >= 0 relative to the body start
    # (after the separator). Conversion: absolute_offset = start_char + local_offset.


# ---------------------------------------------------------------------------
# Phase 0 — Triage
# ---------------------------------------------------------------------------

def classify_strategy(full_text: str, outline_json: Optional[list]) -> str:
    """Return 'single_pass', 'standard', or 'hierarchical' based on text length."""
    n = len(full_text)
    if n < 30_000:
        return "single_pass"
    elif n <= 200_000:
        return "standard"
    else:
        return "hierarchical"


def classify_pipeline_shape(full_text: str) -> str:
    """
    Sub-case selector inside the single-strategy classification. Returns one
    of the pydantic-typed `PipelineShape` literals: stuff | single_map |
    full_mrp | hierarchical. Drives mapper's choice of fan-out vs. roll-up.

    Boundaries (D3):
      <8k          → stuff (1 LLM call, skip MAP/REDUCE)
      8k–20k       → single_map (1 MAP chunk, skip refine/resolve)
      20k–500k     → full_mrp
      >500k        → hierarchical
    """
    n = len(full_text)
    if n < STUFF_THRESHOLD_CHARS:
        return "stuff"
    if n < SINGLE_MAP_THRESHOLD_CHARS:
        return "single_map"
    if n <= 500_000:
        return "full_mrp"
    return "hierarchical"


# ---------------------------------------------------------------------------
# Phase 1a — Chunking
# ---------------------------------------------------------------------------

def _flatten_outline(nodes: list, depth: int = 0) -> list[dict]:
    """Recursively flatten an outline tree into a sorted list of nodes."""
    result = []
    for node in nodes:
        result.append({**node, "_depth": depth})
        if node.get("children"):
            result.extend(_flatten_outline(node["children"], depth + 1))
    return result


def build_chunks(full_text: str, outline_json: Optional[list], strategy: str) -> list[DocumentChunk]:
    """
    Split full_text into DocumentChunks for MAP extraction.

    Uses level-1 and level-2 outline headings as section boundaries. Groups
    sections until accumulated chars exceed CHUNK_TARGET_CHARS. If outline is
    absent or empty, falls back to a sliding-window split.

    The overlap prefix is prepended to each chunk's text for LLM context but
    is NOT part of the [start_char, end_char] range. local_offset values from
    LLM output should be relative to the body (i.e., after the separator).
    """
    flat = _flatten_outline(outline_json or [])
    top_nodes = [n for n in flat if n.get("level", 99) <= 2 and "char_start" in n and "char_end" in n]
    top_nodes.sort(key=lambda n: n["char_start"])

    if not top_nodes:
        return _sliding_window_chunks(full_text)

    chunks: list[DocumentChunk] = []
    current_start: Optional[int] = None
    current_end: int = 0
    current_sections: list[str] = []
    prev_body_end: int = 0  # tracks end of previous chunk body for overlap

    def _flush(idx: int, start: int, end: int, sections: list[str]) -> DocumentChunk:
        body = full_text[start:end]
        section_path = " > ".join(sections) if sections else f"chunk_{idx}"
        # Prepend overlap prefix from previous chunk
        if idx > 0 and prev_body_end > start:
            # overlap already included (sections can overlap); don't double-add
            prefix = ""
            overlap_len = 0
        elif idx > 0 and prev_body_end > 0:
            overlap_start = max(0, prev_body_end - OVERLAP_CHARS)
            overlap_text = full_text[overlap_start:prev_body_end]
            prefix = OVERLAP_SEPARATOR + overlap_text + "\n"
            overlap_len = len(prefix)
        else:
            prefix = ""
            overlap_len = 0
        return DocumentChunk(
            index=idx,
            start_char=start,
            end_char=end,
            section_path=section_path,
            text=prefix + body,
            overlap_prefix_len=overlap_len,
        )

    idx = 0
    for node in top_nodes:
        ns = node["char_start"]
        ne = min(node["char_end"], len(full_text))
        title = node.get("title", "")

        if current_start is None:
            current_start = ns
            current_end = ne
            current_sections = [title]
            continue

        accumulated = current_end - current_start
        section_size = ne - ns

        if accumulated + section_size > CHUNK_TARGET_CHARS and accumulated > 0:
            chunk = _flush(idx, current_start, current_end, current_sections)
            chunks.append(chunk)
            prev_body_end = current_end
            idx += 1
            current_start = ns
            current_end = ne
            current_sections = [title]
        else:
            current_end = max(current_end, ne)
            current_sections.append(title)

    if current_start is not None:
        # Cover any trailing text after last outline node
        trailing_end = len(full_text)
        chunk = _flush(idx, current_start, trailing_end, current_sections)
        chunks.append(chunk)

    # Edge case: if outline only covers part of the document, add a final chunk for the rest
    if chunks:
        last_covered = max(c.end_char for c in chunks)
        if last_covered < len(full_text) - 100:
            idx = len(chunks)
            remainder_start = last_covered
            prev_body_end = last_covered
            tail_chunk = _flush(idx, remainder_start, len(full_text), [f"tail_{idx}"])
            chunks.append(tail_chunk)

    return chunks if chunks else _sliding_window_chunks(full_text)


def _sliding_window_chunks(full_text: str) -> list[DocumentChunk]:
    """Fallback: fixed-size windows with overlap when no outline is available."""
    chunks = []
    n = len(full_text)
    idx = 0
    pos = 0
    prev_end = 0
    while pos < n:
        end = min(pos + CHUNK_TARGET_CHARS, n)
        body = full_text[pos:end]
        if idx > 0 and prev_end > 0:
            overlap_start = max(0, prev_end - OVERLAP_CHARS)
            overlap_text = full_text[overlap_start:prev_end]
            prefix = OVERLAP_SEPARATOR + overlap_text + "\n"
            overlap_len = len(prefix)
        else:
            prefix = ""
            overlap_len = 0
        chunks.append(DocumentChunk(
            index=idx,
            start_char=pos,
            end_char=end,
            section_path=f"chunk_{idx}",
            text=prefix + body,
            overlap_prefix_len=overlap_len,
        ))
        prev_end = end
        pos = end
        idx += 1
    return chunks


# ---------------------------------------------------------------------------
# Phase 1b — Extraction prompt
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM = """\
You are a knowledge extraction engine. Extract structured knowledge from the
provided document section. Return ONLY valid JSON matching the schema exactly.
Never include any text outside the JSON object. If a category has no items, use [].
"""

EXTRACTION_PROMPT_TEMPLATE = """\
## Document section
Section path: {section_path}
Character range in full document: {start_char}–{end_char}
{context_note}

## Text
{chunk_text}

---

Extract all knowledge from this section and return a JSON object with this exact schema:

{{
  "entities": [
    {{
      "name": "string — entity canonical name as it appears in text",
      "type": "string — one of: person|org|product|regulation|location|system|equipment|other",
      "aliases": ["string"],
      "local_offset": 0
    }}
  ],
  "concepts": [
    {{
      "term": "string — concept name OR a thematic section topic (e.g. 'Product Positioning', 'Target Customer Profile', 'Pricing Model'). Prefer the document's own heading wording when the section is coherent and self-contained.",
      "definition_excerpt": "string — verbatim or near-verbatim defining phrase from text; for thematic sections use the opening sentence that frames the section.",
      "local_offset": 0
    }}
  ],
  "claims": [
    {{
      "statement": "string — complete factual claim stated in source",
      "subject": "string — entity/concept this claim is about",
      "local_offset": 0,
      "evidence_length": 200,
      "confidence": "explicit"
    }}
  ],
  "relations": [
    {{
      "from": "string — source entity/concept name",
      "to": "string — target entity/concept name",
      "type": "string — e.g. owns|part_of|caused_by|regulates|uses|located_in|other"
    }}
  ],
  "topics": ["string"]
}}

Rules:
- local_offset is the character position of the entity/concept/claim WITHIN the chunk
  text body (AFTER the context separator line if present). Start counting from 0 at the
  first character of the actual document section content.
- Absolute offset in full document = {start_char} + local_offset.
- confidence must be "explicit" (directly stated) or "inferred" (implied by the text).
- Be exhaustive — include all named entities, defined terms, and factual claims.
- For `concepts`, extract BOTH (a) named terms with definitions (e.g. "RAG",
  "MCP") AND (b) thematic section topics — coherent sub-topics that a reader
  could open as their own wiki page (e.g. "Product Positioning", "Target
  Customer Profile (ICP)", "Content Pillars", "Risk Assessment"). When a
  document is structured around such themes about a primary entity, prefer
  splitting them as separate concepts over collapsing everything into the
  entity's page.
- Return empty arrays [] for categories with no findings.
- Return ONLY the JSON object, no other text.
"""


def _build_extraction_prompt(chunk: DocumentChunk) -> str:
    context_note = (
        f"Note: the first {chunk.overlap_prefix_len} chars are context from the previous "
        "section (before the separator line). local_offset values must start from 0 at "
        "the first character AFTER the separator."
        if chunk.overlap_prefix_len > 0
        else ""
    )
    return EXTRACTION_PROMPT_TEMPLATE.format(
        section_path=chunk.section_path,
        start_char=chunk.start_char,
        end_char=chunk.end_char,
        context_note=context_note,
        chunk_text=chunk.text,
    )


# ---------------------------------------------------------------------------
# Phase 1c — Single chunk extraction
# ---------------------------------------------------------------------------

def _parse_extract_json(raw: str) -> dict:
    """Parse LLM response to extraction dict. Raises ValueError on failure."""
    from app.utils.text import parse_json_loose
    return parse_json_loose(raw)


def _convert_offsets(extract: dict, chunk: DocumentChunk) -> dict:
    """Convert local_offset fields to absolute offsets in full_text."""
    base = chunk.start_char

    for item in extract.get("entities", []):
        item["absolute_offset"] = base + max(0, item.get("local_offset", 0))
        item.pop("local_offset", None)

    for item in extract.get("concepts", []):
        item["absolute_offset"] = base + max(0, item.get("local_offset", 0))
        item.pop("local_offset", None)

    for item in extract.get("claims", []):
        item["absolute_offset"] = base + max(0, item.get("local_offset", 0))
        item.pop("local_offset", None)

    return extract


async def extract_chunk(
    llm: LLMProvider,
    chunk: DocumentChunk,
    extra_system_context: str = "",
    timeout: Optional[int] = None,
) -> dict:
    """
    Single LLM call to extract structured knowledge from one chunk.

    `extra_system_context` (Phase 3) is prepended to the system prompt for
    rolling-refine: passes a ≤500-token summary of the previous chunk so the
    extractor stays coherent across sequential chunks. Default `""` preserves
    cloud-parallel behavior bit-for-bit.

    `timeout` overrides EXTRACT_TIMEOUT — wired from `profile.extract_timeout_s`
    by callers that have a profile in scope.
    """
    prompt = _build_extraction_prompt(chunk)
    system_prompt = (
        f"{extra_system_context}\n\n{EXTRACTION_SYSTEM}"
        if extra_system_context
        else EXTRACTION_SYSTEM
    )
    raw = await asyncio.wait_for(
        llm.generate(prompt, system=system_prompt, temperature=0.1),
        timeout=timeout or EXTRACT_TIMEOUT,
    )
    extract = _parse_extract_json(raw)
    extract = _convert_offsets(extract, chunk)
    return extract


# ---------------------------------------------------------------------------
# Phase 1c-bis — Rolling refine (local profile)
# ---------------------------------------------------------------------------

ROLLING_DISTILL_SYSTEM = (
    "You compress context for the next document section's extractor. "
    "Output PLAIN TEXT only — no JSON, no markdown headers, ≤300 words."
)

ROLLING_DISTILL_PROMPT = """\
Given the extracted JSON below from section N of a document, produce a tight
≤300 word summary that helps the next section's extractor stay consistent.

Focus on:
- Named entities introduced (names + types)
- Key claims/decisions stated
- Open threads to watch for in the next section

Extraction JSON:
{extract_json}

Summary:"""


async def _distill_summary(
    llm: LLMProvider, extract: dict, timeout: int = 60
) -> str:
    """
    Distill a ≤2_000 char rolling-summary from a chunk extract. On failure,
    return empty string (caller falls back to no context — never crashes the
    chain).
    """
    import json

    try:
        # Keep the JSON payload small to stay inside even a 4k-ctx model.
        slim = {
            "entities": [
                {"name": e.get("name"), "type": e.get("type")}
                for e in (extract.get("entities") or [])[:30]
            ],
            "concepts": [
                {"term": c.get("term")} for c in (extract.get("concepts") or [])[:30]
            ],
            "claims": [
                {"statement": (cl.get("statement") or "")[:160]}
                for cl in (extract.get("claims") or [])[:20]
            ],
        }
        prompt = ROLLING_DISTILL_PROMPT.format(extract_json=json.dumps(slim, ensure_ascii=False))
        raw = await asyncio.wait_for(
            llm.generate(
                prompt,
                system=ROLLING_DISTILL_SYSTEM,
                temperature=0.1,
                max_tokens=500,
            ),
            timeout=timeout,
        )
        # Hard cap — LM Studio doesn't reliably honor max_tokens on small models.
        return (raw or "").strip()[:2_000]
    except Exception as exc:
        logger.warning(f"[rolling_distill] failed: {exc}")
        return ""


async def _run_rolling_refine(
    llm: LLMProvider,
    chunks: list[DocumentChunk],
    pending_chunks: list[DocumentChunk],
    existing_by_idx: dict,
    session: AsyncSession,
    tracker: ProgressTracker,
    done_count: int,
    extract_timeout: int,
) -> None:
    """
    Local-profile MAP loop: sequential extract + distill summary for next.

    On per-chunk failure: mark row error, fall back to empty rolling summary,
    continue. NEVER aborts entire chain — that would re-introduce the
    "(Page generation failed)" stub failure mode this plan eliminates.
    """
    prior_summary = ""
    total = len(chunks)
    pending_set = {c.index for c in pending_chunks}

    for chunk in chunks:
        if chunk.index not in pending_set:
            # Skip already-done chunks but still distill from their extract so
            # the rolling context survives resume.
            row = existing_by_idx[chunk.index]
            if row.extract_json and not prior_summary:
                prior_summary = await _distill_summary(llm, row.extract_json)
            continue

        row = existing_by_idx[chunk.index]
        prefix = f"## Previous Section Summary\n{prior_summary}\n\n" if prior_summary else ""

        try:
            extract = await extract_chunk(
                llm, chunk,
                extra_system_context=prefix,
                timeout=extract_timeout,
            )
            row.extract_json = extract
            row.status = "done"
            row.error_message = None
            await session.commit()
        except Exception as exc:
            logger.warning(f"MRP MAP rolling chunk {chunk.index} failed: {exc}")
            row.status = "error"
            row.error_message = str(exc)[:500]
            await session.commit()
            extract = None  # distill will skip

        pct = 10 + int(40 * (done_count + chunk.index + 1) / max(total, 1))
        await tracker.update(pct, f"Extracting chunk {chunk.index + 1}/{total} (rolling)...")

        # Build rolling summary for the next iteration (skip on last).
        if chunk.index < total - 1 and extract is not None:
            prior_summary = await _distill_summary(llm, extract)
        elif chunk.index < total - 1 and extract is None:
            # Don't cascade a failure into a stale summary
            prior_summary = ""

        logger.debug(
            f"[rolling] idx={chunk.index} prior_summary_chars={len(prior_summary)}"
        )


# ---------------------------------------------------------------------------
# Phase 1d — MAP phase orchestrator
# ---------------------------------------------------------------------------

async def run_map_phase(
    session: AsyncSession,
    source_id: uuid.UUID,
    full_text: str,
    outline_json: Optional[list],
    tracker: ProgressTracker,
    llm: LLMProvider,
) -> tuple[str, list]:
    """
    Run Phase 0 (triage) + Phase 1 (MAP).

    Returns (strategy, chunk_extract_rows) where chunk_extract_rows is the list
    of SourceChunkExtract ORM objects with status='done'.

    Persists each chunk result to DB immediately for resume capability.
    Retries failed chunks once sequentially before continuing.
    """
    from app.database.models import Source, SourceChunkExtract

    # Pull runtime profile (attached by ProviderRegistry.get_llm); falls back
    # to legacy constants when absent so tests that pass a bare LLM mock keep
    # working.
    profile = getattr(llm, "runtime_profile", None)
    concurrency = profile.concurrency if profile else MAX_MAP_CONCURRENCY
    extract_timeout = profile.extract_timeout_s if profile else EXTRACT_TIMEOUT
    pipeline_shape = classify_pipeline_shape(full_text)

    strategy = classify_strategy(full_text, outline_json)
    logger.info(
        f"MRP: source={source_id} strategy={strategy} shape={pipeline_shape} "
        f"len={len(full_text)} concurrency={concurrency} timeout={extract_timeout}s"
    )

    chunks = build_chunks(full_text, outline_json, strategy)
    logger.info(f"MRP MAP: {len(chunks)} chunks for source={source_id}")

    # Update source pipeline state
    source = await session.get(Source, source_id)
    if source:
        source.pipeline_strategy = strategy
        source.pipeline_phase = "map"
        await session.commit()

    # Load existing chunk rows (for resume)
    existing_rows = (await session.execute(
        select(SourceChunkExtract).where(SourceChunkExtract.source_id == source_id)
    )).scalars().all()
    existing_by_idx = {r.chunk_index: r for r in existing_rows}

    # Ensure a DB row exists for every chunk
    for chunk in chunks:
        if chunk.index not in existing_by_idx:
            row = SourceChunkExtract(
                source_id=source_id,
                chunk_index=chunk.index,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                section_path=chunk.section_path,
                status="pending",
            )
            session.add(row)
            existing_by_idx[chunk.index] = row
    await session.commit()

    # Reload after flush so IDs are populated
    existing_rows = (await session.execute(
        select(SourceChunkExtract).where(SourceChunkExtract.source_id == source_id)
    )).scalars().all()
    existing_by_idx = {r.chunk_index: r for r in existing_rows}

    pending_chunks = [c for c in chunks if existing_by_idx[c.index].status != "done"]
    done_count = len(chunks) - len(pending_chunks)
    logger.info(f"MRP MAP: {done_count} already done, {len(pending_chunks)} pending for source={source_id}")

    # Local profile → sequential rolling refine (Phase 3). Cloud → fan-out.
    is_local = bool(profile and profile.is_local)
    if is_local and len(pending_chunks) > 1:
        await _run_rolling_refine(
            llm=llm,
            chunks=chunks,
            pending_chunks=pending_chunks,
            existing_by_idx=existing_by_idx,
            session=session,
            tracker=tracker,
            done_count=done_count,
            extract_timeout=extract_timeout,
        )
    else:
        semaphore = asyncio.Semaphore(concurrency)
        commit_lock = asyncio.Lock()

        async def _extract_with_sem(chunk: DocumentChunk):
            async with semaphore:
                row = existing_by_idx[chunk.index]
                try:
                    extract = await extract_chunk(llm, chunk, timeout=extract_timeout)
                    # Serialize mutations and commits — AsyncSession can't handle concurrent state changes
                    async with commit_lock:
                        row.extract_json = extract
                        row.status = "done"
                        row.error_message = None
                        await session.commit()
                except Exception as e:
                    logger.warning(f"MRP MAP chunk {chunk.index} failed: {e}")
                    async with commit_lock:
                        row.status = "error"
                        row.error_message = str(e)[:500]
                        await session.commit()
                pct = 10 + int(40 * (done_count + chunk.index + 1) / max(len(chunks), 1))
                await tracker.update(pct, f"Extracting chunk {chunk.index + 1}/{len(chunks)}...")

        await asyncio.gather(*[_extract_with_sem(c) for c in pending_chunks])

    # Abort-early guard: if first-round success rate is below threshold, skip
    # the sequential retry. A dying LLM won't recover within a retry window;
    # better to surface failure now than burn ~len(failed) × timeout minutes.
    first_round_done = sum(1 for c in chunks if existing_by_idx[c.index].status == "done")
    first_round_rate = first_round_done / max(len(chunks), 1)
    error_chunks = [c for c in chunks if existing_by_idx[c.index].status == "error"]
    if error_chunks and first_round_rate < MIN_FIRST_ROUND_SUCCESS_RATE:
        logger.error(
            f"MRP MAP: aborting retry — first-round success {first_round_done}/{len(chunks)} "
            f"({first_round_rate:.0%}) below threshold {MIN_FIRST_ROUND_SUCCESS_RATE:.0%}. "
            f"LLM likely unresponsive; fix model before re-running."
        )
        error_chunks = []
    if error_chunks:
        logger.info(f"MRP MAP: retrying {len(error_chunks)} failed chunks for source={source_id}")
        for chunk in error_chunks:
            row = existing_by_idx[chunk.index]
            try:
                extract = await extract_chunk(llm, chunk, timeout=extract_timeout)
                row.extract_json = extract
                row.status = "done"
                row.error_message = None
                await session.commit()
            except Exception as e:
                logger.warning(f"MRP MAP chunk {chunk.index} retry failed: {e}")

    # Return all done rows
    done_rows = [existing_by_idx[c.index] for c in chunks if existing_by_idx[c.index].status == "done"]
    logger.info(f"MRP MAP complete: {len(done_rows)}/{len(chunks)} chunks done for source={source_id}")
    return strategy, done_rows
