import math
import re
from collections import Counter, defaultdict


FAMILY_KEYS = (
    "semantic_compound",
    "evocative_metaphor",
    "root_blend",
    "invented_phonetic",
    "abstract",
)


POSITIVE_WORDS = (
    "подоба", "гарно", "клас", "супер", "круто", "добре", "звучить", "приколь",
    "елегант", "красив", "love", "like", "nice", "clean", "premium",
)
NEGATIVE_WORDS = (
    "не подоб", "погано", "дивно", "слаб", "нуд", "не хочу", "занадто популяр",
    "популярне", "баналь", "дебіл", "дибіл", "туп", "смішно", "не прикол", "пздц", "жах",
    "hate", "dislike", "generic", "common", "awkward", "silly", "ugly",
)

COMMENT_DIRECTIVES = {
    "avoid_generic_or_overpopular": (
        "занадто популяр", "популярне", "баналь", "generic", "common", "overused",
    ),
    "avoid_awkward_or_silly_sound": (
        "дебіл", "дибіл", "туп", "смішно", "не прикол", "пздц", "жах", "awkward", "silly", "ugly",
    ),
    "prefer_elegant_or_clean_sound": (
        "гарно", "елегант", "красив", "clean", "premium",
    ),
    "prefer_appealing_sound": (
        "подоба", "клас", "супер", "круто", "добре", "звучить", "приколь", "nice", "love", "like",
    ),
}


FRAGMENT_MIN = 3
FRAGMENT_MAX = 6
MAX_FRAGMENT_FEATURES = 12


def _clean_name(value):
    return re.sub(r"[^a-z]", "", str(value or "").lower())[:30]


def _family(value):
    family = str(value or "").strip()
    return family if family in FAMILY_KEYS else "unknown"


def _comment_analysis(comment):
    text = " ".join(str(comment or "").lower().split())
    if not text:
        return 0.0, []

    positive = sum(token in text for token in POSITIVE_WORDS)
    negative = sum(token in text for token in NEGATIVE_WORDS)
    # A phrase such as "не прикольно" contains the positive stem "приколь";
    # explicit negation must win instead of cancelling itself out.
    if "не прикол" in text and positive:
        positive -= 1

    delta = positive - negative
    if delta > 0:
        polarity = min(0.65, 0.45 + 0.10 * (delta - 1))
    elif delta < 0:
        polarity = max(-0.65, -0.45 - 0.10 * (abs(delta) - 1))
    else:
        polarity = 0.0

    directives = [
        key
        for key, markers in COMMENT_DIRECTIVES.items()
        if any(marker in text for marker in markers)
    ]
    return polarity, directives


def _comment_polarity(comment):
    return _comment_analysis(comment)[0]


def _name_features(name, family="unknown"):
    clean = _clean_name(name)
    family = _family(family)
    features = {f"family:{family}"}
    if not clean:
        return features

    length = len(clean)
    if length <= 7:
        features.add("shape:short")
    elif length <= 10:
        features.add("shape:medium")
    else:
        features.add("shape:long")

    vowel_groups = len(re.findall(r"[aeiouy]+", clean))
    if 2 <= vowel_groups <= 3:
        features.add("shape:balanced_syllables")
    elif vowel_groups >= 4:
        features.add("shape:many_syllables")

    if clean[-1] in "aeiouy":
        features.add("shape:vowel_ending")
    else:
        features.add("shape:consonant_ending")

    if family in {"semantic_compound", "evocative_metaphor"}:
        features.add("style:meaningful")
    if family in {"invented_phonetic", "abstract"}:
        features.add("style:abstract")
    return features


def _fragment_weight(name, fragment, start):
    size = len(fragment)
    length_weight = 0.25 + 0.25 * (size - FRAGMENT_MIN)
    boundary = start == 0 or start + size == len(name)
    return length_weight * (1.2 if boundary else 1.0)


def _name_fragments(name):
    clean = _clean_name(name)
    output = {}
    if not clean:
        return output
    max_size = min(FRAGMENT_MAX, len(clean))
    for size in range(FRAGMENT_MIN, max_size + 1):
        for start in range(0, len(clean) - size + 1):
            fragment = clean[start:start + size]
            # One fragment contributes once per name. Keep its strongest position
            # weight (usually a prefix/suffix occurrence) to avoid repeated-letter bias.
            output[fragment] = max(
                output.get(fragment, 0.0),
                _fragment_weight(clean, fragment, start),
            )
    return output


def _normalized_weights(scores, minimum=0.15):
    max_abs = max((abs(value) for value in scores.values()), default=1.0)
    return {
        key: round(max(-1.0, min(1.0, value / max_abs)), 3)
        for key, value in scores.items()
        if abs(value) >= minimum
    }


