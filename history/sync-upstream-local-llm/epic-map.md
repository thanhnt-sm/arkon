# Bản đồ epic (Epic Map): Local LLM trên MacBook yếu

Mode: `high_risk_feature`

Kết quả cuối: repo đã chứng minh không thiếu upstream, luồng Local LLM chạy tuần tự trên phần cứng yếu, giảm memory pressure, vẫn sinh wiki output không rỗng và có nội dung từ source, rồi được kiểm chứng bằng Docker/runtime.

## Epics

| Epic | Vùng năng lực/rủi ro | Vì sao tồn tại | Stories | Proof cần có |
|---|---|---|---|---|
| E1 | Sync safety | Đã cần audit/report trước khi làm tiếp | S1 audit/report no-op; S2 sync guard proposal | report, logs, topology evidence |
| E2 | Serialization Local LLM | Không được gọi local model song song | S3 audit call paths; S4 patch serialization gap nhỏ nhất | tests/logs chứng minh tuần tự |
| E3 | Memory/performance | MacBook yếu cần giảm RAM/context load | S5 tune chunk/pacing/guard; S6 runtime memory evidence | RAM logs, timeout/retry behavior |
| E4 | Wiki output quality | Tối ưu không được làm output rỗng/source-thin | S7 empty/stub detection; S8 content-grounded checks | tests và wiki output evidence |
| E5 | Docker/runtime proof | Completion cần chạy thật | S9 boot services; S10 retry/regenerate documents | service logs, non-empty wiki output |

## Story queue

| Story | Epic | Outcome | Phụ thuộc | Trạng thái |
|---|---|---|---|---|
| S1 | E1 | Chạy audit/report và quyết định no-op vì upstream đã là ancestor | none | done |
| S2 | E1 | Proposal/fix safe-sync local-ahead guard | S1 | deferred |
| S3 | E2 | Map toàn bộ code path có thể gọi Local LLM song song | S1 | current |
| S4 | E2 | Patch gap serialization nhỏ nhất, không đổi kiến trúc lớn | S3 | pending |
| S5 | E3 | Map memory/context bottlenecks | S3 | pending |
| S6 | E3 | Patch tuning nhỏ hoặc proposal nếu cần kiến trúc lớn | S5 | pending |
| S7 | E4 | Map nguy cơ wiki empty/stub/source-thin | S3 | pending |
| S8 | E4 | Patch validator nhỏ hoặc proposal nếu cần | S7 | pending |
| S9 | E5 | Docker stack và local model settings sẵn sàng | S4-S8 | pending |
| S10 | E5 | Retry/regenerate documents sinh wiki output đủ nội dung | S9 | pending |

Current story: S3 - audit Local LLM call paths và gaps tuần tự/memory/quality.
