# Deployment Guide & Environment Setup

**Version:** 2.17.0  
**Last Updated:** 2026-05-14

## Overview

This guide covers deploying projects built with claudekit-engineer. Since this is a **template boilerplate**, specific deployment infrastructure (AWS, GCP, Vercel, etc.) depends on your project type. This document outlines the general deployment workflow and CI/CD integration points.

## Local Development Setup

### Prerequisites

- **Node.js 16+** — For scripts and build tools
- **Git 2.20+** — For version control
- **Claude Code IDE** — For agent orchestration (claude.ai/code)
- **.env file** — Copy from `.env.example` and customize

### Initial Setup

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd <your-project>

# 2. Set up environment
cp .env.example .env
# Edit .env with your configuration (API keys, database URLs, etc.)

# 3. Install dependencies (if applicable)
npm install
# or: pip install -r requirements.txt (Python)
# or: go mod download (Go)

# 4. Run local development server
npm run dev
# or: python manage.py runserver
# or: go run main.go

# 5. Verify setup
npm run test
npm run lint
```

### Configuration Files

**`.env.example`** — Template (committed to git, no secrets)
```
# Example environment configuration
NODE_ENV=development
DATABASE_URL=postgresql://localhost:5432/devdb
API_PORT=3000
LOG_LEVEL=debug
FEATURE_FLAGS_ENABLED=true
```

**`.env`** — Local configuration (git-ignored, with secrets)
```
# Do NOT commit this file
NODE_ENV=development
DATABASE_URL=postgresql://user:password@localhost:5432/devdb
API_PORT=3000
LOG_LEVEL=debug
API_KEY_STRIPE=sk_test_XXXXXXXXXX
```

## Development Workflow

### Branch Strategy

Use **trunk-based development** or **feature branches**:

```
main (production-ready)
 ├─ feat/user-authentication (feature branch)
 │  └─ Merged via PR after: linting, tests, review
 └─ fix/database-leak (hotfix branch)
    └─ Merged via PR, backported to release branch
```

### Pre-Commit Checks

Before pushing code:

```bash
# 1. Lint code
npm run lint

# 2. Format code
npm run format

# 3. Run tests
npm run test

# 4. Build
npm run build

# 5. Check for secrets
npm run check-secrets
# or: git secrets --scan

# 6. Push
git push origin feat/my-feature
```

## CI/CD Pipeline Setup

### GitHub Actions Configuration

Create `.github/workflows/ci.yml` to automate testing and deployment:

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '16'
      
      - name: Install dependencies
        run: npm ci
      
      - name: Lint
        run: npm run lint
      
      - name: Run tests
        run: npm run test -- --coverage
      
      - name: Check test coverage
        run: npm run coverage:check
      
      - name: Build
        run: npm run build
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Deploy to production
        env:
          DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}
        run: |
          # Your deployment script
          npm run deploy:prod
      
      - name: Notify Slack
        if: success()
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": "Deployment successful! Version ${{ github.ref }}"
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

### Testing Checklist

Before every deployment:

```bash
# Run full test suite
npm run test:full

# Check coverage threshold
npm run coverage:report

# Run integration tests
npm run test:integration

# Run e2e tests (if applicable)
npm run test:e2e

# Performance testing
npm run test:performance
```

## Staging Environment

### Deployment to Staging

Staging should mirror production as closely as possible:

```bash
# 1. Create release candidate from develop
git checkout -b release/v1.2.0 develop

# 2. Update version
npm version minor

# 3. Update CHANGELOG.md
# - Add release date
# - List features, fixes, breaking changes

# 4. Commit and push
git commit -am "chore: release v1.2.0"
git push origin release/v1.2.0

# 5. Deploy to staging
git checkout staging
git merge release/v1.2.0
git push origin staging

# 6. Verify deployment
npm run health:check
# → Should report all systems operational
```

### Staging Validation

- **Smoke tests**: Core functionality works
- **Integration tests**: Components work together
- **Performance tests**: No degradation from main
- **Security scan**: No new vulnerabilities
- **User acceptance testing**: Product team sign-off

## Production Deployment

### Release Process

```bash
# 1. On main branch, create production release
git tag v1.2.0
git push origin v1.2.0

# 2. CI/CD automatically:
#    - Builds artifacts
#    - Runs full test suite
#    - Creates GitHub release
#    - Deploys to production
#    - Sends notifications

# 3. Monitor deployment
npm run monitor:health
npm run monitor:logs
npm run monitor:metrics
```

### Deployment Rollback

If production issues occur:

```bash
# 1. Identify last good version
git log --oneline | head -10

# 2. Rollback (infrastructure-specific)
# Example: Kubernetes
kubectl rollout undo deployment/app --to-revision=3

# 3. Verify rollback
npm run health:check

# 4. Investigate failure
# - Check logs
# - Analyze error metrics
# - Create incident report

