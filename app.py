import os, random, re
from functools import lru_cache
from threading import BoundedSemaphore
from flask import Flask, request, jsonify, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from availability import RESOURCE_KEYS, check_all, check_many, normalize_resources
from ai_engine import (
    BANNED_ROOTS,
    BANNED_SUFFIXES,
    DEFAULT_GENERATION_CONTEXT,
    DEFAULT_SEARCH_CONTEXT,
    SEARCH_MODES,
    clean_generation_context,
    clean_search_context,
    generate_ai_names,
    trademark_links,
)
from brand_dna import WebsiteFetchError, build_brand_dna, clean_brand_dna, fetch_public_website
from identity_bundle import classify_identity_bundle, normalize_required_resources
from prompt_intelligence import compile_generation_input, interpret_prompt

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def bounded_int_env(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


app.config["MAX_CONTENT_LENGTH"] = bounded_int_env(
    "MAX_CONTENT_LENGTH", 32768, 4096, 1048576
)

RATE_LIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
AI_RATE_LIMIT = os.environ.get("AI_RATE_LIMIT", "5 per minute;30 per hour")
CHECK_RATE_LIMIT = os.environ.get("CHECK_RATE_LIMIT", "60 per minute")
LEGACY_RATE_LIMIT = os.environ.get("LEGACY_RATE_LIMIT", "20 per minute")
MAX_CONCURRENT_AI_REQUESTS = bounded_int_env(
    "MAX_CONCURRENT_AI_REQUESTS", 2, 1, 8
)
AI_REQUEST_SLOTS = BoundedSemaphore(MAX_CONCURRENT_AI_REQUESTS)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=RATE_LIMIT_STORAGE_URI,
    headers_enabled=False,
)


@app.after_request
def add_security_headers(response):
    """Apply a conservative browser baseline without breaking the inline UI."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'",
    )
    response.headers.setdefault(
        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
    )
    return response


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "Request body is too large"}), 413


@app.errorhandler(429)
def rate_limit_exceeded(error):
    return jsonify({
        "error": "Too many requests. Please wait before trying again.",
        "detail": str(error.description),
        "retry_after": 60,
    }), 429, {"Retry-After": "60"}


def json_object():
    """Return a JSON object, rejecting arrays/scalars instead of raising 500s."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def resource_error(error):
    return jsonify({
        "error": str(error),
        "allowed_resources": list(RESOURCE_KEYS),
    }), 400


def search_context_error(error):
    return jsonify({
        "error": str(error),
        "allowed_search_modes": list(SEARCH_MODES),
    }), 400


def generation_context_error(error):
    return jsonify({"error": str(error)}), 400


def query_resources():
    raw = request.args.get("resources")
    return normalize_resources(None if raw is None else raw)


def query_required_resources(selected_resources):
    raw = request.args.get("required")
    return normalize_required_resources(None if raw is None else raw, selected_resources)


ONSETS = ["v","n","m","r","l","s","t","k","d","f","z","b","p","c","g","h","br","cr","dr","fr","gr","kr","pr","tr","vr","st","sk","cl","fl","pl"]
NUCLEI = ["a","e","i","o","u","ae","ai","ea","eo","oa","ui"]
CODAS = ["","n","r","s","l","m","x","v","d","t","k"]


def clean(s): return re.sub(r"[^a-z]", "", s.lower())


