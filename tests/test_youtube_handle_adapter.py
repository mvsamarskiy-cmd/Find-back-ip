import unittest
from unittest.mock import Mock, patch

from verification.providers import youtube_handle_adapter


class YouTubeHandleAdapterTests(unittest.TestCase):
    @patch("verification.providers.youtube_handle_adapter.requests.get")
    def test_exact_handle_marker_is_exists(self, get):
        response = Mock(status_code=200, text='{"canonicalBaseUrl":"/@YouTubeCreators"}')
        get.return_value = response
        result = youtube_handle_adapter.check_username("youtubecreators", "youtube")
        self.assertEqual(result["signal"], "exists")
        self.assertEqual(result["source"], "youtube_public_handle")

    @patch("verification.providers.youtube_handle_adapter.requests.get")
    def test_404_is_unknown_not_available(self, get):
        get.return_value = Mock(status_code=404, text="")
        result = youtube_handle_adapter.check_username("unlikelyhandle", "youtube")
        self.assertEqual(result["signal"], "unknown")
        self.assertNotEqual(result["signal"], "claimable")

    @patch("verification.providers.youtube_handle_adapter.requests.get")
    def test_generic_200_without_exact_identity_is_unknown(self, get):
        get.return_value = Mock(status_code=200, text="generic youtube shell")
        result = youtube_handle_adapter.check_username("example", "youtube")
        self.assertEqual(result["signal"], "unknown")

    def test_other_platform_is_unknown(self):
        result = youtube_handle_adapter.check_username("example", "instagram")
        self.assertEqual(result["signal"], "unknown")


if __name__ == "__main__":
    unittest.main()
