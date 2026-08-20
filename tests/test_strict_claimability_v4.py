import os
import unittest
from unittest.mock import Mock, patch

import availability
import browser_queue
import strict_claimability
from telegram_bootstrap import app


class StrictClaimabilityTests(unittest.TestCase):
    def row(self, resource, status="not_found"):
        return {
            "name": "DawnFlock",
            "checked": True,
            "required_resources": [resource],
            "availability": {
                resource: {
                    "status": status,
                    "detail": "fixture",
                    "url": "https://example.test",
                    "source": "fixture",
                    "method": "fixture",
                    "confidence": 0.8,
                    "occupancy": "not_found" if status == "not_found" else "unknown",
                    "claimability": "unconfirmed",
                }
            },
        }

    def test_social_absence_never_turns_green_without_authoritative_provider(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NAMECOM_USERNAME", None)
            os.environ.pop("NAMECOM_API_TOKEN", None)
            os.environ.pop("TELEGRAM_EVIDENCE_URL", None)
            os.environ.pop("TELEGRAM_EVIDENCE_TOKEN", None)
            result = strict_claimability.apply_strict_claimability(self.row("instagram"), ["instagram"])
        self.assertEqual(result["availability"]["instagram"]["status"], "not_found")
        self.assertIn("instagram", result["strict_claimability_unprovable_required"])
        self.assertEqual(result["strict_claimability_state"], "unavailable")

    def test_authoritative_registrar_result_can_promote_com_to_claimable(self):
        strict_row = availability._result(
            "claimable",
            "registrar confirmed",
            "https://name.com",
            source="namecom_core_api",
            method="registrar_check_availability",
            confidence=0.99,
            occupancy="not_found",
            claimability="confirmed",
        )
        with patch.dict(os.environ, {"NAMECOM_USERNAME": "user", "NAMECOM_API_TOKEN": "token"}, clear=False):
            with patch("strict_claimability.probe_strict_resource", return_value=strict_row):
                result = strict_claimability.apply_strict_claimability(self.row("com"), ["com"])
        self.assertEqual(result["availability"]["com"]["status"], "claimable")
        self.assertEqual(result["bundle_availability_state"], "claimable")
        self.assertEqual(result["bundle_claimable"], ["com"])

    def test_failed_authoritative_probe_keeps_useful_absence_non_green(self):
        with patch.dict(
            os.environ,
            {"TELEGRAM_EVIDENCE_URL": "https://telegram.internal", "TELEGRAM_EVIDENCE_TOKEN": "token"},
            clear=False,
        ):
            with patch("strict_claimability.probe_strict_resource", return_value={
                "status": "unknown",
                "detail": "provider unavailable",
                "source": "strict_claimability",
                "method": "provider_error",
                "confidence": 0.0,
                "claimability": "unconfirmed",
            }):
                result = strict_claimability.apply_strict_claimability(self.row("telegram"), ["telegram"])
        self.assertEqual(result["availability"]["telegram"]["status"], "not_found")
        self.assertNotEqual(result["bundle_availability_state"], "claimable")
        self.assertEqual(result["strict_claimability"]["telegram"]["status"], "unknown")

    def test_deferred_com_fast_path_does_not_call_registrar(self):
        original = availability.check_com
        response = Mock(status_code=404)
        try:
            with patch.dict(
                os.environ,
                {
                    "STRICT_CLAIMABILITY_DEFERRED": "1",
                    "NAMECOM_USERNAME": "user",
                    "NAMECOM_API_TOKEN": "token",
                },
                clear=False,
            ):
                strict_claimability.install_fast_path_deference()
                with patch("strict_claimability.requests.get", return_value=response):
                    with patch("availability._check_namecom_registration") as registrar:
                        result = availability.check_com("dawnflock")
                registrar.assert_not_called()
        finally:
            availability.check_com = original
        self.assertEqual(result["status"], "not_found")
        self.assertIn("queued", result["detail"].lower())

    def test_queue_admits_strict_only_com_candidate_when_provider_is_configured(self):
        strict_claimability.install_runtime_overlay()
        with patch.dict(os.environ, {"NAMECOM_USERNAME": "user", "NAMECOM_API_TOKEN": "token"}, clear=False):
            row = self.row("com")
            self.assertTrue(browser_queue._browser_candidate(row))


class StrictClaimabilityDiagnosticsTests(unittest.TestCase):
    def test_pipeline_advertises_authoritative_final_stage_without_weakening_green(self):
        diagnostics = app.test_client().get("/api/verification/diagnostics").get_json()
        pipeline = diagnostics["verification_pipeline"]
        self.assertEqual(pipeline["version"], "v3.1")
        self.assertEqual(pipeline["architecture_version"], "v4")
        self.assertEqual(pipeline["strict_claimability_version"], "strict-v1")
        self.assertIn("authoritative_claimability", pipeline["order"])
        self.assertFalse(pipeline["fast_results_blocked_by_claimability"])
        semantics = diagnostics["strict_free_semantics"]
        self.assertTrue(semantics["authoritative_provider_required"])
        self.assertFalse(semantics["double_browser_absence_is_green"])


if __name__ == "__main__":
    unittest.main()
