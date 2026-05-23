# ClaudeKit — Tham Chiếu Skills Đầy Đủ

> Quick reference: 77+ skills, cách dùng, khi nào dùng, kết hợp gì.

---

## Nhóm Core Workflow

| Skill | Lệnh | Mô tả | Flags quan trọng |
|-------|------|--------|-----------------|
| **Plan** | `/ck:plan "..."` | Lên kế hoạch chi tiết với phases | `--fast` `--hard` `--parallel` `--tdd` `--two` |
| **Cook** | `/ck:cook <path>` | Implement theo plan | `--fast` `--parallel` `--auto` `--no-test` `--tdd` |
| **Test** | `/ck:test` | Chạy tests, coverage | `ui` (UI testing) |
| **Code Review** | `/ck:code-review` | Review adversarial | `--pending` `codebase` `codebase parallel` `#PR` `<hash>` |
| **Ship** | `/ck:ship` | Full shipping pipeline | — |
| **Fix** | `/ck:fix "..."` | Sửa bug có root cause | `--auto` `--review` `--quick` `--parallel` |
| **Journal** | `/ck:journal` | Ghi nhật ký kỹ thuật | — |
| **Scout** | `/ck:scout "..."` | Tìm kiếm trong codebase | `ext` (dùng Gemini) |
| **Debug** | `/ck:ck-debug "..."` | Debug có root cause | — |
| **Simplify** | `/ck:simplify` | Đơn giản hóa code | — |

---

## Nhóm Research & Analysis

| Skill | Lệnh | Mô tả | Best for |
|-------|------|--------|---------|
| **Research** | `/ck:research "topic"` | Nghiên cứu kỹ thuật toàn diện | Library comparison, best practices, migration guides |
| **Brainstorm** | `/ck:brainstorm "..."` | Phân tích trade-off, đề xuất giải pháp | Architecture decisions, feature design, problem solving |
| **Ask** | `/ck:ask "question"` | Expert consultation | Specific technical questions, design decisions |
| **Sequential Thinking** | `/ck:sequential-thinking "..."` | Phân tích step-by-step | Complex problems, debugging, planning |
| **Problem Solving** | `/ck:problem-solving "..."` | Framework giải quyết vấn đề | Khi stuck, nhiều hypothesis thất bại |
| **Scenario** | `/ck:ck-scenario "..."` | What-if analysis | Risk assessment, contingency planning |
| **Predict** | `/ck:ck-predict "..."` | Dự báo | Trend analysis, capacity planning |
| **Autoresearch** | `/ck:ck-autoresearch "..."` | Auto research với iterations | Deep technical research |

---

## Nhóm Frontend

| Skill | Lệnh | Mô tả |
|-------|------|--------|
| **Frontend Dev** | `/ck:frontend-development "..."` | React/TypeScript components |
| **UI Styling** | `/ck:ui-styling "..."` | shadcn/ui, Tailwind CSS |
| **UI/UX Pro Max** | `/ck:ui-ux-pro-max "..."` | Full UI/UX design intelligence (50+ styles, 161 palettes) |
| **Frontend Design** | `/ck:frontend-design "..."` | Replicate UI mockups |
| **React Best Practices** | `/ck:react-best-practices "..."` | React patterns, hooks, performance |
| **Web Frameworks** | `/ck:web-frameworks "..."` | Next.js, Nuxt, Remix |
| **TanStack** | `/ck:tanstack "..."` | TanStack Start, Form, AI |
| **Web Design Guidelines** | `/ck:web-design-guidelines` | Audit UI vs best practices |
| **Three.js** | `/ck:threejs "..."` | 3D WebGL |
| **Shader** | `/ck:shader "..."` | GLSL shaders |
| **Remotion** | `/ck:remotion "..."` | Programmatic video |

---

## Nhóm Backend

| Skill | Lệnh | Mô tả |
|-------|------|--------|
| **Backend Dev** | `/ck:backend-development "..."` | NestJS, FastAPI, Django APIs |
| **Databases** | `/ck:databases "..."` | MongoDB, PostgreSQL schema & queries |
| **Better Auth** | `/ck:better-auth "..."` | OAuth, JWT, passkey authentication |
| **Payment Integration** | `/ck:payment-integration "..."` | Stripe, Polar, SePay |
| **Shopify** | `/ck:shopify "..."` | Shopify app development |

