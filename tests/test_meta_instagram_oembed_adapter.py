from unittest import TestCase
from unittest.mock import Mock, patch

from verification.providers import meta_instagram_oembed_adapter


class MetaInstagramOEmbedAdapterTests(TestCase):
    def _response(self, status, payload=None):
        response = Mock()
        response.status_code = status
        if payload is not None:
            response.json.return_value = payload
        return response

    @patch("verification.providers.meta_instagram_oembed_adapter.requests.get")
    def test_exact_profile_in_oembed_is_exists(self, get):
        get.return_value = self._response(
            200,
            {"html": '<blockquote><a href="https://www.instagram.com/natgeo/">@natgeo</a></blockquote>'},
        )
        row = meta_instagram_oembed_adapter.check_username("NatGeo")
        self.assertEqual(row["signal"], "exists")
        self.assertEqual(row["source"], "meta_instagram_oembed")
        self.assertTrue(row["metadata"]["official_meta_endpoint"])

    @patch("verification.providers.meta_instagram_oembed_adapter.requests.get")
    def test_success_without_exact_identity_is_unknown(self, get):
        get.return_value = self._response(200, {"html": "<blockquote>Instagram</blockquote>"})
        row = meta_instagram_oembed_adapter.check_username("natgeo")
        self.assertEqual(row["signal"], "unknown")

    @patch("verification.providers.meta_instagram_oembed_adapter.requests.get")
    def test_non_200_is_unknown_not_absent_or_claimable(self, get):
        get.return_value = self._response(404)
        row = meta_instagram_oembed_adapter.check_username("rarehandle")
        self.assertEqual(row["signal"], "unknown")
        self.assertNotIn(row["signal"], {"absent", "claimable"})

    @patch("verification.providers.meta_instagram_oembed_adapter.requests.get")
    def test_429_is_explicit(self, get):
        get.return_value = self._response(429)
        row = meta_instagram_oembed_adapter.check_username("nike")
        self.assertEqual(row["signal"], "rate_limited")

    def test_other_platform_fails_closed(self):
        row = meta_instagram_oembed_adapter.check_username("example", "x")
        self.assertEqual(row["signal"], "unknown")
