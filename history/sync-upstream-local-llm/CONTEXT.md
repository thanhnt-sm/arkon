# Đồng bộ upstream và tối ưu Local LLM - Ngữ cảnh (Context)

**Mã nhánh việc (feature slug):** `sync-upstream-local-llm`
**Ngày:** 2026-05-31
**Trạng thái khám phá (exploring):** hoàn tất
**Phạm vi:** sâu (Deep)
**Miền tác động (domain types):** giao diện (SEE) | API (CALL) | luồng chạy (RUN) | tài liệu (READ) | cấu hình/dữ liệu (ORGANIZE)

## Ranh giới công việc

Đã chạy kiểm toán/biên bản đồng bộ upstream (sync audit/report) để chứng minh repo hiện không thiếu commit upstream; trọng tâm tiếp theo là vi phẫu luồng Local LLM để giảm tải hiệu năng/bộ nhớ trên MacBook, không gọi model song song, và vẫn giữ chất lượng wiki đầu ra.

## Quyết định đã khóa

Các quyết định này là nguồn sự thật (source of truth) cho planning, validating, executing, reviewing.

- **D1:** Giữ toàn bộ code local có chủ đích và hạ tầng bảo mật local khi nhận code upstream theo hướng cộng thêm (additive).
  - Lý do: fork có Local AI orchestrator, proxy hardening, retry scripts, migrations và docs mà upstream không có.
- **D2:** Mỗi checkpoint đồng bộ upstream phải chạy đúng skill `.claude/skills/sync-audit-upstream`: fetch/archive dry-run, audit, conflict inventory, report, rồi mới quyết định.
- **D3:** Auto-approve Khuym nghĩa là được đi tiếp qua các phase Khuym, không có nghĩa được bỏ qua audit/report hoặc hard gate của sync skill.
- **D4:** Tối ưu cho giới hạn phần cứng MacBook hiện tại bằng cách chạy Local LLM tuần tự: một model được gọi tại một thời điểm, có pacing rõ ràng, không song song.
- **D5:** Mỗi bước quan trọng phải lưu bằng chứng bền vững (durable evidence) dưới `history/sync-upstream-local-llm/` hoặc thư mục audit/report hiện có.
- **D6:** Mỗi lát thực thi (execution slice) có 3 pass: triển khai (implement), review, rồi vá bổ sung (follow-up patch). Pass 3 bổ sung chứ không đè giải pháp pass 1.
- **D7:** Chưa được coi là hoàn tất nếu chưa chạy runtime/Docker xử lý lại source documents qua retry/regeneration và kiểm tra wiki output không rỗng, có nội dung từ nguồn, không lỗi.
- **D8:** Quyết định sau audit/report theo đề xuất chuyên gia gpt-5.5/xhigh, trừ khi bằng chứng repo trực tiếp mâu thuẫn.
- **D9:** Không tự ý đổi giải pháp sản phẩm hoặc kiến trúc module lớn. Thay đổi impact lớn phải ghi thành tài liệu đề xuất (proposal) cho human review.
- **D10:** Từ sau sync audit/report hiện tại, ưu tiên tuyệt đối là luồng dùng local model: hiệu suất (performance), bộ nhớ (memory), và chất lượng wiki output.
- **D11:** Tương tác Local LLM phải tuần tự (serialized). Text, vision, embedding, verification không được gọi song song vào local model server.
- **D12:** Tối ưu giảm tải không được làm wiki output rỗng, dạng stub, hoặc thiếu nội dung từ nguồn (source-thin).

### Quyền tự quyết của agent

Agent được chọn lát việc nhỏ an toàn, cập nhật artifact Khuym, chạy scripts/tests, và dùng subagent gpt-5.5/xhigh để phản biện. Agent không được reset history, phá local work, bỏ qua security gates, gọi Local LLM song song, hoặc sửa kiến trúc lớn khi chưa có proposal cho human review.

## Tham chiếu và ý tưởng cụ thể

