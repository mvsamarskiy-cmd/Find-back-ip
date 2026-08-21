"""Production web bootstrap that layers private global search over NameMachine."""
from __future__ import annotations

from flask import jsonify

from telegram_bootstrap import app
import app as app_module
from global_search_provider_smoke import maybe_start_provider_smoke
from private_mode import install_private_mode_routes, private_mode_diagnostics
from private_research import install_private_research_routes, private_research_diagnostics
from universal_search_tor import search_universal, universal_search_capabilities


install_private_mode_routes(app, app_module, global_searcher=search_universal)
install_private_research_routes(app, app_module)
maybe_start_provider_smoke()

PRIVATE_GLOBAL_MODE_TAG = '<script src="/static/private_global_mode.js?v=2"></script>'
UNIVERSAL_GLOBAL_MODE_TAG = '<script src="/static/universal_global_mode.js?v=2"></script>'
MONEY_OPPORTUNITY_UI_TAG = '<script src="/static/money_opportunity_ui.js?v=1"></script>'
MONEY_ELIGIBILITY_UI_TAG = '<script src="/static/money_eligibility_ui.js?v=1"></script>'
PRIVATE_RESEARCH_BROWSER_TAG = '<script src="/static/private_research_browser.js?v=1"></script>'
PRIVATE_GLOBAL_MODE_BUNDLE = "\n".join((
    PRIVATE_GLOBAL_MODE_TAG,
    UNIVERSAL_GLOBAL_MODE_TAG,
    MONEY_OPPORTUNITY_UI_TAG,
    MONEY_ELIGIBILITY_UI_TAG,
    PRIVATE_RESEARCH_BROWSER_TAG,
))


@app.after_request
def append_private_global_controller(response):
    if response.mimetype == "text/html":
        body = response.get_data(as_text=True)
        if PRIVATE_GLOBAL_MODE_TAG not in body and "</body>" in body:
            response.set_data(body.replace("</body>", PRIVATE_GLOBAL_MODE_BUNDLE + "\n</body>", 1))
            response.headers.pop("Content-Length", None)
    return response


_callbacks = app.after_request_funcs.get(None, [])
if append_private_global_controller in _callbacks:
    _callbacks.remove(append_private_global_controller)
    _callbacks.insert(0, append_private_global_controller)


@app.get("/api/private-mode/diagnostics")
def api_private_mode_diagnostics():
    payload = private_mode_diagnostics()
    payload["universal_search"] = universal_search_capabilities()
    payload["research_evidence"] = private_research_diagnostics()
    return jsonify(payload)


__all__ = ["app"]
