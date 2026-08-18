from telegram_integration import install


install()

from app import app  # noqa: E402


__all__ = ["app"]
