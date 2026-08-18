import os


def _configured(*names):
    return all(bool(os.environ.get(name, "").strip()) for name in names)


def provider_diagnostics():
    """Return non-secret verification capability diagnostics.

    Only booleans and provider names are exposed. Secret values are never
    returned or logged by this helper.
    """
    namecom = _configured("NAMECOM_USERNAME", "NAMECOM_API_TOKEN")
    youtube = _configured("YOUTUBE_API_KEY")
    x_api = _configured("X_BEARER_TOKEN")
    telegram_evidence = _configured("TELEGRAM_EVIDENCE_URL", "TELEGRAM_EVIDENCE_TOKEN")

    return {
        "domain": {
            "rdap": {
                "provider": "verisign_rdap",
                "configured": True,
                "authoritative_for_registration_presence": True,
            },
            "registrar": {
                "provider": "name.com",
                "configured": namecom,
                "can_confirm_claimability": namecom,
                "required_env": ["NAMECOM_USERNAME", "NAMECOM_API_TOKEN"],
                "strict_green_requires_registrar_confirmation": True,
            },
        },
        "youtube": {
            "official_api": {
                "provider": "youtube_data_api",
                "configured": youtube,
                "required_env": ["YOUTUBE_API_KEY"],
                "can_confirm_occupancy": youtube,
                "can_confirm_claimability": False,
            },
            "public_profile_fallback": True,
            "authoritative_claimability": False,
        },
        "x": {
            "official_api": {
                "provider": "x_api",
                "configured": x_api,
                "required_env": ["X_BEARER_TOKEN"],
                "can_confirm_occupancy": x_api,
                "can_confirm_claimability": False,
            },
            "public_profile_fallback": True,
            "authoritative_claimability": False,
        },
        "instagram": {"public_profile_fallback": True, "authoritative_claimability": False},
        "telegram": {
            "public_profile_fallback": True,
            "evidence_service": {
                "configured": telegram_evidence,
                "required_env": ["TELEGRAM_EVIDENCE_URL", "TELEGRAM_EVIDENCE_TOKEN"],
                "claimability_contract": "channels.checkUsername-v2",
                "strict_green_scope": "channel",
                "strict_green_method": "channels.checkUsername",
                "can_accept_authoritative_claimability": telegram_evidence,
            },
            "authoritative_claimability": telegram_evidence,
        },
        "tiktok": {"public_profile_fallback": True, "authoritative_claimability": False},
        "facebook": {"public_profile_fallback": True, "authoritative_claimability": False},
    }