def clean_preferences(value):
    """Bound browser-supplied feedback before it reaches the adaptive generator."""
    if not isinstance(value, dict):
        return {"liked": [], "disliked": [], "reasons": {}}

    def examples(key, limit=20):
        raw = value.get(key, [])
        if not isinstance(raw, list):
            return []
        output = []
        for item in raw[:limit]:
            name = clean(str(item))[:30]
            if name and name not in output:
                output.append(name)
        return output

    raw_reasons = value.get("reasons", {})
    reasons = {}
    if isinstance(raw_reasons, dict):
        for key, score in list(raw_reasons.items())[:20]:
            safe_key = re.sub(r"[^a-z_]", "", str(key).lower())[:30]
            if not safe_key:
                continue
            try:
                reasons[safe_key] = max(-20, min(20, int(score)))
            except (TypeError, ValueError):
                continue

    feedback = []
    raw_feedback = value.get("feedback", [])
    if isinstance(raw_feedback, list):
        for row in raw_feedback[:80]:
            if not isinstance(row, dict):
                continue
            name = clean(str(row.get("name", "")))[:30]
            if not name:
                continue
            try:
                vote = int(row.get("vote", 0))
            except (TypeError, ValueError):
                vote = 0
            vote = 1 if vote > 0 else -1 if vote < 0 else 0
            family = re.sub(r"[^a-z_]", "", str(row.get("family", "unknown")).lower())[:30]
            comment = " ".join(str(row.get("comment", "")).split())[:300]
            feedback.append({
                "name": name,
                "vote": vote,
                "comment": comment,
                "family": family or "unknown",
            })

    result = {
        "liked": examples("liked"),
        "disliked": examples("disliked"),
        "reasons": reasons,
    }
    direction_anchors = examples("direction_anchors")
    shortlist = examples("shortlist")
    if feedback:
        result["feedback"] = feedback
    if direction_anchors:
        result["direction_anchors"] = direction_anchors
    if shortlist:
        result["shortlist"] = shortlist
    return result


def generate_ai_with_context(
    brief,
    count,
    preferences,
    brand_dna,
    search_context,
    generation_context=None,
):
    """Preserve the legacy call shape when no optional generation context exists."""
    kwargs = {}
    if brand_dna:
        kwargs["brand_dna"] = brand_dna
    if search_context != DEFAULT_SEARCH_CONTEXT:
        kwargs["search_context"] = search_context
    adaptive = generation_context or dict(DEFAULT_GENERATION_CONTEXT)
    if adaptive != DEFAULT_GENERATION_CONTEXT:
        kwargs["generation_context"] = adaptive
    if kwargs:
        return generate_ai_names(brief, count, preferences, **kwargs)
    return generate_ai_names(brief, count, preferences)


def validate_generation_input(data):
    brand_dna = clean_brand_dna(data.get("brand_dna"))
    try:
        search_context = clean_search_context(data.get("search_context"))
    except ValueError as error:
        return None, None, None, search_context_error(error)

    brief = " ".join(str(data.get("brief", "")).split())
    if len(brief) > 500:
        return None, None, None, (jsonify({"error": "Brief must contain at most 500 characters"}), 400)
    if brief and len(brief) < 3:
        return None, None, None, (jsonify({"error": "Brief must contain at least 3 characters"}), 400)
    if search_context["mode"] == "new_brand" and not brief and not brand_dna:
        return None, None, None, (jsonify({"error": "Brief or Brand DNA is required for a new brand"}), 400)
    return brief, brand_dna, search_context, None


@lru_cache(maxsize=128)
def cached_prompt_intelligence(prompt, resources):
    """Avoid paying for the same interpretation again on every batch."""
    return interpret_prompt(prompt, resources)


def apply_prompt_intelligence(brief, resources, search_context):
    intelligence = cached_prompt_intelligence(brief, tuple(resources))
    compiled = compile_generation_input(
        intelligence,
        extra_guidance=search_context.get("guidance", ""),
    )
    return (
        compiled["brief"],
        clean_search_context(compiled["search_context"]),
        intelligence,
    )


def score_name(name):
    n=clean(name); score=100
    if not 5 <= len(n) <= 8: score-=18
    if len(n) in (5,6,7): score+=8
    vowels=sum(c in "aeiouy" for c in n)
    if vowels < 2: score-=35
    if re.search(r"[^aeiouy]{4,}",n): score-=35
    if any(x in n for x in BANNED_ROOTS): score-=100
    if any(n.endswith(x) for x in BANNED_SUFFIXES): score-=100
    if re.search(r"(.)\1",n): score-=5
    return max(0,min(100,score))


def candidate():
    s=""
    for _ in range(random.choice([2,2,2,3])):
        s += random.choice(ONSETS)+random.choice(NUCLEI)+random.choice(CODAS)
    return re.sub(r"(.)\1+",r"\1",clean(s)).capitalize()


def availability_sort_key(row):
    """Rank confirmed actions first, then evidence of absence, never guesses."""
    return (
        -row.get("claimable_count", 0),
        -row.get("purchasable_count", 0),
        -row.get("not_found_count", 0),
        row.get("taken_count", 0)
        + row.get("reserved_count", 0)
        + row.get("invalid_count", 0),
        row.get("unresolved_count", row.get("unknown_count", 0)),
        -row.get("score", 0),
        row.get("length", len(row.get("name", ""))),
        row.get("name", "").lower(),
    )


