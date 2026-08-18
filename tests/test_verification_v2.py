from verification.bridge import (
    attach_verification_verdicts,
    legacy_result_to_evidence,
    verdict_from_legacy_result,
)
from verification.collector import collect_platform_evidence, collect_verification_verdicts
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


def test_claimable_plus_exists_is_never_verified_available():
    verdict = fuse_evidence(
        "com",
        "example.com",
        [
            Evidence(
                platform="com",
                handle="example.com",
                source="namecom_core_api",
                method="registrar_check_availability",
                signal="claimable",
                confidence=0.99,
            ).to_dict(),
            Evidence(
                platform="com",
                handle="example.com",
                source="verisign_rdap",
                method="rdap_exact_domain",
                signal="exists",
                confidence=0.98,
            ).to_dict(),
        ],
    )
    assert verdict.verdict == "unknown"
    assert verdict.verdict != "available_verified"
    assert "Contradictory" in verdict.reason


def test_invalid_wins_over_claimable_signal():
    verdict = fuse_evidence(
        "x",
        "bad handle",
        [
            Evidence(
                platform="x",
                handle="bad handle",
                source="x_api",
                method="lookup",
                signal="invalid",
                confidence=0.99,
            ).to_dict(),
            Evidence(
                platform="x",
                handle="bad handle",
                source="public_web",
                method="fallback",
                signal="claimable",
                confidence=0.5,
            ).to_dict(),
        ],
    )
    assert verdict.verdict == "invalid"


def test_stronger_unresolved_source_blocks_weaker_absence_marketing():
    verdict = fuse_evidence(
        "facebook",
        "example",
        [
            Evidence(
                platform="facebook",
                handle="example",
                source="whatsmyname",
                method="community_fingerprint",
                signal="absent",
                confidence=0.68,
            ).to_dict(),
            Evidence(
                platform="facebook",
                handle="example",
                source="public_web",
                method="public_profile",
                signal="unknown",
                confidence=0.0,
            ).to_dict(),
        ],
    )
    assert verdict.verdict == "unknown"


def test_collector_preserves_original_and_enriched_evidence():
    rows = collect_platform_evidence(
        "x",
        "example",
        legacy_row={
            "status": "not_found",
            "source": "public_web",
            "method": "public_profile",
            "confidence": 0.65,
            "url": "https://x.com/example",
        },
        enriched_row={
            "status": "taken",
            "source": "socialscan",
            "method": "registration_probe",
            "confidence": 0.9,
            "url": "https://x.com/example",
        },
    )
    assert len(rows) == 2
    assert {row["signal"] for row in rows} == {"absent", "exists"}
    assert {row["source"] for row in rows} == {"public_web", "socialscan"}


def test_collector_deduplicates_unchanged_compatibility_rows():
    row = {
        "status": "taken",
        "source": "public_web",
        "method": "public_profile",
        "confidence": 0.85,
        "url": "https://example.test/user",
    }
    rows = collect_platform_evidence("telegram", "user", row, dict(row))
    assert len(rows) == 1


def test_collector_fuses_conflict_instead_of_last_writer_wins():
    verdicts = collect_verification_verdicts(
        "example",
        {"x": {
            "status": "claimable",
            "source": "x_api",
            "method": "official_username_check",
            "confidence": 0.99,
        }},
        {"x": {
            "status": "taken",
            "source": "socialscan",
            "method": "registration_probe",
            "confidence": 0.9,
        }},
    )
    assert verdicts["x"]["verdict"] == "unknown"
    assert len(verdicts["x"]["evidence"]) == 2


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


def test_legacy_not_found_never_becomes_verified_available():
    verdict = verdict_from_legacy_result(
        "instagram",
        "example",
        {
            "status": "not_found",
            "source": "public_web",
            "method": "public_profile",
            "confidence": 0.72,
            "occupancy": "not_found",
            "claimability": "unconfirmed",
        },
    )
    assert verdict["verdict"] == "likely_available"
    assert verdict["verdict"] != "available_verified"


def test_legacy_namecom_claimable_becomes_verified_available():
    evidence = legacy_result_to_evidence(
        "com",
        "example",
        {
            "status": "claimable",
            "source": "namecom_core_api",
            "method": "registrar_check_availability",
            "confidence": 0.99,
            "occupancy": "not_found",
            "claimability": "confirmed",
            "offer": {"provider": "name.com", "domain_name": "example.com"},
        },
    )
    assert evidence.signal == "claimable"
    assert evidence.metadata["offer"]["provider"] == "name.com"

    verdict = fuse_evidence("com", "example", [evidence.to_dict()])
    assert verdict.verdict == "available_verified"
    assert verdict.confidence == 0.99


def test_attach_verification_verdicts_is_additive_per_platform():
    verdicts = attach_verification_verdicts(
        "example",
        {
            "com": {
                "status": "claimable",
                "source": "namecom_core_api",
                "method": "registrar_check_availability",
                "confidence": 0.99,
            },
            "telegram": {
                "status": "taken",
                "source": "public_web",
                "method": "public_profile",
                "confidence": 0.85,
            },
            "youtube": {
                "status": "not_found",
                "source": "youtube_data_api",
                "method": "official_handle_lookup",
                "confidence": 0.92,
            },
        },
    )

    assert verdicts["com"]["verdict"] == "available_verified"
    assert verdicts["telegram"]["verdict"] == "taken"
    assert verdicts["youtube"]["verdict"] == "likely_available"
