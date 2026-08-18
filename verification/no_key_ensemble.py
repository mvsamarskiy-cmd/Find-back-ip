"""Evidence ensemble for optional no-key verifier layers.

The ensemble only gathers evidence. Existing Verification v2 fusion remains the
single deterministic authority for the final verdict.
"""
from verification.fusion import fuse_evidence
from verification.providers import maigret_adapter, socialscan_adapter, whatsmyname_adapter


PROVIDERS = {
    "socialscan": socialscan_adapter.check_username,
    "whatsmyname": whatsmyname_adapter.check_username,
    "maigret": maigret_adapter.check_username,
}


def collect_no_key_evidence(handle, platform, providers=None):
    selected = tuple(providers or PROVIDERS.keys())
    rows = []
    for provider in selected:
        checker = PROVIDERS.get(provider)
        if checker is None:
            continue
        try:
            evidence = checker(handle, platform)
        except Exception:
            evidence = None
        if isinstance(evidence, dict):
            rows.append(evidence)
    return rows


def verify_no_key(handle, platform, providers=None):
    evidence = collect_no_key_evidence(handle, platform, providers=providers)
    return fuse_evidence(platform, handle, evidence).to_dict()
