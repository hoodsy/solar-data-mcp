# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue.

- Use GitHub's private vulnerability reporting: the **Security → Report a
  vulnerability** tab on <https://github.com/hoodsy/solar-data-mcp>, or
- email the maintainer at the address on the GitHub profile.

We aim to acknowledge within a few days and will coordinate a fix and disclosure
timeline with you. Please include reproduction steps and the affected package(s)
and version(s).

## Supported versions

This project is pre-1.0; security fixes land on the latest released version.
Please upgrade to the newest version before reporting.

## Scope and threat model

These are local, stdio MCP servers that run on the user's machine with the
user's own API keys and talk to public US solar-data APIs. The threat model we
design against includes a **prompt-injected agent** — an LLM steered by
untrusted content into calling tools with attacker-chosen arguments. Reports
that are especially in scope:

- Getting a `sync_*` tool to fetch a non-official host or an internal/loopback
  address (SSRF), or to read a file outside the intended data-loading workflow.
- Any path that writes an API key or other secret to disk, logs, or a tool
  result envelope.
- SQL/identifier injection into the DuckDB bulk store or the SQLite cache.
- Anything that lets tool input escape the cache directory or execute code.

Out of scope: vulnerabilities in the upstream data APIs themselves, and issues
that require the user to pass a deliberately malicious local file to a `sync_*`
tool (that is equivalent to running any program on a file you don't trust).

## Handling of secrets

API keys are read only from the documented environment variables, are excluded
from cache keys, are redacted from cached response bodies and error messages,
and are never written to the result envelope. The cache directory and its
databases are created with owner-only permissions.
