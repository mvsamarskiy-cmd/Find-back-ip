# NameMachine v4.3

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

Availability statuses are evidence-limited: UNKNOWN never counts as available. Social checks are best-effort. Trademark links are research aids, not legal clearance.

The staged implementation and reliability requirements are documented in
[`docs/PRODUCT_PLAN.md`](docs/PRODUCT_PLAN.md).

## Local run

1. Install dependencies: `pip install -r requirements.txt`
2. Set `OPENAI_API_KEY` for AI generation.
3. Optionally set `OPENAI_MODEL`, `HTTP_TIMEOUT`, and `AVAILABILITY_WORKERS`.
4. Run `python app.py`.

## Railway

Deploy the `main` branch and set `OPENAI_API_KEY` as a Railway environment variable. The included Procfile starts Gunicorn and Railway supplies `PORT`.

## Tests

`python -m unittest discover -s tests -v`
