import math
import re
from collections import Counter


FAMILY_KEYS = (
    "semantic_compound",
    "evocative_metaphor",
    "root_blend",
    "invented_phonetic",
    "abstract",
)


POSITIVE_WORDS = (
    "подоба", "гарно", "клас", "супер", "круто", "добре", "звучить", "love", "like",
)
NEGATIVE_WORDS = (
    "не подоб", "погано", "дивно", "слаб", "нуд", "не хочу", "hate", "dislike",
)


def _clean_name(value):
    return re.sub(r"[^a-z]", "", str(value or "").lower())[:30]


def _family(value):
    family = str(value or "").strip()
    return family if family in FAMILY_KEYS else "unknown"


def _comment_polarity(comment):
    text = " ".join(str(comment or "").lower().split())
    if not text:
        return 0.0
    positive = sum(token in text for token in POSITIVE_WORDS)
    negative = sum(token in text for token in NEGATIVE_WORDS)
    if positive and not negative:
        return 0.55
    if negative and not positive:
        return -0.55
    return 0.0


def _name_features(name, family="unknown"):
    clean = _clean_name(name)
    features = {f"family:{_family(family)}"}
    if not clean:
        return features
    length = len(clean)
    if length <= 8:
        features.add("shape:short")
    elif length >= 12:
        features.add("shape:long")
    vowel_groups = len(re.findall(r"[aeiouy]+", clean))
    if 2 <= vowel_groups <= 3:
        features.add("shape:balanced_syllables")
    if re.search(r"(sky|wing|flock|bird|goos|gander|plume|feather|roost|nest|wild|dawn|river|reed)", clean):
        features.add("semantic:nature_bird")
    if family in {"semantic_compound", "evocative_metaphor"}:
        features.add("style:meaningful")
    if family in {"invented_phonetic", "abstract"}:
        features.add("style:abstract")
    return features


def build_taste_model(feedback=None, candidate_rows=None, direction_anchors=None, shortlist=None):
    """Compile explicit session feedback into a bounded, auditable taste model.

    The model treats clicks as explicit evidence. Comment sentiment is only a soft
    signal and never rewrites the stored vote. Feature weights are hypotheses used
    for ranking/generation, not claims about the user's motives.
    """
    feedback = feedback if isinstance(feedback, dict) else {}
    rows = candidate_rows if isinstance(candidate_rows, list) else []
    row_by_name = {
        _clean_name(row.get("name")): row
        for row in rows
        if isinstance(row, dict) and _clean_name(row.get("name"))
    }
    anchors = {_clean_name(value) for value in (direction_anchors or []) if _clean_name(value)}
    short = {_clean_name(value) for value in (shortlist or []) if _clean_name(value)}

    feature_scores = Counter()
    liked = []
    disliked = []
    soft_positive = []
    soft_negative = []
    evidence_events = 0

    for raw_name, raw in list(feedback.items())[:80]:
        if not isinstance(raw, dict):
            continue
        name = _clean_name(raw_name)
        if not name:
            continue
        row = row_by_name.get(name, {})
        family = _family(row.get("family"))
        try:
            vote = int(raw.get("vote", 0))
        except (TypeError, ValueError):
            vote = 0
        vote = 1 if vote > 0 else -1 if vote < 0 else 0
        comment = str(raw.get("comment", ""))[:300]
        comment_signal = _comment_polarity(comment)

        signal = float(vote)
        if vote == 0:
            signal = comment_signal
            if signal > 0:
                soft_positive.append(name)
            elif signal < 0:
                soft_negative.append(name)
        elif vote > 0:
            liked.append(name)
        else:
            disliked.append(name)

        if name in anchors:
            signal += 0.65
        if name in short:
            signal += 0.35
        if signal == 0:
            continue
        evidence_events += 1
        for feature in _name_features(name, family):
            feature_scores[feature] += signal

    for name in anchors:
        row = row_by_name.get(name, {})
        for feature in _name_features(name, row.get("family")):
            feature_scores[feature] += 0.4
    for name in short:
        row = row_by_name.get(name, {})
        for feature in _name_features(name, row.get("family")):
            feature_scores[feature] += 0.2

    max_abs = max((abs(value) for value in feature_scores.values()), default=1.0)
    normalized = {
        key: round(max(-1.0, min(1.0, value / max_abs)), 3)
        for key, value in feature_scores.items()
        if abs(value) >= 0.15
    }
    family_weights = {
        family: normalized.get(f"family:{family}", 0.0)
        for family in FAMILY_KEYS
    }
    confidence = round(min(1.0, 1.0 - math.exp(-evidence_events / 5.0)), 3)
    return {
        "liked_examples": liked[-20:],
        "disliked_examples": disliked[-20:],
        "soft_positive_examples": soft_positive[-20:],
        "soft_negative_examples": soft_negative[-20:],
        "direction_examples": list(anchors)[-20:],
        "shortlist_examples": list(short)[-20:],
        "feature_weights": normalized,
        "family_weights": family_weights,
        "confidence": confidence,
        "evidence_events": evidence_events,
    }


def candidate_preference_score(candidate, taste_model):
    """Return a 0-100 user-fit score from explicit/soft session evidence."""
    if not isinstance(candidate, dict) or not isinstance(taste_model, dict):
        return 50.0
    weights = taste_model.get("feature_weights", {})
    if not isinstance(weights, dict) or not weights:
        return 50.0
    features = _name_features(candidate.get("name"), candidate.get("family"))
    values = [float(weights.get(feature, 0.0)) for feature in features]
    signal = sum(values) / max(1, len(values))
    confidence = float(taste_model.get("confidence", 0.0) or 0.0)
    return round(max(0.0, min(100.0, 50.0 + 45.0 * signal * confidence)), 1)


def family_allocation(count, taste_model, exploration=0.25):
    """Allocate a batch across naming families while retaining exploration."""
    count = max(1, int(count))
    weights = taste_model.get("family_weights", {}) if isinstance(taste_model, dict) else {}
    confidence = float(taste_model.get("confidence", 0.0) or 0.0) if isinstance(taste_model, dict) else 0.0
    base = 1.0 / len(FAMILY_KEYS)
    raw = {}
    for family in FAMILY_KEYS:
        preference = max(-1.0, min(1.0, float(weights.get(family, 0.0) or 0.0)))
        learned = math.exp(1.4 * preference * confidence)
        raw[family] = exploration * base + (1.0 - exploration) * learned
    total = sum(raw.values()) or 1.0
    shares = {key: value / total for key, value in raw.items()}
    return shares
