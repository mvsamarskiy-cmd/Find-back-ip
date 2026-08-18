# Verification tools

- `railway_guard.py show` displays the committed production target.
- `railway_guard.py link` links Railway CLI to that exact target.
- `railway_guard.py smoke` tests the canonical root and health endpoint.
- `railway_guard.py audit` finds other Railway projects attached to this repo;
  it requires `RAILWAY_API_TOKEN` and never deletes resources.
- `production_canary.py` performs deeper non-secret production checks against the
  canonical HTTPS deployment: health, `/api/version`, strict green semantics,
  newest-first paginated feed configuration, and durable background-search
  configuration. Add `--require-worker` to require a live worker and `ready=true`.
  Add `--expected-release <marker>` or `--expected-commit <sha>` to reject stale
  production after a deploy. The `Production Canary` GitHub workflow also runs on
  every push to `main`, retries while Railway autodeploy converges, requires the
  live worker, and verifies that `/api/version` reports the pushed commit.
- `check_inline_js.py` extracts every inline script from the active template and
  validates its JavaScript syntax with Node.js.

These checks are the verification area. Application changes still live in the
normal source files and flow through one branch, one PR, and one squash commit.
