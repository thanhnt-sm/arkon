# Codebase Summary & Architecture Overview

**Version:** 2.17.0  
**Last Updated:** 2026-05-14  
**Type:** Boilerplate Template

## Project Overview

**claudekit-engineer** is a comprehensive orchestration boilerplate for Claude Code development workflows. It provides:

- Pre-configured agent definitions (14 specialized agents)
- Development rules and standards enforcement
- Workflow automation via hooks and scripts
- Documentation and planning infrastructure
- Team collaboration tools and protocols

This is a **template project** — users fork/customize it for their specific needs.

## High-Level Architecture

```
claudekit-engineer/
├── .claude/                  # ClaudeKit Configuration & Orchestration
│   ├── agents/              # Agent role definitions (14 files)
│   ├── rules/               # Development standards (7 files)
│   ├── hooks/               # Session/tool-use automation
│   ├── skills/              # Extended AI skill packages
│   ├── scripts/             # Utility automation scripts
│   ├── settings.json        # Global Claude Code settings
│   └── metadata.json        # Project metadata & version
├── .github/workflows/       # CI/CD pipelines (users add)
├── docs/                    # Living documentation (9 core files)
├── plans/                   # Implementation plans & tracking
├── CLAUDE.md                # Project-level instructions
└── .env.example             # Configuration template
```

## Key Components

### 1. Agent Ecosystem (.claude/agents/)

**14 Specialized Agents** orchestrate development:

| Agent | Role | Model | Purpose |
|-------|------|-------|---------|
| `planner.md` | Tech Lead | Opus | Research, architecture, planning |
| `code-reviewer.md` | Code Reviewer | Opus | Quality assurance, best practices |
| `tester.md` | QA Lead | Haiku | Test execution, coverage analysis |
| `debugger.md` | Debug Specialist | Haiku | Investigation, root-cause analysis |
| `docs-manager.md` | Technical Writer | Haiku | Documentation, PDRs, standards |
| `fullstack-developer.md` | Developer | Opus | Feature implementation |
| `researcher.md` | Researcher | Haiku | Technical research, analysis |
| `brainstormer.md` | Strategist | Opus | Solution exploration, alternatives |
| `code-simplifier.md` | Optimizer | Haiku | Complexity reduction, refactoring |
| `ui-ux-designer.md` | Designer | Opus | UI/UX design, prototyping |
| `journal-writer.md` | Historian | Haiku | Decision logging, lessons learned |
| `project-manager.md` | PM | Haiku | Roadmap, milestones, tracking |
| `git-manager.md` | Git Lead | Haiku | Version control coordination |
| `mcp-manager.md` | MCP Admin | Haiku | Model Context Protocol tools |

**Workflows:**
- **Sequential**: Plan → Code → Test → Review → Docs
- **Parallel**: Multiple agents on independent tasks
- **Chain**: Outputs from one agent feed next agent's input

### 2. Development Rules (.claude/rules/)

**7 enforced rule files** guide all development:

| File | Purpose |
|------|---------|
| `primary-workflow.md` | Code → Testing → Review → Integration → Debugging |
| `development-rules.md` | Coding standards, file sizing, code quality |
| `documentation-management.md` | Docs structure, roadmap updates, changelog maintenance |
| `orchestration-protocol.md` | Agent delegation, context isolation, task chaining |
| `skill-domain-routing.md` | When to use which skill (frontend, backend, deployment, etc.) |
| `skill-workflow-routing.md` | Skill sequencing (plan → cook → test → review) |
| `team-coordination-rules.md` | File ownership, git safety, async communication (when in team mode) |

**Key Principles:**
- YAGNI, KISS, DRY
- Evidence-based documentation (verify code before documenting)
- Test-first development (tests validate simplified code)
- Continuous integration (linting, tests, docs required before merge)

### 3. Documentation System (./docs/)

**Core Documentation Files** (800 lines max each):

