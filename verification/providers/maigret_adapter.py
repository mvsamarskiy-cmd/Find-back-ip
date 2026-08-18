"""Optional Maigret adapter for wide username collision discovery.

Maigret is intentionally not a claimability source. Positive hits can strengthen
TAKEN/collision evidence; absence is only weak corroboration.
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter

from verification.models import Evidence


PLATFORM_HINTS = {
    "instagram": ("instagram",),
    "telegram": ("telegram",),
    "tiktok": ("tiktok",),
    "youtube": ("youtube",),
    "facebook": ("facebook",),
    "x": ("twitter", "x.com"),
}


def available():
    return shutil.which("maigret") is not None


def _unknown(platform, handle, detail, latency_ms=None):
    return Evidence(
        platform=platform,
        handle=handle,
        source="maigret",
        method="wide_collision_search",
        signal="unknown",
        confidence=0.0,
        detail=detail,
        latency_ms=latency_ms,
        metadata={"no_api_key": True},
    ).to_dict()


def _extract_hits(payload, platform):
    hints = PLATFORM_HINTS.get(platform, ())
    if not isinstance(payload, dict):
        return []
    hits = []
    for site_name, row in payload.items():
        if not isinstance(row, dict):
            continue
        lower_name = str(site_name).lower()
        if hints and not any(hint in lower_name for hint in hints):
            continue
        status = str(row.get("status") or row.get("status_text") or "").lower()
        exists = row.get("exists")
        if exists is True or status in {"claimed", "found", "exists", "taken"}:
            hits.append({"site": site_name, "url": row.get("url")})
    return hits


def check_username(handle, platform, *, runner=subprocess.run):
    handle = str(handle).strip().lower()
    platform = str(platform).strip().lower()
    if platform not in PLATFORM_HINTS:
        return _unknown(platform, handle, "Maigret platform mapping is unavailable")
    if not available() and runner is subprocess.run:
        return _unknown(platform, handle, "Maigret dependency is not installed")

    started = perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="namemachine-maigret-") as temp_dir:
            output = Path(temp_dir) / "result.json"
            command = [
                "maigret",
                handle,
                "--json",
                "simple",
                "--timeout",
                "5",
                "--top-sites",
                "100",
                "--folderoutput",
                temp_dir,
            ]
            completed = runner(command, capture_output=True, text=True, timeout=35, check=False)
            if int(getattr(completed, "returncode", 1) or 0) not in (0,):
                latency = int((perf_counter() - started) * 1000)
                return _unknown(platform, handle, "Maigret command failed", latency)

            candidates = list(Path(temp_dir).glob("*.json"))
            if output.exists():
                candidates.insert(0, output)
            if not candidates:
                latency = int((perf_counter() - started) * 1000)
                return _unknown(platform, handle, "Maigret produced no machine-readable report", latency)
            payload = json.loads(candidates[0].read_text(encoding="utf-8"))
    except Exception as error:
        latency = int((perf_counter() - started) * 1000)
        return _unknown(platform, handle, f"Maigret failed: {type(error).__name__}", latency)

    latency = int((perf_counter() - started) * 1000)
    hits = _extract_hits(payload, platform)
    if hits:
        return Evidence(
            platform=platform,
            handle=handle,
            source="maigret",
            method="wide_collision_search",
            signal="exists",
            confidence=0.78,
            detail="Maigret found a matching public account",
            url=str(hits[0].get("url") or ""),
            latency_ms=latency,
            metadata={"no_api_key": True, "hits": hits[:5]},
        ).to_dict()

    return Evidence(
        platform=platform,
        handle=handle,
        source="maigret",
        method="wide_collision_search",
        signal="absent",
        confidence=0.45,
        detail="Maigret found no matching account in the bounded scan",
        latency_ms=latency,
        metadata={"no_api_key": True, "bounded_scan": True},
    ).to_dict()
