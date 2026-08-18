"""HTTP routes for explicit, platform-aware identifier variants.

The endpoint never checks availability itself. It only returns syntax-valid
candidate shapes after the caller explicitly opts into mutations; all returned
rows remain unverified until the ordinary NameMachine verifier checks them.
"""

from __future__ import annotations

import os

from flask import jsonify, request

from variant_grammar import (
    RESOURCE_KEYS,
    clean_variant_options,
    generate_variants_for_resources,
    mutation_capabilities,
)


VARIANT_RATE_LIMIT = os.environ.get("VARIANT_RATE_LIMIT", "120 per minute")
MAX_VARIANT_STEM = 63
MAX_VARIANTS_PER_RESOURCE = 50


def _normalize_resources(value):
    if isinstance(value, str):
        raw = [item.strip().lower() for item in value.split(",") if item.strip()]
    elif isinstance(value, (list, tuple)):
        raw = [str(item).strip().lower() for item in value if str(item).strip()]
    else:
        raise ValueError("resources must be a list or comma-separated string")

    output = []
    for resource in raw:
        if resource not in RESOURCE_KEYS:
            raise ValueError(f"Unsupported resource: {resource}")
        if resource not in output:
            output.append(resource)
    if not output:
        raise ValueError("At least one resource is required")
    return output


def variant_diagnostics():
    return {
        "supported": True,
        "user_opt_in_required": True,
        "clean_stem_searched_first": True,
        "availability_checked_here": False,
        "claimability_proved_here": False,
        "numbers_invented_automatically": False,
        "resources": {
            resource: mutation_capabilities(resource)
            for resource in RESOURCE_KEYS
        },
    }


def install_variant_routes(app, app_module):
    if "api_variant_grammar" in app.view_functions:
        return

    @app.get("/api/variant-grammar")
    @app_module.limiter.limit(VARIANT_RATE_LIMIT)
    def api_variant_grammar():
        return jsonify(variant_diagnostics())

    @app.post("/api/variants")
    @app_module.limiter.limit(VARIANT_RATE_LIMIT)
    def api_variants():
        data = app_module.json_object()
        if data is None:
            return jsonify({"error": "JSON body must be an object"}), 400

        stem = str(data.get("stem") or "").strip()
        if not stem:
            return jsonify({"error": "stem is required"}), 400
        if len(stem) > MAX_VARIANT_STEM:
            return jsonify({"error": f"stem must contain at most {MAX_VARIANT_STEM} characters"}), 400

        try:
            resources = _normalize_resources(data.get("resources"))
        except ValueError as error:
            return jsonify({"error": str(error), "allowed_resources": list(RESOURCE_KEYS)}), 400

        try:
            limit = int(data.get("per_resource_limit", 20))
        except (TypeError, ValueError):
            return jsonify({"error": "per_resource_limit must be an integer"}), 400
        if limit < 1 or limit > MAX_VARIANTS_PER_RESOURCE:
            return jsonify({
                "error": f"per_resource_limit must be between 1 and {MAX_VARIANTS_PER_RESOURCE}"
            }), 400

        options = clean_variant_options(data.get("options"))
        variants = generate_variants_for_resources(
            stem,
            resources,
            options,
            per_resource_limit=limit,
        )
        return jsonify({
            "stem": stem,
            "resources": resources,
            "options": options,
            "variants": variants,
            "semantics": {
                "clean_stem_searched_first": True,
                "availability": "unverified",
                "claimability": "unconfirmed",
                "verification_required": True,
            },
        })


__all__ = [
    "MAX_VARIANTS_PER_RESOURCE",
    "VARIANT_RATE_LIMIT",
    "install_variant_routes",
    "variant_diagnostics",
]
