import unittest
from unittest.mock import Mock

from verification.providers import facebook_public_adapter


class FacebookPublicAdapterTests(unittest.TestCase):
    def test_exact_profile_markers_are_exists(self):
        response = Mock()
        response.status_code = 200
        response.text = '<script>{"profile_id":"123","vanity":"facebook"}</script> https://www.facebook.com/facebook'
        evidence = facebook_public_adapter.check_username("facebook", requester=lambda *a, **k: response)
        self.assertEqual(evidence["signal"], "exists")

    def test_404_never_means_claimable(self):
        response = Mock()
        response.status_code = 404
        response.text = "not found"
        evidence = facebook_public_adapter.check_username("unlikelyname", requester=lambda *a, **k: response)
        self.assertEqual(evidence["signal"], "unknown")
        self.assertNotEqual(evidence["signal"], "claimable")

    def test_generic_login_page_is_unknown(self):
        response = Mock()
        response.status_code = 200
        response.text = "Log in or sign up to Facebook"
        evidence = facebook_public_adapter.check_username("facebook", requester=lambda *a, **k: response)
        self.assertEqual(evidence["signal"], "unknown")

    def test_wrong_platform_is_unknown(self):
        evidence = facebook_public_adapter.check_username("facebook", "instagram")
        self.assertEqual(evidence["signal"], "unknown")


if __name__ == "__main__":
    unittest.main()