# 5. Create hotfix branch
git checkout -b hotfix/issue-fix main
# - Fix the issue
# - Test thoroughly
# - Create PR for review
# - Merge and retag
```

### Production Monitoring

After deployment, monitor:

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Uptime | 99.9% | < 99.5% |
| Response Time (p95) | < 200ms | > 500ms |
| Error Rate | < 0.1% | > 0.5% |
| Database Connections | < 80% | > 90% |
| Memory Usage | < 70% | > 85% |
| Disk Usage | < 80% | > 90% |

## Environment Configuration

### Environment Levels

| Environment | Secrets | Data | Update Frequency |
|-------------|---------|------|------------------|
| **Local** | Real (test) | Test database | On-demand |
| **Staging** | Real (test) | Test database clone | Per PR |
| **Production** | Real (production) | Live user data | Per release |

### Secrets Management

**Best practices**:
- Never commit secrets to git
- Use `.env.example` as template
- Store secrets in:
  - Local: `.env` (git-ignored)
  - CI/CD: GitHub Secrets
  - Production: AWS Secrets Manager / Google Secret Manager
- Rotate secrets every 90 days
- Audit secret access

### Infrastructure as Code (IaC)

Store infrastructure configurations in git:

```
.github/
├── workflows/
│   ├── ci.yml
│   └── deploy.yml

infrastructure/
├── terraform/          # (if using Terraform)
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
├── docker/             # (if using Docker)
│   └── Dockerfile
└── kubernetes/         # (if using K8s)
    └── deployment.yaml
```

## Database Migrations

### Schema Updates

```bash
# Create migration
npm run migration:create -- --name=add_user_roles

# Review generated file
cat migrations/20260514_add_user_roles.sql

# Run migration locally
npm run migration:up

# Verify schema
npm run migration:status

# On production (blue-green deployment)
# 1. Deploy new code (handles both old & new schema)
# 2. Run migration on production database
# 3. Monitor for issues
# 4. Rollback if critical issues
```

### Data Migrations

For large data changes:

```bash
# 1. Create backup
npm run backup:database

# 2. Run data migration in transaction
npm run data-migration:run -- --dry-run    # Verify
npm run data-migration:run                 # Execute

# 3. Verify data integrity
npm run data-migration:verify

# 4. If issues, rollback from backup
npm run backup:restore -- backup-20260514.sql
```

## Documentation & Communication

### Deployment Notifications

Notify team on deployment:

```bash
# 1. Update project-changelog.md
vim docs/project-changelog.md
# - Add release version, date, features, fixes

# 2. Send to team channels
# - Slack: Post release notes
# - Email: To stakeholders
# - Docs: Update deployment guide

# 3. Example message
"""
Production Release v1.2.0
- Feature: User authentication
- Fix: Database connection leak
- Breaking: Removed deprecated API endpoint
Deployed: 2026-05-14 14:00 UTC
Monitoring: https://monitoring.example.com/v1.2.0
Rollback: If critical, contact DevOps
"""
```

### Post-Deployment Checklist

After every production deployment:

- [ ] Health checks all pass
- [ ] Error rate normal
- [ ] Performance metrics nominal
- [ ] User feedback channels monitored
- [ ] Team notified
- [ ] Incident on-call aware
- [ ] Release notes published

## Common Deployment Issues

### Issue: Build Fails

```bash
# Diagnosis
npm run build 2>&1 | tail -50

# Solutions
- Check Node.js version (16+)
- Clear node_modules: rm -rf node_modules && npm ci
- Check .env file (required keys present)
- Review recent code changes
```

### Issue: Tests Fail on CI but Pass Locally

```bash
# Diagnosis
npm run test -- --verbose
# Look for environment-specific issues

# Solutions
- Check .env.example vs .env (CI may be missing vars)
- Run tests in CI environment locally: docker run -it node:16 ...
- Check for random/flaky tests: npm run test -- --repeat=10
- Verify test isolation (no shared state between tests)
```

### Issue: Performance Degradation After Deployment

```bash
# Diagnosis
npm run performance:benchmark

# Solutions
- Compare with previous version
- Check for new dependencies (bundle size)
- Profile with: npm run profile
- Check database query performance
- Rollback if critical
```

## Related Documentation

- **[Code Standards](./code-standards.md)** — Pre-commit checks, testing requirements
- **[Project Changelog](./project-changelog.md)** — Release history and breaking changes
- **[Development Roadmap](./development-roadmap.md)** — Planned deployments and timelines

## Tools & Resources

### Monitoring & Logging
- **Datadog** — Application performance monitoring
- **Sentry** — Error tracking
- **CloudWatch** — AWS logging and monitoring
- **ELK Stack** — Elasticsearch, Logstash, Kibana
- **New Relic** — APM and monitoring

### Testing & Quality
- **CodeCov** — Code coverage reporting
- **SonarQube** — Code quality analysis
- **OWASP ZAP** — Security scanning

### Deployment Tools
- **Vercel** — Next.js hosting (recommended for Node.js)
- **Heroku** — Platform-as-a-service
- **AWS** — Comprehensive cloud infrastructure
- **Google Cloud** — Multi-region deployment
- **DigitalOcean** — Simple VPS hosting
