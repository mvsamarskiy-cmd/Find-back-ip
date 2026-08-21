"""Answer-synthesis layer over the proven Universal Search v3 router.

Search planning and provider execution remain owned by universal_search_multi.
This module only adds a deterministic, provenance-preserving synthesis object.
"""
from __future__ import annotations

import requests

import universal_search_multi as multi_search
from evidence_synthesis import evidence_synthesis_capabilities, synthesize_search_payload


def search_universal(
    query,
    *,
    category="all",
    country="EU",
    requester=requests.get,
    poster=requests.post,
    opportunity_searcher=None,
    general_searcher=None,
    module_searcher=None,
    multi_searcher=None,
    synthesizer=synthesize_search_payload,
):
    """Run Universal Search v3, then attach deterministic evidence synthesis."""
    kwargs = {
        "category": category,
        "country": country,
        "requester": requester,
        "poster": poster,
    }
    if opportunity_searcher is not None:
        kwargs["opportunity_searcher"] = opportunity_searcher
    if general_searcher is not None:
        kwargs["general_searcher"] = general_searcher
    if module_searcher is not None:
        kwargs["module_searcher"] = module_searcher
    if multi_searcher is not None:
        kwargs["multi_searcher"] = multi_searcher

    payload = multi_search.search_universal(query, **kwargs)
    payload["synthesis"] = synthesizer(payload)
    return payload


def universal_search_capabilities() -> dict:
    payload = dict(multi_search.universal_search_capabilities())
    payload.update({
        "intelligence_version": "universal-router-v4",
        "answer_synthesis": evidence_synthesis_capabilities(),
    })
    return payload


__all__ = ["search_universal", "universal_search_capabilities"]
