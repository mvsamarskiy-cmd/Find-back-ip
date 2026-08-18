"""Flask routes for conservative brand-collision screening."""
from __future__ import annotations

from brand_collision import brand_collision_diagnostics, build_brand_collision


def install_brand_collision_routes(app, app_module):
    if "api_brand_collision" in app.view_functions:
        return

    @app.post("/api/brand-collision")
    @app_module.limiter.limit(app_module.CHECK_RATE_LIMIT)
    def api_brand_collision():
        data = app_module.json_object()
        if data is None:
            return app_module.jsonify({"error": "JSON body must be an object"}), 400
        name = " ".join(str(data.get("name") or "").split())
        if len(name) < 2:
            return app_module.jsonify({"error": "Brand candidate is required"}), 400
        if len(name) > 80:
            return app_module.jsonify({"error": "Brand candidate is too long"}), 400
        context = data.get("context") if isinstance(data.get("context"), dict) else {}
        try:
            result = build_brand_collision(name, context)
        except ValueError as error:
            return app_module.jsonify({"error": str(error)}), 400
        except Exception as error:
            app.logger.warning("Brand collision screening failed: %s", type(error).__name__)
            return app_module.jsonify({
                "error": "Temporary brand-collision screening error. Please try again.",
                "error_type": type(error).__name__,
            }), 503
        return app_module.jsonify(result)

    @app.get("/api/brand-collision/diagnostics")
    def api_brand_collision_diagnostics():
        return app_module.jsonify(brand_collision_diagnostics())


__all__ = ["install_brand_collision_routes"]
