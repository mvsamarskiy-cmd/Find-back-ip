from verification.diagnostics import provider_diagnostics
from verification.fusion import fuse_evidence
from verification.models import Evidence


def test_claimability_requires_explicit_positive_signal():
    verdict = fuse_evidence(
        "instagram",
        "example",
        [
            Evidence(
                platform="instagram",
                handle="example",
                source="public_web",
                method="public_profile",
                signal="absent",
                confidence=0.8,
            ).to_dict()
        ],
    )
    assert verdict.verdict == "likely_available"
    assert verdict.verdict != "available_verified"


def test_explicit_claimable_signal_becomes_verified_available():
    verdict = fuse_evidence(
        "com",
        "example.com",
        [
            Evidence(
                platform="com",
                handle="example.com",
                source="verisign_rdap",
                method="rdap_exact_domain",
                signal="absent",
                confidence=0.9,
            ).to_dict(),
            Evidence(
                platform="com",
                handle="example.com",
                source="namecom_core_api",
                method="registrar_check_availability",
                signal="claimable",
                confidence=0.99,
            ).to_dict(),
        ],
    )
    assert verdict.verdict == "available_verified"
    assert verdict.confidence == 0.99


def test_exists_evidence_blocks_absence_only_evidence():
    verdict = fuse_evidence(
        "telegram",
        "example",
        [
            Evidence(
                platform="telegram",
                handle="example",
                source="search_engine",
                method="exact_profile_search",
                signal="absent",
                confidence=0.6,
            ).to_dict(),
            Evidence(
                platform="telegram",
                handle="example",
                source="public_web",
                method="public_profile",
                signal="exists",
                confidence=0.85,
            ).to_dict(),
        ],
    )
    assert verdict.verdict == "taken"


def test_diagnostics_never_exposes_secret_values(monkeypatch):
    monkeypatch.setenv("NAMECOM_USERNAME", "secret-user")
    monkeypatch.setenv("NAMECOM_API_TOKEN", "secret-token")
    monkeypatch.setenv("YOUTUBE_API_KEY", "secret-youtube")
    monkeypatch.setenv("X_BEARER_TOKEN", "secret-x")

    diagnostics = provider_diagnostics()
    text = repr(diagnostics)

    assert diagnostics["domain"]["registrar"]["configured"] is True
    assert diagnostics["youtube"]["official_api"]["configured"] is True
    assert diagnostics["x"]["official_api"]["configured"] is True
    assert "secret-user" not in text
    assert "secret-token" not in text
    assert "secret-youtube" not in text
    assert "secret-x" not in text
