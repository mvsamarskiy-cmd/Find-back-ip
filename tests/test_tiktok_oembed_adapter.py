import unittest
from unittest.mock import Mock, patch

from verification.providers import tiktok_oembed_adapter


class TikTokOEmbedAdapterTests(unittest.TestCase):
    def test_exact_creator_profile_is_exists(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "provider_name": "TikTok",
            "author_url": "https://www.tiktok.com/@scout2015",
            "html": '<blockquote data-unique-id="scout2015"></blockquote>',
        }
        with patch.object(tiktok_oembed_adapter.requests, "get", return_value=response):
            evidence = tiktok_oembed_adapter.check_username("scout2015", "tiktok")
        self.assertEqual(evidence["signal"], "exists")
        self.assertEqual(evidence["source"], "tiktok_oembed")

    def test_non_200_never_means_claimable(self):
        response = Mock()
        response.status_code = 404
        with patch.object(tiktok_oembed_adapter.requests, "get", return_value=response):
            evidence = tiktok_oembed_adapter.check_username("unlikelyname", "tiktok")
        self.assertEqual(evidence["signal"], "unknown")
        self.assertNotEqual(evidence["signal"], "claimable")

    def test_ambiguous_success_fails_closed(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "provider_name": "TikTok",
            "author_url": "https://www.tiktok.com/@someoneelse",
            "html": '<blockquote data-unique-id="someoneelse"></blockquote>',
        }
        with patch.object(tiktok_oembed_adapter.requests, "get", return_value=response):
            evidence = tiktok_oembed_adapter.check_username("requested", "tiktok")
        self.assertEqual(evidence["signal"], "unknown")

    def test_wrong_platform_is_unknown(self):
        evidence = tiktok_oembed_adapter.check_username("scout2015", "instagram")
        self.assertEqual(evidence["signal"], "unknown")


if __name__ == "__main__":
    unittest.main()