def generate(count=40, verify=False, resources=None):
    seen=set(); rows=[]; attempts=0
    while len(rows)<count and attempts<20000:
        attempts+=1; n=candidate(); k=n.lower()
        if k in seen or not 5<=len(k)<=9: continue
        sc=score_name(n)
        if sc<72: continue
        row={"name":n,"score":sc,"length":len(k)}
        rows.append(row); seen.add(k)
    if verify and rows:
        checks=check_many((row["name"] for row in rows), resources=resources)
        for row, result in zip(rows, checks): row.update(result)
    return sorted(rows, key=availability_sort_key)


@app.get("/")
def home(): return render_template("index.html")


@app.get("/health")
def health(): return {"status":"ok"}


@app.get("/api/check/<name>")
@limiter.limit(CHECK_RATE_LIMIT)
def api_check(name):
    n=clean(name)
    if not 3<=len(n)<=30: return jsonify({"error":"Name must contain 3-30 latin letters"}),400
    try:
        resources=query_resources()
        required_resources=query_required_resources(resources)
    except ValueError as error:
        return resource_error(error)
    row={"name":n.capitalize(),"score":score_name(n),"length":len(n)}
    row.update(check_all(n,resources))
    row.update(classify_identity_bundle(row.get("availability"), required_resources))
    return jsonify(row)


@app.post("/api/brand-dna")
@limiter.limit(AI_RATE_LIMIT)
def api_brand_dna():
    data = json_object()
    if data is None:
        return jsonify({"error": "JSON body must be an object"}), 400
    brief = " ".join(str(data.get("brief", "")).split())
    website_url = str(data.get("website_url", "")).strip()
    if len(brief) > 1000:
        return jsonify({"error": "Brief must contain at most 1000 characters"}), 400
    if len(website_url) > 2048:
        return jsonify({"error": "Website URL is too long"}), 400
    if not brief and not website_url:
        return jsonify({"error": "Brief or website_url is required"}), 400
    if not AI_REQUEST_SLOTS.acquire(blocking=False):
        return jsonify({
            "error":"AI is busy. Please try again in a few seconds.",
            "retry_after":5,
        }),503,{"Retry-After":"5"}
    try:
        website = fetch_public_website(website_url) if website_url else None
        dna = build_brand_dna(brief, website)
        source = {
            "brief_used": bool(brief),
            "website_used": bool(website),
            "website_url": website.get("url") if website else None,
            "website_title": website.get("title") if website else None,
            "website_text_chars": len(website.get("text", "")) if website else 0,
        }
        return jsonify({"brand_dna": dna, "source": source})
    except WebsiteFetchError as error:
        return jsonify({"error": str(error), "error_type": "WebsiteFetchError"}), 422
    except Exception as error:
        app.logger.exception("Brand DNA analysis failed")
        return jsonify({
            "error": "Temporary Brand DNA analysis error. Please try again.",
            "error_type": type(error).__name__,
        }), 503
    finally:
        AI_REQUEST_SLOTS.release()


@app.post("/api/interpret")
@limiter.limit(AI_RATE_LIMIT)
def api_interpret():
    data = json_object()
    if data is None:
        return jsonify({"error": "JSON body must be an object"}), 400
    prompt = " ".join(str(data.get("prompt", "")).split())
    if len(prompt) < 2:
        return jsonify({"error": "Prompt must contain at least 2 characters"}), 400
    if len(prompt) > 2000:
        return jsonify({"error": "Prompt must contain at most 2000 characters"}), 400
    try:
        resources = normalize_resources(data.get("resources"))
    except ValueError as error:
        return resource_error(error)
    if not AI_REQUEST_SLOTS.acquire(blocking=False):
        return jsonify({
            "error": "AI is busy. Please try again in a few seconds.",
            "retry_after": 5,
        }), 503, {"Retry-After": "5"}
    try:
        intent = interpret_prompt(prompt, resources, data.get("feedback"))
        return jsonify(intent)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        app.logger.exception("Prompt interpretation failed")
        return jsonify({
            "error": "Temporary prompt interpretation error. Please try again.",
            "error_type": type(error).__name__,
        }), 503
    finally:
        AI_REQUEST_SLOTS.release()


