import os

from flask import jsonify

from telegram_integration import install


install()

# Keep the historical import shape because production tests assert that the
# Telegram integration is installed before Flask app import. The module import
# below lets Verification v2 replace checker globals used by existing routes.
from app import app  # noqa: E402
import app as app_module  # noqa: E402
import ai_engine as ai_engine_module  # noqa: E402
from audit_api import install_audit_routes  # noqa: E402
from availability_v2 import check_all as check_all_v2, check_many as check_many_v2  # noqa: E402
from background_search_api import (  # noqa: E402
    background_search_diagnostics,
    install_background_search_routes,
)
from brand_collision import brand_collision_diagnostics  # noqa: E402
from brand_collision_api import install_brand_collision_routes  # noqa: E402
from browser_enrichment import browser_enrichment_diagnostics  # noqa: E402
from browser_queue import BROWSER_JOBS, install_candidate_enqueue  # noqa: E402
from candidate_events_api import install_candidate_event_routes  # noqa: E402
from creative_generation import (  # noqa: E402
    creative_generation_diagnostics,
    install_creative_generation,
)
from creative_lexicon import creative_lexicon_diagnostics  # noqa: E402
from durable_candidate_events import LIVE_CANDIDATES  # noqa: E402
from entry_mode_backend import install_entry_mode_intelligence  # noqa: E402
from final_ranking import install_final_ranking  # noqa: E402
import generic_naming_api as generic_naming_module  # noqa: E402
from generic_naming_api import install_generic_naming_routes  # noqa: E402
from ranking_persistence import install_ranking_persistence  # noqa: E402
import session_api as session_api_module  # noqa: E402
from session_api import install_session_routes, session_storage_diagnostics  # noqa: E402
from session_provenance import install_session_provenance  # noqa: E402
import streaming_search as streaming_search_module  # noqa: E402
from strict_claimability import (  # noqa: E402
    install_strict_claimability,
    strict_claimability_capabilities,
)
from variant_api import install_variant_routes, variant_diagnostics  # noqa: E402
from variant_session_api import install_variant_session_routes  # noqa: E402
from variant_store import VARIANT_STORE  # noqa: E402
from verification.diagnostics import provider_diagnostics  # noqa: E402

app_module.check_all = check_all_v2
app_module.check_many = check_many_v2
install_entry_mode_intelligence(app_module)
install_session_provenance(session_api_module)
install_ranking_persistence(session_api_module)
# A bounded local semantic graph gives GPT and the deterministic expander the
# same creative palette without another model/API call. app.py imported the
# generator by value, so install into both modules before routes are created.
install_creative_generation(ai_engine_module, app_module)
# Verification v4 keeps expensive authoritative assignment/registration checks
# outside the foreground critical path when production enables deferred mode.
# Browser absence can strengthen evidence, but this layer is the only stage that
# may turn a resource strict green.
install_strict_claimability()
# Candidate persistence happens asynchronously after the foreground NDJSON result
# is already visible. Attach the durable browser/claimability queue at that
# boundary so Chromium/WebKit/strict providers cannot extend search latency.
install_candidate_enqueue(session_api_module.STORE)
# Install ranking before route closures are created. This keeps one ranking
# contract across JSON generation, generic naming, and streamed final rows.
install_final_ranking(
    app_module,
    ai_module=ai_engine_module,
    generic_module=generic_naming_module,
    streaming_module=streaming_search_module,
)
streaming_search_module.install_streaming_routes(app, app_module)
install_session_routes(app, app_module)
install_audit_routes(app, app_module)
install_background_search_routes(app, app_module)
install_candidate_event_routes(app, app_module)
install_generic_naming_routes(app, app_module)
install_brand_collision_routes(app, app_module)
install_variant_routes(app, app_module)
install_variant_session_routes(app, app_module)


