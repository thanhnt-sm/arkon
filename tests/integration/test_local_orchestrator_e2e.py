"""
E2E test — Local AI Orchestrator × MRP pipeline.  SCAFFOLD: tests skip when LM Studio absent.

Operator prerequisites (see test-runbook.md for full detail):
  - LM Studio ≥ 0.4.x running on port 1234, three MLX models downloaded:
      vision=mlx-community/Qwen2.5-VL-32B-Instruct-4bit (~19 GB)
      main_llm=mlx-community/Qwen3.6-35B-A3B-4bit-DWQ (~21 GB)
      embedding=Alibaba-NLP/gte-Qwen2-1.5B-instruct (~2 GB)
  - local_ai.mode=max in Arkon admin UI, MinIO running, free RAM ≥ 23 GB

Run: pytest tests/integration/test_local_orchestrator_e2e.py -v -s -m "e2e and requires_lm_studio"
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Generator

import httpx
import psutil
import pytest
import pytest_asyncio

pytestmark = [pytest.mark.slow, pytest.mark.requires_lm_studio, pytest.mark.e2e]

_LMS_BASE = "http://host.docker.internal:1234"
_LMS_MODELS_URL = f"{_LMS_BASE}/api/v0/models"
_PLAN_DIR = pathlib.Path(__file__).parents[2] / "plans" / "260524-2217-local-ai-orchestrator"
_FIXTURE_DIR = pathlib.Path(__file__).parents[1] / "fixtures" / "sources"
_VI_SOURCE_MD = _FIXTURE_DIR / "small-vi-wiki-source.md"
_CHART_PNG = _FIXTURE_DIR / "sample-chart.png"
_SCREENSHOT_PNG = _FIXTURE_DIR / "sample-vi-screenshot.png"
_POLL_INTERVAL_S = 30
_POLL_TIMEOUT_S = 90 * 60
_RAM_CEILING_GB = 31.5
_REQUIRED_MODEL_IDS = {
    "vision": "mlx-community/Qwen2.5-VL-32B-Instruct-4bit",
    "main_llm": "mlx-community/Qwen3.6-35B-A3B-4bit-DWQ",
    "embedding": "Alibaba-NLP/gte-Qwen2-1.5B-instruct",
}

def _has_frontmatter(md: str) -> bool:
    """True if markdown opens with a non-empty YAML frontmatter block."""
    lines = md.strip().splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    for i, ln in enumerate(lines[1:], start=1):
        if ln.strip() == "---":
            return i > 1
    return False


def _parse_ram_max_gb(trace_path: pathlib.Path) -> float:
    """Peak used-RAM (GB) from sampler CSV; 0.0 if missing."""
    if not trace_path.exists():
        return 0.0
    peak = 0.0
    for line in trace_path.read_text().splitlines()[1:]:
        try:
            peak = max(peak, float(line.split(",")[1]))
        except (IndexError, ValueError):
            pass
    return peak

def _save_artifacts(
    run_dir: pathlib.Path,
    pages: list,
    ram_trace: pathlib.Path,
    meta: dict,
) -> None:
    pages_dir = run_dir / "output-pages"
    pages_dir.mkdir(exist_ok=True)
    for p in pages:
        slug = getattr(p, "slug", str(uuid.uuid4())).replace("/", "_")
        (pages_dir / f"{slug}.md").write_text(p.content_md or "", encoding="utf-8")
    if ram_trace.exists():
        shutil.copy(ram_trace, run_dir / "ram-trace.txt")
    for key, fname in (("verify_report", "verify-report.json"), ("phase_timeline", "timeline.json")):
        if key in meta:
            (run_dir / fname).write_text(json.dumps(meta[key], ensure_ascii=False, indent=2))
    print(f"  [artifacts] {run_dir}")

@pytest.fixture(scope="module")
def lm_studio_running() -> None:
    """Probe LM Studio; skip module if unreachable."""
    try:
        httpx.get(_LMS_MODELS_URL, timeout=5).raise_for_status()
    except Exception as exc:
        pytest.skip(f"LM Studio not reachable at {_LMS_BASE}: {exc}")

@pytest.fixture(scope="module")
def models_downloaded(lm_studio_running: None) -> None:  # noqa: ARG001
    """Skip if any required model is missing from LM Studio."""
    try:
        data = httpx.get(_LMS_MODELS_URL, timeout=10).json()
    except Exception as exc:
        pytest.skip(f"Cannot fetch LM Studio model list: {exc}")
    available = {m.get("id", "") for m in data.get("data", [])}
    missing = [f"{s}={mid}" for s, mid in _REQUIRED_MODEL_IDS.items() if mid not in available]
    if missing:
        pytest.skip("Models missing: " + ", ".join(missing))

@pytest_asyncio.fixture
async def local_ai_max_mode(db_session):  # type: ignore[no-untyped-def]
    """Set local_ai.mode='max'; restore on teardown."""
    from app.services.config_service import ConfigService
    svc = ConfigService(db_session)
    prior = await svc.get("local_ai.mode")
    await svc.set("local_ai.mode", "max")
    yield
    await svc.set("local_ai.mode", prior if prior is not None else "off")

@pytest_asyncio.fixture
async def local_ai_other_mode(db_session):  # type: ignore[no-untyped-def]
    """Set local_ai.mode='other'; restore on teardown."""
    from app.services.config_service import ConfigService
    svc = ConfigService(db_session)
    prior = await svc.get("local_ai.mode")
    await svc.set("local_ai.mode", "other")
    yield
    await svc.set("local_ai.mode", prior if prior is not None else "off")

@pytest_asyncio.fixture
async def small_source(db_session):  # type: ignore[no-untyped-def]
    """Upload VI fixture to MinIO + insert Source row; yield source_id; cleanup."""
    import os
    from sqlalchemy import delete
    from app.database.models import Source
    for path in (_VI_SOURCE_MD, _CHART_PNG, _SCREENSHOT_PNG):
        if not path.exists():
            pytest.skip(f"Fixture file missing: {path}")

    endpoint = os.getenv("MINIO_ENDPOINT", "")
    if not endpoint:
        pytest.skip("MinIO not configured — set MINIO_ENDPOINT env var")

    try:
        from minio import Minio
        mc = Minio(
            endpoint,
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        )
        bucket = os.getenv("MINIO_BUCKET", "arkon-sources")
        src_id = uuid.uuid4()
        prefix = f"e2e-test/{src_id}"
        if not mc.bucket_exists(bucket):
            mc.make_bucket(bucket)
        mc.fput_object(bucket, f"{prefix}/small-vi-wiki-source.md", str(_VI_SOURCE_MD))
        mc.fput_object(bucket, f"{prefix}/sample-chart.png", str(_CHART_PNG))
        mc.fput_object(bucket, f"{prefix}/sample-vi-screenshot.png", str(_SCREENSHOT_PNG))
    except Exception as exc:
        pytest.skip(f"MinIO upload failed: {exc}")

    source = Source(
        id=src_id,
        title="[E2E Test] Kiến Trúc Transformer",
        source_type="file",
        file_name="small-vi-wiki-source.md",
        minio_key=f"{prefix}/small-vi-wiki-source.md",
        status="pending",
        full_text=_VI_SOURCE_MD.read_text(encoding="utf-8"),
    )
    db_session.add(source)
    await db_session.commit()
    yield src_id

    await db_session.execute(delete(Source).where(Source.id == src_id))
    await db_session.commit()

@pytest.fixture
def ram_sampler(tmp_path: pathlib.Path) -> Generator[pathlib.Path, None, None]:
    """Sample psutil RAM every 10 s → CSV file; yields path; stops on teardown."""
    trace = tmp_path / "ram-trace.txt"
    stop = threading.Event()

    def _loop() -> None:
        with trace.open("w") as fh:
            fh.write("timestamp_utc,rss_gb,available_gb,percent\n")
            while not stop.wait(timeout=10):
                vm = psutil.virtual_memory()
                ts_now = datetime.now(timezone.utc).isoformat()
                fh.write(f"{ts_now},{vm.used/1024**3:.3f},{vm.available/1024**3:.3f},{vm.percent:.1f}\n")
                fh.flush()

    t = threading.Thread(target=_loop, daemon=True, name="ram-sampler")
    t.start()
    yield trace
    stop.set()
    t.join(timeout=15)

async def _poll_until_done(db_session, source_id: uuid.UUID) -> str:  # type: ignore[no-untyped-def]
    from sqlalchemy import select
    from app.database.models import Source
    deadline = time.monotonic() + _POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        row = (await db_session.execute(
            select(Source.status, Source.progress, Source.progress_message).where(Source.id == source_id)
        )).one_or_none()
        if row is None:
            raise RuntimeError(f"Source {source_id} not found")
        status, progress, msg = row
        print(f"  [poll] {status} {progress}% — {msg}")
        if status in ("done", "completed", "error"):
            return status
        await asyncio.sleep(_POLL_INTERVAL_S)
    raise TimeoutError(f"Source {source_id} not done after {_POLL_TIMEOUT_S // 60} min")

async def _get_wiki_pages(db_session, source_id: uuid.UUID) -> list:  # type: ignore[no-untyped-def]
    from sqlalchemy import select
    from app.database.models import WikiPage
    rows = await db_session.execute(
        select(WikiPage).where(WikiPage.source_ids.any(str(source_id)))  # type: ignore[attr-defined]
    )
    return list(rows.scalars().all())

async def _get_source_meta(db_session, source_id: uuid.UUID) -> dict:  # type: ignore[no-untyped-def]
    from sqlalchemy import select
    from app.database.models import Source
    row = (await db_session.execute(select(Source).where(Source.id == source_id))).scalar_one()
    return dict(row.metadata_ or {})

@pytest.mark.asyncio
async def test_e2e_max_mode(
    lm_studio_running,  # noqa: ARG001
    models_downloaded,  # noqa: ARG001
    small_source,
    local_ai_max_mode,  # noqa: ARG001
    ram_sampler,
    db_session,
):
    """MAX mode: pipeline completes, ≥3 pages, frontmatter, R2<5%, R5==0, timeline, RAM<31.5GB, artifacts."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = _PLAN_DIR / "test-artifacts" / f"run-{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n[e2e max] source={small_source}  run_dir={run_dir}")

    final = await _poll_until_done(db_session, small_source)
    assert final in ("done", "completed"), f"Pipeline ended with status={final!r}"

    pages = await _get_wiki_pages(db_session, small_source)
    assert len(pages) >= 3, f"Expected ≥3 pages, got {len(pages)}"

    bad = [p.slug for p in pages if not _has_frontmatter(p.content_md or "")]
    assert not bad, f"Pages missing frontmatter: {bad}"

    meta = await _get_source_meta(db_session, small_source)
    vr = meta.get("verify_report") or meta.get("mrp_verify")
    if vr is not None:
        total = vr.get("total_claims", 0)
        if total > 0:
            ratio = vr.get("R2_violations", 0) / total
            assert ratio < 0.05, f"R2 violation ratio {ratio:.1%} ≥ 5%"
        assert vr.get("R5_critical_count", 0) == 0, "R5 critical hallucination flags > 0"
    else:
        print("  [warn] verify_report not in metadata — R2/R5 skipped")

    tl = meta.get("phase_timeline")
    if tl is not None:
        names = [e.get("event") for e in tl]
        assert names.count("vision_load") == 1, f"vision_load count={names.count('vision_load')}"
        assert names.count("vision_unload") == 1, f"vision_unload count={names.count('vision_unload')}"
        assert names.count("main_llm_load") >= 1, f"main_llm_load count={names.count('main_llm_load')}"
    else:
        print("  [warn] phase_timeline not in metadata — skipped")

    peak = _parse_ram_max_gb(ram_sampler)
    print(f"  [ram] peak={peak:.2f} GB  ceiling={_RAM_CEILING_GB} GB")
    if peak > 0:
        assert peak < _RAM_CEILING_GB, f"Peak RAM {peak:.2f} GB ≥ ceiling {_RAM_CEILING_GB} GB"
    _save_artifacts(run_dir, pages, ram_sampler, meta)

@pytest.mark.asyncio
async def test_e2e_other_mode(
    lm_studio_running,  # noqa: ARG001
    small_source,
    local_ai_other_mode,  # noqa: ARG001
    db_session,
    tmp_path,
):
    """OTHER mode sanity: pipeline completes, ≥1 page written. RAM/timeline checks omitted."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = _PLAN_DIR / "test-artifacts" / f"run-{ts}-other"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n[e2e other] source={small_source}  run_dir={run_dir}")

    final = await _poll_until_done(db_session, small_source)
    assert final in ("done", "completed"), f"OTHER mode ended with status={final!r}"

    pages = await _get_wiki_pages(db_session, small_source)
    assert len(pages) >= 1, f"OTHER mode: 0 wiki pages produced for source {small_source}"

    meta = await _get_source_meta(db_session, small_source)
    _save_artifacts(run_dir, pages, tmp_path / "no-ram-trace.txt", meta)
