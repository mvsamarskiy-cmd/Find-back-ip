"""Central evidence collection for Verification v2.

This module is deliberately network-free. Provider/network layers may enrich the
legacy availability row, while the collector preserves both the original legacy
evidence and the enriched evidence before deterministic fusion. This prevents a
later verifier from erasing earlier evidence during the migration to a full
multi-provider evidence pipeline.
"""

from .bridge import legacy_result_to_evidence
from .fusion import fuse_evidence


def _fingerprint(row):
    return (
        str(row.get("source") or ""),
        str(row.get("method") or ""),
        str(row.get("signal") or ""),
        str(row.get("url") or ""),
    )


def collect_platform_evidence(platform, handle, legacy_row=None, enriched_row=None, extra_evidence=None):
    """Collect and deduplicate all currently known evidence for one platform.

    `legacy_row` is the result before no-key enrichment; `enriched_row` is the
    post-provider compatibility row. `extra_evidence` is an additive extension
    point for future independent providers. No row is allowed to overwrite a
    previous row here.
    """
    rows = []

    for candidate in (legacy_row, enriched_row):
        if isinstance(candidate, dict):
            rows.append(legacy_result_to_evidence(platform, handle, candidate).to_dict())

    for candidate in extra_evidence or ():
        if isinstance(candidate, dict):
            rows.append(dict(candidate))

    unique = []
    seen = set()
    for row in rows:
        key = _fingerprint(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def collect_verification_verdicts(handle, legacy_availability, enriched_availability, extra_by_platform=None):
    """Return one fused verdict per platform while retaining full evidence arrays."""
    legacy_rows = legacy_availability if isinstance(legacy_availability, dict) else {}
    enriched_rows = enriched_availability if isinstance(enriched_availability, dict) else {}
    extras = extra_by_platform if isinstance(extra_by_platform, dict) else {}

    platforms = list(dict.fromkeys([*legacy_rows.keys(), *enriched_rows.keys(), *extras.keys()]))
    verdicts = {}
    for platform in platforms:
        evidence = collect_platform_evidence(
            platform,
            handle,
            legacy_rows.get(platform),
            enriched_rows.get(platform),
            extras.get(platform),
        )
        verdicts[platform] = fuse_evidence(platform, handle, evidence).to_dict()
    return verdicts


__all__ = ["collect_platform_evidence", "collect_verification_verdicts"]