RELEASE_MARKER = "v8.12.0-ui-v2"
STREAM_CLIENT_TAG = '<script src="/static/streaming.js?v=2"></script>'
RESOURCE_PROGRESS_TAG = '<script src="/static/resource_progress.js"></script>'
SESSION_SYNC_TAG = '<script src="/static/session_sync.js?v=7"></script>'
BACKGROUND_SEARCH_TAG = '<script src="/static/background_search.js"></script>'
HUNTER_UI_TAG = '<script src="/static/availability_hunter_ui.js?v=4"></script>'
AUDIT_SYNC_TAG = '<script src="/static/audit_sync.js?v=5"></script>'
AUDIT_REPORT_TAG = '<script src="/static/audit_report.js?v=4"></script>'
CLIENT_REPORT_TAG = '<script src="/static/client_report.js?v=6"></script>'
CLIENT_REPORT_MODES_TAG = '<script src="/static/client_report_modes.js?v=1"></script>'
REPORT_CONTROLS_TAG = '<script src="/static/report_controls.js?v=5"></script>'
FEED_NAVIGATION_TAG = '<script src="/static/feed_navigation.js?v=3"></script>'
CLAIMABILITY_UI_TAG = '<script src="/static/claimability_ui.js?v=1"></script>'
ENTRY_MODES_TAG = '<script src="/static/entry_modes.js?v=1"></script>'
BRAND_COLLISION_UI_TAG = '<script src="/static/brand_collision_ui.js?v=1"></script>'
DURABLE_LIVE_EVENTS_TAG = '<script src="/static/durable_live_events.js?v=2"></script>'
UI_CLEANUP_TAG = '<script src="/static/ui_cleanup_r8.js?v=4"></script>'
VARIANT_EXPANSION_UI_TAG = '<script src="/static/variant_expansion_ui.js?v=1"></script>'
VARIANT_EXPANSION_SYNC_TAG = '<script src="/static/variant_expansion_sync.js?v=1"></script>'


