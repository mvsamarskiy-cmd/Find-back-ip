import re


VOWELS = frozenset("aeiouy")
LOCAL_SOURCE = "local_lexical_expansion"

# Deliberately small stoplist: the local expander should use project-specific
# nouns/adjectives, not prose glue from a brief. It is not a semantic model.
STOPWORDS = frozenset({
    "about", "after", "also", "brand", "create", "creating", "from", "have",
    "into", "name", "need", "project", "service", "that", "their", "them",
    "this", "want", "with", "your", "для", "бренд", "назва", "назву", "проєкт",
    "проект", "сервіс", "хочу", "щоб", "який", "яка", "яке", "такий", "таке",
    "і", "та", "або", "це", "цей", "ця", "мої", "моя", "мій", "якийсь",
})

CYRILLIC_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d",
    "е": "e", "є": "ye", "ё": "yo", "ж": "zh", "з": "z", "и": "y",
    "і": "i", "ї": "yi", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}


def _letters(value):
    return re.sub(r"[^a-z]", "", str(value).lower())


def _transliterate(value):
    return "".join(CYRILLIC_LATIN.get(char, char) for char in str(value).lower())


def _seed_tokens(value):
    tokens = []
    for raw in re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґЁё]{3,18}", str(value or "")):
        lowered = raw.lower()
        if lowered in STOPWORDS:
            continue
        token = _letters(_transliterate(lowered))
        if 3 <= len(token) <= 14 and token not in STOPWORDS:
            tokens.append(token)
    return tokens


def lexical_seeds(brief="", brand_dna=None, limit=18):
    """Extract a bounded set of literal lexical seeds from user-controlled context.

    Latin roots are preserved and Cyrillic roots are deterministically
    transliterated. The function does not invent synonyms: every root still comes
    from the brief or structured Brand DNA, keeping the local stage auditable.
    """
    values = [brief]
    if isinstance(brand_dna, dict):
        for key in (
            "entity_type", "offer", "positioning", "summary", "audiences",
            "brand_traits", "themes", "naming_directions", "keywords",
        ):
            raw = brand_dna.get(key)
            if isinstance(raw, list):
                values.extend(raw[:12])
            elif raw:
                values.append(raw)

    seeds = []
    seen = set()
    for value in values:
        for token in _seed_tokens(value):
            if token in seen:
                continue
            seen.add(token)
            seeds.append(token)
            if len(seeds) >= limit:
                return seeds
    return seeds


def _candidate(name, family, roots, pattern):
    clean = _letters(name)
    if not 3 <= len(clean) <= 30:
        return None
    title = clean[:1].upper() + clean[1:]
    return {
        "name": title,
        "family": family,
        "reason": (
            "Локальна комбінація з лексики Brand DNA/опису: "
            + " + ".join(roots)
            + f" ({pattern})."
        ),
        "pronunciation": title,
        "language_risks": [],
        "candidate_source": LOCAL_SOURCE,
    }


def expand_local_families(brief="", brand_dna=None, limit=180):
    """Create a bounded deterministic candidate pool without another AI request.

    The expander uses literal project roots and multiple composition strategies.
    It intentionally avoids one-letter typo mutations. Downstream structural,
    blacklist, near-duplicate, family-quota, and external-availability gates still
    decide which candidates survive.
    """
    seeds = lexical_seeds(brief, brand_dna)
    if len(seeds) < 2:
        return []

    output = []
    seen = set()

    def add(name, family, roots, pattern):
        if len(output) >= limit:
            return
        row = _candidate(name, family, roots, pattern)
        if not row:
            return
        key = row["name"].lower()
        if key in seen or key in seeds:
            return
        seen.add(key)
        output.append(row)

    # Direct semantic compounds remain closest to the user's own vocabulary.
    for left in seeds:
        for right in seeds:
            if left == right:
                continue
            add(left + right, "semantic_compound", (left, right), "compound")
            if len(output) >= limit:
                return output

    # Root blends use substantial pieces from both roots, rather than adding a
    # generic suffix to one saturated word.
    for index, left in enumerate(seeds):
        for right in seeds[index + 1:]:
            left_cut = max(3, min(5, (len(left) + 1) // 2))
            right_cut = max(2, min(5, len(right) // 2))
            add(left[:left_cut] + right[-right_cut:], "root_blend", (left, right), "front/back blend")
            add(right[:left_cut] + left[-right_cut:], "root_blend", (right, left), "front/back blend")
            if len(output) >= limit:
                return output

    # A second blend geometry provides phonetic diversity without typo spam.
    for index, left in enumerate(seeds):
        for right in seeds[index + 1:]:
            left_part = left[: max(2, len(left) // 2)]
            right_part = right[max(1, len(right) // 2):]
            add(left_part + right_part, "invented_phonetic", (left, right), "midpoint blend")
            if len(output) >= limit:
                return output

    return output


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
    """Annotate and rank candidates before expensive external checks.

    Stable original order breaks ties so model preference is preserved when the
    deterministic quality score cannot distinguish candidates. Locally expanded
    rows receive a small prior penalty: they are useful breadth, not a claim that
    simple morphology is better than a model-authored concept.
    """
    ranked = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        row = dict(candidate)
        score = structural_quality(row.get("name", ""))
        if row.get("candidate_source") == LOCAL_SOURCE:
            score = max(0, score - 6)
        row["local_quality_score"] = score
        ranked.append((index, row))
    ranked.sort(key=lambda item: (-item[1]["local_quality_score"], item[0]))
    return [row for _, row in ranked]
