"""Bounded concurrent runtime for secondary verification providers.

The runtime keeps external verification fast without allowing one candidate batch
to create unbounded network fan-out. Independent provider calls run on one shared
executor, each provider has its own semaphore, and short-lived decisive evidence
is cached inside the worker process. Inconclusive/rate-limited results are never
cached so the next request can retry immediately.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
import os
from threading import BoundedSemaphore, Lock
from time import monotonic

from verification.models import Evidence


def _bounded_int(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


PROVIDER_WORKERS = _bounded_int("VERIFIER_PROVIDER_WORKERS", 12, 2, 32)
POSITIVE_TTL_SECONDS = _bounded_int("VERIFIER_POSITIVE_CACHE_TTL", 120, 0, 600)
ABSENCE_TTL_SECONDS = _bounded_int("VERIFIER_ABSENCE_CACHE_TTL", 30, 0, 120)

_PROVIDER_LIMIT_DEFAULTS = {
    "socialscan": 4,
    "meta_instagram_oembed": 4,
    "tiktok_oembed": 4,
    "fragment_public_web": 3,
    "whatsmyname": 3,
}


def _provider_limit(provider):
    env_name = "VERIFIER_LIMIT_" + "".join(
        char if char.isalnum() else "_" for char in str(provider).upper()
    )
    default = _PROVIDER_LIMIT_DEFAULTS.get(provider, 3)
    return _bounded_int(env_name, default, 1, 16)


@dataclass(frozen=True)
class ProviderTask:
    key: str
    provider: str
    handle: str
    platform: str
    checker: object


class ProviderRuntime:
    def __init__(self, max_workers=PROVIDER_WORKERS):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="verifier-provider",
        )
        self._semaphores = {
            provider: BoundedSemaphore(_provider_limit(provider))
            for provider in _PROVIDER_LIMIT_DEFAULTS
        }
        self._semaphore_lock = Lock()
        self._cache = {}
        self._cache_lock = Lock()

    def _semaphore(self, provider):
        with self._semaphore_lock:
            if provider not in self._semaphores:
                self._semaphores[provider] = BoundedSemaphore(_provider_limit(provider))
            return self._semaphores[provider]

    @staticmethod
    def _cache_ttl(row):
        signal = str((row or {}).get("signal") or "unknown")
        if signal in {"exists", "reserved", "invalid"}:
            return POSITIVE_TTL_SECONDS
        if signal in {"absent", "claimable", "purchasable"}:
            return ABSENCE_TTL_SECONDS
        return 0

    @staticmethod
    def _cache_key(task):
        # Including checker identity prevents patched test doubles from sharing
        # cached values while production module functions remain stable objects.
        return (
            task.provider,
            task.platform,
            task.handle.strip().lower().lstrip("@"),
            id(task.checker),
        )

    def _cache_get(self, task):
        key = self._cache_key(task)
        now = monotonic()
        with self._cache_lock:
            cached = self._cache.get(key)
            if not cached:
                return None
            expires_at, row = cached
            if expires_at <= now:
                self._cache.pop(key, None)
                return None
            result = deepcopy(row)
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        metadata = dict(metadata)
        metadata["cache_hit"] = True
        result["metadata"] = metadata
        return result

    def _cache_put(self, task, row):
        ttl = self._cache_ttl(row)
        if ttl <= 0 or not isinstance(row, dict):
            return
        key = self._cache_key(task)
        with self._cache_lock:
            self._cache[key] = (monotonic() + ttl, deepcopy(row))

    @staticmethod
    def _runtime_unknown(task, error):
        return Evidence(
            platform=task.platform,
            handle=task.handle,
            source=task.provider,
            method="provider_runtime",
            signal="unknown",
            confidence=0.0,
            detail=f"Provider runtime failed: {type(error).__name__}",
            metadata={"runtime_error": True, "non_blocking": True},
        ).to_dict()

    def _execute(self, task):
        cached = self._cache_get(task)
        if cached is not None:
            return cached

        try:
            with self._semaphore(task.provider):
                row = task.checker(task.handle, task.platform)
        except Exception as error:  # adapters should fail closed; runtime is the last guard
            return self._runtime_unknown(task, error)

        if not isinstance(row, dict):
            row = self._runtime_unknown(task, TypeError("provider returned non-object evidence"))
        self._cache_put(task, row)
        return row

    def run_many(self, tasks):
        """Execute independent tasks concurrently and return rows by task key."""
        tasks = list(tasks)
        if not tasks:
            return {}
        futures = {self._executor.submit(self._execute, task): task for task in tasks}
        result = {}
        for future in as_completed(futures):
            task = futures[future]
            try:
                result[task.key] = future.result()
            except Exception as error:  # defensive: worker exceptions never escape verification
                result[task.key] = self._runtime_unknown(task, error)
        return result

    def clear_cache(self):
        with self._cache_lock:
            self._cache.clear()


RUNTIME = ProviderRuntime()


def run_provider_checks(tasks):
    return RUNTIME.run_many(tasks)


def clear_provider_cache():
    RUNTIME.clear_cache()


__all__ = [
    "ProviderRuntime",
    "ProviderTask",
    "clear_provider_cache",
    "run_provider_checks",
]
