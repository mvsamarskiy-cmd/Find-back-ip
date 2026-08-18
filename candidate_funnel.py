import re


VOWELS = frozenset("aeiouy")


def _letters(value):
    return re.sub(r"[^a-z]", "", str(value).lower())


def structural_quality(name):
    """Return a deterministic 0-100 pre-external-check name quality score.

    This is deliberately language-light: it measures useful structural signals
    such as concise length, vowel balance, pronounceability proxies, and repeated
    character/consonant-run penalties. It does not claim semantic or legal quality.
    """
    value = _letters(name)
    if not value:
        return 0

    score = 100.0
    length = len(value)
    if 5 <= length <= 8:
        pass
    elif 4 <= length <= 10:
        score -= 8
    elif 3 <= length <= 12:
        score -= 20
    else:
        score -= 38

    vowel_count = sum(char in VOWELS for char in value)
    vowel_ratio = vowel_count / length
    if vowel_count == 0:
        score -= 55
    elif not 0.25 <= vowel_ratio <= 0.62:
        score -= 18

    consonant_runs = re.findall(r"[^aeiouy]+", value)
    longest_consonant_run = max((len(run) for run in consonant_runs), default=0)
    if longest_consonant_run >= 5:
        score -= 34
    elif longest_consonant_run == 4:
        score -= 20
    elif longest_consonant_run == 3:
        score -= 5

    vowel_runs = re.findall(r"[aeiouy]+", value)
    longest_vowel_run = max((len(run) for run in vowel_runs), default=0)
    if longest_vowel_run >= 4:
        score -= 22
    elif longest_vowel_run == 3:
        score -= 8

    if re.search(r"(.)\1", value):
        score -= 7
    if re.search(r"(.{2})\1", value):
        score -= 9

    transitions = sum(
        (value[index] in VOWELS) != (value[index - 1] in VOWELS)
        for index in range(1, length)
    )
    transition_ratio = transitions / max(1, length - 1)
    if transition_ratio >= 0.55:
        score += 5
    elif transition_ratio < 0.25:
        score -= 10

    return max(0, min(100, round(score)))


def rank_candidate_pool(candidates):
    """Annotate and rank AI candidates before expensive external checks.

    Stable original order breaks ties so model preference is preserved when the
    deterministic quality score cannot distinguish candidates.
    """
    ranked = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        row = dict(candidate)
        row["local_quality_score"] = structural_quality(row.get("name", ""))
        ranked.append((index, row))
    ranked.sort(key=lambda item: (-item[1]["local_quality_score"], item[0]))
    return [row for _, row in ranked]
