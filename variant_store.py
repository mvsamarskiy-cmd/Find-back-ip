"""Durable, bounded storage for per-candidate variant expansion results.

Variant identifiers are resource-specific and must not be inserted into the main
cross-platform candidate table. This store keeps them in a separate session-owned
namespace while preserving strict status semantics and a compact evidence summary.
"""

from __future__ import annotations

import json
import re

from sqlalchemy import Column, DateTime, ForeignKey, JSON, PrimaryKeyConstraint, String, Table, insert, select, update

from session_store import STORE, SessionStore, _iso, _utcnow, metadata, sessions


VARIANT_STORE_SCHEMA_VERSION = 1
MAX_EXPANSION_BYTES = 32000
MAX_RESULTS = 24
RESOURCES = {"com", "instagram", "telegram", "tiktok", "youtube", "facebook", "x"}
STATUSES = {"claimable", "purchasable", "taken", "not_found", "invalid", "reserved", "rate_limited", "unknown"}
OPTION_KEYS = {"underscore", "digits", "dots", "hyphen", "prefix", "suffix"}


variant_expansions = Table(
    "nm_variant_expansions",
    metadata,
    Column("session_id", String(36), ForeignKey("nm_sessions.id", ondelete="CASCADE"), nullable=False),
    Column("parent_name_key", String(96), nullable=False),
    Column("parent_name", String(96), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("session_id", "parent_name_key"),
)


def _text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _parent_name(value):
    return re.sub(r"[^A-Za-z0-9._-]", "", str(value or ""))[:96]


def _identifier(value):
    return re.sub(r"[^A-Za-z0-9._-]", "", str(value or "").lower())[:96]


def _bounded_tokens(value, *, digits_only=False):
    if not isinstance(value, list):
        return []
    output = []
    seen = set()
    for raw in value[:10]:
        token = str(raw or "").lower()
        token = re.sub(r"[^0-9]" if digits_only else r"[^a-z0-9]", "", token)
        token = token[:4 if digits_only else 12]
        if not token or token in seen:
            continue
        seen.add(token)
        output.append(token)
    return output


def _clean_options(value):
    raw = value if isinstance(value, dict) else {}
    result = {key: bool(raw.get(key, False)) for key in sorted(OPTION_KEYS)}
    result["number_tokens"] = _bounded_tokens(raw.get("number_tokens"), digits_only=True)
    result["prefixes"] = _bounded_tokens(raw.get("prefixes"))
    result["suffixes"] = _bounded_tokens(raw.get("suffixes"))
    return result


def _clean_availability(value, status):
    raw = value if isinstance(value, dict) else {}
    result = {"status": status}
    for key, limit in (
        ("detail", 500), ("url", 600), ("source", 80), ("method", 96),
        ("occupancy", 32), ("claimability", 32),
    ):
        clean = _text(raw.get(key), limit)
        if clean:
            result[key] = clean
    confidence = raw.get("confidence")
    if isinstance(confidence, (int, float)):
        result["confidence"] = max(0.0, min(1.0, float(confidence)))
    return result


def _clean_verification(value):
    if not isinstance(value, dict):
        return None
    result = {}
    for key, limit in (
        ("verdict", 32), ("reason", 500), ("verification_engine_version", 64),
        ("evidence_fusion_version", 64),
    ):
        clean = _text(value.get(key), limit)
        if clean:
            result[key] = clean
    confidence = value.get("confidence")
    if isinstance(confidence, (int, float)):
        result["confidence"] = max(0.0, min(1.0, float(confidence)))
    return result or None


def _clean_result(value):
    if not isinstance(value, dict):
        return None
    resource = str(value.get("resource") or "").strip().lower()
    identifier = _identifier(value.get("identifier"))
    status = str(value.get("status") or (value.get("availability") or {}).get("status") or "unknown").strip().lower()
    if resource not in RESOURCES or not identifier:
        return None
    if status not in STATUSES:
        status = "unknown"
    return {
        "resource": resource,
        "identifier": identifier,
        "mutation": _text(value.get("mutation"), 48),
        "detail": _text(value.get("detail"), 80),
        "status": status,
        "strict_free": status == "claimable",
        "purchasable": status == "purchasable",
        "checked_at": _text(value.get("checked_at"), 64),
        "availability": _clean_availability(value.get("availability"), status),
        "verification": _clean_verification(value.get("verification")),
    }


def clean_expansion(parent_name, value):
    parent = _parent_name(parent_name)
    if not parent:
        raise ValueError("parent_name is required")
    raw = value if isinstance(value, dict) else {}
    resources = []
    for item in raw.get("resources", []) if isinstance(raw.get("resources"), list) else []:
        resource = str(item).lower()
        if resource in RESOURCES and resource not in resources:
            resources.append(resource)
    results = []
    for item in raw.get("results", []) if isinstance(raw.get("results"), list) else []:
        clean = _clean_result(item)
        if clean:
            results.append(clean)
        if len(results) >= MAX_RESULTS:
            break
    payload = {
        "parent_name": parent,
        "resources": resources,
        "options": _clean_options(raw.get("options")),
        "checked_at": _text(raw.get("checked_at"), 64),
        "results": results,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_EXPANSION_BYTES:
        raise ValueError("Variant expansion payload is too large")
    return payload


class VariantExpansionStore:
    def __init__(self, session_store=None):
        self.session_store = session_store or STORE

    @property
    def configured(self):
        return self.session_store.configured

    def _engine(self):
        engine = self.session_store._ensure_engine()
        metadata.create_all(engine)
        return engine

    def diagnostics(self):
        return {
            "configured": self.configured,
            "schema_version": VARIANT_STORE_SCHEMA_VERSION,
            "separate_from_candidate_bundles": True,
            "max_results_per_parent": MAX_RESULTS,
            "strict_free_status": "claimable",
        }

    def upsert(self, session_id, token, parent_name, payload):
        clean = clean_expansion(parent_name, payload)
        key = clean["parent_name"].lower()
        now = _utcnow()
        engine = self._engine()
        with engine.begin() as conn:
            if not SessionStore._authorized(conn, session_id, token):
                return None
            values = {
                "session_id": session_id,
                "parent_name_key": key,
                "parent_name": clean["parent_name"],
                "payload": clean,
                "updated_at": now,
            }
            SessionStore._upsert(
                conn,
                variant_expansions,
                (variant_expansions.c.session_id == session_id)
                & (variant_expansions.c.parent_name_key == key),
                values,
            )
            conn.execute(
                update(sessions)
                .where(sessions.c.id == session_id)
                .values(server_updated_at=now, revision=sessions.c.revision + 1)
            )
        return {**clean, "updated_at": _iso(now)}

    def get(self, session_id, token, parent_name):
        parent = _parent_name(parent_name)
        if not parent:
            return None
        engine = self._engine()
        with engine.connect() as conn:
            if not SessionStore._authorized(conn, session_id, token):
                return None
            row = conn.execute(
                select(variant_expansions.c.payload, variant_expansions.c.updated_at).where(
                    (variant_expansions.c.session_id == session_id)
                    & (variant_expansions.c.parent_name_key == parent.lower())
                )
            ).mappings().one_or_none()
        if row is None:
            return False
        return {**dict(row["payload"] or {}), "updated_at": _iso(row["updated_at"])}


VARIANT_STORE = VariantExpansionStore()


__all__ = [
    "MAX_EXPANSION_BYTES",
    "MAX_RESULTS",
    "VARIANT_STORE",
    "VARIANT_STORE_SCHEMA_VERSION",
    "VariantExpansionStore",
    "clean_expansion",
    "variant_expansions",
]
