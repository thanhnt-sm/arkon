# No Telemetry & Data Exfiltration Rule

**Level:** Critical
**Scope:** Toàn bộ workspace

Để đảm bảo quyền riêng tư tối đa và ngăn chặn mọi nguy cơ rò rỉ dữ liệu hoặc lộ IP ra bên ngoài (Data Exfiltration & IP Leakage), MỌI AI agent và developer khi hoạt động trong repo này phải tuân thủ nghiêm ngặt các quy tắc sau:

## 1. Không External CDNs
- **TUYỆT ĐỐI KHÔNG** sử dụng các thẻ `<link>` hoặc `<script>` để tải tài nguyên (CSS, JS, Fonts, Images) từ các external CDN (như `fonts.googleapis.com`, `cdnjs`, `unpkg`, v.v.).
- Tác hại: Việc trình duyệt gửi request tới các external server sẽ làm lộ địa chỉ IP và thông tin thiết bị của người dùng.
- **Giải pháp**: Tất cả các tài nguyên phải được download và host locally (trong thư mục `public` hoặc thông qua module bundler). Đối với fonts, sử dụng `next/font/google` hoặc cài đặt qua npm (ví dụ `npm install material-symbols`).

## 2. Không Analytics & Tracking
- **KHÔNG** cài đặt hay tích hợp bất kỳ công cụ theo dõi, analytics, hay telemetry nào vào frontend lẫn backend.
- Các công cụ bị cấm bao gồm nhưng không giới hạn: PostHog, Mixpanel, Google Analytics, Datadog, Sentry, LogRocket, Hotjar.
- **Giải pháp**: Mọi log lỗi và metrics chỉ được phép lưu trữ local thông qua các thư viện logger nội bộ (ví dụ: `loguru`, ghi file log local, console.log).

## 3. Chặn Telemetry Mặc Định Của Frameworks
- Khi cấu hình các framework hoặc công cụ mới (như Next.js, Gatsby, Storybook, v.v.), phải luôn tìm cách tắt telemetry mặc định của chúng.
- Ví dụ: Luôn giữ biến môi trường `NEXT_TELEMETRY_DISABLED=1` ở các script build/dev.

## 4. Kiểm Soát Outbound Requests
- Ở backend (Python), mọi requests ra bên ngoài internet (thông qua `httpx`, `aiohttp`, `requests`) chỉ được phục vụ cho mục đích xử lý business logic (như gọi API LLM từ provider do người dùng cấu hình).
- **KHÔNG** gửi telemetry data hay metrics nội bộ của ứng dụng ra ngoài.

> [!WARNING]
> Mọi thay đổi vi phạm quy tắc này (dù vô tình) đều sẽ bị từ chối merge. Luôn ưu tiên offline-first và local-hosted cho mọi tài nguyên tĩnh.
