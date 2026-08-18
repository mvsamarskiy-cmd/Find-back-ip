"""HTTP routes for explicit, platform-aware identifier variants.

Variant generation is deliberately separate from availability evidence. The
``/api/variants`` endpoint only creates syntax-valid shapes after explicit user
opt-in. ``/api/variants/check`` then sends one exact platform identifier through
the normal Verification v2 stack without stripping punctuation or digits.
"""

from __future__ import annotations

import os

from flask import jsonify

from variant_grammar import (
    RESOURCE_KEYS,
    clean_variant_options,
    generate_variants_for_resources,
    mutation_capabilities,
    validate_variant_shape,
)


VARIANT_RATE_LIMIT = os.environ.get("VARIANT_RATE_LIMIT", "120 per minute")
VARIANT_CHECK_RATE_LIMIT = os.environ.get("VARIANT_CHECK_RATE_LIMIT", "60 per minute")
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


def _single_resource(value):
    resource = str(value or "").strip().lower()
    if resource not in RESOURCE_KEYS:
        raise ValueError(f"Unsupported resource: {resource or value!r}")
    return resource


def _identifier(value):
    return str(value or "").strip().lower().lstrip("@")[:MAX_VARIANT_STEM]


def variant_diagnostics():
    return {
        "supported": True,
        "user_opt_in_required": True,
        "clean_stem_searched_first": True,
        "availability_checked_here": False,
        "claimability_proved_here": False,
        "numbers_invented_automatically": False,
        "generation_endpoint": "/api/variants",
        "verification_endpoint": "/api/variants/check",
        "verification_uses_normal_engine": True,
        "strict_free_status": "claimable",
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

    @app.post("/api/variants/check")
    @app_module.limiter.limit(VARIANT_CHECK_RATE_LIMIT)
    def api_check_variant():
        """Verify one exact platform identifier without normalizing it to letters-only."""
        data = app_module.json_object()
        if data is None:
            return jsonify({"error": "JSON body must be an object"}), 400
        try:
            resource = _single_resource(data.get("resource"))
        except ValueError as error:
            return jsonify({"error": str(error), "allowed_resources": list(RESOURCE_KEYS)}), 400

        identifier = _identifier(data.get("identifier"))
        if not identifier:
            return jsonify({"error": "identifier is required"}), 400
        if not validate_variant_shape(resource, identifier):
            return jsonify({
                "error": "identifier is not valid for the selected platform grammar",
                "resource": resource,
                "identifier": identifier,
            }), 400

        try:
            checked = app_module.check_all(identifier, resources=[resource])
        except Exception as error:
            app.logger.warning(
                "Variant verification failed for %s: %s",
                resource,
                type(error).__name__,
            )
            return jsonify({
                "error": "Variant verification is temporarily unavailable",
                "error_type": type(error).__name__,
            }), 503

        if not isinstance(checked, dict):
            return jsonify({"error": "Variant verifier returned an invalid response"}), 503
        availability_map = checked.get("availability")
        availability = (
            availability_map.get(resource)
            if isinstance(availability_map, dict)
            else None
        )
        if not isinstance(availability, dict):
            return jsonify({"error": "Variant verifier omitted availability evidence"}), 503
        verification_map = checked.get("verification")
        verification = (
            verification_map.get(resource)
            if isinstance(verification_map, dict)
            else None
        )
        status = str(availability.get("status") or "unknown")

        return jsonify({
            "resource": resource,
            "identifier": identifier,
            "availability": availability,
            "verification": verification if isinstance(verification, dict) else None,
            "strict_free": status == "claimable",
            "purchasable": status == "purchasable",
            "status": status,
            "semantics": {
                "claimable_is_green": True,
                "purchasable_is_green": False,
                "not_found_is_green": False,
            },
        })


__all__ = [
    "MAX_VARIANTS_PER_RESOURCE",
    "VARIANT_CHECK_RATE_LIMIT",
    "VARIANT_RATE_LIMIT",
    "install_variant_routes",
    "variant_diagnostics",
]
