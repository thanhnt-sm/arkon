# ClaudeKit — Workflow Ngoài Code: PM, BA, Phân Tích Nghiệp Vụ

> Hướng dẫn sử dụng ClaudeKit cho công việc quản lý dự án, phân tích nghiệp vụ, tài liệu hóa — không yêu cầu kỹ năng lập trình.

---

## Mục Lục

1. [Tổng Quan Sử Dụng Ngoài Code](#1-tổng-quan-sử-dụng-ngoài-code)
2. [Role: Project Manager (PM)](#2-role-project-manager-pm)
3. [Role: Business Analyst (BA)](#3-role-business-analyst-ba)
4. [Role: System Analyst / Architect](#4-role-system-analyst--architect)
5. [Role: Technical Writer / Documentation](#5-role-technical-writer--documentation)
6. [Workflow Chung: Từ Ý Tưởng Đến Tài Liệu](#6-workflow-chung-từ-ý-tưởng-đến-tài-liệu)
7. [Skills Hữu Ích Cho Non-Dev](#7-skills-hữu-ích-cho-non-dev)

---

## 1. Tổng Quan Sử Dụng Ngoài Code

ClaudeKit được thiết kế cho developers, nhưng nhiều skills và workflows có giá trị lớn cho **PM, BA, và các role phi kỹ thuật**. Điểm mạnh khi dùng ClaudeKit cho công việc phi code:

- **Tư duy có cấu trúc** — Skills như `sequential-thinking`, `brainstorm`, `ask` giúp phân tích vấn đề có hệ thống
- **Tạo tài liệu chuyên nghiệp** — `docs`, `preview`, `mermaidjs-v11`, `excalidraw`
- **Nghiên cứu thông minh** — `research` tổng hợp thông tin từ nhiều nguồn
- **Quản lý kế hoạch** — `ck-plan`, `project-management`, `plans-kanban`
- **Visualization** — `preview`, `mermaidjs-v11`, `excalidraw` tạo diagram, slide

**Nguyên tắc khi dùng cho công việc phi code:**
- Thay "implement feature" = "phân tích yêu cầu / viết tài liệu / lên kế hoạch"
- Thay "code file" = "tài liệu Word/Markdown"
- Skills vẫn hoạt động theo cùng pipeline

---

## 2. Role: Project Manager (PM)

### 2.1 Quy Trình Từ Ý Tưởng Đến Kế Hoạch Dự Án

#### Giai Đoạn 1: Thu Thập & Làm Rõ Yêu Cầu

```bash
# Phân tích ý tưởng ban đầu, tìm gap và câu hỏi cần làm rõ
/ck:brainstorm "xây dựng hệ thống quản lý sau vay cho ngân hàng PVComBank:
  - Theo dõi khoản vay
  - Nhắc nhở đến hạn
  - Báo cáo nợ xấu
  Đánh giá scope, rủi ro, và các câu hỏi cần làm rõ với stakeholder"
```

**Kết quả**: Danh sách câu hỏi cần clarify, risk assessment sơ bộ, phương án tiếp cận.

```bash
# Nghiên cứu quy định và best practice liên quan
/ck:research "quy định SBV về quản lý sau vay, IFRS 9 loan monitoring, best practices banking CRM 2024"
```

#### Giai Đoạn 2: Phân Tích BRD (Business Requirements Document)

```bash
# Cấu trúc BRD từ yêu cầu thô
/ck:ask "với các yêu cầu sau [paste yêu cầu], giúp tôi:
  1. Phân loại functional vs non-functional requirements
  2. Xác định business rules quan trọng
  3. Tìm các dependency giữa modules
  4. Đánh giá độ ưu tiên theo MoSCoW"
```

```bash
# Tạo visual diagram cho BRD
/ck:mermaidjs-v11 "mindmap của các module hệ thống quản lý sau vay:
  - Quản lý hồ sơ vay
  - Theo dõi thanh toán
  - Cảnh báo rủi ro
  - Báo cáo/Dashboard
  - Tích hợp Core Banking"
```

#### Giai Đoạn 3: Lập URD (User Requirements Document)

```bash
# Phân tích user stories từ BRD
/ck:sequential-thinking "phân tích BRD sau [paste BRD summary] và tạo:
  1. Danh sách user personas (Cán bộ tín dụng, Kiểm soát viên, Ban lãnh đạo)
  2. User stories theo từng persona (format: As a [role], I want [action], so that [benefit])
  3. Acceptance criteria cho 5 user stories quan trọng nhất
  4. Prioritization matrix"
```

```bash
# Tạo user flow diagram
/ck:preview --diagram "user flow của quy trình nhắc nhở nợ quá hạn:
  Hệ thống phát hiện → Tạo task → Giao CBTD → CBTD liên hệ → Ghi nhận kết quả → Escalate nếu cần"
```

#### Giai Đoạn 4: Lập Kế Hoạch Dự Án

```bash
# Lên plan chi tiết cho dự án
/ck:plan "lập kế hoạch triển khai Hệ thống Quản lý Sau Vay PVComBank.
  Context: dự án 6 tháng, team 8 người (2 BA, 4 dev, 1 QA, 1 PM).
  Constraint: tích hợp Core Banking T24, deadline Q4/2026.
  Goal: kế hoạch có milestones, deliverables, dependencies rõ ràng."
```

**Plan output sẽ tạo:**
- `plan.md` — tổng quan, timeline
- `phase-01-discovery.md` — thu thập yêu cầu, design
- `phase-02-mvp.md` — tính năng cốt lõi
- `phase-03-integration.md` — tích hợp T24
- `phase-04-uat.md` — UAT và rollout

```bash
# Xem kanban board của plan
/ck:plans-kanban
```

#### Giai Đoạn 5: Theo Dõi Tiến Độ

```bash
# Báo cáo trạng thái dự án
/ck:project-management "tạo weekly status report cho dự án Quản lý Sau Vay:
  - Sprint 3/10 vừa xong
  - Completed: module hồ sơ vay, API Core Banking
  - In progress: module thanh toán
  - Blocker: chờ credentials T24 từ IT"

# Tạo visual timeline
/ck:preview --slides "project timeline Q3-Q4/2026 với milestones và dependencies"
```

### 2.2 Quản Lý Rủi Ro

```bash
# Risk assessment
/ck:ask "đánh giá risk matrix cho dự án tích hợp Core Banking T24:
  Context: hệ thống T24 cũ, API documentation thiếu, team chưa có kinh nghiệm T24
  Output: risk register với likelihood, impact, mitigation plan"

# Scenario planning
/ck:ck-scenario "nếu tích hợp T24 chậm 4 tuần so với plan:
  - Phân tích impact lên các phase khác
  - Các phương án mitigation
  - Go/No-go criteria"
```

### 2.3 Stakeholder Communication

```bash
# Tạo executive summary
/ck:preview --slides "executive summary tháng 5/2026 dự án QLSV:
  - Progress: 40% hoàn thành
  - Key achievements
  - Risks và mitigation
  - Next steps"

# Tạo demo script
/ck:ask "viết demo script 15 phút cho buổi demo module theo dõi khoản vay với Ban lãnh đạo,
  highlight business value, không dùng technical jargon"
```

---

## 3. Role: Business Analyst (BA)

### 3.1 Phân Tích Yêu Cầu Nghiệp Vụ

#### Thu Thập & Cấu Trúc Yêu Cầu

```bash
# Phân tích yêu cầu thô từ stakeholder
/ck:sequential-thinking "tôi vừa họp với stakeholder và ghi chú:
  [paste meeting notes]
  
  Giúp tôi:
  1. Extract functional requirements
  2. Identify non-functional requirements ẩn
  3. Tìm ambiguities cần clarify
  4. Suggest acceptance criteria"
```

```bash
# Tổ chức yêu cầu thành cấu trúc
/ck:ask "với requirements sau [list], tổ chức thành:
  - Epic → Feature → User Story hierarchy
  - Đánh dấu dependencies
  - Phân loại theo business domain: [domain list]"
```

#### Phân Tích Gap

```bash
# So sánh AS-IS vs TO-BE
/ck:brainstorm "quy trình hiện tại (AS-IS) của nhắc nhở nợ quá hạn:
  [mô tả quy trình thủ công]
  
  Tôi muốn tự động hóa. Phân tích:
  - Gap giữa AS-IS và TO-BE
  - Pain points hiện tại
  - Quick wins có thể làm ngay
  - Rủi ro khi chuyển đổi"
```

#### Process Mapping

```bash
# Tạo BPMN-style process flow
/ck:mermaidjs-v11 "flowchart quy trình xử lý khoản vay quá hạn:
  Phát hiện quá hạn → Phân loại (1-30 ngày / 30-90 ngày / >90 ngày)
  → Giao cán bộ → Liên hệ khách hàng → Ghi nhận kết quả
  → Cập nhật hệ thống → Escalate nếu không liên hệ được"

# Tạo Use Case diagram
/ck:mermaidjs-v11 "sequence diagram của quy trình phê duyệt tái cơ cấu nợ:
  BA/CBTD → Trưởng phòng → Ban tín dụng → Core Banking"
```

#### Data Analysis & Modeling

```bash
# Thiết kế data model cho nghiệp vụ
/ck:ask "thiết kế data model cho module quản lý khoản vay:
  Entities: KhoanVay, KhachHang, LichSuThanhToan, CanhBao
  Relationships và business rules của từng entity
  Output: ERD description + business rules"

# Tạo data dictionary
/ck:ask "tạo data dictionary cho entity KhoanVay trong hệ thống quản lý sau vay:
  Fields: MaKhoanVay, SoTienGoc, LaiSuat, NgayGiaiNgan, KyHanThang...
  Bao gồm: definition, data type, constraints, business rules, examples"
```

### 3.2 Tạo Tài Liệu Đặc Tả

```bash
# Tạo SRS (Software Requirements Specification)
/ck:plan "viết Software Requirements Specification cho module Quản lý Khoản Vay:
  Sections: Introduction, Overall Description, Functional Requirements,
  Non-functional Requirements, External Interface Requirements, Constraints.
  Format: markdown, chi tiết, có diagram references"

# Viết từng section
/ck:cook plans/xxx/plan.md
```

```bash
# Tạo Use Case Specification
/ck:ask "viết Use Case Specification đầy đủ cho UC-001: Tạo Nhắc Nhở Tự Động:
  Sections: Brief Description, Actors, Preconditions, Main Flow,
  Alternative Flows, Exception Flows, Postconditions, Business Rules"
```

### 3.3 Test Cases Nghiệp Vụ

```bash
# Tạo test scenarios từ user stories
/ck:ask "từ user story: 'As a CBTD, I want to receive alert khi khoản vay sắp đến hạn 30 ngày,
  so that I can proactively contact customer'
  
  Tạo:
  1. Happy path test cases (3-5 cases)
  2. Negative test cases (edge cases, boundary values)
  3. Business rule validation tests
  Format: Given-When-Then"
```

---

## 4. Role: System Analyst / Architect

### 4.1 Phân Tích Kiến Trúc Hệ Thống

```bash
# Đánh giá kiến trúc hiện tại
/ck:brainstorm "kiến trúc hệ thống QLSV hiện tại:
  - Monolith .NET Core
  - Oracle DB
  - Tích hợp T24 qua file FTP
  
  Đánh giá: điểm yếu, scalability issues, và đề xuất modernization path
  với trade-off rõ ràng (Monolith giữ nguyên vs Microservices vs Modular Monolith)"
```

```bash
# Nghiên cứu giải pháp kỹ thuật
/ck:research "event-driven architecture cho banking notification system,
  Apache Kafka vs RabbitMQ vs Azure Service Bus,
  so sánh cho banking context với compliance requirements"
```

```bash
# Thiết kế kiến trúc mới
/ck:plan "thiết kế kiến trúc tích hợp T24 Core Banking với hệ thống QLSV:
  Yêu cầu: near-realtime sync, retry mechanism, audit log, rollback capability
  Output: architecture decision record (ADR) với diagram"
```

```bash
# Tạo architecture diagram
/ck:mermaidjs-v11 "C4 Context diagram của hệ thống QLSV:
  Systems: QLSV App, T24 Core Banking, Email Gateway, SMS Gateway, Active Directory
  Users: CBTD, Kiểm soát viên, Ban lãnh đạo
  Flows chính"

/ck:excalidraw "system architecture diagram của QLSV với microservices approach"
```

### 4.2 Đánh Giá Công Nghệ

```bash
# So sánh công nghệ
/ck:ask "đánh giá công nghệ cho notification service trong banking:
  Options: Firebase FCM + Email / Apache Kafka + consumer / Azure Notification Hub
  Criteria: reliability, audit trail, compliance, cost, maintainability
  Context: on-premise deployment, team có .NET background"

# Tạo proof of concept plan
/ck:plan "POC: tích hợp T24 API trong 1 sprint (2 tuần):
  Goal: validate feasibility, identify technical risks
  Deliverables: POC code, findings report, go/no-go recommendation"
```

---

## 5. Role: Technical Writer / Documentation

### 5.1 Tạo Tài Liệu Kỹ Thuật

```bash
# Tạo API documentation
/ck:docs init

# Cập nhật sau khi có thay đổi
/ck:docs update

# Deploy documentation site
/ck:mintlify "tạo documentation site cho QLSV API:
  Sections: Getting Started, Authentication, Endpoints, Webhooks, Errors"
```

### 5.2 Tạo User Manual

```bash
# Viết hướng dẫn sử dụng
/ck:plan "viết User Manual cho module Quản lý Khoản Vay dành cho CBTD:
  Sections: Tổng quan, Đăng nhập, Tra cứu khoản vay, Xử lý nhắc nhở,
  Ghi nhận kết quả liên hệ, Báo cáo
  Format: markdown với screenshots placeholder, step-by-step"

/ck:cook plans/xxx/plan.md
```

```bash
# Tạo quick reference card
/ck:preview --html "quick reference card dạng A4 cho CBTD:
  Top 10 thao tác thường dùng nhất trong QLSV, với keyboard shortcuts"
```

---

## 6. Workflow Chung: Từ Ý Tưởng Đến Tài Liệu

### Template Workflow Phổ Quát

```
Bước 1: KHÁM PHÁ
  /ck:brainstorm "[vấn đề/ý tưởng]"
  /ck:research "[topic cần tìm hiểu]"

Bước 2: PHÂN TÍCH
  /ck:sequential-thinking "[phân tích từng bước]"
  /ck:ask "[câu hỏi chuyên môn cụ thể]"

Bước 3: LÊN KẾ HOẠCH
  /ck:plan "[mục tiêu, context, constraints]"

Bước 4: TẠO NỘI DUNG
  /ck:cook [plan-path]

Bước 5: VISUALIZATION
  /ck:mermaidjs-v11 "[diagram description]"
  /ck:preview --diagram/--slides/--html "[content]"

Bước 6: REVIEW & FINALIZE
  /ck:docs update
  /ck:journal
```

---

### Ví Dụ End-to-End: PM Lập Kế Hoạch Sprint

```bash
# 1. Thu thập yêu cầu từ product backlog
/ck:ask "tôi có backlog gồm 15 items sau [list]:
  Giúp tôi: estimate story points, group theo epic, suggest sprint goal
  cho Sprint 4 với velocity 40 points, team 4 người, 2 tuần"

# 2. Phân tích dependencies
/ck:sequential-thinking "với sprint backlog đã chọn:
  [list items]
  Tìm: technical dependencies, blocked items, critical path"

# 3. Tạo sprint plan
/ck:plan "Sprint 4 Plan: implement core notification system.
  Items: [US-1, US-2, US-3].
  Team: 2 BE dev, 1 FE dev, 1 QA.
  Definition of Done: code reviewed, tests passing, deployed to staging."

# 4. Tạo sprint board visual
/ck:preview --diagram "sprint 4 board với 3 swimlanes: To Do, In Progress, Done.
  Items per lane với assignee và story points"

# 5. Tạo daily standup template
/ck:ask "tạo daily standup template cho sprint 4,
  bao gồm: yesterday, today, blockers, sprint burndown cập nhật"
```

---

### Ví Dụ End-to-End: BA Phân Tích BRD Mới

```bash
# Input: BRD document từ business stakeholder

# Bước 1: Đọc và extract
/ck:sequential-thinking "phân tích BRD sau đây [paste nội dung BRD]:
  1. List tất cả functional requirements (FR)
  2. List non-functional requirements (NFR)  
  3. Identify ambiguities và assumptions
  4. Flag potential conflicts giữa requirements"

# Bước 2: Tạo câu hỏi clarification
/ck:ask "dựa trên phân tích BRD, tạo danh sách câu hỏi cần hỏi stakeholder,
  ưu tiên theo mức độ impact đến thiết kế hệ thống"

# Bước 3: Lên URD sau khi có answers
/ck:plan "viết URD cho module [X] từ BRD đã clarify:
  Personas: [list], User Stories: [số lượng estimated]
  Format: standard BA template với acceptance criteria"

/ck:cook plans/xxx/plan.md

# Bước 4: Process diagrams
/ck:mermaidjs-v11 "BPMN flow của [quy trình chính từ URD]"

# Bước 5: Sign-off package
/ck:preview --slides "URD Review Package cho stakeholder sign-off:
  Summary, Key Changes, Open Items, Next Steps"
```

---

## 7. Skills Hữu Ích Cho Non-Dev

### Nhóm Phân Tích

| Skill | Lệnh | Dùng khi |
|-------|------|---------|
| Brainstorm | `/ck:brainstorm` | Khám phá giải pháp, đánh giá trade-off |
| Research | `/ck:research` | Nghiên cứu quy định, best practice, công nghệ |
| Ask | `/ck:ask` | Câu hỏi chuyên môn cụ thể, cần expert opinion |
| Sequential Thinking | `/ck:sequential-thinking` | Phân tích step-by-step, vấn đề phức tạp |
| Scenario Planning | `/ck:ck-scenario` | What-if analysis, risk scenarios |
| Predict | `/ck:ck-predict` | Dự báo, trend analysis |

### Nhóm Lập Kế Hoạch

| Skill | Lệnh | Dùng khi |
|-------|------|---------|
| Plan | `/ck:plan` | Lên kế hoạch chi tiết với phases |
| Project Management | `/ck:project-management` | Theo dõi tiến độ, status reports |
| Plans Kanban | `/ck:plans-kanban` | Visual board của tất cả plans |
| Kanban | `/ck:kanban` | Tạo kanban board |
| Retro | `/ck:retro` | Retrospective meeting facilitation |

### Nhóm Visualization & Documentation

| Skill | Lệnh | Dùng khi |
|-------|------|---------|
| Preview | `/ck:preview --diagram` | Diagram, flowchart |
| Preview Slides | `/ck:preview --slides` | Presentation |
| Preview HTML | `/ck:preview --html` | Interactive visual |
| Mermaid | `/ck:mermaidjs-v11` | BPMN, sequence, ERD, mindmap |
| Excalidraw | `/ck:excalidraw` | Freeform whiteboard diagram |
| Docs | `/ck:docs` | Quản lý tài liệu dự án |
| Show Off | `/ck:show-off` | Demo page đẹp |
| Copywriting | `/ck:copywriting` | Viết content, email, presentation |

### Nhóm Tích Hợp Công Cụ

| Skill | Lệnh | Dùng khi |
|-------|------|---------|
| Git | `/ck:git` | Version control tài liệu |
| Mintlify | `/ck:mintlify` | Documentation website |
| Markdown Viewer | `/ck:markdown-novel-viewer` | Đọc tài liệu dài |
| Repomix | `/ck:repomix` | Tổng hợp codebase cho review |

---

## Tips Sử Dụng Hiệu Quả Cho Non-Dev

### 1. Cung Cấp Context Đầy Đủ

```bash
# Kém: quá mơ hồ
/ck:ask "làm sao quản lý dự án tốt?"

# Tốt: context rõ ràng
/ck:ask "tôi là PM ngân hàng, đang quản lý dự án tích hợp Core Banking 6 tháng,
  team 8 người, phương pháp Scrum.
  Vấn đề: team thường xuyên miss sprint goal vì dependency bên thứ ba.
  Cần: 3 actionable practices để cải thiện dependency management"
```

### 2. Paste Tài Liệu Thực Để Phân Tích

```bash
# ClaudeKit có thể đọc và phân tích tài liệu bạn paste vào
/ck:sequential-thinking "đây là meeting minutes từ cuộc họp với stakeholder:
  [paste nội dung]
  Hãy: extract action items, decisions made, open issues, next steps"
```

### 3. Yêu Cầu Format Cụ Thể

```bash
# Specify output format bạn cần
/ck:ask "... Output format: bảng markdown với columns: Risk, Likelihood (H/M/L), 
  Impact (H/M/L), Mitigation, Owner"

/ck:preview --slides "... Output: PowerPoint-style slide deck, 5-7 slides,
  executive audience, tiếng Việt"
```

### 4. Dùng Journal Để Ghi Lại Quyết Định

```bash
# Cuối ngày/sprint, ghi lại quyết định quan trọng
/ck:journal "sprint 4 retrospective:
  - Quyết định dùng Kafka thay RabbitMQ (reason: better at-least-once delivery)
  - Blocker: T24 API doc thiếu, giải quyết bằng cách contract với vendor
  - Next sprint focus: notification delivery"
```

---

*Xem thêm: `docs/claudekit-usage-guide.md` cho developer workflows | `docs/claudekit-skills-reference.md` cho danh sách đầy đủ skills*
