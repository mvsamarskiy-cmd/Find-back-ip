"""Fast local semantic vocabulary for NameMachine creativity.

This is not a name list and it does not claim availability.  It is a compact,
curated semantic graph used to move the generator away from literal prompt words
without adding another model/API call.  Prompt Intelligence already reduces human
prose to naming-ready concepts; this layer expands those concepts into adjacent
images, concrete vocabulary, classical roots and phonetic material.

Design goals:
- completely local and deterministic: no network latency on the generation path;
- bounded palettes instead of dumping a dictionary into the model;
- semantic bridges provide creativity without random unrelated words;
- batch rotation explores a different neighboring territory on follow-up batches;
- output is inspiration only and never an availability/trademark assertion.
"""
from __future__ import annotations

import json
import re
from typing import Any


# Each cluster is intentionally compact.  The graph matters more than raw word
# count: direct vocabulary anchors meaning while metaphor/bridge vocabulary lets
# both GPT and the cheap local expander move one semantic step sideways.
LEXICON: dict[str, dict[str, tuple[str, ...]]] = {
    "mobility": {
        "aliases": ("mobility", "move", "motion", "drive", "car", "auto", "vehicle", "wheel", "road", "transport", "авто", "машина", "колесо", "дорога", "рух", "samochod", "droga", "ruch", "transport"),
        "direct": ("drive", "route", "road", "wheel", "track", "shift", "ride", "cruise", "lane", "roam"),
        "metaphor": ("arrow", "falcon", "wind", "current", "horizon", "orbit"),
        "roots": ("motus", "via", "rota", "veho", "cursor"),
        "phonetic": ("mot", "via", "rot", "vel", "rov"),
        "bridges": ("speed", "freedom", "precision", "exploration"),
    },
    "speed": {
        "aliases": ("speed", "fast", "quick", "rapid", "swift", "velocity", "pace", "швидкий", "швидкість", "скорость", "szybki", "predkosc", "tempo"),
        "direct": ("swift", "dash", "rush", "pace", "surge", "sprint", "fleet", "rapid"),
        "metaphor": ("bolt", "comet", "falcon", "gust", "arrow", "flash"),
        "roots": ("celer", "velox", "velum", "impel"),
        "phonetic": ("cel", "vel", "rax", "siv", "tur"),
        "bridges": ("mobility", "energy", "precision"),
    },
    "precision": {
        "aliases": ("precision", "precise", "exact", "accuracy", "accurate", "detail", "measure", "repair", "mechanic", "точний", "точність", "ремонт", "майстер", "dokladny", "precyzja", "naprawa"),
        "direct": ("point", "edge", "gauge", "align", "calibre", "vector", "axis", "mark"),
        "metaphor": ("needle", "compass", "lens", "grid", "beacon", "chisel"),
        "roots": ("acumen", "metra", "axis", "recta", "ordo"),
        "phonetic": ("acu", "metr", "axi", "rect", "kal"),
        "bridges": ("clarity", "craft", "order", "trust"),
    },
    "craft": {
        "aliases": ("craft", "maker", "making", "handmade", "workshop", "artisan", "build", "repair", "майстер", "ремесло", "робити", "виробництво", "rzemioslo", "warsztat", "robic"),
        "direct": ("shape", "form", "grain", "join", "carve", "mold", "weave", "finish"),
        "metaphor": ("chisel", "loom", "anvil", "kiln", "grain", "stitch"),
        "roots": ("ars", "faber", "forma", "manu", "opus"),
        "phonetic": ("fab", "ars", "man", "opus", "karv"),
        "bridges": ("precision", "material", "creativity", "strength"),
    },
    "material": {
        "aliases": ("material", "metal", "steel", "wood", "stone", "glass", "fabric", "solid", "матеріал", "метал", "сталь", "дерево", "камінь", "szklo", "stal", "drewno", "kamien"),
        "direct": ("steel", "stone", "grain", "alloy", "glass", "fiber", "slate", "copper"),
        "metaphor": ("crystal", "ore", "oak", "flint", "marble", "quartz"),
        "roots": ("ferrum", "lithos", "vitrum", "silva", "aes"),
        "phonetic": ("fer", "lith", "vitr", "silv", "aes"),
        "bridges": ("strength", "craft", "earth", "precision"),
    },
    "strength": {
        "aliases": ("strength", "strong", "power", "durable", "tough", "solid", "force", "сила", "міцний", "потужний", "сильний", "moc", "silny", "trwaly"),
        "direct": ("force", "stout", "stead", "brace", "core", "stand", "stamina", "vigor"),
        "metaphor": ("oak", "granite", "anchor", "bison", "ridge", "shield"),
        "roots": ("fortis", "robur", "kratos", "valens"),
        "phonetic": ("fort", "rob", "krat", "val"),
        "bridges": ("protection", "material", "trust", "energy"),
    },
    "trust": {
        "aliases": ("trust", "trusted", "reliable", "safe", "honest", "secure", "dependable", "довіра", "надійний", "безпечний", "чесний", "zaufanie", "pewny", "bezpieczny"),
        "direct": ("sure", "stead", "proof", "bond", "pledge", "true", "guard", "keep"),
        "metaphor": ("anchor", "harbor", "oak", "bridge", "shield", "stone"),
        "roots": ("fides", "secur", "tutus", "certus"),
        "phonetic": ("fid", "sek", "tut", "cert"),
        "bridges": ("protection", "clarity", "strength", "connection"),
    },
    "protection": {
        "aliases": ("protect", "protection", "safe", "security", "guard", "defend", "privacy", "захист", "безпека", "охорона", "ochrona", "bezpieczenstwo", "straza"),
        "direct": ("guard", "shield", "keep", "ward", "haven", "cover", "vault", "sentry"),
        "metaphor": ("castle", "harbor", "shell", "bastion", "reef", "canopy"),
        "roots": ("tutela", "custos", "aegis", "salvus"),
        "phonetic": ("tut", "cust", "aeg", "salv"),
        "bridges": ("trust", "strength", "care", "order"),
    },
    "clarity": {
        "aliases": ("clear", "clarity", "simple", "transparent", "focus", "understand", "clean", "ясний", "прозорий", "простий", "чіткий", "jasny", "prosty", "przejrzysty"),
        "direct": ("clear", "plain", "focus", "lucid", "signal", "sense", "open", "sharp"),
        "metaphor": ("lens", "prism", "window", "beacon", "spring", "sky"),
        "roots": ("clarus", "lucid", "perspic", "visus"),
        "phonetic": ("clar", "luc", "vis", "pris"),
        "bridges": ("light", "precision", "order", "trust"),
    },
    "order": {
        "aliases": ("order", "organize", "system", "structure", "logic", "method", "process", "порядок", "система", "структура", "логіка", "porzadek", "system", "struktura"),
        "direct": ("order", "frame", "grid", "stack", "tier", "sequence", "axis", "schema"),
        "metaphor": ("constellation", "lattice", "rail", "compass", "clock", "map"),
        "roots": ("ordo", "ratio", "series", "nexus"),
        "phonetic": ("ord", "rat", "ser", "nex"),
        "bridges": ("precision", "clarity", "connection", "time"),
    },
    "connection": {
        "aliases": ("connect", "connection", "network", "together", "link", "community", "social", "зв'язок", "зв’язок", "разом", "мережа", "спільнота", "polaczenie", "razem", "siec", "spolecznosc"),
        "direct": ("link", "bond", "join", "mesh", "bridge", "circle", "relay", "node"),
        "metaphor": ("constellation", "mycelium", "braid", "arch", "chain", "weave"),
        "roots": ("nexus", "socius", "juncta", "ligare"),
        "phonetic": ("nex", "soc", "junc", "lig"),
        "bridges": ("community", "trust", "order", "communication"),
    },
    "community": {
        "aliases": ("community", "people", "crowd", "group", "collective", "member", "audience", "спільнота", "люди", "група", "разом", "spolecznosc", "ludzie", "grupa"),
        "direct": ("circle", "tribe", "gather", "union", "commons", "crew", "kin", "guild"),
        "metaphor": ("campfire", "flock", "grove", "constellation", "choir", "harbor"),
        "roots": ("socius", "cohors", "civis", "unio"),
        "phonetic": ("soc", "coh", "civ", "uni"),
        "bridges": ("connection", "care", "communication", "growth"),
    },
    "communication": {
        "aliases": ("communication", "message", "media", "story", "voice", "write", "journalism", "комунікація", "повідомлення", "медіа", "історія", "голос", "журналістика", "komunikacja", "wiadomosc", "glos", "media"),
        "direct": ("voice", "signal", "echo", "relay", "story", "phrase", "tone", "pulse"),
        "metaphor": ("ripple", "radio", "bell", "chorus", "beacon", "thread"),
        "roots": ("vox", "dicta", "sonus", "nuntia"),
        "phonetic": ("vox", "dic", "son", "nun"),
        "bridges": ("sound", "connection", "clarity", "community"),
    },
    "growth": {
        "aliases": ("grow", "growth", "scale", "develop", "future", "progress", "expand", "ріст", "розвиток", "зростання", "майбутнє", "wzrost", "rozwoj", "przyszlosc"),
        "direct": ("rise", "sprout", "gain", "bloom", "branch", "thrive", "scale", "seed"),
        "metaphor": ("forest", "spring", "dawn", "vine", "canopy", "tide"),
        "roots": ("cresca", "vita", "alere", "augere"),
        "phonetic": ("cres", "vit", "aler", "aug"),
        "bridges": ("nature", "future", "energy", "transformation"),
    },
    "transformation": {
        "aliases": ("transform", "change", "adapt", "evolve", "convert", "renew", "зміна", "перетворення", "адаптація", "оновлення", "zmiana", "przemiana", "adaptacja"),
        "direct": ("shift", "turn", "morph", "renew", "adapt", "phase", "recast", "evolve"),
        "metaphor": ("molt", "phoenix", "tide", "season", "prism", "forgefire"),
        "roots": ("morph", "verso", "mutare", "novare"),
        "phonetic": ("morf", "vers", "mut", "nov"),
        "bridges": ("growth", "creativity", "future", "energy"),
    },
    "future": {
        "aliases": ("future", "next", "forward", "new", "tomorrow", "innovation", "майбутнє", "новий", "вперед", "інновація", "przyszlosc", "nowy", "naprzod", "innowacja"),
        "direct": ("next", "ahead", "dawn", "forward", "frontier", "horizon", "newday", "advance"),
        "metaphor": ("dawn", "horizon", "comet", "seed", "frontier", "orbit"),
        "roots": ("futura", "novum", "oriens", "proxima"),
        "phonetic": ("fut", "nov", "ori", "prox"),
        "bridges": ("exploration", "growth", "transformation", "space"),
    },
    "exploration": {
        "aliases": ("explore", "exploration", "discover", "search", "find", "adventure", "journey", "відкриття", "пошук", "подорож", "дослідження", "odkrycie", "szukac", "podroz"),
        "direct": ("quest", "roam", "trail", "range", "seek", "venture", "path", "frontier"),
        "metaphor": ("compass", "horizon", "voyage", "star", "map", "summit"),
        "roots": ("quaero", "iter", "via", "terra"),
        "phonetic": ("qua", "iter", "via", "ter"),
        "bridges": ("freedom", "mobility", "future", "space"),
    },
    "freedom": {
        "aliases": ("free", "freedom", "independent", "open", "liberty", "escape", "вільний", "свобода", "незалежний", "wolny", "wolnosc", "niezalezny"),
        "direct": ("free", "open", "roam", "wild", "range", "loose", "soar", "unbound"),
        "metaphor": ("sky", "wing", "horizon", "ocean", "mustang", "wind"),
        "roots": ("liber", "solvo", "ala", "vagus"),
        "phonetic": ("lib", "sol", "ala", "vag"),
        "bridges": ("exploration", "air", "mobility", "nature"),
    },
    "energy": {
        "aliases": ("energy", "power", "charge", "electric", "dynamic", "active", "енергія", "потужність", "заряд", "активний", "energia", "moc", "ladunek"),
        "direct": ("spark", "charge", "pulse", "surge", "volt", "ignite", "drive", "boost"),
        "metaphor": ("lightning", "sun", "flame", "torrent", "storm", "comet"),
        "roots": ("energe", "dyna", "ignis", "vis"),
        "phonetic": ("dyn", "ign", "vol", "sur"),
        "bridges": ("fire", "speed", "vitality", "growth"),
    },
    "light": {
        "aliases": ("light", "bright", "shine", "glow", "visual", "clear", "світло", "яскравий", "сяйво", "jasny", "swiatlo", "blask"),
        "direct": ("glow", "beam", "ray", "shine", "gleam", "halo", "lumen", "dawn"),
        "metaphor": ("prism", "sun", "star", "beacon", "aurora", "crystal"),
        "roots": ("lux", "lumen", "helios", "phos"),
        "phonetic": ("lux", "lum", "hel", "fos"),
        "bridges": ("clarity", "space", "energy", "elegance"),
    },
    "water": {
        "aliases": ("water", "sea", "ocean", "river", "drink", "fresh", "aqua", "вода", "море", "річка", "свіжий", "woda", "morze", "rzeka", "swiezy"),
        "direct": ("wave", "river", "spring", "tide", "brook", "drop", "mist", "current"),
        "metaphor": ("pearl", "reef", "lagoon", "glacier", "rain", "delta"),
        "roots": ("aqua", "unda", "mare", "hydra"),
        "phonetic": ("aqu", "und", "mar", "hyd"),
        "bridges": ("nature", "clarity", "calm", "freedom"),
    },
    "air": {
        "aliases": ("air", "wind", "breeze", "sky", "breath", "lightweight", "повітря", "вітер", "небо", "легкий", "powietrze", "wiatr", "niebo", "lekki"),
        "direct": ("air", "breeze", "gust", "sky", "drift", "soar", "aero", "wing"),
        "metaphor": ("cloud", "falcon", "kite", "feather", "horizon", "sail"),
        "roots": ("aer", "ventus", "caeli", "spira"),
        "phonetic": ("aer", "vent", "cel", "spir"),
        "bridges": ("freedom", "speed", "nature", "calm"),
    },
    "fire": {
        "aliases": ("fire", "flame", "heat", "warm", "ignite", "burn", "вогонь", "полум'я", "полум’я", "тепло", "огонь", "ogien", "plomien", "cieplo"),
        "direct": ("flame", "ember", "spark", "blaze", "glow", "heat", "kindle", "flare"),
        "metaphor": ("sun", "phoenix", "volcano", "torch", "forgeheat", "comet"),
        "roots": ("ignis", "pyra", "calor", "focus"),
        "phonetic": ("ign", "pyr", "cal", "foc"),
        "bridges": ("energy", "warmth", "transformation", "strength"),
    },
    "earth": {
        "aliases": ("earth", "ground", "soil", "land", "stone", "natural", "земля", "ґрунт", "камінь", "природний", "ziemia", "grunt", "naturalny"),
        "direct": ("earth", "soil", "stone", "clay", "ridge", "field", "terra", "root"),
        "metaphor": ("mountain", "canyon", "grove", "granite", "meadow", "island"),
        "roots": ("terra", "gaia", "humus", "lithos"),
        "phonetic": ("ter", "gai", "hum", "lith"),
        "bridges": ("nature", "material", "strength", "growth"),
    },
    "nature": {
        "aliases": ("nature", "natural", "green", "eco", "organic", "plant", "animal", "природа", "зелений", "рослина", "натуральний", "natura", "zielony", "roslina"),
        "direct": ("grove", "fern", "moss", "leaf", "wild", "root", "bloom", "cedar"),
        "metaphor": ("forest", "meadow", "river", "falcon", "dawn", "canopy"),
        "roots": ("silva", "flora", "viva", "nemus"),
        "phonetic": ("silv", "flor", "viv", "nem"),
        "bridges": ("growth", "earth", "water", "freedom"),
    },
    "space": {
        "aliases": ("space", "cosmos", "star", "orbit", "universe", "satellite", "простір", "космос", "зірка", "орбіта", "przestrzen", "kosmos", "gwiazda"),
        "direct": ("orbit", "nova", "stellar", "lunar", "astro", "zenith", "cosmos", "void"),
        "metaphor": ("comet", "eclipse", "horizon", "constellation", "pulsar", "nebula"),
        "roots": ("astra", "orbis", "caeli", "sidus"),
        "phonetic": ("astr", "orb", "cel", "sid"),
        "bridges": ("future", "exploration", "light", "freedom"),
    },
    "sound": {
        "aliases": ("sound", "music", "audio", "voice", "tone", "rhythm", "звук", "музика", "голос", "ритм", "dzwiek", "muzyka", "glos", "rytm"),
        "direct": ("tone", "echo", "pulse", "beat", "chord", "voice", "sonic", "hum"),
        "metaphor": ("bell", "chorus", "wave", "ripple", "drum", "resonance"),
        "roots": ("sonus", "vox", "melos", "rhythm"),
        "phonetic": ("son", "vox", "mel", "ryt"),
        "bridges": ("communication", "energy", "creativity", "community"),
    },
    "creativity": {
        "aliases": ("creative", "creativity", "design", "art", "imagine", "original", "креатив", "творчість", "дизайн", "мистецтво", "kreatywny", "tworczosc", "sztuka", "design"),
        "direct": ("imagine", "shape", "sketch", "color", "verse", "muse", "novel", "craft"),
        "metaphor": ("prism", "kaleido", "spark", "mosaic", "canvas", "dream"),
        "roots": ("poiesis", "ars", "musa", "fingo"),
        "phonetic": ("poi", "ars", "mus", "fin"),
        "bridges": ("transformation", "craft", "play", "light"),
    },
    "intelligence": {
        "aliases": ("smart", "intelligence", "brain", "think", "knowledge", "decision", "logic", "розум", "мислення", "знання", "рішення", "wiedza", "myslenie", "decyzja"),
        "direct": ("sense", "reason", "insight", "mind", "logic", "wisdom", "learn", "signal"),
        "metaphor": ("lens", "compass", "map", "owl", "beacon", "pattern"),
        "roots": ("nous", "ratio", "sophia", "cogni"),
        "phonetic": ("nous", "rat", "sof", "cog"),
        "bridges": ("clarity", "order", "precision", "future"),
    },
    "care": {
        "aliases": ("care", "health", "wellness", "support", "gentle", "help", "medical", "турбота", "здоров'я", "здоров’я", "підтримка", "допомога", "opieka", "zdrowie", "pomoc"),
        "direct": ("care", "tend", "nurture", "heal", "ease", "kind", "support", "vital"),
        "metaphor": ("harbor", "nest", "garden", "spring", "hand", "canopy"),
        "roots": ("cura", "salus", "vita", "lenis"),
        "phonetic": ("cur", "sal", "vit", "len"),
        "bridges": ("warmth", "trust", "vitality", "protection"),
    },
    "vitality": {
        "aliases": ("life", "vital", "alive", "health", "fresh", "fitness", "життя", "живий", "здоров'я", "здоров’я", "свіжий", "zycie", "zywy", "zdrowie"),
        "direct": ("vital", "alive", "pulse", "fresh", "thrive", "bloom", "breath", "spark"),
        "metaphor": ("spring", "sunrise", "river", "seed", "heartbeat", "leaf"),
        "roots": ("vita", "bios", "anima", "salus"),
        "phonetic": ("vit", "bio", "anim", "sal"),
        "bridges": ("care", "growth", "energy", "nature"),
    },
    "warmth": {
        "aliases": ("warm", "warmth", "friendly", "human", "cozy", "comfort", "теплий", "затишний", "людяний", "дружній", "cieply", "przyjazny", "komfort"),
        "direct": ("warm", "kind", "cozy", "glow", "welcome", "soft", "hearth", "ease"),
        "metaphor": ("hearth", "sun", "amber", "nest", "blanket", "lantern"),
        "roots": ("calor", "amicus", "lenis", "fovea"),
        "phonetic": ("cal", "amic", "len", "fov"),
        "bridges": ("care", "community", "fire", "trust"),
    },
    "calm": {
        "aliases": ("calm", "quiet", "peace", "slow", "relax", "serene", "спокій", "тихий", "мир", "розслаблення", "spokoj", "cichy", "relaks"),
        "direct": ("calm", "still", "quiet", "ease", "serene", "rest", "soft", "hush"),
        "metaphor": ("lake", "mist", "dusk", "meadow", "moon", "harbor"),
        "roots": ("pax", "lenis", "seren", "quies"),
        "phonetic": ("pax", "len", "ser", "qui"),
        "bridges": ("water", "air", "care", "elegance"),
    },
    "elegance": {
        "aliases": ("elegant", "elegance", "premium", "luxury", "refined", "beautiful", "fashion", "елегантний", "преміум", "розкіш", "красивий", "elegancki", "luksus", "piekn y", "premium"),
        "direct": ("grace", "poise", "silk", "fine", "sleek", "pure", "rare", "velvet"),
        "metaphor": ("swan", "pearl", "onyx", "silk", "champagne", "moon"),
        "roots": ("gratia", "levis", "pulcher", "nobilis"),
        "phonetic": ("gra", "lev", "pul", "nob"),
        "bridges": ("clarity", "calm", "material", "light"),
    },
    "play": {
        "aliases": ("play", "fun", "game", "toy", "joy", "kids", "гра", "веселий", "іграшка", "радість", "zabawa", "gra", "zabawka", "radosc"),
        "direct": ("play", "joy", "wink", "bounce", "spark", "pop", "skip", "jolly"),
        "metaphor": ("kite", "bubble", "confetti", "carousel", "puzzle", "firefly"),
        "roots": ("ludo", "gaud", "jocus", "mira"),
        "phonetic": ("lud", "gau", "joc", "mir"),
        "bridges": ("creativity", "community", "energy", "warmth"),
    },
    "food": {
        "aliases": ("food", "restaurant", "sushi", "taste", "flavor", "kitchen", "chef", "їжа", "ресторан", "суші", "смак", "кухня", "jedzenie", "restauracja", "smak", "kuchnia"),
        "direct": ("taste", "savory", "fresh", "zest", "bite", "grain", "spice", "plate"),
        "metaphor": ("harvest", "orchard", "ember", "ocean", "garden", "feast"),
        "roots": ("sapor", "gusta", "cibus", "mensa"),
        "phonetic": ("sap", "gus", "cib", "men"),
        "bridges": ("nature", "craft", "warmth", "vitality"),
    },
}


