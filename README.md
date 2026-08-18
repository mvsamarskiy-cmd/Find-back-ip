# NameMachine v4.5

Deploy-ready Flask application for generating and screening international brand-name candidates.

## Features

- heuristic name generation with configurable blacklists and scoring
- concurrent .com, Instagram, and Telegram checks
- OpenAI-powered generation from a Ukrainian brand brief
- project-specific likes, dislikes, and structured preference learning
- persistent browser history and project profiles
- language-risk notes and pronunciation guidance
- manual EUIPO, WIPO, and UPRP trademark-search links
- health endpoint and automated tests

Availability uses an evidence-limited status model: `not_found` records a source
miss but never counts as claimable. Only direct registration or purchase evidence
may produce `claimable` or `purchasable`. Social checks are best-effort, and
trademark links are research aids rather than legal clearance.

For `.com`, Verisign RDAP is always checked first. When `NAMECOM_USERNAME` and
`NAMECOM_API_TOKEN` are both configured, an RDAP miss is followed by Name.com's
official Core API Check Availability endpoint with `purchaseType=registration`.
A standard registration becomes `claimable`; a premium or other authoritative
purchase path becomes `purchasable`. Missing credentials retain the conservative
`not_found` result, while registrar errors remain non-actionable.

The staged implementation and reliability requirements are documented in
[`docs/PRODUCT_PLAN.md`](docs/PRODUCT_PLAN.md).

## Local run

1. Install dependencies: `pip install -r requirements.txt`
2. Set `OPENAI_API_KEY` for AI generation.
3. Optionally set `NAMECOM_USERNAME` and `NAMECOM_API_TOKEN` for direct `.com`
   registration confirmation.
4. Optionally set `OPENAI_MODEL`, `HTTP_TIMEOUT`, and `AVAILABILITY_WORKERS`.
5. Run `python app.py`.

## Railway

Deploy the `main` branch and set `OPENAI_API_KEY` as a Railway environment variable.
Set `NAMECOM_USERNAME` and `NAMECOM_API_TOKEN` together to activate authoritative
`.com` registration confirmation; neither value is returned to clients. Railway
uses `railway.json` to start Gunicorn with the checked-in `gunicorn.conf.py`; the
default 180-second worker timeout leaves enough time for multi-candidate AI
responses. Railway supplies `PORT`. `GUNICORN_TIMEOUT` can override the default
without changing the start command.

### API protection

The default limits are intentionally conservative for a public, AI-backed service:

- AI generation: `5 per minute;30 per hour` per client IP
- live name checks: `60 per minute` per client IP
- concurrent AI requests: `2` per application process

They can be changed with `AI_RATE_LIMIT`, `CHECK_RATE_LIMIT`, and
`MAX_CONCURRENT_AI_REQUESTS`. A single replica can use the default in-memory
counter. For multiple workers or replicas, provision Redis and set
`RATELIMIT_STORAGE_URI` to its `redis://` or `rediss://` URL so every process
shares the same counters.

## Tests

`python -m unittest discover -s tests -v`
