import unittest
from unittest.mock import patch

import app as core_app
from telegram_bootstrap import app


class VariantApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_diagnostics_are_explicitly_opt_in_and_non_claimability(self):
        response = self.client.get("/api/variant-grammar")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["supported"])
        self.assertTrue(payload["user_opt_in_required"])
        self.assertTrue(payload["clean_stem_searched_first"])
        self.assertFalse(payload["availability_checked_here"])
        self.assertFalse(payload["claimability_proved_here"])
        self.assertFalse(payload["numbers_invented_automatically"])
        self.assertEqual(payload["verification_endpoint"], "/api/variants/check")
        self.assertTrue(payload["verification_uses_normal_engine"])
        self.assertEqual(payload["strict_free_status"], "claimable")
        self.assertIn("telegram", payload["resources"])
        self.assertIn("youtube", payload["resources"])

    def test_default_request_generates_no_mutations(self):
        response = self.client.post(
            "/api/variants",
            json={"stem": "botella", "resources": ["telegram", "youtube"]},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["variants"]["telegram"], [])
        self.assertEqual(payload["variants"]["youtube"], [])
        self.assertTrue(payload["semantics"]["clean_stem_searched_first"])
        self.assertEqual(payload["semantics"]["availability"], "unverified")
        self.assertEqual(payload["semantics"]["claimability"], "unconfirmed")
        self.assertTrue(payload["semantics"]["verification_required"])

    def test_explicit_telegram_variants_remain_unverified(self):
        response = self.client.post(
            "/api/variants",
            json={
                "stem": "botella",
                "resources": ["telegram"],
                "options": {
                    "underscore": True,
                    "digits": True,
                    "number_tokens": ["24"],
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["variants"]["telegram"]
        identifiers = [row["identifier"] for row in rows]
        self.assertIn("bot_ella", identifiers)
        self.assertIn("botella24", identifiers)
        for row in rows:
            self.assertEqual(row["availability"], "unverified")
            self.assertEqual(row["claimability"], "unconfirmed")
            self.assertTrue(row["syntax_valid"])

    def test_platform_grammars_do_not_leak_between_resources(self):
        response = self.client.post(
            "/api/variants",
            json={
                "stem": "botella",
                "resources": ["telegram", "youtube", "x"],
                "options": {"dots": True, "underscore": True},
            },
        )
        self.assertEqual(response.status_code, 200)
        variants = response.get_json()["variants"]
        self.assertFalse(any("." in row["identifier"] for row in variants["telegram"]))
        self.assertTrue(any("." in row["identifier"] for row in variants["youtube"]))
        self.assertFalse(any("." in row["identifier"] for row in variants["x"]))

    def test_numbers_are_not_invented_without_explicit_tokens(self):
        response = self.client.post(
            "/api/variants",
            json={
                "stem": "botella",
                "resources": ["instagram"],
                "options": {"digits": True},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["variants"]["instagram"], [])

    def test_invalid_requests_fail_closed(self):
        self.assertEqual(self.client.post("/api/variants", json={"resources": ["telegram"]}).status_code, 400)
        self.assertEqual(self.client.post("/api/variants", json={"stem": "botella"}).status_code, 400)
        self.assertEqual(
            self.client.post("/api/variants", json={"stem": "botella", "resources": ["threads"]}).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/variants",
                json={"stem": "botella", "resources": ["telegram"], "per_resource_limit": 999},
            ).status_code,
            400,
        )

    def test_variant_check_preserves_exact_identifier_and_strict_green(self):
        checked = {
            "availability": {
                "telegram": {
                    "status": "claimable",
                    "claimability": "confirmed",
                    "source": "telegram_claimability_service",
                }
            },
            "verification": {
                "telegram": {
                    "verdict": "claimable",
                    "verification_engine_version": "verification-engine-v2",
                }
            },
        }
        with patch.object(core_app, "check_all", return_value=checked) as verifier:
            response = self.client.post(
                "/api/variants/check",
                json={"resource": "telegram", "identifier": "bot_ella"},
            )

        self.assertEqual(response.status_code, 200)
        verifier.assert_called_once_with("bot_ella", resources=["telegram"])
        payload = response.get_json()
        self.assertEqual(payload["identifier"], "bot_ella")
        self.assertEqual(payload["status"], "claimable")
        self.assertTrue(payload["strict_free"])
        self.assertFalse(payload["purchasable"])
        self.assertFalse(payload["semantics"]["purchasable_is_green"])
        self.assertFalse(payload["semantics"]["not_found_is_green"])

    def test_variant_check_not_found_and_purchase_are_not_green(self):
        for status, expected_purchase in (("not_found", False), ("purchasable", True)):
            with self.subTest(status=status):
                checked = {
                    "availability": {"youtube": {"status": status}},
                    "verification": {"youtube": {"verdict": status}},
                }
                with patch.object(core_app, "check_all", return_value=checked):
                    response = self.client.post(
                        "/api/variants/check",
                        json={"resource": "youtube", "identifier": "bota.vess"},
                    )
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertFalse(payload["strict_free"])
                self.assertEqual(payload["purchasable"], expected_purchase)

    def test_variant_check_rejects_platform_invalid_shape_before_verifier(self):
        with patch.object(core_app, "check_all") as verifier:
            response = self.client.post(
                "/api/variants/check",
                json={"resource": "telegram", "identifier": "bota.vess"},
            )
        self.assertEqual(response.status_code, 400)
        verifier.assert_not_called()

    def test_variant_check_fails_closed_if_verifier_payload_is_malformed(self):
        with patch.object(core_app, "check_all", return_value={"availability": {}}):
            response = self.client.post(
                "/api/variants/check",
                json={"resource": "x", "identifier": "_botella"},
            )
        self.assertEqual(response.status_code, 503)

    def test_main_verification_diagnostics_include_conservative_variant_contract(self):
        response = self.client.get("/api/verification/diagnostics")
        self.assertEqual(response.status_code, 200)
        contract = response.get_json()["variant_grammar"]
        self.assertTrue(contract["supported"])
        self.assertTrue(contract["user_opt_in_required"])
        self.assertFalse(contract["availability_checked_here"])
        self.assertFalse(contract["claimability_proved_here"])
        self.assertEqual(contract["verification_endpoint"], "/api/variants/check")


if __name__ == "__main__":
    unittest.main()