DEFAULT_BRIDGES = ("clarity", "motion", "nature")
ASCII_ROOT = re.compile(r"^[a-z]{3,14}$")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґЁёĄąĆćĘęŁłŃńÓóŚśŹźŻż]{3,24}")


def _tokens(*values: Any) -> set[str]:
    output: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            values_to_scan = []
            for raw in value.values():
                if isinstance(raw, list):
                    values_to_scan.extend(raw[:20])
                elif isinstance(raw, str):
                    values_to_scan.append(raw)
        elif isinstance(value, list):
            values_to_scan = value[:30]
        else:
            values_to_scan = [value]
        for raw in values_to_scan:
            for token in WORD_RE.findall(str(raw or "").lower()):
                output.add(token)
    return output


def _cluster_scores(tokens: set[str]) -> list[tuple[int, str]]:
    scores = []
    for key, cluster in LEXICON.items():
        aliases = {str(alias).lower() for alias in cluster.get("aliases", ())}
        direct = {str(word).lower() for word in cluster.get("direct", ())}
        score = 3 * len(tokens & aliases) + len(tokens & direct)
        # Naming roots such as "automotive" often share a useful stem with an
        # alias even if the interpreter chose a different inflection.
        for token in tokens:
            if len(token) < 5:
                continue
            if any(len(alias) >= 5 and (token.startswith(alias[:5]) or alias.startswith(token[:5])) for alias in aliases):
                score += 1
                break
        if score:
            scores.append((score, key))
    scores.sort(key=lambda row: (-row[0], row[1]))
    return scores


