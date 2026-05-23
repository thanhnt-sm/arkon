"""
Regenerate wiki pages for a source whose previous MRP refine left
'(Page generation failed: ...)' stubs baked into content_md.

Usage (inside arkon_worker container):
    docker exec arkon_worker python scripts/regen-failed-source.py <source_id>

Or via mount-less path (script is copied in by run-regen.sh):
    docker exec arkon_worker python /tmp/regen_failed_source.py <source_id>

Idempotent. Safe to re-run — refine task overwrites by slug.

What it does:
  1. Verifies source exists and has full_text + plan.
  2. Resets source.status -> 'processing' and pipeline_phase -> 'refine'.
  3. Enqueues ingest_refine_task via the existing arq pool.
  4. Prints job_id and exits — monitoring is the caller's job (tail worker.log).

The retry decorator added in app/ai/providers/openai_provider.py now
auto-retries transient LM Studio crashes (BadRequestError 'model has crashed',
APIConnectionError, APITimeoutError, InternalServerError) up to 3 attempts
with exponential backoff.
"""

import asyncio
import sys
import uuid

from loguru import logger

from app.database import async_session_factory
from app.database.models import Source
from app.worker import get_arq_pool


async def regen(source_id: str) -> None:
    sid = uuid.UUID(source_id)
    async with async_session_factory() as session:
        source = await session.get(Source, sid)
        if not source:
            logger.error(f"Source {source_id} not found")
            sys.exit(2)
        if not source.full_text:
            logger.error(f"Source {source_id} has no full_text — cannot regen")
            sys.exit(3)

        logger.info(
            f"Source {source_id}: status={source.status}, phase={source.pipeline_phase}, "
            f"text_len={len(source.full_text)}"
        )

        source.status = "processing"
        source.pipeline_phase = "refine"
        source.progress = 78
        source.progress_message = "Regen: re-writing wiki pages..."
        source.error_message = None
        await session.commit()

    pool = await get_arq_pool()
    job = await pool.enqueue_job("ingest_refine_task", source_id)
    job_id = job.job_id if job else "N/A"
    logger.success(f"Enqueued ingest_refine_task job={job_id} for source={source_id}")
    print(job_id)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python regen-failed-source.py <source_id>", file=sys.stderr)
        sys.exit(1)
    asyncio.run(regen(sys.argv[1]))