def _compile_fragment_preferences(fragment_scores, fragment_support):
    eligible = {
        fragment: score
        for fragment, score in fragment_scores.items()
        if len(fragment_support.get(fragment, ())) >= 2 and abs(score) >= 0.75
    }
    if not eligible:
        return {}, {}

    max_abs = max(abs(value) for value in eligible.values()) or 1.0
    ranked = sorted(
        eligible.items(),
        key=lambda item: (abs(item[1]), len(fragment_support[item[0]]), len(item[0])),
        reverse=True,
    )[: MAX_FRAGMENT_FEATURES * 2]

    preferred = {}
    avoided = {}
    for fragment, value in ranked:
        normalized = round(max(-1.0, min(1.0, value / max_abs)), 3)
        if normalized > 0 and len(preferred) < MAX_FRAGMENT_FEATURES:
            preferred[fragment] = normalized
        elif normalized < 0 and len(avoided) < MAX_FRAGMENT_FEATURES:
            avoided[fragment] = abs(normalized)
    return preferred, avoided


def build_taste_model(feedback=None, candidate_rows=None, direction_anchors=None, shortlist=None):
    """Compile explicit session feedback into a bounded, auditable taste model.

    The model learns contrastively from likes/dislikes and repeated name fragments.
    Comments can add soft sentiment and explicit directives, but they never rewrite
    a stored vote. Repeated fragments require support from at least two evidence
    names, which prevents one accidental candidate from becoming a hard naming rule.
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
    fragment_scores = Counter()
    fragment_support = defaultdict(set)
    directive_scores = Counter()
    liked = []
    disliked = []
    soft_positive = []
    soft_negative = []
    evidence_events = 0

    def add_name_signal(name, family, signal):
        if not name or signal == 0:
            return
        for feature in _name_features(name, family):
            feature_scores[feature] += signal
        for fragment, weight in _name_fragments(name).items():
            fragment_scores[fragment] += signal * weight
            fragment_support[fragment].add(name)

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
        comment_signal, directives = _comment_analysis(comment)
        directive_scores.update(directives)

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
        add_name_signal(name, family, signal)

    # An anchor/shortlist entry can exist without an explicit feedback row.
    for name in anchors:
        if name not in feedback:
            row = row_by_name.get(name, {})
            add_name_signal(name, row.get("family"), 0.4)
    for name in short:
        if name not in feedback:
            row = row_by_name.get(name, {})
            add_name_signal(name, row.get("family"), 0.2)

    normalized = _normalized_weights(feature_scores)
    family_weights = {
        family: normalized.get(f"family:{family}", 0.0)
        for family in FAMILY_KEYS
    }
    preferred_fragments, avoided_fragments = _compile_fragment_preferences(
        fragment_scores,
        fragment_support,
    )
    directives = [
        key for key, _count in directive_scores.most_common(8)
    ]
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
        "preferred_fragments": preferred_fragments,
        "avoided_fragments": avoided_fragments,
        "comment_directives": directives,
        "confidence": confidence,
        "evidence_events": evidence_events,
    }


def candidate_preference_score(candidate, taste_model):
    """Return a 0-100 user-fit score from explicit and contrastive session evidence."""
    if not isinstance(candidate, dict) or not isinstance(taste_model, dict):
        return 50.0

    weights = taste_model.get("feature_weights", {})
    if not isinstance(weights, dict):
        weights = {}
    features = _name_features(candidate.get("name"), candidate.get("family"))
    feature_values = [float(weights.get(feature, 0.0)) for feature in features]
    feature_signal = sum(feature_values) / max(1, len(feature_values))

    clean = _clean_name(candidate.get("name"))
    preferred = taste_model.get("preferred_fragments", {})
    avoided = taste_model.get("avoided_fragments", {})
    if not isinstance(preferred, dict):
        preferred = {}
    if not isinstance(avoided, dict):
        avoided = {}

    fragment_signal = 0.0
    for fragment, weight in preferred.items():
        if fragment and fragment in clean:
            fragment_signal += float(weight) * min(1.0, len(fragment) / 5.0)
    for fragment, weight in avoided.items():
        if fragment and fragment in clean:
            fragment_signal -= float(weight) * min(1.0, len(fragment) / 5.0)
    fragment_signal = math.tanh(fragment_signal)

    if not weights and not preferred and not avoided:
        return 50.0

    combined = 0.58 * feature_signal + 0.42 * fragment_signal
    confidence = float(taste_model.get("confidence", 0.0) or 0.0)
    return round(max(0.0, min(100.0, 50.0 + 45.0 * combined * confidence)), 1)


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
    return {key: value / total for key, value in raw.items()}
