#!/usr/bin/env python3
"""Non-secret production canary checks for the canonical NameMachine deployment."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "ops" / "railway-production.json"
USER_AGENT = "NameMachine-production-canary/1.1"


class CanaryError(RuntimeError):
    pass


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _get_json(url, timeout=20):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get_content_type()
        body = response.read()
        status = response.status
    if status != 200:
        raise CanaryError(f"{url} returned HTTP {status}")
    if content_type != "application/json":
        raise CanaryError(f"{url} returned {content_type}, expected application/json")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise CanaryError(f"{url} returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise CanaryError(f"{url} returned a non-object JSON payload")
    return payload


def _require(condition, message):
    if not condition:
        raise CanaryError(message)


def _commit_matches(actual, expected):
    actual = str(actual or "").strip().lower()
    expected = str(expected or "").strip().lower()
    if not actual or not expected:
        return False
    return actual == expected or actual.startswith(expected) or expected.startswith(actual)


def run_canary(
    base_url,
    *,
    expected_release=None,
    expected_commit=None,
    require_worker=False,
    fetch_json=_get_json,
):
    base = str(base_url or "").rstrip("/")
    _require(base.startswith("https://"), "Production canary requires an HTTPS base URL")

    health = fetch_json(f"{base}/health")
    _require(health.get("status") == "ok", f"Unexpected health payload: {health!r}")

    version = fetch_json(f"{base}/api/version")
    release = str(version.get("release") or "").strip()
    commit = str(version.get("git_commit") or "").strip()
    _require(release, "Production version endpoint has no release marker")
    _require(commit, "Production version endpoint has no git commit marker")
    if expected_release:
        _require(
            release == expected_release,
            f"Release mismatch: expected {expected_release!r}, got {release!r}",
        )
    if expected_commit:
        _require(
            _commit_matches(commit, expected_commit),
            f"Commit mismatch: expected {expected_commit!r}, got {commit!r}",
        )

    diagnostics = fetch_json(f"{base}/api/verification/diagnostics")
    strict = diagnostics.get("strict_free_semantics") or {}
    _require(strict.get("green_status") == "claimable", "Strict green status is not claimable")
    _require(strict.get("purchasable_is_green") is False, "Purchasable must not be strict green")
    _require(strict.get("not_found_is_green") is False, "not_found must not be strict green")

    feed = diagnostics.get("large_feed_navigation") or {}
    _require(feed.get("newest_first") is True, "Production feed is not newest-first")
    _require(feed.get("pagination") is True, "Production feed pagination is not enabled")

    background = fetch_json(f"{base}/api/background-search")
    _require(background.get("configured") is True, "Durable background storage is not configured")
    _require(background.get("enabled") is True, "Background search is not enabled")
    worker_online = background.get("worker_online") is True
    worker_count = int(background.get("worker_count") or 0)
    if require_worker:
        _require(worker_online, "Background worker is offline")
        _require(worker_count >= 1, "Background worker count is zero")
        _require(background.get("ready") is True, "Background search is not ready")

    return {
        "target": base,
        "health": "ok",
        "release": release,
        "git_commit": commit,
        "strict_green_status": strict.get("green_status"),
        "feed": {
            "newest_first": True,
            "pagination": True,
        },
        "background_search": {
            "configured": True,
            "enabled": True,
            "worker_online": worker_online,
            "worker_count": worker_count,
            "ready": bool(background.get("ready")),
            "worker_required": bool(require_worker),
        },
    }


def main(argv=None):
    manifest = load_manifest()
    parser = argparse.ArgumentParser(description="Run NameMachine production canary checks")
    parser.add_argument(
        "--url",
        default=manifest["productionUrl"],
        help="HTTPS deployment base URL; defaults to the committed canonical Railway target",
    )
    parser.add_argument(
        "--expected-release",
        default=None,
        help="Fail unless /api/version reports this exact release marker",
    )
    parser.add_argument(
        "--expected-commit",
        default=None,
        help="Fail unless /api/version reports this Git commit (full or short SHA)",
    )
    parser.add_argument(
        "--require-worker",
        action="store_true",
        help="Also require at least one live background worker and ready=true",
    )
    args = parser.parse_args(argv)
    try:
        report = run_canary(
            args.url,
            expected_release=args.expected_release,
            expected_commit=args.expected_commit,
            require_worker=args.require_worker,
        )
    except (CanaryError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        print(f"CANARY FAILED: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
