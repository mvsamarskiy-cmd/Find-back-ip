"""Production web bootstrap that layers private global search over NameMachine."""
from __future__ import annotations

from flask import jsonify

from telegram_bootstrap import app
import app as app_module
from global_search_provider_smoke import maybe_start_provider_smoke
from money_opportunity_graph_search import search_money_opportunities as search_money_with_graph
from private_mode import install_private_mode_routes, private_mode_diagnostics
from private_research import install_private_research_routes, private_research_diagnostics
from search_query_quality import (
    apply_general_relevance_guard,
    looks_like_business_idea_query,
    query_quality_capabilities,
    search_business_ideas,
)
from universal_search_tor import search_universal, universal_search_capabilities


def search_private_universal(
    query, *, category="all", country="EU", requester=None, poster=None,
    cancel_checker=None,
):
    """Keep Universal Search intact while adding private query-quality safeguards."""
    requested_category = str(category or "all").strip().lower().replace("-", "_")

    # Business-idea discovery is a research intent, not automatically a grant or
    # Money claim. Detect it only when the user left the Money category on ALL.
    # The specialized search preserves the exact original query as lane 0, then
    # uses a bounded typo repair / English market-discovery expansion.
    if requested_category == "all" and looks_like_business_idea_query(query):
        idea_kwargs = {"country": country}
        if requester is not None:
            idea_kwargs["requester"] = requester
        if poster is not None:
            idea_kwargs["poster"] = poster
        if cancel_checker is not None:
            idea_kwargs["cancel_checker"] = cancel_checker
        return search_business_ideas(query, **idea_kwargs)

    kwargs = {"category": category, "country": country}
    if requester is not None:
        kwargs["requester"] = requester
    if poster is not None:
        kwargs["poster"] = poster
    if cancel_checker is not None:
        def cancellable_money(*args, **money_kwargs):
            money_kwargs["cancel_checker"] = cancel_checker
            return search_money_with_graph(*args, **money_kwargs)
        kwargs["opportunity_searcher"] = cancellable_money

    payload = search_universal(query, **kwargs)
    # Generic web provider rank is not semantic relevance. A zero-overlap page
    # must not survive merely because a search engine returned it near the top.
    return apply_general_relevance_guard(payload, query=query)


install_private_mode_routes(app, app_module, global_searcher=search_private_universal)
install_private_research_routes(app, app_module)
maybe_start_provider_smoke()

PRIVATE_GLOBAL_MODE_TAG = '<script src="/static/private_global_mode.js?v=3"></script>'
UNIVERSAL_GLOBAL_MODE_TAG = '<script src="/static/universal_global_mode.js?v=2"></script>'
MONEY_OPPORTUNITY_UI_TAG = '<script src="/static/money_opportunity_ui.js?v=1"></script>'
MONEY_ELIGIBILITY_UI_TAG = '<script src="/static/money_eligibility_ui.js?v=1"></script>'
MONEY_GRAPH_UI_TAG = '<script src="/static/money_graph_ui.js?v=1"></script>'
PRIVATE_MONEY_CONTROLS_TAG = '<script src="/static/private_money_controls_v24.js?v=1"></script>'
PRIVATE_RESEARCH_BROWSER_TAG = '<script src="/static/private_research_browser.js?v=1"></script>'
PRIVATE_STOP_MOBILE_FIX_TAG = '<script src="/static/private_stop_mobile_fix.js?v=1"></script>'
PRIVATE_RESULTS_PAGE_SCROLL_FIX_TAG = '<script src="/static/private_results_page_scroll_fix.js?v=1"></script>'
PRIVATE_MONEY_REPORT_TAG = '<script src="/static/private_money_report.js?v=1"></script>'
PRIVATE_REPORT_RUN_IDENTITY_TAG = '<script src="/static/private_report_run_identity.js?v=2"></script>'
PRIVATE_RESULT_EXPLAINER_TAG = '<script src="/static/private_result_explainer.js?v=1"></script>'
PRIVATE_GLOBAL_MODE_BUNDLE = "\n".join((
    PRIVATE_GLOBAL_MODE_TAG,
    UNIVERSAL_GLOBAL_MODE_TAG,
    MONEY_OPPORTUNITY_UI_TAG,
    MONEY_ELIGIBILITY_UI_TAG,
    MONEY_GRAPH_UI_TAG,
    PRIVATE_MONEY_CONTROLS_TAG,
    PRIVATE_RESEARCH_BROWSER_TAG,
    PRIVATE_STOP_MOBILE_FIX_TAG,
    PRIVATE_RESULTS_PAGE_SCROLL_FIX_TAG,
    PRIVATE_MONEY_REPORT_TAG,
    PRIVATE_REPORT_RUN_IDENTITY_TAG,
    PRIVATE_RESULT_EXPLAINER_TAG,
))

# PR #134 changed report_controls.js but kept its old ?v=5 URL. Existing iPhone
# sessions can therefore execute the cached pre-fix file, which dynamically loads
# search_reliability_overlay.js?v=1 in addition to the canonical v2 tag. Rewrite
# only the asset version in the production HTML shell so clients fetch the fixed
# controls. This does not change report semantics or expose private-mode state.
STALE_REPORT_CONTROLS_TAG = '<script src="/static/report_controls.js?v=5"></script>'
FRESH_REPORT_CONTROLS_TAG = '<script src="/static/report_controls.js?v=6"></script>'


@app.after_request
def append_private_global_controller(response):
    if response.mimetype == "text/html":
        body = response.get_data(as_text=True)
        if STALE_REPORT_CONTROLS_TAG in body:
            body = body.replace(STALE_REPORT_CONTROLS_TAG, FRESH_REPORT_CONTROLS_TAG)
        if PRIVATE_GLOBAL_MODE_TAG not in body and "</body>" in body:
            body = body.replace("</body>", PRIVATE_GLOBAL_MODE_BUNDLE + "\n</body>", 1)
        if body != response.get_data(as_text=True):
            response.set_data(body)
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
    payload["query_quality"] = query_quality_capabilities()
    payload["research_evidence"] = private_research_diagnostics()
    return jsonify(payload)


__all__ = ["app", "search_private_universal"]
