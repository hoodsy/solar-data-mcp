# Releasing

Six packages ship to PyPI together from one `v*` tag: `solar-data-mcp-core`,
`solar-data-mcp-nrel`, `solar-data-mcp-economics`, `solar-data-mcp-market`,
`solar-data-mcp-forecast`, and the `solar-data-mcp` umbrella. Publishing runs in
`.github/workflows/release.yml` via PyPI Trusted Publishing (OIDC) — no API
tokens anywhere. The workflow publishes core + the four domain servers first,
then the umbrella, so `uvx solar-data-mcp` always resolves its dependencies.

Versions are bumped in lockstep across all six packages. The bare `solar-mcp`
name on PyPI belongs to an unrelated project — never use it.

## One-time setup

Done once before the first release; kept for the record and for anyone
cloning this setup.

- [x] Six projects created on PyPI via token bootstrap (2026-07-06)
- [x] Trusted publisher added on each of the six project pages (2026-07-07)
- [x] `pypi` environment created in the GitHub repo (2026-07-05)

### 1. Bootstrap the projects, then add trusted publishers

**Pending publishers do not work for this monorepo.** PyPI rejects a second
*pending* publisher that shares the repo/workflow/environment config with an
existing one ("A pending trusted publisher matching this configuration has
already been registered for a different project name") — and all six of ours
are identical except the project name. The restriction only applies while a
project doesn't exist yet, so the projects were created with a one-time
token instead (done for v0.1.0):

1. Create an **account-scoped API token** at
   <https://pypi.org/manage/account/token/>; put it in `.env` (gitignored)
   as `PYPI_TOKEN=...`.
2. Build and publish, dependencies first:

   ```sh
   uv build --all-packages
   export UV_PUBLISH_TOKEN=$(grep '^PYPI_TOKEN=' .env | cut -d= -f2-)
   uv publish --check-url https://pypi.org/simple/ dist/solar_data_mcp_core-*
   uv publish --check-url https://pypi.org/simple/ dist/solar_data_mcp_{nrel,economics,market,forecast}-*
   uv publish --check-url https://pypi.org/simple/ dist/solar_data_mcp-[0-9]*
   ```

   Expect `429 Too many new projects created`: new accounts can create only
   ~4 projects per rolling ~24 h window. Just re-run the same commands after
   the window clears — `--check-url` makes them idempotent.
3. On each of the six now-existing projects, add a trusted publisher:
   project page → **Manage → Publishing** → GitHub form. Identical config
   across *existing* projects is allowed:

   | Field             | Value            |
   | ----------------- | ---------------- |
   | Owner             | `hoodsy`         |
   | Repository name   | `solar-data-mcp` |
   | Workflow name     | `release.yml`    |
   | Environment name  | `pypi`           |

4. **Delete the API token** and any leftover pending publisher.

If a later publish fails with `invalid-publisher`, one of the table values
doesn't match — fix the publisher registration, not the workflow.

**Adding a seventh package later:** its first upload creates a new project,
so either bootstrap that one package with a token as above, or register a
*single* pending publisher for it (one pending registration is fine — the
conflict only arises with a second pending one on the same config).

### 2. Create the GitHub `pypi` environment

Repo → Settings → Environments → New environment → `pypi`, or:

```sh
gh api -X PUT repos/hoodsy/solar-data-mcp/environments/pypi
```

Optional but recommended: add yourself as a required reviewer on the
environment, so a tag push pauses for one-click approval before anything
reaches PyPI.

## Every release

Run top to bottom; stop at the first failure.

### 1. Preflight — on a clean `main`, CI green

```sh
git status                                   # clean, on main
uv run pytest                                # fixture replay only, no live calls
uv run ruff check . && uv run mypy --strict
uv build --all-packages                      # all six build
```

### 2. Pick the version

Semver, all six packages in lockstep. **On a minor bump** (e.g. 0.1.x → 0.2.0),
also widen the `solar-data-mcp-*>=0.1,<0.2` caps in the five dependent
`pyproject.toml` files — they pin to the current minor series.

### 3. Bump all six versions

```sh
NEW=0.1.0   # ← the new version
sed -i '' "s/^version = .*/version = \"$NEW\"/" packages/*/pyproject.toml
uv sync                                      # refresh uv.lock
uv run pytest -q                             # sanity after the bump
```

Also bump **both** `version` fields in `server.json` (the MCP registry
listing: top-level and inside `packages[0]`).

### 4. Commit, tag, push

```sh
git add packages/*/pyproject.toml uv.lock docs/RELEASING.md
git commit -m "Release v$NEW"
git push
git tag "v$NEW"
git push origin "v$NEW"                      # ← this triggers the release
```

### 5. Watch and verify

```sh
gh run watch --repo hoodsy/solar-data-mcp
```

When it's green, verify from a machine/env that has never seen this repo:

```sh
uvx solar-data-mcp@$NEW doctor               # resolves umbrella + deps from PyPI
```

and spot-check <https://pypi.org/project/solar-data-mcp/> shows the new version.

### 6. GitHub release notes

```sh
gh release create "v$NEW" --title "v$NEW" --generate-notes
```

### 7. Update the MCP registry listing

```sh
mcp-publisher publish                        # reads server.json
```

Uses the `io.github.hoodsy/*` namespace; if the session isn't authenticated,
run `mcp-publisher login github` first (GitHub device flow). The registry
validates PyPI ownership via the `mcp-name: io.github.hoodsy/solar-data-mcp`
HTML comment in `packages/solar-data-mcp/README.md` — don't remove it, and
remember the marker only "exists" once the new version is live on PyPI.

## If the release workflow fails

- PyPI versions are **immutable** — you can never re-upload a
  name+version that already landed. Both publish steps set
  `skip-existing: true`, so after a partial failure (e.g. domain packages
  published, umbrella didn't) it is safe to just **re-run the failed job**:
  already-published packages are skipped, missing ones publish.
- `invalid-publisher` → trusted-publisher registration mismatch; see the
  one-time setup table.
- `invalid-pending-publisher: valid token, but project already exists` → a
  stale **pending** publisher on the account matches the workflow's claims
  and shadows the per-project publishers. Delete it at
  <https://pypi.org/manage/account/publishing/>, then re-run the failed job.
  (Hit this on v0.1.0.)
- If the fix needs a code change, land it on `main`, bump the **patch**
  version, and restart from step 3 with a new tag. Never delete or reuse a
  tag that already triggered a publish.

## Before the first public announcement

Not blockers for publishing, but resolve before promoting the release:

- [ ] Validate the quartz-solar-forecast adapter against the real library in a
      scratch venv (it's intentionally not a dependency — pydantic pin
      conflict; see `packages/solar-forecast/README.md`)
- [ ] Re-record `fixtures/ahj/*` with a real `AHJ_REGISTRY_TOKEN` — current
      fixtures are hand-authored (registry host had no DNS when built)
