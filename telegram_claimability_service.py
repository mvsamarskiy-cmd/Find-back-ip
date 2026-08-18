"""Isolated Telegram channel-claimability service for NameMachine.

This process is intentionally separate from the public web/worker services. It
owns the Telegram user session needed for the official MTProto
``channels.checkUsername`` method and exposes only a narrow bearer-authenticated
HTTP contract to NameMachine.

The configured probe channel is never modified. It is used only as the target
argument required by ``channels.checkUsername`` so Telegram can confirm that a
candidate username is assignable to a channel/supergroup.

Never put TELEGRAM_SESSION_STRING, TELEGRAM_API_HASH, or the bearer token in the
public web service or source control.
"""
from __future__ import annotations

import asyncio
import hmac
import os
import re
from threading import BoundedSemaphore, Lock

from flask import Flask, jsonify, request
from telethon import TelegramClient, functions, errors, types
from telethon.sessions import StringSession


app = Flask(__name__)
MAX_CONCURRENT = max(1, min(4, int(os.environ.get("TELEGRAM_CLAIMABILITY_CONCURRENCY", "2"))))
SLOTS = BoundedSemaphore(MAX_CONCURRENT)
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")
_PROBE_CACHE = {}
_PROBE_CACHE_LOCK = Lock()


def _probe_channel_value():
    return (
        os.environ.get("TELEGRAM_PROBE_CHANNEL", "").strip()
        or os.environ.get("TELEGRAM_PROBE_CHANNEL_ID", "").strip()
    )


def _config():
    try:
        api_id = int(os.environ.get("TELEGRAM_API_ID", ""))
    except (TypeError, ValueError):
        api_id = 0
    return {
        "api_id": api_id,
        "api_hash": os.environ.get("TELEGRAM_API_HASH", "").strip(),
        "session": os.environ.get("TELEGRAM_SESSION_STRING", "").strip(),
        "token": os.environ.get("TELEGRAM_EVIDENCE_TOKEN", "").strip(),
        "probe_channel": _probe_channel_value(),
    }


def _configured(config=None):
    config = config or _config()
    return bool(
        config["api_id"]
        and config["api_hash"]
        and config["session"]
        and config["token"]
        and config["probe_channel"]
    )


def _authorized(config):
    header = request.headers.get("Authorization", "")
    expected = f"Bearer {config['token']}"
    return bool(config["token"] and hmac.compare_digest(header, expected))


def _rpc_code(error):
    message = str(getattr(error, "message", "") or "").upper()
    class_name = type(error).__name__.upper()
    compact = re.sub(r"[^A-Z0-9]", "", class_name)
    if "USERNAME_OCCUPIED" in message or "USERNAMEOCCUPIED" in compact:
        return "occupied"
    if "USERNAME_PURCHASE_AVAILABLE" in message or "USERNAMEPURCHASEAVAILABLE" in compact:
        return "purchasable"
    if "USERNAME_INVALID" in message or "USERNAMEINVALID" in compact:
        return "invalid"
    if "FLOOD_WAIT" in message or "FLOODWAIT" in compact:
        return "rate_limited"
    if "CHANNELS_ADMIN_PUBLIC_TOO_MUCH" in message or "CHANNELSADMINPUBLICTOOMUCH" in compact:
        return "scope_blocked"
    if any(code in message for code in (
        "CHANNEL_INVALID",
        "CHANNEL_PRIVATE",
        "CHAT_ADMIN_REQUIRED",
        "CHAT_WRITE_FORBIDDEN",
        "PEER_ID_INVALID",
    )):
        return "scope_unavailable"
    return "unknown"


def _normalize_probe_channel(value):
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Telegram probe channel is not configured")
    numeric = raw.lstrip("-")
    if numeric.isdigit():
        channel_id = int(raw)
        if channel_id < 0:
            digits = str(abs(channel_id))
            # Accept the common Bot API -100<channel_id> representation.
            if digits.startswith("100") and len(digits) > 3:
                digits = digits[3:]
            channel_id = int(digits)
        if channel_id <= 0:
            raise ValueError("Telegram probe channel id is invalid")
        return "id", channel_id
    return "username", raw.lower().lstrip("@")


