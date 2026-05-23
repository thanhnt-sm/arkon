# System Architecture & Data Flow

**Version:** 2.17.0  
**Last Updated:** 2026-05-14

## Architecture Overview

claudekit-engineer follows a **distributed agent architecture** where specialized agents operate independently and coordinate via async Task/SendMessage protocols. Unlike traditional monolithic systems, this is an **orchestration template** — users customize it for their project's actual architecture.

## High-Level Component Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                        Claude Code IDE                         │
│  (User Interface for Agent Orchestration & File Management)    │
└────────────────────────────────────────────────────────────────┘
                              ↓
                 ┌────────────────────────────┐
                 │   Session State Manager    │
                 │  (.claude/session-state/)  │
                 └────────────────────────────┘
                              ↓
        ┌─────────────────────────────────────────┐
        │    Task & Communication Router          │
        │  (Task/TaskCreate/SendMessage protocols)│
        └─────────────────────────────────────────┘
                         ↙    ↓    ↖
        ┌────────────┐  ┌──────────┐  ┌─────────────┐
        │ PLANNER    │  │ DEVELOPER│  │ TESTER      │
        │ (Opus)     │  │ (Opus)   │  │ (Haiku)     │
        └────────────┘  └──────────┘  └─────────────┘
             ↓                ↓               ↓
        ┌────────────────────────────────────────────┐
        │         Codebase & Documentation           │
        │    (./src, ./docs, ./plans, ./tests)      │
        └────────────────────────────────────────────┘
             ↓
        ┌────────────────────────────────────────────┐
        │      Development Rules & Standards         │
        │  (.claude/rules/*.md enforced by agents)  │
        └────────────────────────────────────────────┘
             ↓
        ┌────────────────────────────────────────────┐
        │         CI/CD Pipeline (GitHub Actions)    │
        │  (Linting, Testing, Build, Deploy)        │
        └────────────────────────────────────────────┘
```

## Agent Orchestration Layer

### Agent Roles & Responsibilities

**Command Layer** (Agents Invoked by User)
```
User: "/ck:plan Build authentication system"
    ↓
PLANNER Agent spawned
    ├─ Researches auth patterns
    ├─ Designs architecture
    ├─ Creates ./plans/{date}/plan.md
    └─ Awaits user approval
```

**Execution Layer** (Agents Working on Features)
```
User: "/ck:cook ./plans/date-feature/"
    ↓
DEVELOPER Agent spawned
    ├─ Reads plan phases
    ├─ Implements code per phase
    ├─ Commits to git
    └─ Signals TESTER via Task
```

**Verification Layer** (Quality Assurance)
```
TESTER Agent triggered by DEVELOPER
    ├─ Runs test suite
    ├─ Checks coverage (>80%)
    ├─ Reports pass/fail
    └─ Triggers CODE-REVIEWER on pass
```

**Integration Layer** (Final Steps)
```
CODE-REVIEWER → approves → DOCS-MANAGER
                              ├─ Updates docs
                              ├─ Updates roadmap
                              └─ Merges to main
```

### Agent Communication Patterns

**Sequential (Blocking)**
```
PLANNER → DEVELOPER → TESTER → CODE-REVIEWER → DOCS-MANAGER
  ↓          ↓          ↓          ↓              ↓
Plan     Implement   Verify    Approve       Document
```

**Parallel (Non-Blocking)**
```
User Request
    ↓
RESEARCHER #1        RESEARCHER #2        RESEARCHER #3
  (Database)           (Auth)               (API Design)
    ↓                   ↓                    ↓
Report 1           Report 2              Report 3
    ↓
PLANNER synthesizes reports → creates comprehensive plan
```

**Async Coordination**
```
DEVELOPER creates PR
    ↓
CODE-REVIEWER reviews (may take hours)
    ↓
DEVELOPER fixes issues (independent of reviewer)
    ↓
CODE-REVIEWER approves when ready
    ↓
DOCS-MANAGER updates docs (doesn't block deployment)
```

## Data Flow

### Feature Implementation Data Flow

```
1. Planning Phase
   User Request → PLANNER reads: CLAUDE.md, rules/*, docs/* 
                     ↓
                  Creates: ./plans/{date}/
                     - plan.md (YAML frontmatter + phases)
                     - phase-01-*.md
                     - phase-02-*.md
                     - ...
                     - reports/

2. Development Phase
   DEVELOPER reads: ./plans/{date}/plan.md
                     ↓
                  Implements code per phase
                     ↓
                  Outputs: Modified src/ files, commits to git
                     ↓
                  Task: "Testing required for feat/auth"

3. Testing Phase
   TESTER reads: code changes, test files
                     ↓
                  Runs: `npm test`, coverage analysis
                     ↓
                  Reports: Pass/fail, coverage %, failures
                     ↓
                  Task: "Code review approved" or "Fix tests"

4. Review Phase
   CODE-REVIEWER reads: PR changes, test results
                     ↓
                  Reviews: Code style, security, best practices
                     ↓
                  Reports: Approved / Request Changes
                     ↓
                  Task: "Merge approved" or "Address feedback"

5. Documentation Phase
   DOCS-MANAGER reads: Code changes, updated docs
                     ↓
                  Updates: ./docs/* files
                     ↓
                  Syncs: Changelog, roadmap, architecture
                     ↓
                  Task: "Docs merged, feature complete"

6. CI/CD Phase (Automated)
   GitHub Actions reads: .github/workflows/
                     ↓
                  Runs: Linting, tests, build, deploy
                     ↓
                  Updates: Notifications (Slack, Discord)
                     ↓
                  Result: Release created or deployment failed
```

### Documentation Sync Data Flow

```
Code Change
    ↓
docs-manager agent invoked
    ↓
Reads: Updated code, .env.example, package.json
    ↓
Generates: ./docs/codebase-summary.md (via repomix)
    ↓
Updates: ./docs/project-overview-pdr.md (requirements)
         ./docs/code-standards.md (examples)
         ./docs/system-architecture.md (diagrams)
    ↓
Updates: ./docs/development-roadmap.md (progress)
         ./docs/project-changelog.md (release notes)
    ↓
Verifies: All links exist, code examples compile
    ↓
Commits: git commit -m "docs: sync with code changes"
```

## Configuration & State Management

### Session State Flow

```
Session Start
    ↓
session-init.cjs hook runs
    ├─ Initializes: .claude/session-state/
    ├─ Loads: .env, settings.json
    ├─ Sets: current plan context (if any)
    └─ Caches: file metadata, recent commands

Agent Spawned (Subagent)
    ↓
subagent-init.cjs hook runs
    ├─ Injects: Work context, reports path, plans path
    ├─ Reads: CLAUDE.md, .claude/rules/*
    ├─ Loads: Agent definition from .claude/agents/{name}.md
    └─ Initializes: Agent memory (if persistent)

Agent Completes
    ↓
session-state.cjs hook runs
    ├─ Saves: Session telemetry
    ├─ Updates: Task status via Task tool
    ├─ Clears: Temporary state
    └─ Caches: Command history for analytics
```

### Configuration Sources (Precedence)

```
1. Environment Variables (.env)
   └─ API keys, deployment targets, secrets

2. .claude/rules/*.md
   └─ Development standards, workflow rules

3. .claude/agents/{name}.md
   └─ Agent-specific instructions & capabilities

4. ./docs/*
   └─ Project-specific conventions & patterns

5. .claude/settings.json
   └─ Global Claude Code hooks & UI settings

6. CLAUDE.md
   └─ Project root instructions
```

## Deployment Architecture

### Local Development
```
Developer machine
    ↓
.env configured locally
    ↓
Git worktree or feature branch
    ↓
Agents implement & test locally
    ↓
Push to remote, create PR
```

### CI/CD Pipeline
```
.github/workflows/ files run on every push
    ├─ npm run lint
    ├─ npm run test
    ├─ npm run build
    └─ Deploy to staging (if tests pass)

Manual deploy to production (after approval)
    ├─ Tag release (semantic versioning)
    ├─ Update CHANGELOG.md
    ├─ Deploy to production
    └─ Notify team (Discord, Slack)
```

## Storage & File Organization

### Documentation Storage
```
./docs/
├── project-overview-pdr.md        (50-150 lines)
├── code-standards.md               (50-150 lines)
├── codebase-summary.md             (100-150 lines)
├── system-architecture.md          (100-150 lines)
├── design-guidelines.md            (50-100 lines)
├── deployment-guide.md             (50-100 lines)
├── project-roadmap.md              (50-100 lines)
├── development-roadmap.md          (living, updated weekly)
└── project-changelog.md            (grows over time)

Max 800 lines per file; split if exceeding.
```

### Plan Storage
```
./plans/
├── {date}-{slug}/
│   ├── plan.md                     (overview, <80 lines)
│   ├── phase-01-research.md        (requirements, findings)
│   ├── phase-02-architecture.md    (design, data flows)
│   ├── phase-03-implementation.md  (steps, code changes)
│   ├── phase-04-testing.md         (test cases, coverage)
│   ├── phase-05-documentation.md   (docs updates)
│   ├── reports/
│   │   ├── researcher-1-report.md
│   │   ├── researcher-2-report.md
│   │   └── code-reviewer-report.md
│   └── visuals/
│       ├── architecture-diagram.mmd
│       └── data-flow-diagram.mmd

One plan per feature/epic; archive when complete.
```

### Agent Memory Storage
```
./.claude/agent-memory/
├── planner-MEMORY.md               (persistent learnings)
├── developer-MEMORY.md
├── tester-MEMORY.md
└── ...

Limited to 200 lines per agent; stores project conventions.
```

## Security & Access Control

### Data Isolation
- **Secrets**: Stored in `.env` (not committed)
- **Config**: `.env.example` template in git
- **Sensitive Docs**: Can be marked private (outside git)
- **Team Access**: Via file ownership rules (team-coordination-rules.md)

### Git & Code Review
- **Commits**: Must pass linting & tests
- **PRs**: Require code review before merge
- **Secrets Scanning**: Pre-commit hooks check for leaked keys
- **Audit Trail**: All commits logged with author, timestamp

### Agent Permissions
- **Agents read**: Code, docs, plans, configuration
- **Agents write**: Code, docs, plans (per task permissions)
- **Agents execute**: Linting, tests, builds (sandboxed)
- **Agents cannot**: Modify .claude/rules/, delete repositories

## Performance Characteristics

### Latency
```
Planning phase:      15-30 min (research + architecture)
Development phase:   1-4 hrs (depends on complexity)
Testing phase:       5-15 min (automated test execution)
Review phase:        30 min - 2 hrs (code review queue)
Documentation:       10-20 min (doc updates)
Total (feature):     ~4-8 hrs per feature
```

### Throughput
- **Single agent**: 1-2 features/week
- **3 agents parallel**: 3-6 features/week
- **10 agents (teams)**: 10-20 features/week (with coordination overhead)

### Storage
```
.claude/: ~5 MB (templates, configs, scripts)
docs/: Grows ~100 KB/major release
plans/: ~1 MB per 20 completed plans
Codebase (user's src/): Varies

Git history: Plan on 100 MB / year for small team
```

## Scalability Limits

### Single Developer
- **Supported**: Yes (straightforward workflow)
- **Limit**: Mental context; ~2-3 concurrent features

### Small Team (3-5)
- **Supported**: Yes (async coordination via Tasks)
- **Limit**: File conflicts; recommend worktrees for independence

### Large Team (10+)
- **Challenges**: 
  - Coordination overhead increases
  - Shared .claude/rules/ may become contentious
  - Plan dependencies harder to track
- **Mitigations**:
  - Split into multiple repositories per domain
  - Extend team-coordination-rules.md
  - Create cross-team oversight agents
  - Implement regular sync meetings (despite async design)

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Orchestration** | Claude Code IDE | Agent execution environment |
| **Agent Framework** | ClaudeKit (custom) | Task/SendMessage protocols |
| **Configuration** | YAML (frontmatter), Markdown, JSON | Settings, plans, rules |
| **Automation** | Node.js scripts (.cjs files) | Hooks, utilities |
| **VCS** | Git | Version control |
| **CI/CD** | GitHub Actions (user-configured) | Testing, deployment |
| **Notifications** | Discord/Slack/Telegram (optional) | Team alerts |
| **Documentation** | Markdown + Mermaid | Living docs |

## Related Documentation

- **[Project Overview & PDR](./project-overview-pdr.md)** — Requirements, success metrics
- **[Code Standards](./code-standards.md)** — Implementation patterns, security checklist
- **[Codebase Summary](./codebase-summary.md)** — Components, modules, architecture overview
- **[Development Roadmap](./development-roadmap.md)** — Phases, timeline, progress tracking
