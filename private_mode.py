"""Hidden server-side private/global search mode for NameMachine.

The public UI never receives the unlock/lock phrases. Production stores only
scrypt hashes in environment variables and grants a short-lived signed HttpOnly
session after a matching command is submitted through the normal search field.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import unicodedata
from dataclasses import dataclass
from typing import Callable

from flask import jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from global_search import global_search_capabilities, search_global


COOKIE_NAME = "nm_private_global"
SESSION_SCOPE = "private_global"
SESSION_TTL_SECONDS = 12 * 60 * 60
DEFAULT_COMMAND_LIMIT = "8 per minute"
DEFAULT_SEARCH_LIMIT = "30 per minute"


@dataclass(frozen=True)
class PrivateModeConfig:
    unlock_hash: str
    lock_hash: str
    session_key: str

    @property
    def configured(self) -> bool:
        return bool(self.unlock_hash and self.lock_hash and len(self.session_key) >= 32)


def _config() -> PrivateModeConfig:
    return PrivateModeConfig(
        unlock_hash=str(os.environ.get("PRIVATE_MODE_UNLOCK_HASH") or "").strip(),
        lock_hash=str(os.environ.get("PRIVATE_MODE_LOCK_HASH") or "").strip(),
        session_key=str(os.environ.get("PRIVATE_MODE_SESSION_KEY") or "").strip(),
    )


def _normalize_secret(value: object) -> str:
    return unicodedata.normalize("NFC", str(value or "").strip())


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def hash_secret_for_env(secret: str, *, salt: bytes | None = None) -> str:
    """Create an env-safe scrypt hash. Intended for setup/tests, never browser use."""
    normalized = _normalize_secret(secret)
    if not normalized:
        raise ValueError("Secret must not be empty")
    salt = salt or os.urandom(16)
    n, r, p = 16384, 8, 1
    digest = hashlib.scrypt(
        normalized.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32
    )
    return f"scrypt${n}${r}${p}${_b64encode(salt)}${_b64encode(digest)}"


def verify_secret(secret: str, encoded: str) -> bool:
    """Constant-time verification of the configured scrypt hash."""
    try:
        scheme, n_raw, r_raw, p_raw, salt_raw, digest_raw = str(encoded).split("$", 5)
        if scheme != "scrypt":
            return False
        n, r, p = int(n_raw), int(r_raw), int(p_raw)
        if not (16384 <= n <= 262144 and 1 <= r <= 16 and 1 <= p <= 8):
            return False
        salt = _b64decode(salt_raw)
        expected = _b64decode(digest_raw)
        if not (8 <= len(salt) <= 64 and 16 <= len(expected) <= 64):
            return False
        actual = hashlib.scrypt(
            _normalize_secret(secret).encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError, MemoryError):
        return False


def _serializer(config: PrivateModeConfig) -> URLSafeTimedSerializer | None:
    if not config.configured:
        return None
    return URLSafeTimedSerializer(config.session_key, salt="namemachine-private-global-v1")


def _session_token(config: PrivateModeConfig) -> str | None:
    serializer = _serializer(config)
    if serializer is None:
        return None
    return serializer.dumps({"scope": SESSION_SCOPE, "v": 1})


def _session_active(config: PrivateModeConfig) -> bool:
    serializer = _serializer(config)
    token = request.cookies.get(COOKIE_NAME, "")
    if serializer is None or not token:
        return False
    try:
        payload = serializer.loads(token, max_age=SESSION_TTL_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    return isinstance(payload, dict) and payload.get("scope") == SESSION_SCOPE


def _json_body() -> dict:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _set_private_cookie(response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="Strict",
        path="/",
    )


def _clear_private_cookie(response) -> None:
    response.delete_cookie(
        COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="Strict",
        path="/",
    )


def _hide_private_route():
    return jsonify({"error": "Not found"}), 404


def _capability_payload() -> dict:
    return {
        "mode": "private",
        "search": global_search_capabilities(),
        "shared_namemachine_logic": [
            "query_generation",
            "parallel_source_search",
            "deduplication",
            "source_evidence",
            "ranking",
            "filters",
            "history_boundary",
            "feedback_ready",
        ],
    }


def private_mode_diagnostics() -> dict:
    config = _config()
    capabilities = global_search_capabilities()
    return {
        "configured": config.configured,
        "backend_authorized": True,
        "plaintext_secret_in_client": False,
        "session_cookie": {
            "http_only": True,
            "secure": True,
            "same_site": "Strict",
            "ttl_seconds": SESSION_TTL_SECONDS,
        },
        "global_search_provider_configured": bool(capabilities.get("provider_configured")),
    }


def install_private_mode_routes(app, app_module=None, *, global_searcher: Callable = search_global):
    """Install the hidden mode gate and private search routes on the Flask app."""
    if getattr(app, "_namemachine_private_mode_installed", False):
        return
    app._namemachine_private_mode_installed = True

    limiter = getattr(app_module, "limiter", None)

    def command_view():
        config = _config()
        if not config.configured:
            return jsonify({"handled": False})
        payload = _json_body()
        command = _normalize_secret(payload.get("command"))
        if not command or len(command) > 512:
            return jsonify({"handled": False})

        if verify_secret(command, config.unlock_hash):
            token = _session_token(config)
            if not token:
                return jsonify({"handled": False})
            response = jsonify({"handled": True, "mode": "private"})
            _set_private_cookie(response, token)
            return response

        if verify_secret(command, config.lock_hash):
            response = jsonify({"handled": True, "mode": "public"})
            _clear_private_cookie(response)
            return response

        return jsonify({"handled": False})

    def state_view():
        config = _config()
        if _session_active(config):
            return jsonify(_capability_payload())
        return jsonify({"mode": "public"})

    def search_view():
        config = _config()
        if not _session_active(config):
            return _hide_private_route()
        payload = _json_body()
        query = " ".join(str(payload.get("query") or "").split())
        if len(query) < 2:
            return jsonify({"error": "Query must contain at least 2 characters"}), 400
        if len(query) > 2000:
            return jsonify({"error": "Query must contain at most 2000 characters"}), 400
        category = str(payload.get("category") or "all").strip().lower()
        country = str(payload.get("country") or "EU").strip()
        try:
            result = global_searcher(query, category=category, country=country)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except Exception:
            app.logger.exception("Private global search failed")
            return jsonify({"error": "Temporary global search error"}), 503
        return jsonify(result)

    if limiter is not None:
        command_view = limiter.limit(DEFAULT_COMMAND_LIMIT)(command_view)
        search_view = limiter.limit(DEFAULT_SEARCH_LIMIT)(search_view)

    app.add_url_rule(
        "/api/private-mode/command",
        endpoint="private_mode_command",
        view_func=command_view,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/private-mode/state",
        endpoint="private_mode_state",
        view_func=state_view,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/private-mode/search",
        endpoint="private_mode_search",
        view_func=search_view,
        methods=["POST"],
    )


__all__ = [
    "COOKIE_NAME",
    "hash_secret_for_env",
    "install_private_mode_routes",
    "private_mode_diagnostics",
    "verify_secret",
]
