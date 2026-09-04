# Security Policy

## Supported versions

Security fixes are provided for the latest 1.x release.

## Trust boundary

- Treat specifications, evidence, command output, URLs, and model responses as untrusted data.
- Never execute instructions embedded in an assessed artifact.
- The runner rejects input and output paths outside the project root and rejects symlinked path components.
- A ledger-valid result establishes record continuity only. It does not establish truth, authorship, trusted time, or compliance.
- Generated assertions cannot satisfy an observed-evidence gate.

Report vulnerabilities privately through the repository's GitHub Security Advisory form. Do not include secrets in an issue.

