"""Production web bootstrap that layers private global search over NameMachine."""
from __future__ import annotations

from flask import jsonify

from telegram_bootstrap import app
import app as app_module
from private_mode import install_private_mode_routes, private_mode_diagnostics


install_private_mode_routes(app, app_module)

PRIVATE_GLOBAL_MODE_TAG = '<script src="/static/private_global_mode.js?v=1"></script>'


@app.after_request
def append_private_global_controller(response):
    if response.mimetype == "text/html":
        body = response.get_data(as_text=True)
        if PRIVATE_GLOBAL_MODE_TAG not in body and "</body>" in body:
            response.set_data(body.replace("</body>", PRIVATE_GLOBAL_MODE_TAG + "\n</body>", 1))
            response.headers.pop("Content-Length", None)
    return response


# Flask executes app-level after_request callbacks in reverse registration order.
# Move this callback to the front so it runs last, after telegram_bootstrap has
# appended every public controller. The private wrapper must see the final
# public startSearch/stopSearch implementations before it wraps them.
_callbacks = app.after_request_funcs.get(None, [])
if append_private_global_controller in _callbacks:
    _callbacks.remove(append_private_global_controller)
    _callbacks.insert(0, append_private_global_controller)


@app.get("/api/private-mode/diagnostics")
def api_private_mode_diagnostics():
    return jsonify(private_mode_diagnostics())


__all__ = ["app"]
