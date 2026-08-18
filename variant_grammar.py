"""User-controlled identifier variants with platform-specific grammar.

This module is deliberately separate from availability verification. It only
creates syntactically plausible *shapes* after the user explicitly expands a
clean-name search. A generated variant is never evidence that the identifier is
free or claimable; the normal verifier must still prove that separately.
"""

from __future__ import annotations

import re


RESOURCE_KEYS = (
    "com",
    "instagram",
    "telegram",
    "tiktok",
    "youtube",
    "facebook",
    "x",
)

OPTION_KEYS = (
    "underscore",
    "digits",
    "dots",
    "hyphen",
    "prefix",
    "suffix",
)

DEFAULT_OPTIONS = {
    "underscore": False,
    "digits": False,
    "dots": False,
    "hyphen": False,
    "prefix": False,
    "suffix": False,
    "number_tokens": [],
    "prefixes": [],
    "suffixes": [],
}

# The authoritative limits below are encoded only where the platform publishes
# them clearly. For Instagram/TikTok/Facebook we keep NameMachine's own 30-char
# product cap rather than pretending it is a complete legal/platform contract.
# Final acceptance always belongs to the platform/verifier.
PLATFORM_RULES = {
    "com": {
        "min_length": 1,
        "max_length": 63,
        "length_basis": "dns_label",
        "supports": {"underscore": False, "digits": True, "dots": False, "hyphen": True},
        "notes": ["ASCII LDH label; hyphen cannot begin or end the label."],
    },
    "instagram": {
        "min_length": 1,
        "max_length": 30,
        "length_basis": "namemachine_product_cap",
        "supports": {"underscore": True, "digits": True, "dots": True, "hyphen": False},
        "notes": ["Instagram Help explicitly recommends periods, numbers and underscores as variants."],
    },
    "telegram": {
        "min_length": 5,
        "max_length": 32,
        "length_basis": "telegram_checkUsername",
        "supports": {"underscore": True, "digits": True, "dots": False, "hyphen": False},
        "notes": ["Telegram checkUsername accepts letters, digits and underscores."],
    },
    "tiktok": {
        "min_length": 1,
        "max_length": 30,
        "length_basis": "namemachine_product_cap",
        "supports": {"underscore": True, "digits": True, "dots": True, "hyphen": False},
        "notes": ["TikTok Help allows letters, numbers, underscores and periods; a period cannot end the username."],
    },
    "youtube": {
        "min_length": 3,
        "max_length": 30,
        "length_basis": "youtube_handle_guidelines",
        "supports": {"underscore": True, "digits": True, "dots": True, "hyphen": True},
        "notes": ["ASCII subset only; separators cannot begin or end the handle."],
    },
    "facebook": {
        "min_length": 5,
        "max_length": 30,
        "length_basis": "facebook_min_plus_namemachine_product_cap",
        "supports": {"underscore": False, "digits": True, "dots": False, "hyphen": False},
        "notes": [
            "Facebook syntax allows periods, but periods and capitalization do not distinguish usernames, so NameMachine does not generate dot variants as availability escapes."
        ],
    },
    "x": {
        "min_length": 5,
        "max_length": 15,
        "length_basis": "x_username_guidelines",
        "supports": {"underscore": True, "digits": True, "dots": False, "hyphen": False},
        "notes": ["X usernames use letters, digits and underscores only."],
    },
}


def _resource(value):
    resource = str(value or "").strip().lower()
    if resource not in RESOURCE_KEYS:
        raise ValueError(f"Unsupported resource: {resource or value!r}")
    return resource


def _base(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())[:63]


def _token_list(value, *, limit=12, item_limit=12, digits_only=False):
    if not isinstance(value, (list, tuple)):
        return []
    output = []
    seen = set()
    for raw in value[:limit]:
        text = str(raw or "").strip().lower()
        if digits_only:
            text = re.sub(r"[^0-9]", "", text)
        else:
            text = re.sub(r"[^a-z0-9]", "", text)
        text = text[:item_limit]
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def clean_variant_options(value=None):
    """Return bounded opt-in options; every mutation is OFF by default."""
    raw = value if isinstance(value, dict) else {}
    result = dict(DEFAULT_OPTIONS)
    for key in OPTION_KEYS:
        result[key] = bool(raw.get(key, False))
    result["number_tokens"] = _token_list(
        raw.get("number_tokens"), limit=10, item_limit=4, digits_only=True
    )
    result["prefixes"] = _token_list(raw.get("prefixes"), limit=10, item_limit=12)
    result["suffixes"] = _token_list(raw.get("suffixes"), limit=10, item_limit=12)
    return result


def mutation_capabilities(resource):
    resource = _resource(resource)
    rule = PLATFORM_RULES[resource]
    return {
        "resource": resource,
        "supports": dict(rule["supports"]),
        "min_length": rule["min_length"],
        "max_length": rule["max_length"],
        "length_basis": rule["length_basis"],
        "notes": list(rule["notes"]),
        "strict_availability_proof": False,
    }