def _rotate(values: list[str], batch_number: int) -> list[str]:
    if not values:
        return []
    offset = max(0, int(batch_number or 1) - 1) % len(values)
    return values[offset:] + values[:offset]


def _bounded_unique(values, limit, forbidden=frozenset()):
    output = []
    seen = set()
    forbidden = {str(value).lower() for value in forbidden}
    for raw in values:
        value = re.sub(r"[^a-z]", "", str(raw).lower())
        if not ASCII_ROOT.fullmatch(value) or value in seen:
            continue
        if value in forbidden:
            continue
        seen.add(value)
        output.append(value)
        if len(output) >= limit:
            break
    return output


def creative_palette(
    brief="",
    brand_dna=None,
    guidance="",
    *,
    batch_number=1,
    forbidden=None,
    max_primary=3,
    max_bridge=3,
) -> dict[str, Any]:
    """Return a bounded semantic palette for one generation batch.

    The same prompt is stable within a batch. Follow-up batches rotate bridge
    clusters, which gives adaptive search new semantic neighborhoods without
    injecting randomness into tests or production.
    """
    forbidden = set(forbidden or ())
    tokens = _tokens(brief, brand_dna or {}, guidance)
    scored = _cluster_scores(tokens)
    primary = [key for _score, key in scored[: max(1, int(max_primary))]]
    if not primary:
        return {
            "version": "creative-lexicon-v1",
            "matched_clusters": [],
            "bridge_clusters": [],
            "direct_words": [],
            "metaphor_words": [],
            "classical_roots": [],
            "phonetic_fragments": [],
            "local_roots": [],
        }

    bridge_candidates = []
    for key in primary:
        for bridge in LEXICON[key].get("bridges", ()):
            if bridge in LEXICON and bridge not in primary and bridge not in bridge_candidates:
                bridge_candidates.append(bridge)
    bridge_candidates = _rotate(bridge_candidates, batch_number)
    bridges = bridge_candidates[: max(0, int(max_bridge))]

    direct_values = []
    metaphor_values = []
    classical_values = []
    phonetic_values = []
    for key in primary:
        cluster = LEXICON[key]
        direct_values.extend(cluster.get("direct", ())[:6])
        metaphor_values.extend(cluster.get("metaphor", ())[:5])
        classical_values.extend(cluster.get("roots", ())[:4])
        phonetic_values.extend(cluster.get("phonetic", ())[:4])
    for key in bridges:
        cluster = LEXICON[key]
        metaphor_values.extend(cluster.get("direct", ())[:4])
        metaphor_values.extend(cluster.get("metaphor", ())[:2])
        classical_values.extend(cluster.get("roots", ())[:2])
        phonetic_values.extend(cluster.get("phonetic", ())[:2])

    direct = _bounded_unique(direct_values, 16, forbidden)
    metaphors = _bounded_unique(metaphor_values, 16, forbidden)
    classical = _bounded_unique(classical_values, 12, forbidden)
    phonetic = _bounded_unique(phonetic_values, 10, forbidden)
    # Local combinatorial generation needs a smaller set than GPT. Prefer
    # concrete/metaphorical roots, then classical/phonetic material.
    local_roots = _bounded_unique(
        direct[:8] + metaphors[:8] + classical[:6] + phonetic[:5],
        18,
        forbidden,
    )
    return {
        "version": "creative-lexicon-v1",
        "matched_clusters": primary,
        "bridge_clusters": bridges,
        "direct_words": direct,
        "metaphor_words": metaphors,
        "classical_roots": classical,
        "phonetic_fragments": phonetic,
        "local_roots": local_roots,
    }


