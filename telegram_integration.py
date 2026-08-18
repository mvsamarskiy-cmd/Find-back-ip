import availability
from telegram_evidence import fetch_telegram_evidence


_PUBLIC_CHECKER = availability.check_telegram
_INSTALLED = False


def _service_result(status, detail, url, *, confidence, occupancy=None, claimability="unconfirmed", offer=None, evidence=None):
    result = availability._result(
        status,
        detail,
        url,
        source="telegram_evidence_service",
        method="mtproto_fragment",
        confidence=confidence,
        occupancy=occupancy,
        claimability=claimability,
        offer=offer,
    )
    if evidence is not None:
        result["telegram_evidence"] = evidence
    return result


def classify_telegram_evidence(name, envelope):
    """Convert secured MTProto/Fragment observations to NameMachine evidence."""
    handle = name.lower().lstrip("@")
    telegram_url = f"https://t.me/{handle}"
    transport = envelope.get("transport_status") if isinstance(envelope, dict) else None

    if transport == "rate_limited":
        return _service_result(
            "rate_limited",
            envelope.get("detail") or "Telegram evidence service rate limited the check",
            telegram_url,
            confidence=0.95,
        )
    if transport != "ok":
        return _service_result(
            "unknown",
            (envelope or {}).get("detail") if isinstance(envelope, dict) else "Telegram evidence service returned invalid transport data",
            telegram_url,
            confidence=0.9,
        )

    evidence = envelope.get("evidence") or {}
    mtproto = evidence.get("mtproto") or {}
    fragment = evidence.get("fragment") or {}
    mt_status = mtproto.get("status", "unknown")
    fragment_status = fragment.get("status", "unknown")
    fragment_url = fragment.get("url") or f"https://fragment.com/username/{handle}"

    if fragment_status == "for_sale":
        offer = {
            "provider": "fragment",
            "purchase_type": "marketplace",
            "premium": True,
            "username": handle,
            "url": fragment_url,
        }
        if fragment.get("price") is not None:
            offer["purchase_price"] = fragment["price"]
        if fragment.get("currency"):
            offer["currency"] = fragment["currency"]
        return _service_result(
            "purchasable",
            "Fragment reports this Telegram username as available for purchase",
            fragment_url,
            confidence=0.97,
            occupancy="occupied" if mt_status == "occupied" else "unknown",
            claimability="purchase_available",
            offer=offer,
            evidence=evidence,
        )

    if mt_status == "occupied" or fragment_status == "occupied":
        return _service_result(
            "taken",
            "Secured Telegram evidence reports the username as occupied",
            telegram_url,
            confidence=0.99,
            occupancy="occupied",
            claimability="not_claimable",
            evidence=evidence,
        )

    if mt_status == "reserved" or fragment_status == "reserved":
        return _service_result(
            "reserved",
            "Telegram/Fragment evidence reports the username as reserved",
            fragment_url if fragment_status == "reserved" else telegram_url,
            confidence=0.97,
            occupancy="unknown",
            claimability="not_claimable",
            evidence=evidence,
        )

    if mt_status == "not_found" and fragment_status == "not_found":
        return _service_result(
            "not_found",
            "MTProto and Fragment found no current username record; final claimability is still unconfirmed",
            telegram_url,
            confidence=0.94,
            occupancy="not_found",
            claimability="unconfirmed",
            evidence=evidence,
        )

    return _service_result(
        "unknown",
        "MTProto/Fragment evidence is inconclusive",
        telegram_url,
        confidence=0.9,
        evidence=evidence,
    )


def check_telegram(name):
    """Prefer secured evidence; use public t.me only when service is unconfigured."""
    envelope = fetch_telegram_evidence(name, timeout=availability.HTTP_TIMEOUT)
    if envelope is None:
        return _PUBLIC_CHECKER(name)
    return classify_telegram_evidence(name, envelope)


def install():
    """Install the stronger checker into availability.check_all at process start."""
    global _INSTALLED
    if not _INSTALLED:
        availability.check_telegram = check_telegram
        _INSTALLED = True
    return availability
