# Phân tích WARN audit - 2026-05-31

## Input

- Patch: `.agent/sync_history/20260531_073639_upstream_main.patch`
- Audit log: `history/sync-upstream-local-llm/evidence/20260531-audit.log`
- Audit log đã bỏ màu ANSI: `history/sync-upstream-local-llm/evidence/20260531-audit.clean.log`
- Review CDN grep: `history/sync-upstream-local-llm/evidence/20260531-cdn-warn-review.txt`
- Report: `plans/reports/sync-audit-260531-0736-upstream-already-ancestor.md`

## Kết quả

`run_audit.sh` exit `2`:

```text
[WARN] Upstream patch adds external CDN reference — may leak user IP at runtime
AUDIT_EXIT=2
```

## Review thủ công

Current working tree runtime scan đã pass:

```text
[PASS] No external CDN references in runtime code
```

WARN nằm trong archived patch, nhưng patch này không phải incoming upstream work. Đây là reverse/ahead-only diff được tạo vì local `HEAD` đã chứa `upstream/main` và có thêm commit local.

Bằng chứng topology:

```text
git rev-list --left-right --count HEAD...upstream/main -> 47 0
git rev-list --left-right --count upstream/main...HEAD -> 0 47
git merge-base --is-ancestor upstream/main HEAD -> rc=0
```

File grep review cho thấy CDN strings chủ yếu có diff prefix như `-`, `--`, `--+`, hoặc nằm trong patch fixture/archive text. Đây là deleted/reverse-diff lines hoặc nội dung fixture, không phải runtime code mới.

## Quyết định

Theo chuyên gia gpt-5.5/xhigh: **không merge**.

Lý do:

- Upstream đã nằm trong local history.
- `commits_behind: 0` và conflict inventory rỗng.
- Report WARN hiện tại là trace artifact, không phải PASS authorization để merge.
- Chạy `safe_sync.sh upstream main --merge` trong trạng thái này là sai, kể cả khi có report PASS cũ cho cùng upstream SHA.

## Follow-up

Issue còn lại: `safe_sync.sh` nên nhận diện local-ahead/no-op trước khi tạo reverse patch. Việc này đã được ghi thành residual sync issue; tạm hoãn vì trọng tâm mới là audit/tối ưu Local LLM.
