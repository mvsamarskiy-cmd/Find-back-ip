"""Isolated Telegram claimability service for NameMachine.

This process is intentionally separate from the public web/worker services. It
owns the Telegram user session needed for the official MTProto
``account.checkUsername`` method and exposes only a narrow bearer-authenticated
HTTP contract to NameMachine.

Never put TELEGRAM_SESSION_STRING, TELEGRAM_API_HASH, or the bearer token in the
public web service or source control.
"""
from __future__ import annotations

import asyncio
import hmac
import os
import re
from threading import BoundedSemaphore

from flask import Flask, jsonify, request
from telethon import TelegramClient, functions, errors
from telethon.sessions import StringSession


app = Flask(__name__)
MAX_CONCURRENT = max(1, min(4, int(os.environ.get("TELEGRAM_CLAIMABILITY_CONCURRENCY", "2"))))
SLOTS = BoundedSemaphore(MAX_CONCURRENT)
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


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
    }


def _configured(config=None):
    config = config or _config()
    return bool(config["api_id"] and config["api_hash"] and config["session"] and config["token"])


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
    return "unknown"


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
    elif status == "invalid":
        mt_status = "unknown"

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
            "status": status if status in {"claimable", "occupied", "purchasable", "invalid"} else "unknown",
            "method": "account.checkUsername",
            "scope": "account",
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
        try:
            result = await client(functions.account.CheckUsernameRequest(username=username))
        except errors.RPCError as error:
            status = _rpc_code(error)
            if status == "rate_limited":
                raise
            detail = {
                "occupied": "Telegram account.checkUsername reports USERNAME_OCCUPIED",
                "purchasable": "Telegram account.checkUsername reports USERNAME_PURCHASE_AVAILABLE",
                "invalid": "Telegram account.checkUsername reports USERNAME_INVALID",
            }.get(status, f"Telegram RPC error: {type(error).__name__}")
            return _payload(username, status, detail)
        if bool(result):
            return _payload(
                username,
                "claimable",
                "Telegram account.checkUsername directly confirmed this username is available",
            )
        return _payload(
            username,
            "unknown",
            "Telegram account.checkUsername returned false without a classified RPC error",
        )
    finally:
        await client.disconnect()


@app.get("/health")
def health():
    return jsonify({
        "status": "ok" if _configured() else "configuration_required",
        "configured": _configured(),
        "method": "account.checkUsername",
        "strict_claimability": True,
    })


@app.get("/v1/username/<username>")
def username_check(username):
    config = _config()
    if not _configured(config):
        return jsonify({"error": "Telegram claimability service is not configured"}), 503
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
            app.logger.exception("Telegram claimability probe failed")
            return jsonify({
                "error": "Telegram claimability probe failed",
                "error_type": type(error).__name__,
            }), 503
        return jsonify(payload)
    finally:
        SLOTS.release()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
