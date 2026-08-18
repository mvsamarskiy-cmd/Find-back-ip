"""Catalog the verifier layers that can run without user API credentials."""


def no_key_capabilities():
    return {
        "direct_public_web": {
            "enabled": True,
            "resources": ["instagram", "telegram", "tiktok", "youtube", "facebook", "x"],
            "role": "public_presence",
            "can_confirm_claimability": False,
        },
        "verisign_rdap": {
            "enabled": True,
            "resources": ["com"],
            "role": "authoritative_registration_presence",
            "can_confirm_claimability": False,
        },
        "socialscan": {
            "enabled": False,
            "optional_dependency": "socialscan",
            "resources": ["instagram", "x"],
            "role": "registration_side_probe",
            "can_confirm_claimability": True,
            "authoritative": False,
        },
        "whatsmyname": {
            "enabled": False,
            "resources": ["instagram", "telegram", "tiktok", "youtube", "facebook", "x"],
            "role": "public_presence_corroboration",
            "can_confirm_claimability": False,
        },
        "maigret": {
            "enabled": False,
            "resources": ["instagram", "telegram", "tiktok", "youtube", "facebook", "x"],
            "role": "wide_collision_search",
            "can_confirm_claimability": False,
        },
        "search_corroboration": {
            "enabled": False,
            "resources": ["instagram", "telegram", "tiktok", "youtube", "facebook", "x"],
            "role": "indexed_presence_corroboration",
            "can_confirm_claimability": False,
        },
    }
