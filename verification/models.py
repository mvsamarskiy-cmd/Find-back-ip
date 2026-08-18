from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


EVIDENCE_SIGNALS = frozenset({
    "exists",
    "absent",
    "claimable",
    "purchasable",
    "reserved",
    "invalid",
    "blocked",
    "rate_limited",
    "unknown",
})

VERDICTS = frozenset({
    "available_verified",
    "likely_available",
    "taken",
    "reserved",
    "invalid",
    "unknown",
})


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Evidence:
    platform: str
    handle: str
    source: str
    method: str
    signal: str
    confidence: float = 0.0
    detail: str = ""
    url: str = ""
    checked_at: str = field(default_factory=utc_now_iso)
    latency_ms: Optional[int] = None
    http_status: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.signal not in EVIDENCE_SIGNALS:
            raise ValueError(f"Unsupported evidence signal: {self.signal}")
        object.__setattr__(self, "confidence", round(max(0.0, min(1.0, float(self.confidence))), 3))
        if self.latency_ms is not None:
            object.__setattr__(self, "latency_ms", max(0, int(self.latency_ms)))

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class VerificationVerdict:
    platform: str
    handle: str
    verdict: str
    confidence: float
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""

    def __post_init__(self):
        if self.verdict not in VERDICTS:
            raise ValueError(f"Unsupported verification verdict: {self.verdict}")
        object.__setattr__(self, "confidence", round(max(0.0, min(1.0, float(self.confidence))), 3))

    def to_dict(self):
        return asdict(self)
