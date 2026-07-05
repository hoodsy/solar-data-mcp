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

Do these once before the first release; check them off here as they're done.

- [ ] Six pending publishers registered on PyPI
- [x] `pypi` environment created in the GitHub repo (2026-07-05)

### 1. Register the PyPI trusted publishers

The projects don't exist on PyPI yet, so use **pending publishers**:
<https://pypi.org/manage/account/publishing/> → "Add a new pending publisher"
(GitHub tab). Repeat six times, once per project name, with identical values
otherwise:

| Field             | Value                                    |
| ----------------- | ---------------------------------------- |
| PyPI project name | each of the six package names above      |
| Owner             | `hoodsy`                                 |
| Repository name   | `solar-data-mcp`                         |
| Workflow name     | `release.yml`                            |
| Environment name  | `pypi`                                   |

Pending publishers convert to regular trusted publishers automatically on
first publish. If a publish fails with `invalid-publisher`, one of these
values doesn't match — fix the registration, not the workflow.

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

### 7. Still manual after publish

- MCP registry listing (points at the PyPI package) — first release, then on
  metadata changes
- Demo GIF in the README — first release

## If the release workflow fails

- PyPI versions are **immutable** — you can never re-upload a
  name+version that already landed. Both publish steps set
  `skip-existing: true`, so after a partial failure (e.g. domain packages
  published, umbrella didn't) it is safe to just **re-run the failed job**:
  already-published packages are skipped, missing ones publish.
- `invalid-publisher` → trusted-publisher registration mismatch; see the
  one-time setup table.
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
