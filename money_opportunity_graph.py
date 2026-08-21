"""Evidence-aware Opportunity Graph for Money Intelligence v2.3.

The graph unifies search records into call, program-candidate, organization,
source-observation and constraint nodes. Strong edges are created only from
observed evidence. Similarity-based relationships are explicitly labelled as
candidates and never become legal/factual identity claims by themselves.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


OPPORTUNITY_GRAPH_VERSION = "money-opportunity-graph-v2.3"
MAX_GRAPH_NODES = 500
MAX_GRAPH_EDGES = 1000

_STOPWORDS = {
    "the", "and", "for", "with", "from", "open", "call", "programme", "program", "fund",
    "funding", "grant", "grants", "support", "application", "applications", "poland", "europe",
    "european", "eu", "dla", "oraz", "program", "nabór", "nabor", "konkurs", "dotacja",
    "dofinansowanie", "wsparcie", "fundusz", "підтримка", "грант", "програма", "конкурс",
}
_TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid", "ref"}
_REFERENCE_PATTERNS = (
    re.compile(r"\b(?:call|reference|ref\.?|project|competition|tender|procedure|notice)\s*(?:no\.?|number|id|#|:)\s*([A-Z0-9][A-Z0-9._/\-]{2,40})\b", re.I),
    re.compile(r"\b(?:nr|numer|oznaczenie|postępowanie|postepowanie)\s*(?:[:#]|nr)?\s*([A-Z0-9][A-Z0-9._/\-]{2,40})\b", re.I),
    re.compile(r"\b(?:номер|ідентифікатор|id)\s*(?:[:#№])?\s*([A-Z0-9][A-Z0-9._/\-]{2,40})\b", re.I),
)
_CONSTRAINT_PATTERNS = {
    "de_minimis": (
        r"\bde[ -]?minimis\b", r"\bpomoc de minimis\b", r"\bдопомог\w* de minimis\b",
    ),
    "double_financing_restriction": (
        r"\bdouble funding\b", r"\bdouble financ(?:ing|ed)\b", r"\bsame costs? (?:cannot|may not) be financed\b",
        r"\bpodw[oó]jn\w* finansowan\w*\b", r"\btych samych koszt[oó]w\b", r"\bподвійн\w* фінансуван\w*\b",
    ),
    "state_aid": (
        r"\bstate aid\b", r"\bpomoc publiczn\w*\b", r"\bдержавн\w* допомог\w*\b",
    ),
    "own_contribution": (
        r"\bown contribution\b", r"\bco-?financing\b", r"\bwklad wlasny\b", r"\bwkład własny\b", r"\bвласн\w* внесок\b",
    ),
}


def _clean(value: object, limit: int = 2000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _slug(value: object) -> str:
    text = _clean(value, 600).casefold()
    text = re.sub(r"[^0-9a-ząćęłńóśźżа-яіїєґ]+", "-", text, flags=re.I).strip("-")
    return text[:120] or "unknown"


def _id(prefix: str, *parts: object) -> str:
    material = "|".join(_clean(part, 1000).casefold() for part in parts)
    return f"{prefix}_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:18]


def _canonical_url(value: object) -> str:
    raw = _clean(value, 3000)
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if not scheme or not host:
        return raw
    port = parsed.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.casefold() not in _TRACKING_KEYS))
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, query, ""))


def _tokens(value: object) -> set[str]:
    words = re.findall(r"[0-9a-ząćęłńóśźżа-яіїєґ]{3,}", _clean(value, 1000).casefold(), flags=re.I)
    return {word for word in words if word not in _STOPWORDS and not word.isdigit()}


def _program_key(record: dict) -> str:
    title = _clean(record.get("title"), 600)
    # Remove common call-cycle/date noise but retain substantive programme words.
    title = re.sub(r"\b(?:19|20)\d{2}(?:[/\-](?:19|20)?\d{2})?\b", " ", title)
    title = re.sub(r"\b(?:open call|call for proposals?|nab[oó]r|nabor|konkurs|round|edition|edycja|етап|раунд)\b", " ", title, flags=re.I)
    tokens = sorted(_tokens(title))
    counterparty = _slug(record.get("funder_or_counterparty") or "")
    core = " ".join(tokens[:16]) or _slug(title)
    return f"{counterparty}|{core}"


def _extract_references(record: dict) -> list[dict]:
    text = " ".join((_clean(record.get("title"), 800), _clean(record.get("description"), 3000)))
    output = []
    seen = set()
    for pattern in _REFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1).strip(".,;:()[]{}").upper()
            if value in seen:
                continue
            seen.add(value)
            output.append({"value": value, "evidence": _clean(text[max(0, match.start()-80):match.end()+80], 220)})
    return output[:8]


def _constraints(record: dict) -> list[dict]:
    text = " ".join((_clean(record.get("title"), 700), _clean(record.get("description"), 4000)))
    lower = text.casefold()
    output = []
    for kind, patterns in _CONSTRAINT_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, lower, flags=re.I)
            if match:
                output.append({
                    "kind": kind,
                    "evidence": _clean(text[max(0, match.start()-100):match.end()+100], 260),
                    "source_level": "retrieval_or_normalized_text",
                })
                break
    return output


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _node(nodes: dict, node_id: str, node_type: str, **fields) -> str:
    current = nodes.get(node_id)
    payload = {"id": node_id, "type": node_type, **fields}
    if current:
        # Never let a later weak observation erase previously retained fields.
        for key, value in payload.items():
            if value not in (None, "", [], {}) and current.get(key) in (None, "", [], {}):
                current[key] = value
    else:
        nodes[node_id] = payload
    return node_id


def _edge(edges: list, seen: set, source: str, relation: str, target: str, *, confidence: float, evidence: list | None = None, state: str = "observed"):
    key = (source, relation, target)
    if key in seen or len(edges) >= MAX_GRAPH_EDGES:
        return
    seen.add(key)
    edges.append({
        "source": source,
        "relation": relation,
        "target": target,
        "state": state,
        "confidence": round(float(confidence), 3),
        "evidence": [item for item in (evidence or []) if item][:6],
    })


def build_opportunity_graph(records: list[dict]) -> dict:
    """Build one deterministic graph for a normalized Money search payload."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    edge_seen: set[tuple] = set()
    call_meta = []
    now = datetime.now(timezone.utc).isoformat()

    for record in records or []:
        if not isinstance(record, dict) or len(nodes) >= MAX_GRAPH_NODES:
            continue
        title = _clean(record.get("title"), 700) or "Untitled opportunity"
        record_id = _clean(record.get("opportunity_id"), 120) or _id("call", title, record.get("opportunity_type"), record.get("deadline"))
        call_id = record_id if record_id.startswith("call_") else _id("call", record_id)
        references = _extract_references(record)
        source_urls = [_canonical_url(url) for url in (record.get("source_urls") or []) if _canonical_url(url)]
        counterparty = _clean(record.get("funder_or_counterparty"), 500)
        organization_id = _id("org", counterparty or "unknown-counterparty")
        program_key = _program_key(record)
        program_id = _id("program", program_key)

        _node(
            nodes, call_id, "call",
            opportunity_id=record_id,
            title=title,
            opportunity_type=record.get("opportunity_type"),
            family=record.get("family"),
            status=record.get("status"),
            deadline=record.get("deadline"),
            current_call_verified=bool(record.get("current_call_verified")),
            eligibility_state=record.get("eligibility_state"),
            practical_score=(record.get("practical_ranking") or {}).get("score"),
            explicit_references=[item["value"] for item in references],
        )
        _node(nodes, program_id, "program_candidate", label=title, program_key=program_key, state="candidate_group")
        _edge(edges, edge_seen, program_id, "program_contains_call_candidate", call_id, confidence=0.62, evidence=["deterministic normalized programme key"], state="candidate")

        if counterparty:
            _node(nodes, organization_id, "organization", name=counterparty, identity_state="observed_label_not_legal_entity_verified")
            _edge(edges, edge_seen, call_id, "offered_by_observed_counterparty", organization_id, confidence=0.72, evidence=[counterparty], state="observed_label")

        for url in source_urls:
            source_id = _id("source", url)
            host = (urlsplit(url).hostname or "").lower() if url else ""
            _node(
                nodes, source_id, "source_observation",
                url=url, host=host,
                transport=(record.get("retrieval") or {}).get("transport") or "web",
                source_observed=bool(record.get("source_observed")),
                snapshot_sha256=((record.get("direct_verification") or {}).get("snapshot_sha256")),
                observed_at=((record.get("direct_verification") or {}).get("observed_at")),
            )
            _edge(edges, edge_seen, call_id, "observed_at", source_id, confidence=1.0, evidence=[url])

        for constraint in _constraints(record):
            constraint_id = _id("constraint", constraint["kind"])
            _node(nodes, constraint_id, "constraint", kind=constraint["kind"], scope="requires_rule_level_confirmation")
            _edge(edges, edge_seen, call_id, "subject_to_observed_constraint", constraint_id, confidence=0.7, evidence=[constraint["evidence"]], state="observed_text")

        call_meta.append({
            "call_id": call_id,
            "program_id": program_id,
            "title": title,
            "tokens": _tokens(title),
            "counterparty_key": _slug(counterparty),
            "references": {item["value"] for item in references},
            "source_urls": set(source_urls),
        })

    # Cross-call relationships. Explicit references are strong evidence. Title
    # similarity is never promoted to factual identity.
    for index, left in enumerate(call_meta):
        for right in call_meta[index + 1:]:
            shared_refs = sorted(left["references"] & right["references"])
            if shared_refs:
                _edge(
                    edges, edge_seen, left["call_id"], "same_call_candidate", right["call_id"],
                    confidence=0.92, evidence=[f"shared explicit reference {ref}" for ref in shared_refs], state="candidate_needs_authoritative_confirmation",
                )
                continue
            shared_urls = sorted(left["source_urls"] & right["source_urls"])
            if shared_urls:
                _edge(
                    edges, edge_seen, left["call_id"], "same_call_candidate", right["call_id"],
                    confidence=0.98, evidence=[f"same canonical source {shared_urls[0]}"], state="candidate",
                )
                continue
            similarity = _jaccard(left["tokens"], right["tokens"])
            if left["counterparty_key"] != "unknown" and left["counterparty_key"] == right["counterparty_key"] and similarity >= 0.62:
                _edge(
                    edges, edge_seen, left["call_id"], "same_program_candidate", right["call_id"],
                    confidence=min(0.88, 0.55 + similarity * 0.35),
                    evidence=[f"same observed counterparty label; title token similarity {similarity:.2f}"],
                    state="similarity_candidate_not_identity_fact",
                )

    node_list = list(nodes.values())[:MAX_GRAPH_NODES]
    by_type = {}
    for item in node_list:
        by_type[item["type"]] = by_type.get(item["type"], 0) + 1
    by_relation = {}
    for item in edges:
        by_relation[item["relation"]] = by_relation.get(item["relation"], 0) + 1

    return {
        "version": OPPORTUNITY_GRAPH_VERSION,
        "generated_at": now,
        "nodes": node_list,
        "edges": edges[:MAX_GRAPH_EDGES],
        "summary": {
            "nodes": len(node_list),
            "edges": len(edges[:MAX_GRAPH_EDGES]),
            "by_type": by_type,
            "by_relation": by_relation,
        },
        "combination_analysis": {
            "state": "not_inferred_without_rule_evidence",
            "confirmed_combinations": 0,
            "confirmed_conflicts": 0,
            "note": "Shared constraints such as de minimis or double-financing rules are evidence nodes; pairwise legal compatibility is not inferred from category similarity.",
        },
        "truth_semantics": {
            "source_edge": "observed_url_relation",
            "counterparty_edge": "observed_label_not_verified_legal_entity",
            "same_call_candidate": "candidate_identity_not_fact_without_authoritative_confirmation",
            "same_program_candidate": "similarity_candidate_only",
            "program_node": "deterministic_candidate_group_not_official_program_identity",
        },
    }


