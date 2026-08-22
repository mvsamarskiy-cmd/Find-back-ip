#!/usr/bin/env python3
"""Create a Telethon StringSession for the isolated Telegram evidence service.

Run on your laptop only. Prints TELEGRAM_SESSION_STRING once.
Never commit the output. Never paste it into chat logs or git.

Requires:
  pip install Telethon==1.44.0
  TELEGRAM_API_ID and TELEGRAM_API_HASH from https://my.telegram.org
"""
from __future__ import annotations

import asyncio
import os
import sys


def main() -> int:
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print("Install Telethon first: pip install Telethon==1.44.0", file=sys.stderr)
        return 1

    try:
        api_id = int(os.environ.get("TELEGRAM_API_ID", "").strip())
    except (TypeError, ValueError):
        api_id = 0
    api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip()
    if not api_id or not api_hash:
        print(
            "Set TELEGRAM_API_ID and TELEGRAM_API_HASH from https://my.telegram.org",
            file=sys.stderr,
        )
        return 1

    async def _run() -> str:
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.start()
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram client is not authorized after start()")
        me = await client.get_me()
        session = client.session.save()
        await client.disconnect()
        label = getattr(me, "username", None) or getattr(me, "id", "?")
        print(f"# authorized as: {label}", file=sys.stderr)
        print("# paste into Railway telegram-evidence service only:", file=sys.stderr)
        print(f"TELEGRAM_SESSION_STRING={session}")
        return session

    try:
        asyncio.run(_run())
    except Exception as error:
        print(f"Failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