def creative_palette_prompt(palette: dict[str, Any]) -> str:
    """Compact model context; never send the whole dictionary to GPT."""
    if not isinstance(palette, dict) or not palette.get("matched_clusters"):
        return "No local semantic lexicon match; rely on the interpreted brief."
    compact = {
        "matched_semantic_clusters": list(palette.get("matched_clusters") or [])[:4],
        "adjacent_metaphor_clusters": list(palette.get("bridge_clusters") or [])[:4],
        "direct_vocabulary": list(palette.get("direct_words") or [])[:14],
        "metaphor_vocabulary": list(palette.get("metaphor_words") or [])[:14],
        "classical_roots": list(palette.get("classical_roots") or [])[:10],
        "phonetic_material": list(palette.get("phonetic_fragments") or [])[:8],
        "rule": (
            "Use this as optional semantic material, not mandatory suffixes. Cross one semantic bridge when useful; "
            "do not simply concatenate every word, and do not let the palette override user constraints."
        ),
    }
    return json.dumps(compact, ensure_ascii=False, separators=(",", ":"))


def creative_lexicon_diagnostics() -> dict[str, Any]:
    words = sum(
        len(cluster.get("direct", ()))
        + len(cluster.get("metaphor", ()))
        + len(cluster.get("roots", ()))
        + len(cluster.get("phonetic", ()))
        for cluster in LEXICON.values()
    )
    return {
        "version": "creative-lexicon-v1",
        "local_only": True,
        "network_calls": 0,
        "clusters": len(LEXICON),
        "semantic_items": words,
        "batch_bridge_rotation": True,
        "full_dictionary_sent_to_model": False,
        "availability_semantics": False,
    }


__all__ = [
    "LEXICON",
    "creative_lexicon_diagnostics",
    "creative_palette",
    "creative_palette_prompt",
]
