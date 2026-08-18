import unittest
from unittest.mock import patch

import telegram_claimability_service as service


class TelegramClaimabilityServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = service.app.test_client()
        self.env = {
            "TELEGRAM_API_ID": "12345",
            "TELEGRAM_API_HASH": "hash",
            "TELEGRAM_SESSION_STRING": "session",
            "TELEGRAM_EVIDENCE_TOKEN": "secret",
        }

    @patch.dict("telegram_claimability_service.os.environ", {}, clear=True)
    def test_health_reports_configuration_required_without_secrets(self):
        response = self.client.get("/health")
        payload = response.get_json()
        self.assertEqual(payload["status"], "configuration_required")
        self.assertFalse(payload["configured"])
        self.assertTrue(payload["strict_claimability"])

    @patch.dict("telegram_claimability_service.os.environ", {
        "TELEGRAM_API_ID": "12345",
        "TELEGRAM_API_HASH": "hash",
        "TELEGRAM_SESSION_STRING": "session",
        "TELEGRAM_EVIDENCE_TOKEN": "secret",
    }, clear=True)
    def test_bearer_token_is_required(self):
        response = self.client.get("/v1/username/example")
        self.assertEqual(response.status_code, 401)

    @patch.dict("telegram_claimability_service.os.environ", {
        "TELEGRAM_API_ID": "12345",
        "TELEGRAM_API_HASH": "hash",
        "TELEGRAM_SESSION_STRING": "session",
        "TELEGRAM_EVIDENCE_TOKEN": "secret",
    }, clear=True)
    def test_local_invalid_username_never_calls_telegram(self):
        response = self.client.get(
            "/v1/username/a-b",
            headers={"Authorization": "Bearer secret"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["claimability"]["status"], "invalid")
        self.assertEqual(payload["claimability"]["method"], "account.checkUsername")

    def test_rpc_error_mapping(self):
        class RpcLike(Exception):
            message = "USERNAME_OCCUPIED"
        self.assertEqual(service._rpc_code(RpcLike()), "occupied")

        class PurchaseLike(Exception):
            message = "USERNAME_PURCHASE_AVAILABLE"
        self.assertEqual(service._rpc_code(PurchaseLike()), "purchasable")

        class InvalidLike(Exception):
            message = "USERNAME_INVALID"
        self.assertEqual(service._rpc_code(InvalidLike()), "invalid")


if __name__ == "__main__":
    unittest.main()
