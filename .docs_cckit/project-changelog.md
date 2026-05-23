# Project Changelog

**Version:** 2.17.0  
**Last Updated:** 2026-05-14

All notable changes to claudekit-engineer are documented here. This file follows [Semantic Versioning](https://semver.org/) and [Keep a Changelog](https://keepachangelog.com/) conventions.

## [Unreleased]

### Planned for v2.18.0
- Skill marketplace integration
- Enhanced plan kanban board
- Agent memory persistence system
- Community skill templates and examples
- Expanded documentation (agent deep-dives)

---

## [2.17.0] - 2026-05-14

### Added

#### Documentation Framework
- Added 9 core documentation files (`./docs/` structure):
  - `project-overview-pdr.md` — Product requirements and scope
  - `code-standards.md` — Coding conventions and standards
  - `codebase-summary.md` — Architecture and module overview
  - `system-architecture.md` — Data flows and component interactions
  - `design-guidelines.md` — UI/UX and accessibility standards
  - `deployment-guide.md` — Environment setup and CI/CD integration
  - `project-roadmap.md` — Feature roadmap and release plan
  - `development-roadmap.md` — Living roadmap with progress tracking
  - `project-changelog.md` — This file (version history)

#### Agent Definitions
- 14 specialized agent role definitions in `.claude/agents/`:
  - `planner.md` — Tech Lead for architecture and planning
  - `developer.md` (fullstack) — Feature implementation
  - `tester.md` — QA and test automation
  - `code-reviewer.md` — Code quality and best practices
  - `docs-manager.md` — Documentation management
  - `debugger.md` — Root cause analysis
  - `researcher.md` — Technical research
  - `brainstormer.md` — Solution exploration
  - `code-simplifier.md` — Refactoring and optimization
  - `ui-ux-designer.md` — UI/UX design
  - `journal-writer.md` — Decision logging
  - `project-manager.md` — Roadmap and metrics
  - `git-manager.md` — Git workflow coordination
  - `mcp-manager.md` — MCP tool management

#### Development Rules
- 7 comprehensive rule files in `.claude/rules/`:
  - `primary-workflow.md` — Development cycle (Plan → Code → Test → Review → Docs)
  - `development-rules.md` — Code quality, file sizing, naming conventions
  - `documentation-management.md` — Docs structure and maintenance
  - `orchestration-protocol.md` — Agent coordination and delegation
  - `skill-domain-routing.md` — When to use which skill
  - `skill-workflow-routing.md` — Skill sequencing patterns
  - `team-coordination-rules.md` — File ownership and team safety

#### Hook System
- Session management hooks:
  - `session-init.cjs` — Initialize session state on startup
  - `subagent-init.cjs` — Inject context for subagent execution
  - `team-context-inject.cjs` — Add team collaboration data
- Validation hooks:
  - `scout-block.cjs` — Prevent overly broad file searches
  - `privacy-block.cjs` — Prompt before accessing sensitive files
  - `descriptive-name.cjs` — Enforce meaningful file names
- Utility hooks:
  - `plan-format-kanban.cjs` — Maintain plan kanban state
  - `session-state.cjs` — Save session telemetry

#### Configuration
- `.env.example` — Configuration template with all required and optional variables
- `settings.json` — Claude Code global settings with hook configuration
- `metadata.json` — Project metadata, version, and repository info
- `.ckignore` — Files excluded from tooling
- `.repomixignore` — Files excluded from code compaction

#### Plans & Templates
- `./plans/` directory structure for implementation plans
- Plan templates with YAML frontmatter (title, status, priority, effort)
- Phase file structure for multi-phase implementations
- Reports directory for research and analysis documentation

#### Team Collaboration
- Task-based delegation protocols
- SendMessage async communication patterns
- File ownership and conflict resolution guidelines
- Git safety rules for team development
- Workpltre support for isolated feature branches

### Changed

- Reorganized project structure with `.claude/` as primary configuration hub
- Moved agent definitions to agent-centric model (not command-based)
- Shifted from command-driven to workflow-driven development
- Emphasized documentation-first approach with code verification

### Fixed

- Corrected agent memory initialization paths
- Fixed hook ordering for session state consistency
- Resolved documentation cross-reference issues
- Clarified git safety rules for team workflows

### Deprecated

- Previous command-based agent invocation (replaced by workflow-based approach)
- Old `.commands/` directory structure (replaced by `.claude/agents/`)

### Removed

- Removed obsolete agent definitions (scout.md, copywriter.md, database-admin.md)
- Removed deprecated command structures
- Removed outdated hook implementations
- Cleaned up legacy skill directories

### Security

- Added privacy-block hook for sensitive file protection
- Implemented secrets scanning in pre-commit guidelines
- Added security checklist to code-standards.md
- Defined OWASP/STRIDE audit requirements

### Performance

- Optimized session-init hook for fast startup (< 2 seconds)
- Reduced hook overhead with lazy-loading patterns
- Improved scout-block efficiency for large repositories

---

## [2.16.0] - 2026-04-28

### Added
- Initial boilerplate template structure
- Core agent framework
- Development rules foundation
- Hook system skeleton

### Changed
- Restructured from monolithic to distributed agent architecture

### Fixed
- Hook initialization order

---

## Versioning Strategy

**claudekit-engineer** follows [Semantic Versioning](https://semver.org/):

- **MAJOR** (e.g., 3.0.0) — Breaking changes to agent definitions, workflows, or APIs
  - Requires migration guide
  - 12-month compatibility window for old versions
- **MINOR** (e.g., 2.18.0) — New features, backward compatible
  - New agents or significant enhancements
  - New rule files or extensions
  - Additive changes only
- **PATCH** (e.g., 2.17.1) — Bug fixes, documentation updates
  - No API changes
  - No new features
  - Fixes for existing functionality

## Release Cycle

- **Stable Releases**: Every 6-8 weeks (planned)
- **Patch Releases**: As needed for critical bugs
- **Beta Releases**: For community testing (2-week window)

## Upgrade Guide

### From v2.16.0 to v2.17.0

**No breaking changes.** This is a purely additive release.

```bash
# 1. Pull latest version
git pull origin main

# 2. Review new documentation in ./docs/
cat ./docs/README.md

# 3. Update your local .claude/rules/ if customized
# Compare your customizations with new v2.17.0 defaults
diff your-rules/ .claude/rules/

# 4. No migration steps needed
# v2.16.0 projects continue to work as-is
```

### From v2.x to v3.0.0 (Future)

**Breaking changes planned.** Migration guide will be provided 6 months before release.

---

## Contributors

### v2.17.0 Contributors
- **docs-manager** — Documentation framework and content
- **planner** — Agent architecture design
- **project-manager** — Roadmap and coordination
- **researcher** — Technical research and analysis

### Contributing

See `CLAUDE.md` for contribution guidelines. To contribute:

1. Fork the repository
2. Create a feature branch (`feat/your-feature`)
3. Follow code standards in `./docs/code-standards.md`
4. Submit a pull request with detailed description
5. Request review from project team

## Support

- **Bug Reports**: [GitHub Issues](https://github.com/claudekit/claudekit-engineer/issues)
- **Feature Requests**: [GitHub Discussions](https://github.com/claudekit/claudekit-engineer/discussions)
- **Urgent Issues**: Contact project-manager@claudekit.dev

## License

claudekit-engineer is open source. See LICENSE file for details.

## Acknowledgments

Built with Claude Code and ClaudeKit. Special thanks to the community for feedback and contributions.

---

## Archive (Historical)

### v2.15.0 and earlier
- See [historical releases](https://github.com/claudekit/claudekit-engineer/releases?page=2)
- Legacy documentation maintained in `git log`

---

## What's Next?

- **v2.18.0** (Q3 2026): Skill marketplace, enhanced collaboration
- **v3.0.0** (Q4 2026): Advanced workflows, enterprise features
- See [Project Roadmap](./project-roadmap.md) for detailed timeline
