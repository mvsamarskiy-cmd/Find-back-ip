import os

from flask import jsonify

from telegram_integration import install


install()

# Keep the historical import shape because production tests assert that the
# Telegram integration is installed before Flask app import. The module import
# below lets Verification v2 replace checker globals used by existing routes.
from app import app  # noqa: E402
import app as app_module  # noqa: E402
from availability_v2 import check_all as check_all_v2, check_many as check_many_v2  # noqa: E402
from verification.diagnostics import provider_diagnostics  # noqa: E402

app_module.check_all = check_all_v2
app_module.check_many = check_many_v2


RELEASE_MARKER = "v6.6-tiktok-oembed"


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
    providers = provider_diagnostics()
    providers["socialscan"] = {
        "configured": True,
        "no_api_key": True,
        "live_platforms": ["x"],
        "benchmark_only_platforms": ["instagram"],
        "claimable_promoted": False,
    }
    providers["instagram_web_profile_info"] = {
        "configured": True,
        "no_api_key": True,
        "live": False,
        "benchmark_only": True,
        "authoritative_claimability": False,
    }
    providers["meta_instagram_oembed"] = {
        "configured": True,
        "no_api_key": True,
        "official_meta_endpoint": True,
        "live": True,
        "positive_only": True,
        "can_confirm_occupancy": True,
        "authoritative_claimability": False,
    }
    providers["tiktok_oembed"] = {
        "configured": True,
        "no_api_key": True,
        "official_tiktok_endpoint": True,
        "live": True,
        "positive_only": True,
        "can_confirm_occupancy": True,
        "authoritative_claimability": False,
    }
    return jsonify({
        "verification_engine": "v2",
        "providers": providers,
    })


__all__ = ["app"]
