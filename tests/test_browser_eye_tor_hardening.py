import asyncio
import unittest

import browser_eye_tor as tor_module
from browser_eye_tor_hardening import (
    MAX_DOCUMENT_BYTES,
    MAX_PAGE_REQUESTS,
    _guarded_route,
    install_tor_hardening,
    safe_tor_url,
)


VALID_ONION = "a" * 56 + ".onion"


def public_resolver(host, port, type=None):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


def private_resolver(host, port, type=None):
    return [(2, 1, 6, "", ("10.0.0.7", port))]


class FakeRequest:
    def __init__(self, url, method="GET", resource_type="document"):
        self.url = url
        self.method = method
        self.resource_type = resource_type


class FakeRoute:
    def __init__(self, request):
        self.request = request
        self.aborted = False
        self.continued = False

    async def abort(self):
        self.aborted = True


class FakeRuntime:
    async def _route(self, route):
        route.continued = True


class TorHardeningTests(unittest.TestCase):
    def test_dns_private_resolution_is_blocked(self):
        self.assertEqual(
            safe_tor_url("https://example.com/opportunity", resolver=private_resolver),
            "",
        )
        self.assertEqual(
            safe_tor_url("https://example.com/opportunity", resolver=public_resolver),
            "https://example.com/opportunity",
        )

    def test_nonstandard_ports_and_special_hosts_are_blocked(self):
        self.assertEqual(safe_tor_url("https://example.com:8080/a", resolver=public_resolver), "")
        self.assertEqual(safe_tor_url("http://localhost/a", resolver=public_resolver), "")
        self.assertEqual(safe_tor_url("http://service.internal/a", resolver=public_resolver), "")
        self.assertEqual(safe_tor_url("http://169.254.169.254/latest", resolver=public_resolver), "")

    def test_onion_does_not_need_local_dns(self):
        def explode(*args, **kwargs):
            raise AssertionError("onion address must not use local DNS")

        target = "http://" + VALID_ONION + "/call"
        self.assertEqual(safe_tor_url(target, resolver=explode), target)

    def test_guard_aborts_non_read_methods_before_runtime(self):
        route = FakeRoute(FakeRequest("https://example.com/", method="POST"))
        asyncio.run(_guarded_route(route, runtime=FakeRuntime(), counter={"count": 0}))
        self.assertTrue(route.aborted)
        self.assertFalse(route.continued)

    def test_guard_aborts_heavy_assets(self):
        route = FakeRoute(FakeRequest("https://example.com/image.png", resource_type="image"))
        asyncio.run(_guarded_route(route, runtime=FakeRuntime(), counter={"count": 0}))
        self.assertTrue(route.aborted)
        self.assertFalse(route.continued)

    def test_install_exposes_bounded_security_contract(self):
        install_tor_hardening(tor_module)
        payload = tor_module.tor_diagnostics()
        self.assertTrue(payload["dns_private_resolution_guard"])
        self.assertTrue(payload["redirect_and_subresource_guard"])
        self.assertEqual(payload["read_only_methods"], ["GET", "HEAD"])
        self.assertEqual(payload["max_page_requests"], MAX_PAGE_REQUESTS)
        self.assertEqual(payload["max_document_bytes"], MAX_DOCUMENT_BYTES)
        self.assertEqual(payload["allowed_ports"], [80, 443])
        self.assertFalse(payload["direct_source_verification"])


if __name__ == "__main__":
    unittest.main()
