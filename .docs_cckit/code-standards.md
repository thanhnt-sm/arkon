# Code Standards & Development Guidelines

**Version:** 2.17.0  
**Last Updated:** 2026-05-14

## Core Principles

All code in this project follows three pillars:

- **YAGNI** — You Aren't Gonna Need It. Build only what's required now.
- **KISS** — Keep It Simple, Stupid. Prefer clarity over cleverness.
- **DRY** — Don't Repeat Yourself. Extract reusable patterns.

These principles guide architecture decisions, refactoring, and code review.

## File & Naming Conventions

### Code Files
- **Case Style**: Use kebab-case for file names
- **Length**: Keep individual files under 200 lines of code
- **Naming**: Use descriptive, self-documenting names
- **Example**: `user-authentication-service.ts`, `validate-email-format.js`

### Documentation Files
- **Case Style**: Use hyphens in markdown file names (e.g., `code-standards.md`)
- **Length**: Keep to 800 lines maximum (see size-limit rules below)
- **Structure**: Use clear headers (H1, H2, H3) for navigation
- **Links**: Use relative paths within `./docs/` (e.g., `[link](./other-doc.md)`)

### Configuration Files
- Use exact naming: `.env.example`, `settings.json`, `.ckignore`
- Do NOT modularize configuration files

## Code Organization

### File Size Management
- **Code files**: Max 200 lines
- **Documentation files**: Max 800 lines
- **Strategy**: When approaching limit, split into focused modules/topics

### Modularization Triggers
Create separate files when:
- Single responsibility is violated (file handles 2+ unrelated concerns)
- Interdependencies between sections are minimal
- File has 150+ lines of complex logic

Do NOT split:
- Markdown/documentation files (unless exceeding 800 lines)
- Configuration files, environment variables, bash scripts

### Directory Structure
```
project-root/
├── .claude/                  # ClaudeKit configuration
│   ├── agents/              # Agent definitions
│   ├── rules/               # Development rules
│   ├── hooks/               # Session & tool-use hooks
│   ├── scripts/             # Automation scripts
│   └── skills/              # Extended skills
├── .github/workflows/       # CI/CD workflows
├── docs/                    # Project documentation
├── plans/                   # Implementation plans
├── src/                     # Source code (if applicable)
├── tests/                   # Test files
└── .env.example             # Configuration template
```

## Code Quality Standards

### Comments & Documentation
- **Self-Documenting Code**: Prefer clear names over comments
- **Complex Logic**: Add comments explaining the "why", not the "what"
- **TODOs**: Use `TODO: [description]` for future work; track in issues/plans
- **Avoid**: Dead code, commented-out code blocks

### Error Handling
- **Try-Catch**: Use for recoverable errors; provide context
- **Error Messages**: Be specific; avoid generic "Error" messages
- **Logging**: Log errors at appropriate levels (error, warn, info)
- **Example Pattern**:
  ```javascript
  try {
    // attempt operation
  } catch (error) {
    logger.error('Failed to save user profile', { userId, error });
    throw new UserSaveError('Could not persist changes', { cause: error });
  }
  ```

### Performance & Security
- **Input Validation**: Validate all external inputs
- **SQL Injection**: Use parameterized queries / ORMs
- **XSS Prevention**: Sanitize user-generated content
- **Secrets**: Never commit `.env` files; use `.env.example` template
- **Dependencies**: Keep transitive dependencies minimal; review lockfiles

## Git & Commit Standards

### Commit Messages
- **Format**: Conventional commits (feat:, fix:, docs:, refactor:, test:, chore:)
- **Length**: Keep title under 70 characters
- **Body**: Include rationale for non-obvious changes
- **Example**:
  ```
  feat: add user profile validation

  Validates email and phone number formats before persistence.
  Prevents invalid data from entering the database.
  ```

### Branch Naming
- **Format**: `{type}/{short-description}`
- **Examples**: `feat/auth-oauth2`, `fix/db-connection-leak`, `docs/api-update`
- **Type Values**: feature, fix, docs, refactor, chore, experiment

### Pull Requests
- Link to related issues: "Closes #123"
- Include test results summary
- Request code review from team
- Enforce: linting passes, tests pass, docs updated