@app.after_request
def prevent_stale_html(response):
    """Disable stale shells and load incremental clients on HTML pages."""
    if response.mimetype == "text/html":
        body = response.get_data(as_text=True)
        tags = []
        if STREAM_CLIENT_TAG not in body:
            tags.append(STREAM_CLIENT_TAG)
        if RESOURCE_PROGRESS_TAG not in body:
            tags.append(RESOURCE_PROGRESS_TAG)
        if SESSION_SYNC_TAG not in body:
            tags.append(SESSION_SYNC_TAG)
        if BACKGROUND_SEARCH_TAG not in body:
            tags.append(BACKGROUND_SEARCH_TAG)
        if HUNTER_UI_TAG not in body:
            tags.append(HUNTER_UI_TAG)
        if AUDIT_SYNC_TAG not in body:
            tags.append(AUDIT_SYNC_TAG)
        if AUDIT_REPORT_TAG not in body:
            tags.append(AUDIT_REPORT_TAG)
        if CLIENT_REPORT_TAG not in body:
            tags.append(CLIENT_REPORT_TAG)
        if CLIENT_REPORT_MODES_TAG not in body:
            tags.append(CLIENT_REPORT_MODES_TAG)
        if REPORT_CONTROLS_TAG not in body:
            tags.append(REPORT_CONTROLS_TAG)
        if FEED_NAVIGATION_TAG not in body:
            tags.append(FEED_NAVIGATION_TAG)
        if CLAIMABILITY_UI_TAG not in body:
            tags.append(CLAIMABILITY_UI_TAG)
        if ENTRY_MODES_TAG not in body:
            tags.append(ENTRY_MODES_TAG)
        if BRAND_COLLISION_UI_TAG not in body:
            tags.append(BRAND_COLLISION_UI_TAG)
        if DURABLE_LIVE_EVENTS_TAG not in body:
            tags.append(DURABLE_LIVE_EVENTS_TAG)
        if UI_CLEANUP_TAG not in body:
            tags.append(UI_CLEANUP_TAG)
        if VARIANT_EXPANSION_UI_TAG not in body:
            tags.append(VARIANT_EXPANSION_UI_TAG)
        # Sync is an overlay on the visible expansion controller and must load last.
        if VARIANT_EXPANSION_SYNC_TAG not in body:
            tags.append(VARIANT_EXPANSION_SYNC_TAG)
        if tags and "</body>" in body:
            response.set_data(body.replace("</body>", "\n".join(tags) + "\n</body>", 1))
            response.headers.pop("Content-Length", None)
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
    providers["telegram_positive_ensemble"] = {
        "configured": True,
        "no_api_key": True,
        "live": True,
        "positive_only": True,
        "sources": ["legacy_t_me", "fragment_public_web", "whatsmyname_positive_only"],
        "negative_evidence_promoted": False,
        "fragment_marketplace_available_is_free_claimable": False,
        "authoritative_claimability": False,
    }
    return jsonify({
        "verification_engine": "v2",
        "verification_pipeline": {
            # Keep the historical field stable for clients while advertising the
            # newer architecture/stages explicitly below.
            "version": "v3.1",
            "architecture_version": "v4",
            "strict_claimability_version": "strict-v1",
            "order": [
                "generation",
                "local_filters",
                "fast_network_sensors",
                "durable_candidate_boundary",
                "async_chromium_eye",
                "selective_webkit_eye",
                "sparse_search_eye",
                "evidence_fusion",
                "authoritative_claimability",
                "final_ranking",
            ],
            "browser_intelligence": browser_enrichment_diagnostics(),
            "strict_claimability": strict_claimability_capabilities(),
            "browser_queue": BROWSER_JOBS.diagnostics(),
            "foreground_and_background_share_browser_pipe": True,
            "fast_results_blocked_by_browser": False,
            "fast_results_blocked_by_claimability": False,
        },
        "generation_intelligence": {
            "creative_lexicon": creative_lexicon_diagnostics(),
            "creative_generation": creative_generation_diagnostics(),
        },
        "final_ranking": {
            "enabled": True,
            "model": "final-v1",
            "dimensions": [
                "name_quality_score",
                "user_fit_score",
                "availability_opportunity_score",
                "availability_evidence_confidence_score",
            ],
            "semantic_state_field": "bundle_availability_state",
            "strict_free_state": "claimable",
            "paid_state": "purchasable",
            "absence_only_state": "promising",
            "availability_can_rewrite_semantic_truth": False,
            "durable_scores": True,
        },
        "entry_modes": {
            "supported": True,
            "modes": ["brand", "identity", "generic_name", "other"],
            "generic_name_verification": False,
            "explicit_mode_overrides_ai_inference": True,
        },
        "brand_collision": brand_collision_diagnostics(),
        "variant_grammar": variant_diagnostics(),
        "variant_storage": VARIANT_STORE.diagnostics(),
        "strict_free_semantics": {
            "green_status": "claimable",
            "purchasable_is_green": False,
            "not_found_is_green": False,
            "double_browser_absence_is_green": False,
            "authoritative_provider_required": True,
        },
        "streaming_feed": {
            "enabled": True,
            "transport": "ndjson",
            "endpoint": "/api/ai-generate-stream",
            "newest_first_feed": True,
            "candidate_events": True,
            "resource_progress_events": True,
            "pre_generation_phase_events": True,
            "operational_activity_only": True,
            "browser_enrichment_after_persist": True,
            "strict_claimability_after_browser": True,
        },
        "durable_candidate_events": LIVE_CANDIDATES.diagnostics(),
        "large_feed_navigation": {
            "enabled": True,
            "newest_first": True,
            "alphabetical_sort": False,
            "pagination": True,
            "render_page_size": 25,
            "views_paginated": ["feed", "recommended", "shortlist"],
            "filters": ["all", "confirmed", "promising", "conflict", "unresolved"],
            "turbo_primary_feed_strict_free_only": True,
        },
        "background_search_ui": {
            "enabled_when_worker_ready": True,
            "candidate_delta_endpoint": "/api/sessions/<session_id>/candidate-feed",
            "candidate_lifecycle_endpoint": "/api/sessions/<session_id>/candidate-events",
            "candidate_page_size": 100,
            "lifecycle_poll_ms": 900,
            "targets": [500, 1000, 5000, 20000],
            "availability_hunter_api": True,
            "result_goal_field": "target_matches",
            "budget_field": "max_checks",
            "default_search_strategy": "procedural",
            "search_strategies": ["procedural", "turbo"],
            "procedural_focus_visible": True,
            "telemetry_default": "compact",
            "technical_details_toggle": True,
            "report_preview_closable": True,
            "variant_expansion_ui": True,
            "variant_expansion_durable_sync": True,
        },
        "session_storage": session_storage_diagnostics(),
        "background_search": background_search_diagnostics(),
        "providers": providers,
    })


__all__ = ["app"]
