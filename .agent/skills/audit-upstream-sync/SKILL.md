---
name: audit-upstream-sync
description: Skill rà soát và tái áp dụng các bản vá bảo mật (Zero Trust) sau khi sync upstream fork. Chặn đứng telemetry, exfiltration và supply chain attacks (bao gồm cả mã độc tự viết).
---

# Skill: Audit Upstream Sync (Advanced Anti-Exfiltration)

Hệ thống Wiki nhạy cảm yêu cầu bảo vệ dữ liệu ở mức cao nhất. Skill này không chỉ chặn các thư viện phổ biến mà còn quét các **mẫu logic tự viết (custom code)** có hành vi thu thập hoặc gửi dữ liệu người dùng ra ngoài.

## 🚀 QUY TRÌNH THỰC HIỆN (Unified Workflow)

Khi được kích hoạt, Agent PHẢI thực hiện các bước sau theo thứ tự:

### Bước 0: Đồng bộ hóa an toàn (Safe Sync)
- **Hành động**: Chạy script `./.agent/workflows/safe_sync.sh`.
- **Mục tiêu**: Fetch code từ `upstream`, hiển thị file diff (`.agent/sync_diff.patch`) để người dùng xem trước khi merge.
- **Yêu cầu**: Chỉ tiến hành Merge khi người dùng xác nhận "y".

### Bước 1: Quét bảo mật tự động (Automated Audit)
- **Hành động**: Chạy script `./.agent/workflows/run_audit.sh`.
- **Mục tiêu**: Tự động phát hiện các điểm rò rỉ dữ liệu, telemetry và logic mạng nghi vấn trong code mới.

### Bước 2: Rà soát thủ công (Deep Manual Audit)
Dựa trên kết quả từ Bước 1 và file diff, rà soát các danh mục sau:

#### 1. Quét Logic Tự Viết (Custom Data Collection)
- [ ] **Network Request Patterns**: Quét toàn bộ code tìm các hàm `fetch`, `axios`, `requests.post`, `urllib` trỏ tới các URL lạ.
- [ ] **Suspicious Event Handlers**: Tìm các hàm có tên như `track`, `sendEvent`, `reportUsage`, `capture`, `emitAction`.
- [ ] **Hidden Metadata**: Kiểm tra các request "bình thường" xem có bị chèn thêm "payload" dữ liệu người dùng hay không.
- [ ] **Browser Storage Abuse**: Kiểm tra việc ghi vào `localStorage`, `sessionStorage` hoặc `Cookies` thông tin nhạy cảm.

#### 2. Kiểm Soát Nhật Ký & Hành Vi (Logging & Behavior)
- [ ] **External Transports**: Chặn các transport log gửi dữ liệu ra server bên ngoài.
- [ ] **Audit Trail Storage**: Đảm bảo log thao tác chỉ ghi vào bảng `audit_logs` nội bộ.

#### 3. Vô hiệu hóa Telemetry & Tracking (Libraries)
- [ ] Kiểm tra `.env`, `package.json`, `pyproject.toml` để chặn đứng các SDK nổi tiếng.
- [ ] Đảm bảo `NEXT_TELEMETRY_DISABLED=1`.

#### 4. Cách Ly Hạ Tầng & Proxy (Final Defense)
- [ ] **Squid Proxy Whitelist**: Đảm bảo `squid/squid.conf` vẫn chỉ cho phép các domain an toàn.
- [ ] **Network Isolation**: Đảm bảo `arkon_internal` vẫn được thiết lập `internal: true`.

---

## 🛠️ Hướng Dẫn Thực Hiện Fix

Nếu phát hiện logic tự viết nghi vấn:
1. **Neutralize Calls**: Vô hiệu hóa các đoạn code `fetch` hoặc `post` trỏ ra server lạ.
2. **Redirect to Local**: Chuyển hướng các log/event này về hệ thống logging nội bộ hoặc xóa bỏ hoàn toàn.
3. **Strict Whitelisting**: Thắt chặt Squid Proxy hơn nữa.
4. **Code Removal**: Xóa bỏ các đoạn mã "theo dõi" hành vi người dùng.

---

## 🚀 Cách Sử Dụng
Dùng skill này ngay sau khi:
- Người dùng yêu cầu đồng bộ từ repo gốc (`/audit-upstream-sync`).
- Thấy xuất hiện các file mới nghi vấn trong folder `services/`, `utils/` hoặc `hooks/`.