| File | Purpose | Users |
|------|---------|-------|
| `project-overview-pdr.md` | Requirements, scope, success metrics | PMs, architects |
| `code-standards.md` | Coding conventions, anti-patterns, review checklists | All developers |
| `codebase-summary.md` | Architecture, components, module map (this file) | New devs, reviewers |
| `system-architecture.md` | Data flows, component interactions, deployment | Architects |
| `design-guidelines.md` | UI/UX patterns, accessibility, design systems | Frontend developers |
| `deployment-guide.md` | Environment setup, CI/CD, release process | DevOps, release lead |
| `project-roadmap.md` | Phases, milestones, release plan | PMs, all team |
| `development-roadmap.md` | Living roadmap with status, metrics | Team leads |
| `project-changelog.md` | Features, fixes, breaking changes (chronological) | Users, release notes |

**Documentation Philosophy:**
- Living documents synced with codebase reality
- Generated codebase summaries from `repomix` output
- Links verified to exist
- Code examples guaranteed to compile
- No TODO markers; remove stale sections entirely

### 4. Hooks & Automation (.claude/hooks/)

**Session-aware automation** triggered at key points:

| Hook | Trigger | Purpose |
|------|---------|---------|
| `session-init.cjs` | Session start | Initialize session state |
| `subagent-init.cjs` | Subagent spawn | Inject context, set permissions |
| `team-context-inject.cjs` | Subagent spawn | Add team collaboration data |
| `scout-block.cjs` | Pre-glob/grep | Prevent overly broad searches |
| `privacy-block.cjs` | Pre-read | Prompt before accessing sensitive files |
| `descriptive-name.cjs` | Pre-write | Enforce meaningful file names |
| `plan-format-kanban.cjs` | Post-edit | Maintain plan kanban board state |
| `session-state.cjs` | End of session | Save session telemetry |

### 5. Skills Ecosystem (.claude/skills/)

**Extended capabilities** via skill packages:

- `ck-plan/` — Planning and architecture workflows
- `ck-help/` — Help command and skill discovery
- `plans-kanban/` — Kanban board UI for tracking
- 50+ specialized skills (frontend, backend, deployment, etc.)

### 6. Configuration & Scripts

| File | Purpose |
|------|---------|
| `.env.example` | Configuration template (secrets NOT committed) |
| `settings.json` | Claude Code global settings (hooks, UI) |
| `metadata.json` | Project version, build info, repository |
| `.ckignore` | Files to exclude from tooling |
| `scripts/` | Utility automation (generate catalogs, validate docs) |

## Data Flow & Interactions

### Typical Feature Implementation Workflow

```
User Request
    ↓
┌─────────────────────────────────────┐
│ 1. PLANNER Agent (Opus)             │
│    - Research technical approach    │
│    - Design architecture            │
│    - Create implementation plan     │
└─────────────────────────────────────┘
    ↓ (plan.md created in ./plans/)
┌─────────────────────────────────────┐
│ 2. DEVELOPER Agents (Opus/Haiku)    │
│    - Implement code per phases      │
│    - Follow code standards          │
│    - Run linting, building          │
└─────────────────────────────────────┘
    ↓ (code committed, PR created)
┌─────────────────────────────────────┐
│ 3. TESTER Agent (Haiku)             │
│    - Run test suite                 │
│    - Check coverage (>80%)          │
│    - Validate performance           │
└─────────────────────────────────────┘
    ↓ (tests pass or fail → fix loop)
┌─────────────────────────────────────┐
│ 4. CODE-REVIEWER Agent (Opus)       │
│    - Review code quality            │
│    - Check standards compliance     │
│    - Suggest improvements           │
└─────────────────────────────────────┘
    ↓ (PR approved)
┌─────────────────────────────────────┐
│ 5. DOCS-MANAGER Agent (Haiku)       │
│    - Update documentation           │
│    - Sync with codebase             │
│    - Update roadmap & changelog     │
└─────────────────────────────────────┘
    ↓ (merge to main)
CI/CD Pipeline:
  - Run tests
  - Build artifacts
  - Deploy to staging/production
  - Update release notes
```

## Key Design Decisions

### 1. Agent Isolation
**Decision**: Agents operate independently with async Task/SendMessage coordination
**Rationale**: Scales to large teams; reduces shared state bugs; enables parallel work
**Trade-off**: Requires careful context passing; no real-time agent-to-agent communication

