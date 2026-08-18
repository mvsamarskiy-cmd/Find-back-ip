"""Optional adapter for the open-source Socialscan library.

The dependency is intentionally optional. Production must not fail to boot when
Socialscan is absent or when a remote registration endpoint changes.
"""
from importlib.util import find_spec
from time import perf_counter

from verification.models import Evidence


PLATFORM_MAP = {
    "instagram": "INSTAGRAM",
    "x": "TWITTER",
}


def available():
    return find_spec("socialscan") is not None


def _unknown(platform, handle, detail, latency_ms=None):
    return Evidence(
        platform=platform,
        handle=handle,
        source="socialscan",
        method="registration_probe",
        signal="unknown",
        confidence=0.0,
        detail=detail,
        latency_ms=latency_ms,
        metadata={"no_api_key": True},
    ).to_dict()


def check_username(handle, platform):
    """Return one conservative Evidence record from Socialscan.

    A successful Socialscan `available=True` is treated as a registration-side
    claimability signal, but deliberately below authoritative first-party API
    confidence because these undocumented endpoints can change without notice.
    """
    handle = str(handle).strip().lower()
    platform = str(platform).strip().lower()
    if platform not in PLATFORM_MAP:
        return _unknown(platform, handle, "Socialscan does not support this NameMachine resource")
    if not available():
        return _unknown(platform, handle, "Socialscan dependency is not installed")

    started = perf_counter()
    try:
        from socialscan.util import Platforms, sync_execute_queries

        provider_platform = getattr(Platforms, PLATFORM_MAP[platform])
        rows = sync_execute_queries([handle], [provider_platform])
    except Exception as error:
        latency = int((perf_counter() - started) * 1000)
        return _unknown(platform, handle, f"Socialscan failed: {type(error).__name__}", latency)

    latency = int((perf_counter() - started) * 1000)
    if not rows:
        return _unknown(platform, handle, "Socialscan returned no result", latency)

    row = rows[0]
    success = bool(getattr(row, "success", False))
    valid = getattr(row, "valid", None)
    is_available = getattr(row, "available", None)
    message = str(getattr(row, "message", ""))[:300]

    if not success:
        return _unknown(platform, handle, message or "Socialscan query was unsuccessful", latency)
    if valid is False:
        signal = "invalid"
        confidence = 0.88
    elif is_available is True:
        signal = "claimable"
        confidence = 0.86
    elif is_available is False:
        signal = "exists"
        confidence = 0.9
    else:
        signal = "unknown"
        confidence = 0.0

    return Evidence(
        platform=platform,
        handle=handle,
        source="socialscan",
        method="registration_probe",
        signal=signal,
        confidence=confidence,
        detail=message,
        latency_ms=latency,
        metadata={
            "no_api_key": True,
            "success": success,
            "valid": valid,
            "available": is_available,
        },
    ).to_dict()
