# MRP Pipeline — Operations Guide

Hướng dẫn vận hành pipeline xử lý tài liệu (MAP → REDUCE → PLAN → REFINE → VERIFY → COMMIT).

**Related:** For local AI orchestrator (LM Studio on M1 Max), see [Local AI Orchestrator](./local-ai-orchestrator.md), [Model Checklist](./local-ai-model-checklist.md), [Migration Playbook](./local-ai-migration-playbook.md).

---

## Script `scripts/retry-sources.sh`

Script tổng hợp để retry, monitor và cấu hình timeout cho pipeline.

### Yêu cầu

- `docker` + `docker compose` (containers arkon_postgres, arkon_worker đang chạy)
- `curl`, `jq`
- Chạy từ thư mục gốc của project

### Cú pháp

```bash
bash scripts/retry-sources.sh [MODE] [OPTIONS]
```

### Modes

| Lệnh | Mô tả |
|------|-------|
| _(không có args)_ | Retry tất cả sources đang ở `error` hoặc `plan_ready` |
| `--list` | Hiện bảng danh sách tất cả sources kèm status |
| `<id>` | Retry 1 source cụ thể theo UUID |
| `<id1> <id2> ...` | Retry nhiều sources cùng lúc |
| `--all` | Force-reset TẤT CẢ sources (kể cả `ready`) rồi retry |
| `--watch <id>` | Chỉ theo dõi tiến trình, không retry |
| `--set-timeout` | Cập nhật timeout LLM vào `.env.docker` và recreate worker |

### Ví dụ

```bash
# Xem trạng thái tất cả sources
bash scripts/retry-sources.sh --list

# Retry sources đang lỗi (auto-detect)
bash scripts/retry-sources.sh

# Retry 1 source cụ thể (tự động watch tiến trình)
bash scripts/retry-sources.sh 0235e644-d090-4ef3-ad0b-3aba188aa526

# Retry nhiều sources
bash scripts/retry-sources.sh <id1> <id2> <id3>

# Force retry toàn bộ (kể cả đã ready)
bash scripts/retry-sources.sh --all

# Chỉ xem tiến trình (không retry)
bash scripts/retry-sources.sh --watch 0235e644-d090-4ef3-ad0b-3aba188aa526

# Cập nhật timeout và restart worker
bash scripts/retry-sources.sh --set-timeout
bash scripts/retry-sources.sh --set-timeout --dedup 600 --reconcile 300 --planning 900
```

### Env overrides

```bash
ARKON_URL=http://localhost:5055 \
ARKON_EMAIL=admin@arkon.local \
ARKON_PASSWORD=admin123 \
POLL_INTERVAL=10 \
bash scripts/retry-sources.sh
```

Mặc định script tự đọc credentials từ `.env.docker`.

---

## Cấu hình Timeout LLM

### Vấn đề với local model (LM Studio)

Model local (26B+) sinh token chậm hơn nhiều so với cloud. Pipeline có 3 LLM call trong REDUCE phase — mỗi cái có timeout riêng:

| Env var | Mô tả | Default |
|---------|-------|---------|
| `MRP_TIMEOUT_DEDUP` | Timeout (s) cho LLM call dedup entities | 600 |
| `MRP_TIMEOUT_RECONCILE` | Timeout (s) cho LLM call KB reconciliation | 300 |
| `MRP_TIMEOUT_PLANNING` | Timeout (s) cho LLM call sinh compilation plan | 900 |

> **Timeout là gì:** Đo từ lúc gửi HTTP request đến LM Studio đến khi nhận **token cuối cùng** về — bao gồm cả thời gian prefill và generation. Không phải timeout giữa các token.

### Cập nhật timeout

**Cách 1 — Script (recommended):**
```bash
bash scripts/retry-sources.sh --set-timeout --planning 1200
```
Script tự cập nhật `.env.docker` và `docker compose up -d worker` để apply ngay.

**Cách 2 — Thủ công:**
```bash
# Thêm/sửa trong .env.docker
MRP_TIMEOUT_DEDUP=600
MRP_TIMEOUT_RECONCILE=300
MRP_TIMEOUT_PLANNING=900

# Recreate worker (restart không load env mới)
docker compose --env-file .env.docker up -d worker

# Kiểm tra đã apply chưa
docker exec arkon_worker env | grep MRP_TIMEOUT
```

