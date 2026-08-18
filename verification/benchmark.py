"""Small deterministic benchmark harness for verifier adapters.

The default fixtures contain only known occupied handles. Unknown/random controls
must never be asserted as claimable in CI because real-world availability can
change between runs.
"""
from dataclasses import dataclass
from typing import Callable, Iterable, List


@dataclass(frozen=True)
class Fixture:
    handle: str
    platform: str
    expected_signal: str
    note: str = ""


KNOWN_FIXTURES = (
    Fixture("mazomoto", "youtube", "exists", "Known YouTube handle"),
    Fixture("youtubecreators", "youtube", "exists", "YouTube official handle URL example"),
    Fixture("googledevelopers", "youtube", "exists", "YouTube Data API forHandle documentation example"),
    Fixture("mazomoto", "tiktok", "exists", "Known TikTok handle"),
    Fixture("scout2015", "tiktok", "exists", "TikTok official creator-oEmbed documentation example"),
    Fixture("mazomoto", "telegram", "exists", "Known Telegram handle"),
    Fixture("drity", "x", "exists", "Known X handle"),
    Fixture("warsawcity", "x", "exists", "Known X handle"),
    Fixture("instagram", "instagram", "exists", "Known Instagram platform account"),
    Fixture("nike", "instagram", "exists", "Known Nike Instagram account"),
    Fixture("natgeo", "instagram", "exists", "Known National Geographic Instagram account"),
)


def evaluate(fixtures: Iterable[Fixture], checker: Callable[[str, str], dict]):
    rows: List[dict] = []
    for fixture in fixtures:
        evidence = checker(fixture.handle, fixture.platform)
        actual = evidence.get("signal", "unknown") if isinstance(evidence, dict) else "unknown"
        rows.append({
            "handle": fixture.handle,
            "platform": fixture.platform,
            "expected": fixture.expected_signal,
            "actual": actual,
            "matched": actual == fixture.expected_signal,
            "source": evidence.get("source") if isinstance(evidence, dict) else None,
            "latency_ms": evidence.get("latency_ms") if isinstance(evidence, dict) else None,
            "note": fixture.note,
        })
    return rows


def summary(rows):
    rows = list(rows)
    total = len(rows)
    matched = sum(1 for row in rows if row.get("matched"))
    return {
        "total": total,
        "matched": matched,
        "failed": total - matched,
        "accuracy_on_known_fixtures": (matched / total) if total else None,
    }
