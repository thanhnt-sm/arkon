# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (60-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk go test             # Go test failures only (90%)
rtk jest                # Jest failures only (99.5%)
rtk vitest              # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk pytest              # Python test failures only (90%)
rtk rake test           # Ruby test failures only (90%)
rtk rspec               # RSpec test failures only (60%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%)
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->

---

# Arkon — Development Guide

Arkon is a self-hosted enterprise knowledge management platform that compiles organizational documents into a structured wiki and serves it to LLMs via MCP (Model Context Protocol).

## Development Commands

### Backend (Python / FastAPI)

```bash
# Install
pip install -e ".[dev]"

# Run API server (port 5055)
uvicorn app.main:app --host 0.0.0.0 --port 5055 --reload

# Run background workers (two separate processes required)
python -m arq app.worker.WorkerSettings          # Wiki compilation worker
python -m arq app.worker.SkillWorkerSettings     # Skills processing worker

# Database migrations
alembic upgrade head                             # Apply all migrations
alembic revision --autogenerate -m "description" # Generate new migration
alembic downgrade -1                             # Roll back one migration

# Lint
ruff check app/                                  # Check linting issues
ruff check app/ --fix                            # Auto-fix safe issues
ruff format app/                                 # Format code

# Tests
rtk pytest tests/                               # Run all tests
rtk pytest tests/path/test_file.py::test_name  # Run single test
```

### Frontend (Next.js / React)

```bash
cd frontend
npm install
npm run dev        # Dev server at http://localhost:3000
npm run build      # Production build
npm run lint       # ESLint check
```

### Docker (Full Stack)

```bash
# Start all 7 services (postgres, redis, minio, squid, api, worker, worker_skills, frontend)
docker compose --env-file .env.docker up -d --build

# View logs for a specific service
rtk docker logs arkon-api
rtk docker logs arkon-worker
```

### Environment Setup

Copy the appropriate env file and configure it before running:
- **Docker:** `.env.docker.example` → `.env.docker`
- **Local dev:** `.env.local.example` → `.env.local`

Required: `SECRET_KEY`, `DATABASE_URL`, `REDIS_HOST`, `MINIO_*`, `DEFAULT_ADMIN_EMAIL/PASSWORD`.

## Architecture

### System Overview

```
Frontend (Next.js :3000) ─── REST API ──► FastAPI (:5055)
                                              │
Claude Desktop ──────────── MCP (/mcp) ──────┤
                                              │
                          ┌───────────────────┤
                          ▼                   ▼
                       PostgreSQL         Redis Queue
                       (pgvector)              │
                          │            ┌───────┴──────────┐
                       MinIO          Wiki Worker    Skills Worker
                       (files)        (MRP pipeline) (skill processing)
```

### Key Backend Modules

**`app/ai/`** — All LLM integration lives here.
- `mrp/` — The **MRP pipeline** (Map → Reduce → Plan-review → Refine → Verify → Commit): the core document-to-wiki compilation engine. Each phase is a separate step run by the wiki worker.
- `llm_catalog.py` / `embedding_catalog.py` — Provider-agnostic model registries (Anthropic, Google, OpenAI). Configured at runtime via admin settings, not hardcoded.
- `wiki_compiler.py` — Orchestrates MRP phases; determines whether to create a new wiki page or merge into an existing one.

**`app/worker.py`** — Arq-based background workers. Two separate `WorkerSettings` classes: `WorkerSettings` (wiki jobs) and `SkillWorkerSettings` (skill processing). Jobs are enqueued from API routers and consumed here.

**`app/routers/`** — FastAPI routers, one file per domain. `wiki_drafts.py` handles the propose → review → approve workflow; `sources.py` handles document upload and ingestion triggering.

**`app/services/permission_engine.py`** — RBAC enforcement. Permissions are evaluated against a hierarchy: role → department → project → knowledge type. All wiki reads and writes pass through this engine.

**`app/mcp/`** — FastMCP server mounted at `/mcp`. `tools.py` exposes `search_wiki`, `read_wiki_page`, `propose_wiki_edit`, etc. Access is gated by MCP tokens (scoped, not full user auth).

**`app/database/models.py`** — SQLAlchemy 2.0 async ORM. Key models: `WikiPage` (content + pgvector embedding), `Source` (uploaded documents), `Project`, `Department`, `KnowledgeType`, `MCPToken`, `AuditLog`.

### Data Flow: Document → Wiki Page

1. Admin uploads a document via the frontend (stored in MinIO via `app/services/storage_service.py`)
2. Upload triggers a wiki compilation job enqueued to Redis
3. Wiki Worker picks up the job and runs the MRP pipeline (`app/ai/mrp/`)
4. Each MRP phase calls the configured LLM; the Plan-review phase decides whether to create a new page or merge into an existing one
5. The final `WikiPage` is written to PostgreSQL with a pgvector embedding for semantic search
6. All changes are recorded in `AuditLog`

### Frontend Structure

Next.js 16 App Router with React 19. Pages in `frontend/src/app/`, reusable UI in `frontend/src/components/`. Components follow shadcn conventions with Tailwind CSS 4. API calls use typed fetch wrappers in `frontend/src/lib/`.

---

# Arkon MCP — Knowledge Base Access

Arkon exposes a FastMCP server for Claude Desktop and Claude Code to query the enterprise knowledge base.

## Setup (Claude Desktop)

```json
{
  "mcpServers": {
    "arkon": {
      "url": "http://localhost:8000/mcp",
      "headers": { "Authorization": "Bearer <your-mcp-token>" }
    }
  }
}
```

Get a token from an Arkon admin. Tokens are scoped to specific knowledge types — what you can read depends on your token.

## Skills

| Skill | Trigger | Role needed |
|-------|---------|------------|
| `/arkon-query` | "what do we know about X", "find in KB", "query:" | Any (scoped by token) |
| `/arkon-edit` | "update wiki", "propose edit", "fix this page" | Contributor+ |
| `/arkon-review` | "review drafts", "approve draft", "check queue" | Editor/Admin |

Skills live in `skills/`. Claude Code picks them up automatically when working in this repo.

## Key Principles

- **Wiki first, sources second.** `search_wiki` → `read_wiki_page` → source drill-down only for precise citations.
- **Your token is your scope.** RBAC is enforced server-side; "access denied" means contact an admin.
- **Always confirm before writing.** `propose_wiki_edit` and `edit_wiki_page` modify the live KB — get user approval first.