---

## Nhóm Infrastructure & DevOps

| Skill | Lệnh | Mô tả |
|-------|------|--------|
| **Deploy** | `/ck:deploy` | Auto-detect & deploy (Vercel, Netlify, Cloudflare, GCP, AWS...) |
| **DevOps** | `/ck:devops "..."` | Docker, Kubernetes, CI/CD |
| **Git** | `/ck:git "..."` | Git workflows, commits, PRs |
| **Worktree** | `/ck:worktree "..."` | Git worktree management |

---

## Nhóm Security

| Skill | Lệnh | Mô tả |
|-------|------|--------|
| **CK Security** | `/ck:ck-security` | STRIDE + OWASP audit, optional auto-fix |
| **Security Scan** | `/ck:security-scan` | Scan secrets & vulnerabilities |
| **CTI Expert** | `/ck:cti-expert "..."` | Cybersecurity threat intelligence |

---

## Nhóm AI & LLM

| Skill | Lệnh | Mô tả |
|-------|------|--------|
| **Context Engineering** | `/ck:context-engineering "..."` | Optimize LLM context, prompts |
| **LLMs** | `/ck:llms "..."` | llms.txt, LLM context management |
| **AI Multimodal** | `/ck:ai-multimodal "..."` | Image, video, document analysis |
| **Google ADK Python** | `/ck:google-adk-python "..."` | Google Agent Development Kit |
| **AI Artist** | `/ck:ai-artist "..."` | AI image generation |

---

## Nhóm Mobile

| Skill | Lệnh | Mô tả |
|-------|------|--------|
| **Mobile Development** | `/ck:mobile-development "..."` | React Native, Flutter, SwiftUI |

---

## Nhóm Documentation & Visualization

| Skill | Lệnh | Mô tả | Flags |
|-------|------|--------|-------|
| **Docs** | `/ck:docs` | Manage project docs | `init` `update` `summarize` |
| **Preview** | `/ck:preview "..."` | Visual output | `--explain` `--diagram` `--slides` `--html` |
| **Mermaid** | `/ck:mermaidjs-v11 "..."` | Mermaid v11 diagrams (flowchart, sequence, ERD, mindmap...) | — |
| **Excalidraw** | `/ck:excalidraw "..."` | Freeform whiteboard | — |
| **Mintlify** | `/ck:mintlify "..."` | Documentation website | — |
| **Show Off** | `/ck:show-off "..."` | Self-contained HTML showcase | — |
| **Markdown Viewer** | `/ck:markdown-novel-viewer "..."` | View long markdown docs | — |
| **Graphify** | `/ck:graphify "..."` | Data visualization | — |

---

## Nhóm Project & Team Management

| Skill | Lệnh | Mô tả |
|-------|------|--------|
| **Project Management** | `/ck:project-management "..."` | Status tracking, reports, task coordination |
| **Plans Kanban** | `/ck:plans-kanban` | Visual kanban của tất cả plans |
| **Kanban** | `/ck:kanban "..."` | Tạo kanban board |
| **Retro** | `/ck:retro "..."` | Retrospective facilitation |
| **Team** | `/ck:team "..."` | Multi-agent team coordination |
| **Loop** | `/ck:ck-loop "..."` | Recurring task execution |

---

## Nhóm Testing

| Skill | Lệnh | Mô tả |
|-------|------|--------|
| **Test** | `/ck:test` | Unit/integration/e2e tests, coverage |
| **Web Testing** | `/ck:web-testing "..."` | Playwright, k6, accessibility |
| **Chrome DevTools** | `/ck:chrome-devtools "..."` | Browser automation |
| **Agent Browser** | `/ck:agent-browser "..."` | Autonomous browser testing |

---

## Nhóm MCP & Tools

