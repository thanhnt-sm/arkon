# ClaudeKit Engineer — Hướng Dẫn Sử Dụng Toàn Diện

> Version: 2.17.0 | Cập nhật: 2026-05

---

## Mục Lục

1. [Tổng Quan Framework](#1-tổng-quan-framework)
2. [Khái Niệm Cốt Lõi](#2-khái-niệm-cốt-lõi)
3. [Thiết Lập Ban Đầu](#3-thiết-lập-ban-đầu)
4. [Pipeline Phát Triển Chính](#4-pipeline-phát-triển-chính)
5. [Workflow: Phát Triển Tính Năng Mới](#5-workflow-phát-triển-tính-năng-mới)
6. [Workflow: Sửa Lỗi (Bug Fix)](#6-workflow-sửa-lỗi-bug-fix)
7. [Workflow: Phân Tích & Bảo Trì](#7-workflow-phân-tích--bảo-trì)
8. [Workflow: Bảo Mật & Kiểm Định](#8-workflow-bảo-mật--kiểm-định)
9. [Kết Hợp Skills Nâng Cao](#9-kết-hợp-skills-nâng-cao)
10. [Best Practices & Anti-Patterns](#10-best-practices--anti-patterns)

---

## 1. Tổng Quan Framework

ClaudeKit Engineer là bộ framework orchestration cho **Claude Code** — AI coding CLI của Anthropic. Framework cung cấp:

| Thành phần | Số lượng | Mục đích |
|-----------|----------|---------|
| Skills | 77+ | Lệnh chuyên biệt cho từng tác vụ (`/ck:plan`, `/ck:cook`...) |
| Agents | 14 | Subagent chuyên biệt (planner, tester, code-reviewer...) |
| Hooks | 16 | Tự động hóa vòng đời (session, tool, prompt) |
| Rules | 7 | Quy trình và tiêu chuẩn bắt buộc |

**Triết lý cốt lõi**: YAGNI · KISS · DRY — Chỉ làm điều cần thiết, làm đơn giản, không lặp lại.

---

## 2. Khái Niệm Cốt Lõi

### 2.1 Skills vs Agents

- **Skills** (`/ck:xxx`) — lệnh bạn gõ trực tiếp vào Claude Code, điều phối toàn bộ workflow
- **Agents** — subagent được skills tự động spawn, bạn không gọi trực tiếp

```
Bạn gõ: /ck:cook "thêm tính năng login"
         ↓
cook skill spawn: researcher → planner → fullstack-developer → tester → code-reviewer
         ↓
Kết quả: code đã implement, test, review
```

### 2.2 Coding Level

Điều chỉnh văn phong và độ sâu phản hồi trong `.claude/.ck.json`:

| Level | Mô tả | Dùng khi |
|-------|--------|---------|
| 0 | ELI5 — giải thích cực kỳ đơn giản | Học viên mới |
| 1 | Junior developer | Mới học |
| 2 | Mid-level developer | Có kinh nghiệm cơ bản |
| 3 | Senior engineer | Chuyên nghiệp |
| 4 | Tech lead *(default)* | Kiến trúc, trade-off | 
| 5 | Expert/thought leader | Deep dive, architecture |

Đổi level: `/ck:coding-level 3`

### 2.3 Plan Files

Plans được lưu tại `./plans/{YYMMDD-HHmm}-{issue}-{slug}/`:
- `plan.md` — tổng quan với YAML frontmatter
- `phase-01-xxx.md` đến `phase-N-xxx.md` — từng giai đoạn
- `reports/` — báo cáo từ subagents

Plans **persist across sessions** — Claude có thể tiếp tục công việc từ session trước.

### 2.4 Hooks Tự Động

Framework tự động inject context qua hooks — bạn không cần làm gì:

| Hook | Khi nào | Làm gì |
|------|---------|--------|
| `session-init` | Mở session | Load project context |
| `dev-rules-reminder` | Mỗi prompt | Inject development rules |
| `privacy-block` | Đọc file nhạy cảm | Yêu cầu approval |
| `simplify-gate` | Prompt có "ship/deploy" | Chặn cho đến khi simplify xong |
| `usage-quota-cache-refresh` | Định kỳ | Hiển thị usage trên statusline |

---

## 3. Thiết Lập Ban Đầu

### 3.1 Khởi Động Session

Khi mở Claude Code trong thư mục project:
1. Hook `session-init` tự chạy — detect project type, load config
2. Statusline hiển thị: coding level, usage, active plan (nếu có)
3. Framework sẵn sàng

### 3.2 Cài Python Environment (Một Lần)

Cần thiết cho các skills: design, ai-multimodal, databases, devops, media-processing:

```bash
# Chạy từ thư mục gốc project
bash .claude/skills/install.sh -y
```

Script tự động:
- Tạo `.claude/skills/.venv/` (isolated, không ảnh hưởng Python hệ thống)
- Cài tất cả packages từ requirements.txt của từng skill
- Cài npm global tools: repomix, pnpm, wrangler

### 3.3 Kiểm Tra Framework

```
/ck:ask "framework ClaudeKit đang hoạt động không?"
```

### 3.4 Tạo README cho Project

CLAUDE.md yêu cầu đọc `./README.md` trước mọi tác vụ. Tạo file này:

```
/ck:docs init
```

---

## 4. Pipeline Phát Triển Chính

### 4.1 Pipeline Đầy Đủ (Standard)

```
/ck:plan → /ck:cook → /ck:test → /ck:code-review → /ck:ship → /ck:journal
```

| Bước | Skill | Agent spawn | Output |
|------|-------|-------------|--------|
| 1. Lên kế hoạch | `/ck:plan` | planner, researcher | `plans/xxx/plan.md` + phases |
| 2. Implement | `/ck:cook <plan-path>` | fullstack-developer, tester | Code đã viết |
| 3. Test | `/ck:test` | tester | Coverage report |
| 4. Review | `/ck:code-review` | code-reviewer | Review report |
| 5. Deploy | `/ck:ship` | git-manager, devops | Deployed |
| 6. Ghi nhật ký | `/ck:journal` | journal-writer | Journal entry |

### 4.2 Pipeline Nhanh (Fast Mode)

Khi task đơn giản, không cần nghiên cứu sâu:

```
/ck:cook "mô tả task" --fast → /ck:test → /ck:code-review
```

### 4.3 Pipeline Song Song (Parallel)

Khi có 3+ tính năng độc lập cần implement cùng lúc:

```
/ck:plan → /ck:cook <plan-path> --parallel → /ck:test → /ck:code-review
```

---

## 5. Workflow: Phát Triển Tính Năng Mới

### Bước 1 — Làm Rõ Yêu Cầu

Trước khi lên kế hoạch, dùng brainstorm để khám phá giải pháp và trade-off:

```
/ck:brainstorm "thêm hệ thống xác thực OAuth2 với Google và GitHub"
```

Output: 2-3 phương án với trade-off rõ ràng. Chọn phương án phù hợp.

**Khi nào dùng brainstorm?**
- Tính năng mới chưa có hướng rõ ràng
- Có nhiều cách implement, cần so sánh
- Cần đánh giá rủi ro trước khi cam kết

### Bước 2 — Nghiên Cứu Kỹ Thuật (Nếu Cần)

Khi cần tìm hiểu library, best practice, hay giải pháp:

```
/ck:research "OAuth2 implementation với NextAuth.js, best practices 2025"
```

### Bước 3 — Lên Kế Hoạch

```
/ck:plan "implement OAuth2 authentication với Google và GitHub provider"
```

**Các mode của plan:**

| Mode | Lệnh | Khi nào dùng |
|------|------|-------------|
| Standard | `/ck:plan "..."` | Tính năng bình thường |
| Nhanh | `/ck:plan "..." --fast` | Tính năng đơn giản, rõ ràng |
| Phức tạp | `/ck:plan "..." --hard` | Có nhiều rủi ro, cần red team |
| Song song | `/ck:plan "..." --parallel` | 3+ tính năng độc lập |
| TDD | `/ck:plan "..." --tdd` | Test-driven development |

**Plan output mẫu:**
```
plans/
└── 260516-0900-GH-42-oauth2-auth/
    ├── plan.md                    ← Overview, status, phases
    ├── phase-01-setup.md          ← Setup dependencies
    ├── phase-02-providers.md      ← Configure Google/GitHub
    ├── phase-03-session.md        ← Session management
    └── reports/                   ← Agent reports
```

### Bước 4 — Implement

Sau khi plan được tạo, cook tự đọc plan và implement:

```
/ck:cook plans/260516-0900-GH-42-oauth2-auth/plan.md
```

Hoặc nếu muốn interactive (Claude hỏi từng bước):
```
/ck:cook plans/260516-0900-GH-42-oauth2-auth/plan.md --interactive
```

**Cook tự động làm:**
1. Đọc plan → hiểu scope
2. Scout codebase → tìm patterns hiện có
3. Implement theo từng phase
4. Simplify code (YAGNI/KISS check)
5. Test
6. Code review

### Bước 5 — Test Độc Lập

Sau cook, chạy test riêng để xác nhận:

```
/ck:test
```

Nếu có UI, test visual:
```
/ck:test ui
```

### Bước 6 — Code Review

```
/ck:code-review
```

Hoặc review cụ thể pending changes:
```
/ck:code-review --pending
```

### Bước 7 — Ship

```
/ck:ship
```

> ⚠️ **Lưu ý `simplify-gate`**: Nếu prompt chứa "deploy/ship/publish/merge", hook sẽ chặn và nhắc chạy `/ck:simplify` trước. Đây là intentional — đảm bảo code đã được tối giản.

### Bước 8 — Ghi Journal

```
/ck:journal
```

Journal tự động ghi lại: quyết định kỹ thuật, vấn đề gặp phải, giải pháp chọn.

---

### Ví Dụ End-to-End: Xây Dựng REST API Mới

```bash
# 1. Brainstorm kiến trúc
/ck:brainstorm "REST API cho quản lý sản phẩm: Node/Express vs FastAPI vs NestJS"

# 2. Lên kế hoạch (chọn NestJS sau brainstorm)
/ck:plan "xây dựng REST API quản lý sản phẩm với NestJS, PostgreSQL, JWT auth"

# 3. Implement từng phase
/ck:cook plans/xxx/plan.md

# 4. Test
/ck:test

# 5. Security audit
/ck:ck-security

# 6. Code review
/ck:code-review

# 7. Ship
/ck:ship

# 8. Update docs
/ck:docs update

# 9. Journal
/ck:journal
```

---

## 6. Workflow: Sửa Lỗi (Bug Fix)

### Pipeline Sửa Lỗi

```
/ck:scout → /ck:ck-debug → /ck:fix → /ck:test → /ck:code-review
```

### Bước 1 — Scout: Hiểu Codebase

Trước khi đụng vào code, scout để hiểu phạm vi ảnh hưởng:

```
/ck:scout "tìm tất cả code liên quan đến payment processing"
```

Scout spawn 2-3 Explore agents song song, trả về report các file liên quan.

### Bước 2 — Debug: Tìm Root Cause

**HARD-GATE**: Không được sửa trước khi tìm ra root cause.

```
/ck:ck-debug "lỗi 500 khi checkout với PayPal, stack trace: [paste error]"
```

Debug skill:
1. Phân tích error message và stack trace
2. Tạo 2-3 hypothesis
3. Spawn parallel Explore agents để test từng hypothesis
4. Báo cáo root cause + evidence

### Bước 3 — Fix

Sau khi biết root cause, sửa lỗi:

```
/ck:fix "thanh toán PayPal fail do currency format sai, root cause đã xác định"
```

**Modes của fix:**

| Mode | Lệnh | Khi nào |
|------|------|---------|
| Auto | `/ck:fix` | Hầu hết trường hợp |
| Review | `/ck:fix --review` | Code quan trọng, production |
| Quick | `/ck:fix --quick` | Typo, lint error, trivial |
| Parallel | `/ck:fix --parallel` | 2+ bugs độc lập |

### Bước 4 — Verify

Fix skill tự động chạy verify, nhưng bạn có thể chạy thêm:

```
/ck:test
```

### Anti-Patterns Phổ Biến Khi Fix Bug

❌ **Sai**: `/ck:fix "sửa bug checkout"` — quá mơ hồ, không có root cause

✅ **Đúng**: `/ck:fix "checkout 500 error do null check thiếu ở PaymentService.process(), xảy ra khi amount = 0"`

❌ **Sai**: Fix xong không chạy test

✅ **Đúng**: Luôn chạy `/ck:test` sau fix, verify bằng regression test

---

### Ví Dụ: Sửa Bug Performance

```bash
# 1. Scout phạm vi
/ck:scout "tìm tất cả database queries trong module dashboard"

# 2. Debug nguyên nhân chậm
/ck:ck-debug "dashboard load 8 giây, profile cho thấy N+1 query problem"

# 3. Fix với review (production code)
/ck:fix "N+1 query ở DashboardRepository.getStats(), cần eager loading" --review

# 4. Test performance
/ck:test

# 5. Review
/ck:code-review

# 6. Journal ghi lại giải pháp
/ck:journal
```

---

## 7. Workflow: Phân Tích & Bảo Trì

### 7.1 Phân Tích Codebase Hiện Có

Khi vào project mới hoặc cần hiểu sâu:

```bash
# Tổng quan codebase
/ck:scout "phân tích toàn bộ cấu trúc project"

# Tóm tắt bằng AI
/ck:docs summarize
```

### 7.2 Refactor

```bash
# 1. Scout vùng cần refactor
/ck:scout "tìm tất cả code dùng UserService"

# 2. Brainstorm cách refactor
/ck:brainstorm "tách UserService thành AuthService + ProfileService, đánh giá trade-off"

# 3. Lên kế hoạch refactor
/ck:plan "refactor UserService: tách authentication logic ra AuthService" --hard

# 4. Thực hiện (code mode, không cần research)
/ck:cook plans/xxx/plan.md

# 5. Test đầy đủ
/ck:test

# 6. Code review nghiêm ngặt
/ck:code-review codebase

# 7. Update docs
/ck:docs update
```

### 7.3 Kiểm Tra & Cải Thiện Code Quality

```bash
# Review toàn bộ codebase
/ck:code-review codebase

# Hoặc review song song (nhanh hơn)
/ck:code-review codebase parallel

# Simplify code phức tạp
/ck:simplify

# Security audit
/ck:ck-security

# Scan secrets/vulnerabilities
/ck:security-scan
```

### 7.4 Cập Nhật Documentation

```bash
# Cập nhật docs sau thay đổi lớn
/ck:docs update

# Init docs cho project mới
/ck:docs init

# Tạo visual diagram
/ck:preview --diagram "luồng xử lý thanh toán"

# Tạo Mermaid diagram
/ck:mermaidjs-v11 "sequence diagram của OAuth2 flow"
```

### 7.5 Dependency & Tech Debt

```bash
# Nghiên cứu upgrade path
/ck:research "upgrade từ React 18 lên React 19, breaking changes và migration guide"

# Lên kế hoạch upgrade
/ck:plan "upgrade React 18 → 19: migrate từng component, fix breaking changes"

# Preview impact
/ck:preview --explain "impact của React 19 lên project hiện tại"
```

---

## 8. Workflow: Bảo Mật & Kiểm Định

### 8.1 Security Audit Định Kỳ

```bash
# Full STRIDE + OWASP audit
/ck:ck-security

# Scan secrets và vulnerabilities
/ck:security-scan

# Chỉ audit authentication
/ck:ck-security "audit authentication và authorization layer"
```

### 8.2 Trước Khi Deploy Production

```bash
# 1. Security audit
/ck:ck-security

# 2. Code review toàn diện
/ck:code-review codebase

# 3. Test coverage check
/ck:test

# 4. Ship với confirmation
/ck:ship
```

---

## 9. Kết Hợp Skills Nâng Cao

### 9.1 Map Kết Hợp Skills Theo Domain

**Frontend Development:**
```
/ck:brainstorm (UI/UX) → /ck:ui-ux-pro-max (design) → /ck:plan → /ck:cook → /ck:frontend-development → /ck:ui-styling → /ck:test ui → /ck:web-design-guidelines
```

**Backend API:**
```
/ck:research (API design) → /ck:plan → /ck:cook → /ck:backend-development → /ck:databases → /ck:better-auth (auth) → /ck:test → /ck:ck-security
```

**Full-Stack Feature:**
```
/ck:brainstorm → /ck:plan --hard → /ck:cook --parallel → /ck:test → /ck:code-review → /ck:ship
```

**AI/LLM Feature:**
```
/ck:context-engineering → /ck:research → /ck:plan → /ck:cook → /ck:llms → /ck:test → /ck:code-review
```

**DevOps/Infrastructure:**
```
/ck:devops → /ck:deploy → /ck:ck-security
```

**MCP Server:**
```
/ck:mcp-builder → /ck:mcp-management → /ck:use-mcp
```

### 9.2 Multi-Agent Team Workflow

Khi project lớn cần nhiều người làm song song:

```
/ck:team → [planner tạo tasks] → [developer-1, developer-2 làm song song] → [tester verify] → [code-reviewer]
```

Chi tiết: xem `docs/claudekit-advanced-workflows.md`

### 9.3 Bootstrap Project Mới

Từ ý tưởng → project hoàn chỉnh:

```bash
# Full interactive (nghiên cứu → thiết kế → plan → code)
/ck:bootstrap "SaaS platform quản lý inventory với React, NestJS, PostgreSQL"

# Nhanh (bỏ qua research)
/ck:bootstrap "..." --fast

# Auto (không cần confirm từng bước)
/ck:bootstrap "..." --auto
```

Bootstrap tự động: research → tech stack → design → plan → implement.

### 9.4 Preview & Visualization

Tạo visual output để giải thích:

```bash
# Giải thích bằng ASCII diagram
/ck:preview --explain "luồng authentication"

# Mermaid diagram
/ck:preview --diagram "database schema"

# Slide presentation
/ck:preview --slides "kiến trúc hệ thống cho team review"

# Interactive HTML
/ck:preview --html "dashboard mockup"
```

### 9.5 Sequential Thinking cho Vấn Đề Phức Tạp

Khi cần phân tích từng bước, không vội vàng:

```bash
/ck:sequential-thinking "phân tích tại sao hệ thống bị bottleneck ở peak hours"
```

---

## 10. Best Practices & Anti-Patterns

### 10.1 Best Practices

**Luôn làm:**
- Chạy `/ck:plan` trước khi code bất kỳ tính năng nào (trừ trivial fix)
- Chạy `/ck:test` sau mỗi implement
- Dùng `/ck:scout` để hiểu codebase trước khi sửa
- Cập nhật `./docs` sau mỗi tính năng lớn bằng `/ck:docs update`
- Ghi `/ck:journal` vào cuối session quan trọng
- Giữ file code dưới 200 LOC (tự động được nhắc bởi hook)

**Không làm:**
- Implement không có plan (bị cook skill hard-gate)
- Sửa bug không tìm root cause (bị fix skill hard-gate)
- Ship trước khi simplify (bị `simplify-gate` hook chặn)
- Hardcode credentials (bị `privacy-block` hook chặn)
- Commit file nhạy cảm (`.env`, `*.key`)

### 10.2 Anti-Patterns Phổ Biến

| Anti-Pattern | Vấn Đề | Giải Pháp |
|-------------|---------|-----------|
| "Fix nhanh, test sau" | Tech debt tích lũy | Luôn `/ck:test` sau fix |
| Mô tả task mơ hồ | Plan/cook kém chất lượng | Mô tả cụ thể: context + goal + constraint |
| Skip brainstorm | Chọn sai hướng | Dùng `/ck:brainstorm` cho tính năng phức tạp |
| Plan quá lớn | Một phase = nhiều tuần | Chia phase ≤ 1 ngày mỗi phase |
| Override simplify-gate | Code bloat | Chạy `/ck:simplify` trước khi ship |

### 10.3 Mô Tả Task Hiệu Quả

**Template tốt cho `/ck:plan` và `/ck:cook`:**
```
[Tính năng/Vấn đề]: [Mô tả ngắn gọn]
Context: [Thông tin nền tảng]
Goal: [Kết quả mong muốn]
Constraints: [Giới hạn kỹ thuật, business]
Scope: [Trong/ngoài phạm vi]
```

**Ví dụ tốt:**
```
/ck:plan "thêm email notification khi order được xử lý.
Context: đang dùng NestJS + SendGrid, có OrderService.
Goal: gửi email xác nhận cho customer sau khi order status = PROCESSING.
Constraints: không thay đổi OrderService hiện có, dùng queue để async.
Scope: chỉ email, không notification khác."
```

### 10.4 Quản Lý Plans Dài Hạn

```bash
# Xem tất cả plans và trạng thái
/ck:plans-kanban

# Tiếp tục plan đang dở
/ck:cook plans/xxx/plan.md

# Kiểm tra trạng thái plan
# Claude tự đọc phase files và tiếp tục từ phase chưa xong
```

---

*Xem thêm: `docs/claudekit-workflows-pm-ba.md` cho workflow PM/BA | `docs/claudekit-skills-reference.md` cho tham chiếu skills đầy đủ*
