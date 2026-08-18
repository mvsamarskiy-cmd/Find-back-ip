import os

from flask import jsonify

from telegram_integration import install


install()

from app import app  # noqa: E402


RELEASE_MARKER = "v5.1"


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


__all__ = ["app"]
