import unittest
from threading import Barrier
from unittest.mock import Mock

from verification.provider_runtime import ProviderRuntime, ProviderTask


def evidence(platform, handle, signal="exists", source="test_provider"):
    return {
        "platform": platform,
        "handle": handle,
        "source": source,
        "method": "test",
        "signal": signal,
        "confidence": 0.9 if signal == "exists" else 0.0,
        "metadata": {},
    }


class ProviderRuntimeTests(unittest.TestCase):
    def test_independent_tasks_execute_concurrently(self):
        runtime = ProviderRuntime(max_workers=2)
        barrier = Barrier(2)

        def checker(handle, platform):
            barrier.wait(timeout=1.0)
            return evidence(platform, handle)

        try:
            rows = runtime.run_many([
                ProviderTask("a", "test_provider", "alpha", "x", checker),
                ProviderTask("b", "test_provider", "beta", "instagram", checker),
            ])
        finally:
            runtime.shutdown()

        self.assertEqual(rows["a"]["signal"], "exists")
        self.assertEqual(rows["b"]["signal"], "exists")
        self.assertFalse(rows["a"].get("metadata", {}).get("runtime_error", False))
        self.assertFalse(rows["b"].get("metadata", {}).get("runtime_error", False))

    def test_decisive_result_is_cached_for_repeat_check(self):
        runtime = ProviderRuntime(max_workers=2)
        checker = Mock(return_value=evidence("x", "alpha"))
        task = ProviderTask("x", "socialscan", "alpha", "x", checker)
        try:
            first = runtime.run_many([task])["x"]
            second = runtime.run_many([task])["x"]
        finally:
            runtime.shutdown()

        checker.assert_called_once_with("alpha", "x")
        self.assertFalse(first.get("metadata", {}).get("cache_hit", False))
        self.assertTrue(second["metadata"]["cache_hit"])

    def test_unknown_result_is_not_cached(self):
        runtime = ProviderRuntime(max_workers=2)
        checker = Mock(return_value=evidence("x", "alpha", signal="unknown"))
        task = ProviderTask("x", "socialscan", "alpha", "x", checker)
        try:
            runtime.run_many([task])
            runtime.run_many([task])
        finally:
            runtime.shutdown()

        self.assertEqual(checker.call_count, 2)

    def test_provider_exception_fails_closed(self):
        runtime = ProviderRuntime(max_workers=2)

        def checker(_handle, _platform):
            raise RuntimeError("boom")

        try:
            row = runtime.run_many([
                ProviderTask("x", "socialscan", "alpha", "x", checker)
            ])["x"]
        finally:
            runtime.shutdown()

        self.assertEqual(row["signal"], "unknown")
        self.assertTrue(row["metadata"]["non_blocking"])
        self.assertTrue(row["metadata"]["runtime_error"])
        self.assertNotIn("boom", row["detail"])


if __name__ == "__main__":
    unittest.main()
