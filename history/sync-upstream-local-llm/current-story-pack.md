# Current Story Pack: S3 - Audit Local LLM tuần tự

Epic: E2 Serialization Local LLM

## Entry state

- Sync audit/report đã chạy và quyết định no-op: upstream đã là ancestor của `HEAD`.
- User yêu cầu tập trung vào luồng local model trên MacBook yếu.
- User cấm local LLM calls chạy song song.
- Chưa có bằng chứng đầy đủ rằng worker, phase router, retry scripts, và MRP pipeline serialize mọi tương tác Local LLM.

## Exit state

- Có bản đồ code path gọi Local LLM, gồm text/vision/embedding/verification.
- Có danh sách gaps/risk theo performance, memory, và wiki output quality.
- Có phân loại: fix nhỏ có thể làm ngay vs thay đổi impact lớn cần proposal.
- Có test/baseline command đã chạy hoặc ghi rõ blocker.

## Files cần đọc

- `app/ai/local_orchestrator/phase_router.py`
- `app/ai/local_orchestrator/lms_client.py`
- `app/ai/local_orchestrator/lms_client_guarded.py`
- `app/ai/local_orchestrator/ram_guard.py`
- `app/ai/local_orchestrator/provider_adapter.py`
- `app/worker.py`
- `app/ai/mrp/writer.py`
- `app/ai/mrp/pipeline.py`
- `app/ai/mrp/mapper.py`
- `app/ai/mrp/reducer.py`
- `app/ai/mrp/digest.py`
- `scripts/retry-sources.sh`
- `scripts/regen-failed-source.py`
- `scripts/run-regen.sh`
- `tests/unit/ai/local_orchestrator/`
- `tests/unit/ai/mrp/`
- `tests/integration/test_local_orchestrator_e2e.py`

## Feasibility assumptions

| Giả định | Risk | Proof cần có |
|---|---:|---|
| Có thể xác định concurrency bằng đọc code và tests hiện có | MEDIUM | symbol search, file reads, pytest baseline |
| Fix nhỏ đầu tiên có thể không đổi kiến trúc lớn | MEDIUM | gap map và specialist critique |
| Runtime full cần Docker/model sẵn sàng nên chưa chạy ngay | LOW | ghi rõ blocker nếu thiếu service/model |

## Verification dự kiến

- `uv run pytest tests/unit/ai/local_orchestrator tests/unit/ai/mrp -q`
- `uv run pytest tests/integration/test_local_orchestrator_e2e.py -q`
- `uv run ruff check app/ai/local_orchestrator app/ai/mrp app/worker.py`
- Code review evidence file: `history/sync-upstream-local-llm/evidence/20260531-local-llm-audit.md`

## Out of scope

- Rewrite kiến trúc global queue/lease manager nếu chưa có proposal.
- Chạy nhiều model song song.
- Full Docker document retry trước khi code-level risks được xử lý.

## Bead mapping

Chưa tạo bead. S3 là audit/read-only, phù hợp thực hiện trực tiếp trong validating/planning trước khi mở execution slice code.
