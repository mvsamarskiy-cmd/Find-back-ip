import os, random, re
from threading import BoundedSemaphore
from flask import Flask, request, jsonify, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from availability import check_all, check_many
from ai_engine import BANNED_ROOTS, BANNED_SUFFIXES, generate_ai_names, trademark_links

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

ONSETS = ["v","n","m","r","l","s","t","k","d","f","z","b","p","c","g","h","br","cr","dr","fr","gr","kr","pr","tr","vr","st","sk","cl","fl","pl"]
NUCLEI = ["a","e","i","o","u","ae","ai","ea","eo","oa","ui"]
CODAS = ["","n","r","s","l","m","x","v","d","t","k"]

def clean(s): return re.sub(r"[^a-z]", "", s.lower())

def clean_preferences(value):
    """Bound browser-supplied feedback before it reaches the model prompt."""
    if not isinstance(value, dict):
        return {"liked": [], "disliked": [], "reasons": {}}

    def examples(key):
        raw = value.get(key, [])
        if not isinstance(raw, list):
            return []
        output = []
        for item in raw[:20]:
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
    return {"liked": examples("liked"), "disliked": examples("disliked"), "reasons": reasons}

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

def generate(count=40, verify=False):
    seen=set(); rows=[]; attempts=0
    while len(rows)<count and attempts<20000:
        attempts+=1; n=candidate(); k=n.lower()
        if k in seen or not 5<=len(k)<=9: continue
        sc=score_name(n)
        if sc<72: continue
        row={"name":n,"score":sc,"length":len(k)}
        rows.append(row); seen.add(k)
    if verify and rows:
        checks=check_many(row["name"] for row in rows)
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
    row={"name":n.capitalize(),"score":score_name(n),"length":len(n)}; row.update(check_all(n)); return jsonify(row)

@app.post("/api/ai-names")
@limiter.limit(AI_RATE_LIMIT)
def api_ai_names():
    data=json_object()
    if data is None:
        return jsonify({"error":"JSON body must be an object"}),400
    brief=str(data.get("brief","")).strip()
    if not 3<=len(brief)<=500:
        return jsonify({"error":"Brief must contain 3-500 characters"}),400
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
                names=generate_ai_names(brief,count,clean_preferences(data.get("preferences")))
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
    brief=str(data.get("brief","")).strip()
    if not 3<=len(brief)<=500: return jsonify({"error":"Brief must contain 3-500 characters"}),400
    try: count=max(1,min(20,int(data.get("count",10))))
    except (ValueError,TypeError): count=10
    if not AI_REQUEST_SLOTS.acquire(blocking=False):
        return jsonify({
            "error":"AI is busy. Please try again in a few seconds.",
            "retry_after":5,
        }),503,{"Retry-After":"5"}
    try:
        last_error = None
        for attempt in range(3):
            try:
                names=generate_ai_names(brief,count,clean_preferences(data.get("preferences")))
                break
            except Exception as error:
                last_error = error
                app.logger.warning("AI generation attempt %s failed: %s", attempt + 1, type(error).__name__)
        else:
            raise last_error
        checks=check_many(row["name"] for row in names)
        for row, availability in zip(names, checks):
            row.update(availability)
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
    return jsonify(generate(count,verify))

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",8080)))
