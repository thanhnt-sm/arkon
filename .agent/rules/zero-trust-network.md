# Rule: Zero Trust Network Enforcement

This workspace is a Zero Trust environment. ALL outbound network traffic must be strictly controlled and audited.

## 🛡️ Mandatory Networking Standards

1.  **Isolation**: All services (API, Workers, Database, etc.) MUST reside in an internal-only network (`arkon_internal`).
2.  **No Direct Egress**: No container (except the Proxy) should have direct access to the internet. The `arkon_internal` network must always have `internal: true`.
3.  **Controlled Proxy**: The only allowed egress point is the `arkon_squid` container.
4.  **Whitelist Policy**: Any new external service (e.g., a new LLM provider) must be explicitly whitelisted in `squid/squid.conf`.
5.  **No CDNs**: Do not use external CDNs for fonts, icons, or scripts. All assets must be self-hosted within the project.
6.  **Read-Only Filesystem**: Services must run with `read_only: true` unless there is a critical, justified need for a writable volume. Use `tmpfs` for caches.

## 🚫 Prohibited Actions

- **NEVER** set `internal: false` for the `arkon_internal` network.
- **NEVER** add external trackers, analytics SDKs, or telemetry tools.
- **NEVER** bypass the proxy for external API calls.

## 🔍 Continuous Auditing

- Run `.agent/workflows/run_audit.sh` after every dependency update or upstream sync.
- Any pull request modifying `docker-compose.yml` or `squid/squid.conf` MUST be audited for security regressions.
