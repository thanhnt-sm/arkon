---
name: audit-upstream-sync
description: Skill rà soát và tái áp dụng các bản vá bảo mật (Zero Trust) sau khi sync upstream fork. Chặn đứng telemetry, exfiltration và supply chain attacks (bao gồm cả mã độc tự viết).
---

# Skill: Audit Upstream Sync (Advanced Anti-Exfiltration)

Hệ thống Wiki nhạy cảm — mọi dữ liệu người dùng, hành vi, log, metric đều KHÔNG được gửi ra bên thứ 3.
Chỉ được phép giao tiếp: nội bộ hệ thống + AI provider (OpenAI, Anthropic, Google Gemini).

## Kiến Trúc Bảo Vệ (Defense-in-Depth)

```
[Code scan]  →  [Squid whitelist]  →  [Network isolation]  →  [Container hardening]
 Static grep      Specific domains     arkon_internal:true     read_only filesystem
```

## Quy Trình Thực Hiện

### Bước 0: Đồng bộ hóa an toàn
- Chạy `./.agent/workflows/safe_sync.sh`
- Script sẽ: fetch → hiện diff stats → **alert nếu dependency files thay đổi** → hỏi xác nhận
- Diff được **archive** vào `.agent/sync_history/` (không bao giờ xóa — forensic record)
- Sau khi merge: tự động chạy `run_audit.sh`

### Bước 1: Audit tự động
`run_audit.sh` chạy 8 kiểm tra:
1. Framework telemetry (`NEXT_TELEMETRY_DISABLED`)
2. Forbidden SDKs (PostHog, Mixpanel, Sentry, Datadog, v.v.)
3. Custom network calls (`fetch`, `axios`, `httpx`, `aiohttp`, `sendBeacon`, `WebSocket`, `eval`)
4. Behavioral tracking patterns
5. External CDN references (runtime — leak IP người dùng)
6. Squid whitelist integrity (chặn wildcard `.googleapis.com`)
7. Container hardening (`read_only`, `internal: true`)
8. Dependency CVE audit (`npm audit`, `pip-audit`)

### Bước 2: Rà soát thủ công (khi audit báo WARN)
- [ ] Kiểm tra network call bị flag — có trỏ URL ngoài whitelist không?
- [ ] Kiểm tra dependency mới trong `package.json` / `pyproject.toml`
- [ ] Kiểm tra `localStorage`/`sessionStorage`/`Cookie` có ghi thông tin nhạy cảm không?
- [ ] Xác nhận `squid/squid.conf` chỉ có domain cụ thể (không có wildcard)

## Squid Whitelist — Nguyên Tắc

| Domain | Mục đích | Cho phép |
|--------|----------|----------|
| `api.openai.com` | OpenAI LLM/Embedding | ✅ |
| `api.anthropic.com` | Anthropic Claude | ✅ |
| `generativelanguage.googleapis.com` | Google Gemini (LLM, OCR, Embedding) | ✅ |
| `.googleapis.com` (wildcard) | Quá rộng — analytics/firebase/drive | ❌ |
| `.google.com` (wildcard) | Quá rộng | ❌ |
| Bất kỳ analytics/tracking SDK | Thu thập hành vi người dùng | ❌ |

Để thêm provider mới: thêm **specific subdomain** vào `squid/squid.conf` và document lý do.

## Fix Khi Phát Hiện Vi Phạm

1. **Network call lạ**: Xóa hoặc redirect về internal logging
2. **SDK tracking**: Xóa khỏi `package.json`/`pyproject.toml`, chạy lại lock
3. **Squid quá rộng**: Thay wildcard bằng subdomain cụ thể
4. **CDN external**: Download asset về `public/` hoặc cài qua npm

## Git Hook (Auto-Enforcement)

`post-merge` hook tự động chạy audit sau mỗi merge.
Cài lần đầu sau clone: `bash .agent/workflows/install-git-hooks.sh`

## Kích Hoạt Skill
- Người dùng yêu cầu sync từ upstream (`/audit-upstream-sync`)
- Xuất hiện file mới trong `services/`, `utils/`, `hooks/`, `providers/`
- Sau mỗi `npm install` hoặc `pip install` thêm package mới