## Testing Standards

### Test Organization
- **Colocation**: Store test files next to implementation
- **Naming**: `{file}.test.js` or `{file}.spec.js`
- **Structure**: Arrange-Act-Assert pattern
- **Coverage**: Aim for 80%+ code coverage

### Test Types
| Type | Purpose | Target |
|------|---------|--------|
| Unit | Isolated function/module testing | 70% coverage |
| Integration | Multi-component interaction | 10% coverage |
| E2E | Full workflow validation | 10% coverage (critical paths) |

### Error Scenario Testing
- Test happy path AND error cases
- Validate exception handling
- Check boundary conditions
- Test with invalid/malformed inputs

## Security Checklist

Before committing code:

- [ ] No secrets in committed code (check `.env`, API keys, tokens)
- [ ] Input validation on all external data
- [ ] SQL queries use parameterized statements
- [ ] Error messages don't leak implementation details
- [ ] Authentication/authorization properly enforced
- [ ] Sensitive operations logged for audit trails
- [ ] Dependencies reviewed for known vulnerabilities

## Linting & Formatting

### Pre-Commit Checks
Run before every commit:
```bash
npm run lint          # Fix linting errors
npm run format        # Auto-format code
npm run test          # Ensure tests pass
npm run build         # Verify build succeeds
```

### Enforcement
- **Linting**: Should pass without warnings (errors block PR)
- **Formatting**: Use consistent formatter (Prettier/ESLint)
- **Types**: Enable strict type-checking (TypeScript/JSDoc)

## Code Review Guidelines

### Reviewer Responsibilities
- Verify code meets standards above
- Check for security vulnerabilities
- Ensure test coverage remains above 80%
- Validate documentation is updated
- Suggest improvements for clarity and maintainability

### Author Responsibilities
- Include descriptive PR description
- Respond to feedback promptly
- Keep commits focused (one feature per PR)
- Update docs alongside code changes

## Anti-Patterns (Avoid These)

| Anti-Pattern | Problem | Solution |
|---|---|---|
| God Objects | Class/function does too much | Split into smaller, focused units |
| Magic Numbers | Unexplained constants | Extract to named constants |
| Deep Nesting | >3 levels of indentation | Extract early returns, break into functions |
| Copy-Paste Code | Violates DRY principle | Extract shared logic into utility |
| Incomplete Error Handling | Bugs go silent | Catch and log all exceptions |
| Temporal Coupling | Undocumented call order | Make dependencies explicit |

## Tools & Integration

### Recommended Tools
- **Linting**: ESLint (JavaScript), pylint (Python)
- **Formatting**: Prettier (JavaScript), Black (Python)
- **Type Checking**: TypeScript, mypy (Python)
- **Testing**: Jest (JavaScript), pytest (Python)
- **Documentation**: Markdown + Mermaid diagrams

### CI/CD Integration
- Run linting and tests on every push
- Block merges if coverage drops below threshold
- Auto-generate documentation on release
- Tag versions with semantic versioning

## Documentation Standards

### Code Examples
- Ensure all code examples compile/run
- Include language syntax highlighting
- Provide real-world context
- Update examples when code changes

### Link Hygiene
- Verify all links exist before documenting
- Use relative paths within `./docs/`
- Update links when moving documentation files
- No broken internal references

### Accuracy Protocol
- Read actual code before documenting
- Verify function names, parameters, return types
- Check configuration keys exist in `.env.example`
- Document only what is verified to exist

## Refactoring Guidelines

When refactoring code:

1. **Test First**: Ensure comprehensive test coverage exists
2. **Small Steps**: Make minimal changes per commit
3. **Verify**: Run full test suite after each change
4. **Document**: Update docs if behavior changes
5. **No Feature Creep**: Refactor only; don't add features

## Versioning & Releases

- Use **Semantic Versioning**: MAJOR.MINOR.PATCH
- **MAJOR**: Breaking API/workflow changes
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, documentation updates
- Update `CHANGELOG.md` on each release

## Questions & Escalation

For questions on standards:
1. Check this document and related docs in `./docs/`
2. Review similar code patterns in the codebase
3. Discuss in team channels or PR comments
4. Escalate to tech lead for architectural decisions
