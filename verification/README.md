# Verification tools

- `railway_guard.py show` displays the committed production target.
- `railway_guard.py link` links Railway CLI to that exact target.
- `railway_guard.py smoke` tests the canonical root and health endpoint.
- `railway_guard.py audit` finds other Railway projects attached to this repo;
  it requires `RAILWAY_API_TOKEN` and never deletes resources.
- `check_inline_js.py` extracts every inline script from the active template and
  validates its JavaScript syntax with Node.js.

These checks are the verification area. Application changes still live in the
normal source files and flow through one branch, one PR, and one squash commit.