@app.post("/api/ai-names")
@limiter.limit(AI_RATE_LIMIT)
def api_ai_names():
    data=json_object()
    if data is None:
        return jsonify({"error":"JSON body must be an object"}),400
    brief, brand_dna, search_context, error_response = validate_generation_input(data)
    if error_response:
        return error_response
    try:
        generation_context=clean_generation_context(data.get("generation_context"))
    except ValueError as error:
        return generation_context_error(error)
    try:
        count=max(1,min(20,int(data.get("count",10))))
    except (ValueError,TypeError):
        count=10
    if not AI_REQUEST_SLOTS.acquire(blocking=False):
        return jsonify({
            "error":"AI is busy. Please try again in a few seconds.",
            "retry_after":5,
        }),503,{"Retry-After":"5"}
    try:
        last_error=None
        for attempt in range(3):
            try:
                names=generate_ai_with_context(
                    brief,
                    count,
                    clean_preferences(data.get("preferences")),
                    brand_dna,
                    search_context,
                    generation_context,
                )
                for row in names:
                    row["trademark"]=trademark_links(row["name"])
                return jsonify(names)
            except Exception as error:
                last_error=error
                app.logger.warning("AI names attempt %s failed: %s",attempt+1,type(error).__name__)
        app.logger.exception("AI names failed",exc_info=last_error)
        return jsonify({"error":"Temporary AI error. Please try again.","error_type":type(last_error).__name__}),503
    finally:
        AI_REQUEST_SLOTS.release()


@app.post("/api/ai-generate")
@limiter.limit(AI_RATE_LIMIT)
def api_ai_generate():
    data=json_object()
    if data is None:
        return jsonify({"error":"JSON body must be an object"}),400
    brief, brand_dna, search_context, error_response = validate_generation_input(data)
    if error_response:
        return error_response
    try:
        resources=normalize_resources(data.get("resources"))
        required_resources=normalize_required_resources(
            data.get("required_resources"), resources
        )
    except ValueError as error:
        return resource_error(error)
    try:
        generation_context=clean_generation_context(data.get("generation_context"))
    except ValueError as error:
        return generation_context_error(error)
    try: count=max(1,min(20,int(data.get("count",10))))
    except (ValueError,TypeError): count=10
    if not AI_REQUEST_SLOTS.acquire(blocking=False):
        return jsonify({
            "error":"AI is busy. Please try again in a few seconds.",
            "retry_after":5,
        }),503,{"Retry-After":"5"}
    try:
        if os.environ.get("OPENAI_API_KEY"):
            brief, search_context, _intelligence = apply_prompt_intelligence(
                brief,
                resources,
                search_context,
            )
        last_error = None
        for attempt in range(3):
            try:
                names=generate_ai_with_context(
                    brief,
                    count,
                    clean_preferences(data.get("preferences")),
                    brand_dna,
                    search_context,
                    generation_context,
                )
                break
            except Exception as error:
                last_error = error
                app.logger.warning("AI generation attempt %s failed: %s", attempt + 1, type(error).__name__)
        else:
            raise last_error
        checks=check_many((row["name"] for row in names),resources=resources)
        for row, availability in zip(names, checks):
            row.update(availability)
            row.update(classify_identity_bundle(row.get("availability"), required_resources))
            row["trademark"]=trademark_links(row["name"])
        names.sort(key=availability_sort_key)
        return jsonify(names)
    except Exception as error:
        app.logger.exception("AI generation failed")
        return jsonify({"error":"Temporary AI error. Please tap Generate again.","error_type":type(error).__name__}),503
    finally:
        AI_REQUEST_SLOTS.release()


@app.get("/api/generate")
@limiter.limit(LEGACY_RATE_LIMIT)
def api_generate():
    try: count=max(1,min(40,int(request.args.get("count",20))))
    except ValueError: count=20
    verify=request.args.get("verify","0").lower() in {"1","true","yes","on"}
    try:
        resources=query_resources()
    except ValueError as error:
        return resource_error(error)
    if request.args.get("resources") is None:
        return jsonify(generate(count,verify))
    return jsonify(generate(count,verify,resources))


if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",8080)))
