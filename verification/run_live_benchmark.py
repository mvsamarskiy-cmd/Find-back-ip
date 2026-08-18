"""Run live no-key verifier benchmarks against known occupied handles.

This script is intentionally informational. Network providers are unstable by
nature, so it records evidence and provider-level accuracy without turning a
single transient miss into a CI failure.
"""
import json
from pathlib import Path

from verification.benchmark import KNOWN_FIXTURES, evaluate, summary
from verification.providers import maigret_adapter, socialscan_adapter, whatsmyname_adapter


PROVIDERS = {
    "socialscan": socialscan_adapter.check_username,
    "whatsmyname": whatsmyname_adapter.check_username,
    "maigret": maigret_adapter.check_username,
}


def _eligible(fixtures, provider_name):
    if provider_name == "socialscan":
        allowed = {"instagram", "x"}
    else:
        allowed = {"instagram", "telegram", "tiktok", "youtube", "facebook", "x"}
    return [fixture for fixture in fixtures if fixture.platform in allowed]


def main():
    report = {"providers": {}}
    for name, checker in PROVIDERS.items():
        fixtures = _eligible(KNOWN_FIXTURES, name)
        rows = evaluate(fixtures, checker)
        report["providers"][name] = {
            "summary": summary(rows),
            "rows": rows,
        }

    output_dir = Path("artifacts")
    output_dir.mkdir(exist_ok=True)
    output = output_dir / "no-key-live-benchmark.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Wrote benchmark report to {output}")


if __name__ == "__main__":
    main()