| Skill | Lệnh | Mô tả |
|-------|------|--------|
| **MCP Builder** | `/ck:mcp-builder "..."` | Tạo MCP server mới |
| **MCP Management** | `/ck:mcp-management "..."` | Discover & manage MCPs |
| **Use MCP** | `/ck:use-mcp "..."` | Execute MCP tools |
| **Repomix** | `/ck:repomix "..."` | Codebase dump cho LLM review |
| **Agentize** | `/ck:agentize "..."` | Tạo agent từ skill |
| **Skill Creator** | `/ck:skill-creator "..."` | Tạo custom skill mới |
| **Find Skills** | `/ck:find-skills "..."` | Tìm skill phù hợp cho task |
| **Coding Level** | `/ck:coding-level <0-5>` | Đổi coding level |

---

## Nhóm Content & Design

| Skill | Lệnh | Mô tả |
|-------|------|--------|
| **Copywriting** | `/ck:copywriting "..."` | Conversion copy, headlines, email |
| **Design** | `/ck:design "..."` | Brand identity, logos, banners |
| **Stitch** | `/ck:stitch "..."` | AI design generation |
| **Media Processing** | `/ck:media-processing "..."` | FFmpeg, ImageMagick |
| **Bootstrap** | `/ck:bootstrap "..."` | Bootstrap project mới | 

---

## Nhóm Đặc Biệt

| Skill | Lệnh | Mô tả |
|-------|------|--------|
| **Bootstrap** | `/ck:bootstrap "..."` | Full project bootstrap (research → design → plan → code) |
| **GKG** | `/ck:gkg "..."` | Semantic code analysis (GitLab Knowledge Graph) |
| **XIA** | `/ck:xia "..."` | Extended intelligence analysis |
| **Watzup** | `/ck:watzup "..."` | WhatsApp integration |

---

## Kết Hợp Skills Theo Use Case

### Use Case: Tính Năng Phức Tạp
```
/ck:brainstorm → /ck:research → /ck:plan --hard → /ck:cook → /ck:test → /ck:code-review → /ck:ck-security → /ck:ship → /ck:journal
```

### Use Case: Bug Production Khẩn Cấp
```
/ck:scout → /ck:ck-debug → /ck:fix --review → /ck:test → /ck:code-review --pending → /ck:ship
```

### Use Case: Security Audit Định Kỳ
```
/ck:ck-security → /ck:security-scan → /ck:code-review codebase → (fix nếu cần) → /ck:journal
```

### Use Case: Onboard Codebase Mới
```
/ck:scout "toàn bộ project" → /ck:docs summarize → /ck:ask "explain architecture" → /ck:preview --diagram "architecture overview"
```

### Use Case: Deploy
```
/ck:test → /ck:code-review --pending → /ck:ck-security → /ck:deploy → /ck:journal
```

### Use Case: Phân Tích Nghiệp Vụ (PM/BA)
```
/ck:brainstorm → /ck:research → /ck:sequential-thinking → /ck:plan → /ck:cook → /ck:mermaidjs-v11 → /ck:preview --slides → /ck:docs update
```

### Use Case: Bootstrap Project Mới
```
/ck:bootstrap "..." → /ck:ck-security → /ck:docs init → /ck:journal
```

---

## Agents Được Spawn Tự Động

> Bạn không gọi trực tiếp — skills tự spawn khi cần.

| Agent | Model | Spawn bởi | Vai trò |
|-------|-------|-----------|---------|
| `planner` | opus | ck-plan, cook | Kiến trúc, lên kế hoạch |
| `researcher` | sonnet | cook, fix | Nghiên cứu kỹ thuật |
| `fullstack-developer` | sonnet | cook | Implement code |
| `tester` | sonnet | cook, fix | Chạy tests |
| `code-reviewer` | sonnet | code-review | Audit code |
| `debugger` | sonnet | fix, ck-debug | Root cause analysis |
| `code-simplifier` | sonnet | simplify | Đơn giản hóa |
| `docs-manager` | sonnet | cook, fix | Cập nhật docs |
| `project-manager` | sonnet | cook | Sync tasks, progress |
| `git-manager` | sonnet | ship, cook | Git commits, PRs |
| `journal-writer` | sonnet | journal | Ghi journal entry |
| `mcp-manager` | sonnet | use-mcp | MCP discovery |
| `brainstormer` | sonnet | brainstorm | Ideation |
| `ui-ux-designer` | sonnet | cook (frontend) | UI/UX guidance |

---

*Cập nhật: 2026-05 | Framework version: 2.17.0*
