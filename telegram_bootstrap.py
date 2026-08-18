import os

from flask import jsonify

from telegram_integration import install


install()

# Production still imports the legacy Flask module, but Verification v2 replaces
# its checker globals at bootstrap time. Existing routes therefore keep their
# URLs and response compatibility while gaining the additive `verification` map.
import app as app_module  # noqa: E402
from availability_v2 import check_all as check_all_v2, check_many as check_many_v2  # noqa: E402
from verification.diagnostics import provider_diagnostics  # noqa: E402

app_module.check_all = check_all_v2
app_module.check_many = check_many_v2
app = app_module.app


RELEASE_MARKER = "v6.3-verification-v2"


@app.after_request
def prevent_stale_html(response):
    """Ensure the browser cannot keep an obsolete application shell after deploys."""
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/api/version")
def api_version():
    """Expose a non-secret release marker and Railway/Git commit for smoke checks."""
    commit = (
        os.environ.get("RAILWAY_GIT_COMMIT_SHA")
        or os.environ.get("GIT_COMMIT_SHA")
        or "unknown"
    )
    return jsonify({"release": RELEASE_MARKER, "git_commit": commit})


@app.get("/api/verification/diagnostics")
def api_verification_diagnostics():
    """Expose only non-secret provider capability/configuration state."""
    return jsonify({
        "verification_engine": "v2",
        "providers": provider_diagnostics(),
    })


__all__ = ["app"]