def validate_variant_shape(resource, value):
    """Validate the conservative ASCII shape used by this variant generator.

    This is a syntax guard, not an availability or claimability verdict.
    """
    resource = _resource(resource)
    text = str(value or "").strip().lower().lstrip("@")
    if not text:
        return False
    rule = PLATFORM_RULES[resource]
    if not rule["min_length"] <= len(text) <= rule["max_length"]:
        return False

    if resource == "com":
        return bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", text))
    if resource == "telegram":
        return bool(re.fullmatch(r"[a-z0-9_]+", text))
    if resource == "x":
        return bool(re.fullmatch(r"[a-z0-9_]+", text))
    if resource == "youtube":
        if text[0] in "_.-" or text[-1] in "_.-":
            return False
        return bool(re.fullmatch(r"[a-z0-9._-]+", text))
    if resource == "instagram":
        return bool(re.fullmatch(r"[a-z0-9._]+", text))
    if resource == "tiktok":
        return not text.endswith(".") and bool(re.fullmatch(r"[a-z0-9._]+", text))
    if resource == "facebook":
        return bool(re.fullmatch(r"[a-z0-9.]+", text))
    return False


def canonical_namespace_key(resource, value):
    """Return a dedupe key for variants that share a platform namespace."""
    resource = _resource(resource)
    text = str(value or "").strip().lower().lstrip("@")
    if resource == "facebook":
        # Facebook explicitly says dots/capitalization do not distinguish names.
        text = text.replace(".", "")
    return text


def _midpoint_variant(base, separator):
    if len(base) < 4:
        return ""
    midpoint = max(2, min(len(base) - 2, len(base) // 2))
    return base[:midpoint] + separator + base[midpoint:]


def generate_variants(stem, resource, options=None, *, limit=50):
    """Generate opt-in variants in quality-first order for one platform.

    The unmodified clean stem is intentionally NOT returned. NameMachine should
    search it first, then call this function only after the user chooses
    "Розширити пошук". Numbers are never invented: ``number_tokens`` must be
    supplied explicitly, preventing automatic ``name123`` spam.
    """
    resource = _resource(resource)
    base = _base(stem)
    if not base:
        return []
    config = clean_variant_options(options)
    supports = PLATFORM_RULES[resource]["supports"]
    limit = max(1, min(200, int(limit)))

    output = []
    seen = {canonical_namespace_key(resource, base)}

    def add(value, mutation, detail=""):
        candidate = str(value or "").lower()
        if not validate_variant_shape(resource, candidate):
            return
        key = canonical_namespace_key(resource, candidate)
        if not key or key in seen:
            return
        seen.add(key)
        output.append({
            "identifier": candidate,
            "resource": resource,
            "mutation": mutation,
            "detail": detail,
            "syntax_valid": True,
            "availability": "unverified",
            "claimability": "unconfirmed",
        })

    # Meaningful user-supplied affixes come before punctuation or digits.
    if config["prefix"]:
        for prefix in config["prefixes"]:
            add(prefix + base, "prefix", prefix)
    if config["suffix"]:
        for suffix in config["suffixes"]:
            add(base + suffix, "suffix", suffix)

    # Platform-specific separators. Facebook periods are intentionally excluded
    # because they do not create a distinct username namespace there.
    for option, separator in (("underscore", "_"), ("dots", "."), ("hyphen", "-")):
        if not config[option] or not supports.get(option):
            continue
        if option == "underscore" and resource == "x":
            # X itself recommends leading/trailing underscores when a name is taken.
            add("_" + base, "underscore", "leading")
            add(base + "_", "underscore", "trailing")
        else:
            add(_midpoint_variant(base, separator), option, "internal_separator")

    if config["digits"] and supports.get("digits"):
        for token in config["number_tokens"]:
            add(base + token, "digits", token)

    # If the user enabled both an affix and a supported separator, offer a small
    # number of clearer segmented forms after the direct affix candidates.
    separator_priority = []
    if config["underscore"] and supports.get("underscore"):
        separator_priority.append("_")
    if config["dots"] and supports.get("dots"):
        separator_priority.append(".")
    if config["hyphen"] and supports.get("hyphen"):
        separator_priority.append("-")
    for separator in separator_priority[:1]:
        if config["prefix"]:
            for prefix in config["prefixes"][:3]:
                add(prefix + separator + base, "prefix_separator", prefix + separator)
        if config["suffix"]:
            for suffix in config["suffixes"][:3]:
                add(base + separator + suffix, "suffix_separator", separator + suffix)

    return output[:limit]


def generate_variants_for_resources(stem, resources, options=None, *, per_resource_limit=50):
    if isinstance(resources, str):
        resources = [item.strip() for item in resources.split(",") if item.strip()]
    if not isinstance(resources, (list, tuple, set, frozenset)):
        raise ValueError("resources must be a collection or comma-separated string")
    result = {}
    for raw in resources:
        resource = _resource(raw)
        result[resource] = generate_variants(
            stem,
            resource,
            options,
            limit=per_resource_limit,
        )
    return result


__all__ = [
    "DEFAULT_OPTIONS",
    "OPTION_KEYS",
    "PLATFORM_RULES",
    "RESOURCE_KEYS",
    "canonical_namespace_key",
    "clean_variant_options",
    "generate_variants",
    "generate_variants_for_resources",
    "mutation_capabilities",
    "validate_variant_shape",
]
