# Đồng bộ upstream và Local LLM - Hướng tiếp cận (Approach)

## 1. Mode gate

Mode tổng thể: `high_risk_feature`.

Lý do không dùng mode nhỏ cho toàn bộ goal:

- Công việc liên quan git sync safety, security audit, Local LLM runtime, Docker/runtime, và chất lượng document-to-wiki.
- Hoàn tất thật sự cần bằng chứng runtime, không chỉ đọc code.
- Sai sót có thể làm mất local work hoặc tạo wiki output rỗng/sai.

Lát việc hiện tại (current slice): audit luồng Local LLM tuần tự. Issue `safe_sync.sh` local-ahead đã được ghi nhận nhưng tạm hoãn, trừ khi nó block local-model execution.

## 2. Hướng đi đã chốt

1. Hoàn tất checkpoint sync audit/report cho trạng thái upstream hiện tại.
   - Đã chứng minh upstream không còn commit thiếu (`commits_behind=0`).
   - Đã chạy audit/report theo sync skill.
   - Theo chuyên gia gpt-5.5/xhigh: không merge.
2. Tập trung audit Local LLM.
   - Soi `phase_router`, `lms_client`, guarded client, worker retry, và scripts regeneration.
   - Tìm gap với quyết định D4/D11/D12: một local model call tại một thời điểm, memory bounded, không làm output wiki rỗng/source-thin.
   - Không rewrite kiến trúc lớn trực tiếp; thay đổi impact lớn phải thành proposal.
3. Thực thi từng fix nhỏ.
   - Pass 1: triển khai (implement).
   - Pass 2: review bằng tests/logs/chuyên gia.
   - Pass 3: vá bổ sung cho điểm thiếu.
4. Chỉ chạy Docker document retry full sau khi code-level gate của Local LLM ổn.

## 3. Issue sync tạm hoãn: `safe_sync.sh` local-ahead guard

Vấn đề: `safe_sync.sh` chỉ exit khi `HEAD == upstream/main`. Khi local đã chứa upstream nhưng có commit local đi trước, script tạo reverse patch `HEAD..upstream`, nhìn như xóa local fork.

Đề xuất fix sau này:

- Sau fetch, nếu `upstream/main` là ancestor của `HEAD`, in thông báo no-op rõ ràng rồi exit 0.
- Không archive patch, không prompt merge, không append pending sync index.
- Thêm regression test cho local-ahead dry-run.

Trạng thái: proposal-level, chưa triển khai vì trọng tâm mới là Local LLM.

## 4. Current work: audit Local LLM tuần tự

Audit phải trả lời:

- Code path nào có thể gọi local model song song?
- Có điều khiển load/unload model thật không, hay chỉ pacing/RAM check?
- Worker/retry có thể chạy nhiều source job cùng lúc vào cùng LM Studio server không?
- Chunk/batch/context sizing nào tạo memory pressure hoặc giảm chất lượng output?
- Validator nào chặn wiki output rỗng/stub/source-thin trước khi mark done?

## 5. Rủi ro và proof cần có

| Khu vực | Mức rủi ro | Lý do | Bằng chứng cần có |
|---|---:|---|---|
| Worker concurrency | HIGH | Nhiều source có thể tranh cùng local model server | đọc code, test, logs |
| Phase router | HIGH | Có thể gọi nhiều model/phase mà không serialize toàn cục | unit tests và flow trace |
| LMS client / guarded client | HIGH | RAM guard không đồng nghĩa unload model | code evidence và runtime probe |
| MRP writer/reducer | MEDIUM | Prompt/context lớn có thể làm output source-thin | tests output quality |
| Retry/regeneration scripts | MEDIUM | Có thể chạy nhiều job song song hoặc không chặn empty wiki | script review + runtime smoke |
| Thay đổi kiến trúc lớn | HIGH | User yêu cầu review trước | proposal tiếng Việt |

## 6. Validation questions

- `uv run pytest tests/unit/ai/local_orchestrator tests/unit/ai/mrp -q` có pass trên baseline không?
- Có test nào chứng minh local calls serialize không?
- Có điểm nào cần proposal thay vì patch trực tiếp không?
- Có thể tạo fix nhỏ đầu tiên không đổi kiến trúc lớn không?