- `.claude/skills/sync-audit-upstream/SKILL.md` - quy trình đồng bộ upstream bắt buộc.
- User yêu cầu: giữ local code hoàn toàn, nhưng vẫn sync được upstream.
- User yêu cầu mới: tập trung hoàn toàn vào local model trên MacBook yếu, tối ưu performance/memory/output quality.
- User yêu cầu mới: tài liệu cho human đọc phải viết bằng tiếng Việt, kèm keyword tiếng Anh trong ngoặc khi cần.
- User yêu cầu: mỗi bước có chuyên gia gpt-5.5/xhigh phản biện.

## Bối cảnh code hiện có

### Tài sản tái sử dụng

- `.agent/workflows/safe_sync.sh` - dry-run archive và merge hard gate cho upstream sync.
- `.agent/workflows/run_audit.sh` - security audit cho tree hiện tại và patch upstream đã archive.
- `.agent/workflows/categorize_conflicts.sh` - phân loại file thay đổi deterministic.
- `plans/reports/sync-audit-260531-0736-upstream-already-ancestor.md` - report hiện tại: upstream đã là ancestor, không merge.
- `app/ai/local_orchestrator/` - provider, router, guardrails, pacing, cấu hình phase local.
- `app/ai/mrp/` - pipeline document-to-wiki.
- `app/worker.py` - background processing/retry.
- `scripts/retry-sources.sh`, `scripts/regen-failed-source.py`, `scripts/run-regen.sh` - entrypoint vận hành retry/regeneration.

### Pattern đã có

- Artifact Khuym nằm ở `history/<feature>/`; runtime state nằm ở `.khuym/state.json`.
- Audit report nằm ở `plans/reports/sync-audit-*.md`; patch archive nằm ở `.agent/sync_history/`.
- Local fork ưu tiên bảo toàn Local AI runtime thay vì nhận upstream deletion không tương đương.

### Điểm tích hợp cần đọc

- `app/ai/local_orchestrator/phase_router.py` - điều phối phase và pacing.
- `app/ai/local_orchestrator/lms_client.py` - client gọi LM Studio/OpenAI-compatible local server.
- `app/ai/local_orchestrator/lms_client_guarded.py` - guard bộ nhớ và preflight.
- `app/ai/local_orchestrator/ram_guard.py` - kiểm tra RAM.
- `app/ai/local_orchestrator/provider_adapter.py` - adapter provider local.
- `app/worker.py` - job orchestration.
- `app/ai/mrp/writer.py`, `pipeline.py`, `mapper.py`, `reducer.py`, `digest.py` - chất lượng wiki output.
- `docker-compose.yml`, `squid/squid.conf` - runtime và network hardening.

## Câu hỏi chuyển sang planning

- [ ] Code path nào hiện có thể gọi Local LLM song song?
- [ ] Load/unload model thật sự được điều khiển ở đâu, hay hiện mới chỉ là pacing/RAM check?
- [ ] Worker/retry có thể chạy nhiều source job cùng lúc và tranh cùng LM Studio server không?
- [ ] Chunk/batch sizing nào gây áp lực memory hoặc context quá dài làm output yếu?
- [ ] Cơ chế nào đang chặn wiki output rỗng/stub/source-thin trước khi đánh dấu source done?

## Ý tưởng tạm hoãn

- Chạy model song song, giữ nhiều model trong RAM, hoặc nâng phần cứng - ngoài phạm vi vì trái yêu cầu phần cứng hiện tại.
- Redesign sản phẩm/wiki lớn - chỉ làm proposal nếu audit chứng minh cần thiết.
- Sửa sync workflow guard - đã document thành residual issue; chưa ưu tiên hơn local model.

## Handoff

`CONTEXT.md` là nguồn sự thật. Các decision ID ổn định. Planning đọc locked decisions, code context, references, và câu hỏi chuyển tiếp. Validating/reviewing dùng các decision này để kiểm tra độ phủ và bằng chứng thực tế.