def attach_graph_to_payload(payload: dict) -> dict:
    result = dict(payload or {})
    graph = build_opportunity_graph(result.get("money_records") or [])
    result["opportunity_graph"] = graph
    # Lightweight graph references on records make UI/card correlation cheap.
    call_by_opportunity = {
        node.get("opportunity_id"): node.get("id")
        for node in graph.get("nodes") or [] if node.get("type") == "call"
    }
    for record in result.get("money_records") or []:
        opportunity_id = record.get("opportunity_id")
        record["graph_call_id"] = call_by_opportunity.get(opportunity_id)
    return result


def opportunity_graph_capabilities() -> dict:
    return {
        "version": OPPORTUNITY_GRAPH_VERSION,
        "node_types": ["call", "program_candidate", "organization", "source_observation", "constraint"],
        "relations": [
            "program_contains_call_candidate", "offered_by_observed_counterparty", "observed_at",
            "subject_to_observed_constraint", "same_call_candidate", "same_program_candidate",
        ],
        "explicit_reference_identity_evidence": True,
        "canonical_source_identity_evidence": True,
        "similarity_promoted_to_fact": False,
        "legal_combination_inferred_without_rules": False,
        "persistent_across_searches": False,
        "truth_semantics": "evidence_graph_with_candidate_identity_edges",
    }


__all__ = [
    "MAX_GRAPH_EDGES", "MAX_GRAPH_NODES", "OPPORTUNITY_GRAPH_VERSION",
    "attach_graph_to_payload", "build_opportunity_graph", "opportunity_graph_capabilities",
]
