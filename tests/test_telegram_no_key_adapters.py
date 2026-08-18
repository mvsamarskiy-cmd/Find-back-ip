import unittest
from unittest.mock import Mock, patch

from verification.providers import fragment_username_adapter, telegram_public_adapter


class TelegramPublicAdapterTests(unittest.TestCase):
    def test_concrete_peer_card_is_exists(self):
        response = Mock()
        response.status_code = 200
        response.text = (
            '<div class="tgme_page_title">Telegram</div>'
            '<div class="tgme_page_extra">10M subscribers</div>'
            '<a class="tgme_action_button_new">View in Telegram</a>'
        )
        with patch.object(telegram_public_adapter.requests, "get", return_value=response):
            evidence = telegram_public_adapter.check_username("telegram", "telegram")
        self.assertEqual(evidence["signal"], "exists")

    def test_generic_contact_shell_fails_closed(self):
        response = Mock()
        response.status_code = 200
        response.text = (
            '<div class="tgme_page_title">Contact</div>'
            '<div class="tgme_page_extra">If you have Telegram, you can contact @unlikely right away.</div>'
            '<a class="tgme_action_button_new">Send Message</a>'
        )
        with patch.object(telegram_public_adapter.requests, "get", return_value=response):
            evidence = telegram_public_adapter.check_username("unlikely", "telegram")
        self.assertEqual(evidence["signal"], "unknown")

    def test_404_never_means_claimable(self):
        response = Mock()
        response.status_code = 404
        with patch.object(telegram_public_adapter.requests, "get", return_value=response):
            evidence = telegram_public_adapter.check_username("unlikely", "telegram")
        self.assertEqual(evidence["signal"], "unknown")
        self.assertNotEqual(evidence["signal"], "claimable")


class FragmentUsernameAdapterTests(unittest.TestCase):
    def test_taken_is_positive_occupancy(self):
        response = Mock()
        response.status_code = 200
        response.text = '<span class="status-taken">Taken</span>'
        with patch.object(fragment_username_adapter.requests, "get", return_value=response):
            evidence = fragment_username_adapter.check_username("telegram", "telegram")
        self.assertEqual(evidence["signal"], "exists")

    def test_marketplace_available_is_not_free_claimable(self):
        response = Mock()
        response.status_code = 200
        response.text = '<span class="status-avail">Available</span>'
        with patch.object(fragment_username_adapter.requests, "get", return_value=response):
            evidence = fragment_username_adapter.check_username("premiumname", "telegram")
        self.assertEqual(evidence["signal"], "purchasable")
        self.assertNotEqual(evidence["signal"], "claimable")

    def test_generic_unavailable_fails_closed(self):
        response = Mock()
        response.status_code = 200
        response.text = '<span class="status-unavail">Unavailable</span>'
        with patch.object(fragment_username_adapter.requests, "get", return_value=response):
            evidence = fragment_username_adapter.check_username("somehandle", "telegram")
        self.assertEqual(evidence["signal"], "unknown")


if __name__ == "__main__":
    unittest.main()
