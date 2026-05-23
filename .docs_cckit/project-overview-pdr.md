# Project Overview & Product Development Requirements

**Version:** 2.17.0  
**Last Updated:** 2026-05-14  
**Status:** Active Boilerplate Template

## Executive Summary

claudekit-engineer is a comprehensive boilerplate template for building professional software projects using Claude Code and ClaudeKit workflows. It provides production-ready foundations for:

- **Multi-agent orchestration** via Claude Code for coordinated AI-driven development
- **Workflow automation** with pre-configured agents for planning, coding, testing, reviewing, and documentation
- **Project standardization** through enforced development rules, documentation standards, and architecture patterns
- **Team collaboration** tools for parallel task execution, file ownership management, and synchronized workflows

This is a **template project**, not a finished product. Users customize and extend it for their specific needs.

## Core Functional Requirements

### FR-1: Agent-Based Development Orchestration
- Support 14+ specialized agents (planner, coder, tester, reviewer, debugger, docs-manager, etc.)
- Enable agents to operate independently or in coordinated workflows
- Support sequential chaining (Plan → Code → Test → Review) and parallel execution
- Agents must read/write project files and coordinate via Task/SendMessage protocols

### FR-2: Workflow Rule Enforcement
- Enforce development standards through `.claude/rules/` configuration
- Support YAGNI/KISS/DRY principles in all workflows
- Validate code against pre-defined patterns (naming, structure, error handling)
- Enable teams to customize rules without modifying core templates

### FR-3: Documentation-Driven Development
- Maintain living documentation in `./docs/` synced with codebase reality
- Auto-generate codebase summaries from code compaction (`repomix`)
- Define PDRs (Product Development Requirements) for feature implementation
- Ensure docs are verified against actual code before publication

### FR-4: Plan Management & Tracking
- Support creation and execution of multi-phase implementation plans
- Track plan progress with status, priority, effort estimates
- Enable phase-level subtasks and dependency management
- Archive and review completed plans for lessons learned

### FR-5: CI/CD Integration
- Provide hooks for GitHub Actions / CI pipeline integration
- Support test execution, linting, and build validation
- Enable automated documentation updates on code changes
- Support notifications (Discord, Slack, Telegram) for critical events

## Non-Functional Requirements

### NFR-1: Developer Productivity
- Minimize onboarding time for new team members (~1-2 hours)
- Enable single-command project setup and configuration
- Provide quick-reference guides for common workflows
- Support IDE integration and CLI tooling

### NFR-2: Scalability & Flexibility
- Support projects from solo developers to large teams (10+ members)
- Work across monorepos and multi-project structures
- Enable custom agent configurations and skill extensions
- Scale documentation without performance degradation

### NFR-3: Security & Data Protection
- No credentials or secrets committed to git (`.env.example` pattern)
- Support OWASP/STRIDE security audits
- Enable role-based access control for team workflows
- Maintain audit trails for code review and approval workflows

### NFR-4: Maintainability
- Keep configuration DRY; avoid duplication across rules/agents
- Use semantic versioning for releases
- Document all architectural decisions and trade-offs
- Support migration paths for breaking changes

## Technical Constraints

- **Node.js 16+** required for repomix and build tools
- **Git** required for version control and CI integration
- **Claude Code** (claude.ai/code) for agent execution
- **Markdown** as the standard for all documentation
- **Python 3.8+** for optional skill scripts (via `.venv`)

## Success Metrics

| Metric | Target | Rationale |
|--------|--------|-----------|
| Agent setup time | < 5 min | Enable quick project initialization |
| Documentation coverage | > 80% | Reduce knowledge gaps |
| Plan-to-code latency | < 1 hr | Accelerate development cycles |
| Test coverage | > 80% | Ensure code quality |
| Deploy success rate | > 95% | Reliable production releases |

## Scope (Out of Scope)

### In Scope
- Boilerplate agent templates and workflow configurations
- Documentation structure and standards
- Development rules and coding guidelines
- CI/CD hook integration patterns
- Example plans and phase structures

### Out of Scope
- Actual project-specific code (users customize)
- Database schema design
- Frontend component libraries
- Backend API implementations
- Deployment infrastructure (AWS, GCP, etc.)

## Integration Points

| Component | Purpose | Status |
|-----------|---------|--------|
| `.claude/agents/` | Pre-configured agent definitions | Complete |
| `.claude/rules/` | Development standards enforcement | Complete |
| `.claude/hooks/` | Session and tool-use hooks | Complete |
| `./docs/` | Living documentation | Being populated |
| `./plans/` | Implementation plans & tracking | Ready |
| `.env.example` | Configuration template | Complete |

## Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| repomix | Latest | Generate code compaction for summaries |
| Node.js | 16+ | Run hooks and scripts |
| Git | 2.20+ | Version control |
| Claude Code | Latest | Agent execution environment |

## Known Limitations

1. **Agent Context Isolation** — Agents operate independently; large-scale coordination relies on Task/SendMessage protocols rather than shared state
2. **Documentation Lag** — Docs require manual sync when code changes; auto-generation works only for high-level summaries
3. **File Ownership Conflicts** — Teams must define ownership via task descriptions; conflicts require manual resolution
4. **Test Coverage Gaps** — Boilerplate includes no tests; users must implement coverage for their code

## Next Steps for Users

1. Read `./docs/codebase-summary.md` to understand the architecture
2. Review `./docs/code-standards.md` for coding conventions
3. Customize `.claude/rules/` for team-specific standards
4. Create first plan using `./.claude/agents/planner.md` guidelines
5. Set up CI/CD hooks in `./.github/workflows/`