> ⚠️ `docker compose restart worker` **không** load lại env vars — phải dùng `up -d`.

---

## Writer Pacing & Breaker (REFINE phase)

Phase REFINE chạy 1 writer/page. Khi LM Studio crash mid-batch, writer cũ
(`asyncio.gather` + commit cuối) làm mất hết kết quả thành công. Refactor
2026-05-24 đổi sang **sequential loop + per-page commit + consecutive-stub
breaker** — pages thành công persist ngay, batch tự abort khi LM degraded.

| Env var | Mặc định | Mô tả |
|---------|----------|-------|
| `MRP_WRITER_CONCURRENCY` | `1` | `1` = sequential (recommended cho local LLM). `>1` = parallel `asyncio.gather` + semaphore (escape hatch, dùng khi LM khỏe). |
| `MRP_WRITER_PACE_BASE_MS` | `0` | Delay giữa các page khi LM healthy. |
| `MRP_WRITER_PACE_FAIL_MS` | `3000` | Delay giữa các page sau khi gặp stub (auto-reset về `base_ms` sau 3 success liên tiếp). |
| `MRP_WRITER_BREAKER_THRESHOLD` | `3` | Abort batch sau N stub liên tiếp. Trip → log warning + dừng vòng lặp. |

**Hành vi:**

- Mỗi page commit vào `plan_json._page_drafts` ngay sau khi sinh ra → LM crash giữa batch không mất pages-before-crash.
- Breaker trip ⇒ writer raise `WriterBatchIncomplete`, pipeline.py **không** advance `pipeline_phase` lên `verify` (giữ ở `refine`), set `source.status='failed'` với `error_message` mô tả số page đã/chưa drafted. Re-run retry sẽ re-enter REFINE, skip slugs **real-drafted**, retry các **stub** và pages còn thiếu.
- Stub trong `_page_drafts` (do batch trước trip) bị prune trước khi loop mới chạy — KHÔNG được ship làm "ready". Real drafts được giữ.
- Pre-batch probe (`GET /v1/models`) log structured latency để soi LM health trước khi spawn batch: `MRP REFINE pre-batch probe ... latency_ms=NN status=ok|slow|fail`.
- Parallel mode (`MRP_WRITER_CONCURRENCY>1`) giữ per-page commit + breaker, nhưng breaker là best-effort (chỉ cancel tasks chưa bắt đầu); in-flight HTTP calls vẫn chạy đến hết.
- Env values bị malformed (e.g. `MRP_WRITER_CONCURRENCY=abc`, `=0`, `=-1`) fallback về default thay vì crash worker boot.

**Cập nhật:**

```bash
# .env.docker
MRP_WRITER_CONCURRENCY=1
MRP_WRITER_PACE_BASE_MS=0
MRP_WRITER_PACE_FAIL_MS=3000
MRP_WRITER_BREAKER_THRESHOLD=3

docker compose --env-file .env.docker up -d worker
docker exec arkon_worker env | grep MRP_WRITER
```

---

## Trạng thái Pipeline

| Status | Pipeline phase | Ý nghĩa |
|--------|---------------|---------|
| `pending` | — | Đang chờ trong queue |
| `processing` | `map` | Đang extract knowledge từng chunk |
| `processing` | `reduce` | Đang dedup entities + sinh compilation plan |
| `plan_ready` | `reduce` | Compilation plan đã tạo, chờ approve |
| `processing` | `refine` | Đang viết wiki pages |
| `processing` | `verify` | Đang kiểm tra coverage + conflict |
| `processing` | `commit` | Đang ghi pages vào DB |
| `ready` | `commit` | Hoàn thành |
| `error` | _(bất kỳ)_ | Lỗi — dùng script retry |

### Retry chỉ hoạt động khi status = `error` hoặc `plan_ready`

Nếu source đang `ready` mà muốn chạy lại:
```bash
# Force-reset toàn bộ
bash scripts/retry-sources.sh --all

# Hoặc reset thủ công 1 source rồi retry
docker exec arkon_postgres psql -U arkon -d arkon \
  -c "UPDATE sources SET status='error', progress=0 WHERE id='<uuid>';"
bash scripts/retry-sources.sh <uuid>
```

