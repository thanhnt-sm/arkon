# Đồng bộ upstream và Local LLM - Khám phá (Discovery)

## 1. Bằng chứng sync upstream hiện tại

gkg đã được chuẩn bị bằng `gkg index /Volumes/Data/101.AI/GitHub/arkon` và `gkg server start`; scout báo repo đã indexed và server reachable. Tool MCP gkg không xuất hiện trong tool surface hiện tại, nên phần discovery dùng lệnh git và đọc file trực tiếp.

Trạng thái fork:

- `HEAD`: `834323767680fa747426322916ab28579d2aebdf`
- `origin/main`: `834323767680fa747426322916ab28579d2aebdf`
- `upstream/main`: `a735a00095d221daca9a23721b7918658322c3f8`
- `git rev-list --left-right --count HEAD...upstream/main`: `47 0`
- `git merge-base --is-ancestor upstream/main HEAD`: true

Kết luận: repo local đang đi trước upstream 47 commits và không thiếu commit upstream. Merge commit `803423a chore: finalize upstream sync resolution for MRP writer` đã đưa upstream `a735a00` vào local history.

Artifact sync đã ghi:

- Dry-run log: `history/sync-upstream-local-llm/evidence/20260531-safe-sync-dryrun.log`
- Audit log: `history/sync-upstream-local-llm/evidence/20260531-audit.log`
- Conflict JSON: `history/sync-upstream-local-llm/evidence/20260531-conflicts.json`
- Conflict summary: `history/sync-upstream-local-llm/evidence/20260531-conflicts-summary.txt`
- Branch topology: `history/sync-upstream-local-llm/evidence/20260531-branch-topology.txt`
- WARN analysis: `history/sync-upstream-local-llm/evidence/20260531-audit-warn-analysis.md`
- Report: `plans/reports/sync-audit-260531-0736-upstream-already-ancestor.md`

## 2. Kết quả audit/report

Runtime tree hiện tại pass các check:

- Telemetry framework (framework telemetry)
- SDK tracking bị cấm (forbidden SDK)
- Network call đáng ngờ (suspicious network call)
- Behavioral tracking
- External CDN runtime
- Squid whitelist
- Container hardening
- npm high/critical vulnerabilities
- PII exfiltration

Audit exit code là `2` vì WARN CDN trong archived patch. Manual review cho thấy patch đó là reverse-diff local-ahead, không phải incoming upstream. Conflict inventory rỗng (`total: 0`). Theo chuyên gia gpt-5.5/xhigh: **không merge**.

## 3. Issue sync còn lại

`safe_sync.sh` chỉ thoát sớm khi `HEAD == upstream/main`. Khi local chứa upstream và có commit local đi trước, script vẫn in "Incoming changes" và archive `git diff HEAD..upstream`, tạo patch reverse-diff trông như xóa local work. Đây là issue UX/an toàn vận hành, nhưng không block công việc Local LLM hiện tại.

Đề xuất fix đã ghi trong approach/proposal; chưa triển khai vì user yêu cầu tập trung local model.

## 4. Bề mặt Local LLM cần audit

Các file trọng tâm:

- `app/ai/local_orchestrator/phase_router.py` - route phase, retry, pacing.
- `app/ai/local_orchestrator/lms_client.py` - request local model.
- `app/ai/local_orchestrator/lms_client_guarded.py` - RAM/preflight guard.
- `app/ai/local_orchestrator/ram_guard.py` - memory policy.
- `app/ai/local_orchestrator/provider_adapter.py` - adapter local provider.
- `app/worker.py` - job orchestration và retry.
- `app/ai/mrp/writer.py`, `pipeline.py`, `mapper.py`, `reducer.py`, `digest.py` - pipeline sinh wiki.
- `scripts/retry-sources.sh`, `scripts/regen-failed-source.py`, `scripts/run-regen.sh` - vận hành retry/regeneration.

## 5. Rủi ro cần soi tiếp

- Local calls có thể chạy song song qua worker concurrency, retry nhiều source, hoặc phase nội bộ.
- RAM guard có thể chỉ check trước request nhưng không đảm bảo unload model.
- Context/chunk quá lớn có thể làm model local chậm, hết RAM, hoặc sinh output source-thin.
- Retry/regeneration có thể mark done dù wiki output rỗng/stub nếu validator chưa đủ chặt.
- Nếu cần sửa kiến trúc lớn như global local-model queue hoặc lease manager, phải viết proposal tiếng Việt cho human review trước.