async def _resolve_probe_channel(client, config):
    """Resolve a configured channel without exposing or persisting its access hash."""
    raw = config["probe_channel"]
    with _PROBE_CACHE_LOCK:
        cached = _PROBE_CACHE.get(raw)
    if cached is not None:
        return types.InputChannel(channel_id=cached[0], access_hash=cached[1])

    kind, value = _normalize_probe_channel(raw)
    entity = None
    if kind == "username":
        candidate = await client.get_entity(value)
        if isinstance(candidate, types.Channel):
            entity = candidate
    else:
        async for dialog in client.iter_dialogs():
            candidate = dialog.entity
            if isinstance(candidate, types.Channel) and int(candidate.id) == value:
                entity = candidate
                break

    if entity is None:
        raise RuntimeError("Configured Telegram probe channel was not found for this session")
    access_hash = getattr(entity, "access_hash", None)
    if access_hash is None:
        raise RuntimeError("Configured Telegram probe channel has no usable access hash")

    packed = (int(entity.id), int(access_hash))
    with _PROBE_CACHE_LOCK:
        _PROBE_CACHE[raw] = packed
    return types.InputChannel(channel_id=packed[0], access_hash=packed[1])


def _payload(username, status, detail):
    mt_status = "unknown"
    fragment_status = "unknown"
    if status == "claimable":
        mt_status = "not_found"
        fragment_status = "not_found"
    elif status == "occupied":
        mt_status = "occupied"
    elif status == "purchasable":
        mt_status = "not_found"
        fragment_status = "for_sale"

    normalized = status if status in {"claimable", "occupied", "purchasable", "invalid"} else "unknown"
    return {
        "username": username,
        "mtproto": {
            "status": mt_status,
            "detail": detail,
        },
        "fragment": {
            "status": fragment_status,
            "detail": "Telegram reported Fragment purchase availability" if status == "purchasable" else "",
            "url": f"https://fragment.com/username/{username}",
        },
        "claimability": {
            "status": normalized,
            "method": "channels.checkUsername",
            "scope": "channel",
            "detail": detail,
        },
    }


async def _probe_username(username, config):
    client = TelegramClient(
        StringSession(config["session"]),
        config["api_id"],
        config["api_hash"],
        connection_retries=1,
        request_retries=1,
        timeout=8,
    )
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram StringSession is not authorized")
        probe_channel = await _resolve_probe_channel(client, config)
        try:
            result = await client(functions.channels.CheckUsernameRequest(
                channel=probe_channel,
                username=username,
            ))
        except errors.RPCError as error:
            status = _rpc_code(error)
            if status == "rate_limited":
                raise
            if status in {"scope_blocked", "scope_unavailable"}:
                detail = {
                    "scope_blocked": "Telegram cannot test assignment because this account has reached its public-channel limit",
                    "scope_unavailable": "Configured Telegram probe channel is not usable by this session",
                }[status]
                return _payload(username, "unknown", detail)
            detail = {
                "occupied": "Telegram channels.checkUsername reports USERNAME_OCCUPIED",
                "purchasable": "Telegram channels.checkUsername reports USERNAME_PURCHASE_AVAILABLE",
                "invalid": "Telegram channels.checkUsername reports USERNAME_INVALID",
            }.get(status, f"Telegram RPC error: {type(error).__name__}")
            return _payload(username, status, detail)
        if bool(result):
            return _payload(
                username,
                "claimable",
                "Telegram channels.checkUsername directly confirmed this username can be assigned to the configured channel",
            )
        return _payload(
            username,
            "unknown",
            "Telegram channels.checkUsername returned false without a classified RPC error",
        )
    finally:
        await client.disconnect()


@app.get("/health")
def health():
    config = _config()
    return jsonify({
        "status": "ok" if _configured(config) else "configuration_required",
        "configured": _configured(config),
        "method": "channels.checkUsername",
        "scope": "channel",
        "probe_channel_configured": bool(config["probe_channel"]),
        "strict_claimability": True,
    })


@app.get("/v1/username/<username>")
def username_check(username):
    config = _config()
    if not _configured(config):
        return jsonify({"error": "Telegram channel-claimability service is not configured"}), 503
    if not _authorized(config):
        return jsonify({"error": "Unauthorized"}), 401

    handle = str(username or "").strip().lower().lstrip("@")
    if not USERNAME_RE.fullmatch(handle):
        return jsonify(_payload(
            handle,
            "invalid",
            "Telegram usernames must contain 5-32 ASCII letters, digits, or underscores",
        ))

    if not SLOTS.acquire(blocking=False):
        return jsonify({"error": "Telegram claimability service is busy"}), 429
    try:
        try:
            payload = asyncio.run(_probe_username(handle, config))
        except errors.FloodWaitError:
            return jsonify({"error": "Telegram rate limited the claimability probe"}), 429
        except Exception as error:
            app.logger.exception("Telegram channel claimability probe failed")
            return jsonify({
                "error": "Telegram channel claimability probe failed",
                "error_type": type(error).__name__,
            }), 503
        return jsonify(payload)
    finally:
        SLOTS.release()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