### 2. Documentation-First
**Decision**: Docs updated alongside code; verified against reality
**Rationale**: Prevents knowledge loss; reduces onboarding time; catches inconsistencies
**Trade-off**: Adds time to feature development; requires discipline

### 3. File Size Limits
**Decision**: Code files max 200 lines; docs max 800 lines
**Rationale**: Improves readability; easier context for LLMs; forces modularization
**Trade-off**: Requires upfront planning for decomposition

### 4. Rules-Over-Constraints
**Decision**: Standards enforced via configuration, not code
**Rationale**: Teams can customize rules; no forking needed; explicit intent
**Trade-off**: Requires agent discipline; no hard compile-time checks

## Module Dependencies

### Critical Path
1. **CLAUDE.md** → root instructions (all agents read this)
2. **.claude/rules/** → development standards (enforced by agents)
3. **.claude/agents/** → role definitions (agents instantiate from these)
4. **./docs/** → living documentation (referenced throughout)

### Integration Points
- Agents read `.claude/rules/` for behavior guidance
- Hooks (settings.json) intercept tool usage for validation
- Skills extend agents with domain-specific capabilities
- Plans organize work into phases per documentation-management.md

## Running the Boilerplate

### Initial Setup
```bash
# 1. Clone/fork the repository
git clone https://github.com/claudekit/claudekit-engineer.git
cd claudekit-engineer

# 2. Customize configuration
cp .env.example .env           # Edit for your environment
vim .claude/rules/development-rules.md  # Adjust standards

# 3. Review documentation
cat ./docs/code-standards.md   # Understand coding conventions
cat ./CLAUDE.md                # Read project instructions

# 4. Create first implementation plan
# In Claude Code: "/ck:plan Design the user authentication system"
# This spawns planner agent, creates ./plans/{date}-{slug}/
```

### Common Agent Invocations
```bash
# Plan a feature
/ck:plan Implement user profile editing

# Write code (after plan is approved)
/ck:cook ./plans/{date}-feature-name/

# Run tests
/ck:test

# Review code
/ck:code-review

# Update documentation
/ck:docs
```

## Customization Points

Teams customize these areas:

| Area | File(s) | Example |
|------|---------|---------|
| Coding standards | `.claude/rules/development-rules.md` | Add project-specific linting rules |
| Workflow | `.claude/rules/primary-workflow.md` | Add security audit phase |
| Documentation | `./docs/*` | Add API reference, deployment guide |
| Agents | `.claude/agents/*` | Create custom domain-specific agent |
| Skills | `.claude/skills/` | Add framework-specific skill |
| CI/CD | `.github/workflows/` | Add deploy steps, notifications |

## Performance & Scalability

### Single Developer
- Setup time: ~30 min
- Per-feature cycle: ~4 hrs (plan → code → test → review → docs)
- Knowledge retention: High (docs + decision logs)

### Small Team (3-5 developers)
- Parallel agents reduce cycle time to ~2-3 hrs per feature
- File ownership prevents conflicts
- Async Task/SendMessage coordination avoids meetings
- Shared rules/docs maintain consistency

### Large Team (10+)
- Consider multiple repositories (monorepo strategy)
- Extend team-coordination-rules.md for governance
- Create additional agents for cross-team concerns
- Use plans/kanban for visibility across teams

## Troubleshooting

| Issue | Diagnosis | Fix |
|-------|-----------|-----|
| Agents can't find code | Wrong `./docs/` references | Verify file exists; use relative paths |
| Documentation out of sync | Docs not updated with code | Run `/ck:docs` after code changes |
| Tests failing | Coverage requirement not met | Implement tests; validate with tester agent |
| Merge conflicts | File ownership not clear | Define ownership in task; use worktrees |

## Related Documentation

- **[Project Overview & PDR](./project-overview-pdr.md)** — Requirements, scope, success metrics
- **[Code Standards](./code-standards.md)** — Conventions, anti-patterns, review guidelines
- **[System Architecture](./system-architecture.md)** — Data flows, component diagrams
- **[Development Roadmap](./development-roadmap.md)** — Living project phases and progress
- **[Project Changelog](./project-changelog.md)** — Features, fixes, breaking changes
