import re


VOWELS = frozenset("aeiouy")
LOCAL_SOURCE = "local_lexical_expansion"
DEFAULT_LOCAL_RAW_LIMIT = 4000
DEFAULT_STRUCTURAL_LIMIT = 1200
DEFAULT_LINGUISTIC_LIMIT = 420
DEFAULT_COLLISION_LIMIT = 180

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
    """Extract bounded literal roots from the brief and structured Brand DNA."""
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


def _expand_raw_local_families(brief="", brand_dna=None, limit=DEFAULT_LOCAL_RAW_LIMIT):
    """Create a large deterministic raw pool without another AI request."""
    limit = max(0, min(10000, int(limit)))
    seeds = lexical_seeds(brief, brand_dna)
    if len(seeds) < 2 or limit == 0:
        return []

    output = []
    seen = set()

    def add(name, family, roots, pattern):
        if len(output) >= limit:
            return False
        row = _candidate(name, family, roots, pattern)
        if not row:
            return True
        key = row["name"].lower()
        if key in seen or key in seeds:
            return True
        seen.add(key)
        output.append(row)
        return len(output) < limit

    for left in seeds:
        for right in seeds:
            if left == right:
                continue
            if not add(left + right, "semantic_compound", (left, right), "compound"):
                return output

    for index, left in enumerate(seeds):
        for right in seeds[index + 1:]:
            left_front = max(2, min(5, (len(left) + 1) // 2))
            right_back = max(2, min(5, len(right) // 2))
            if not add(left[:left_front] + right[-right_back:], "root_blend", (left, right), "front/back blend"):
                return output
            if not add(right[:left_front] + left[-right_back:], "root_blend", (right, left), "front/back blend"):
                return output
            if not add(
                left[: max(2, len(left) // 2)] + right[max(1, len(right) // 2):],
                "invented_phonetic",
                (left, right),
                "midpoint blend",
            ):
                return output
            if not add(
                right[: max(2, len(right) // 2)] + left[max(1, len(left) // 2):],
                "invented_phonetic",
                (right, left),
                "reverse midpoint blend",
            ):
                return output

    seed_count = len(seeds)
    for i in range(seed_count - 2):
        for j in range(i + 1, seed_count - 1):
            for k in range(j + 1, seed_count):
                first, second, third = seeds[i], seeds[j], seeds[k]
                compact = (
                    first[: max(2, min(4, len(first) // 2))]
                    + second[:2]
                    + third[-max(2, min(4, len(third) // 2)):]
                )
                if not add(compact, "root_blend", (first, second, third), "three-root blend"):
                    return output
                rotated = (
                    second[: max(2, min(4, len(second) // 2))]
                    + third[:2]
                    + first[-max(2, min(4, len(first) // 2)):]
                )
                if not add(rotated, "invented_phonetic", (second, third, first), "rotated three-root blend"):
                    return output

    return output


def structural_quality(name):
    """Return a deterministic 0-100 structural pre-check quality score."""
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


def linguistic_quality(name):
    """Conservative readability/pronounceability proxy, not semantic judgement."""
    value = _letters(name)
    if not value:
        return 0
    score = 100.0
    syllable_proxy = len(re.findall(r"[aeiouy]+", value))
    if syllable_proxy == 0:
        score -= 60
    elif syllable_proxy == 1 and len(value) > 7:
        score -= 18
    elif syllable_proxy > 4:
        score -= 14

    if re.search(r"[bcdfghjklmnpqrstvwxz]{4,}", value):
        score -= 35
    if re.search(r"[aeiouy]{4,}", value):
        score -= 25
    if re.search(r"(q[^u]|q$)", value):
        score -= 12
    if any(pair in value for pair in ("qx", "xq", "qj", "jq", "wq", "qz", "zq")):
        score -= 18
    if len(value) > 12:
        score -= 18
    if 5 <= len(value) <= 9 and 2 <= syllable_proxy <= 3:
        score += 5

    return max(0, min(100, round(score)))


def rank_candidate_pool(candidates):
    """Annotate and rank candidates before expensive external checks."""
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


def _collision_signature(name):
    """Coarse internal cluster key; this is not legal/trademark collision data."""
    value = _letters(name)
    if not value:
        return ""
    collapsed = re.sub(r"(.)\1+", r"\1", value)
    consonants = re.sub(r"[aeiouy]", "", collapsed)
    vowel_groups = len(re.findall(r"[aeiouy]+", collapsed))
    return f"{consonants[:7]}:{vowel_groups}:{len(collapsed)//2}"


def _dedupe_exact(candidates):
    output = []
    seen = set()
    for row in candidates:
        if not isinstance(row, dict):
            continue
        key = _letters(row.get("name", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(dict(row))
    return output


def _stage_rows(
    candidates,
    structural_limit=DEFAULT_STRUCTURAL_LIMIT,
    linguistic_limit=DEFAULT_LINGUISTIC_LIMIT,
    collision_limit=DEFAULT_COLLISION_LIMIT,
):
    structural_limit = max(1, min(5000, int(structural_limit)))
    linguistic_limit = max(1, min(structural_limit, int(linguistic_limit)))
    collision_limit = max(1, min(linguistic_limit, int(collision_limit)))

    raw = _dedupe_exact(candidates)
    structural = rank_candidate_pool(raw)[:structural_limit]

    linguistic = []
    for index, row in enumerate(structural):
        clean = dict(row)
        clean["linguistic_quality_score"] = linguistic_quality(clean.get("name", ""))
        clean["funnel_score"] = round(
            0.58 * clean.get("local_quality_score", 0)
            + 0.42 * clean["linguistic_quality_score"],
            1,
        )
        linguistic.append((index, clean))
    linguistic.sort(key=lambda item: (-item[1]["funnel_score"], item[0]))
    linguistic_rows = [row for _, row in linguistic[:linguistic_limit]]

    collision_rows = []
    signature_counts = {}
    family_counts = {}
    family_cap = max(8, collision_limit // 3)
    for row in linguistic_rows:
        signature = _collision_signature(row.get("name", ""))
        family = str(row.get("family", "unknown"))
        if signature and signature_counts.get(signature, 0) >= 2:
            continue
        if family_counts.get(family, 0) >= family_cap:
            continue
        signature_counts[signature] = signature_counts.get(signature, 0) + 1
        family_counts[family] = family_counts.get(family, 0) + 1
        collision_rows.append(row)
        if len(collision_rows) >= collision_limit:
            break

    return collision_rows, {
        "raw_unique": len(raw),
        "structural_survivors": len(structural),
        "linguistic_survivors": len(linguistic_rows),
        "collision_survivors": len(collision_rows),
    }


def expand_local_families(brief="", brand_dna=None, limit=180):
    """Return the best local survivors from a much larger cheap candidate space.

    The public `limit` remains the returned-pool limit for backward compatibility.
    Internally the generator explores up to 4,000 deterministic candidates and
    reduces them through structural, readability, and internal-collision stages.
    """
    limit = max(0, min(DEFAULT_COLLISION_LIMIT, int(limit)))
    if limit == 0:
        return []
    raw = _expand_raw_local_families(
        brief,
        brand_dna,
        limit=DEFAULT_LOCAL_RAW_LIMIT,
    )
    survivors, _metrics = _stage_rows(
        raw,
        structural_limit=DEFAULT_STRUCTURAL_LIMIT,
        linguistic_limit=DEFAULT_LINGUISTIC_LIMIT,
        collision_limit=max(limit, 1),
    )
    return survivors[:limit]


def staged_candidate_pool(
    model_candidates,
    brief="",
    brand_dna=None,
    local_limit=DEFAULT_LOCAL_RAW_LIMIT,
    structural_limit=DEFAULT_STRUCTURAL_LIMIT,
    linguistic_limit=DEFAULT_LINGUISTIC_LIMIT,
    collision_limit=DEFAULT_COLLISION_LIMIT,
):
    """Expose the full hybrid pre-check funnel with stage metrics for tests/audit."""
    local_limit = max(0, min(10000, int(local_limit)))
    model_rows = [dict(row) for row in model_candidates if isinstance(row, dict)]
    local_rows = _expand_raw_local_families(brief, brand_dna, limit=local_limit)
    survivors, metrics = _stage_rows(
        model_rows + local_rows,
        structural_limit=structural_limit,
        linguistic_limit=linguistic_limit,
        collision_limit=collision_limit,
    )
    metrics = {
        "model_candidates": len(model_rows),
        "local_candidates": len(local_rows),
        **metrics,
    }
    return survivors, metrics