---

## Retry thông minh theo Phase

Script tự chọn task queue phù hợp dựa trên `pipeline_phase` hiện tại:

| Phase khi lỗi | Task được enqueue |
|---------------|------------------|
| `map`, `reduce`, `plan_review` | `ingest_map_reduce_task` (từ đầu) |
| `refine`, `verify`, `commit` | `ingest_refine_task` (bỏ qua MAP+REDUCE) |
| _(không có)_ | `ingest_file_task` / `ingest_url_task` |

Pipeline hỗ trợ **resume** — nếu lỗi ở REFINE, page drafts đã lưu trong `plan_json._page_drafts` và sẽ không chạy lại REFINE.

---

## Troubleshooting

### Lỗi timeout ở REDUCE/planning

```
TimeoutError at reducer.py run_planning_call
```

**Nguyên nhân:** LM Studio đang sinh response nhưng chậm hơn timeout.

**Fix:**
```bash
bash scripts/retry-sources.sh --set-timeout --planning 1200
bash scripts/retry-sources.sh <source-id>
```

Kiểm tra LM Studio đang active generation:
```bash
docker logs arkon_worker --tail 20 | grep -E "MRP|error|timeout"
```

### Worker không nhận job mới

```bash
docker logs arkon_worker --tail 10
# Nếu thấy "redis connection refused" → restart redis
docker compose --env-file .env.docker restart redis
docker compose --env-file .env.docker up -d worker
```

### Source stuck ở `processing` > 30 phút

```bash
# Kiểm tra worker còn sống không
docker ps | grep arkon_worker

# Force reset và retry
docker exec arkon_postgres psql -U arkon -d arkon \
  -c "UPDATE sources SET status='error', progress=0 WHERE status='processing';"
bash scripts/retry-sources.sh
```

---

## A/B Validation Harness

`scripts/ab-validate-mrp-v2.sh` exercises the local-LLM MRP path end-to-end
against 1+ live source UUIDs. Pauses worker intake via `mrp.intake_paused`,
baselines `wiki_pages` via `pg_dump`, DELETEs the source's pages, enqueues
regen, polls until ready/failed (30 min timeout per id), and unpauses on
EXIT (even on Ctrl-C via trap).

```bash
DATABASE_URL=postgresql://arkon:arkon_secret@localhost:5432/arkon \
  ./scripts/ab-validate-mrp-v2.sh <uuid-A> <uuid-B> <uuid-C>
```

Prod guard refuses to run if `DATABASE_URL` matches `*prod*`, `*production*`,
`*amazonaws*`, `*supabase.co*`, or `*neon.tech*` unless `--confirm-prod` is
passed.

## Migration 028 — KV seed for LLM profile

`alembic upgrade head` seeds 4 rows into `app_config`: `llm_profile`
(auto-detected `cloud` if `llm_base_url` matches a known cloud host, else
`local`), `llm_context_length`, `llm_model_name` (both NULL — populated on
first `runtime_profile` probe), and `mrp.intake_paused`=`false`.

### Rollback gotcha — runtime_profile cache TTL

`alembic downgrade -1` removes the 4 KV rows, **but** the `runtime_profile`
module-scope cache (`_PROFILE_CACHE` in `app/ai/runtime_profile.py`) holds
the previous snapshot for up to 60s (TTL). Worker processes continue serving
the cached profile until either the TTL expires or `PATCH /api/app-config`
is called (which triggers `invalidate()`). On rollback, restart workers to
force a fresh probe:

```bash
docker compose --env-file .env.docker restart worker
```

If running multiple worker replicas, restart all — the cache is process-local.

## F1 fix verification — digest_failed metadata write

MRP DIGEST phase writes `source.metadata->'digest_failed'=true` on isolated
failure (does not block `source.status='ready'`). Schema validation via
synthetic insert:

```sql
UPDATE sources
   SET metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object(
     'digest_failed', true,
     'digest_error', 'synthetic-test',
     'digest_failed_at', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
   )
 WHERE id='<source-uuid>';

SELECT metadata->>'digest_failed' FROM sources WHERE id='<source-uuid>';
-- Rollback: SET metadata = metadata - 'digest_failed' - 'digest_error' - 'digest_failed_at';
```
