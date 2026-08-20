# Live audit — 2026-08-20

## App availability

- Production URL responds: https://web-production-04fec.up.railway.app
- `/health` → `{"status":"ok"}`
- UI shell loads (NameMachine, resources, Start/Stop, tabs)

## Speed

Parallel 7-resource check for one synthetic name completed in under **1 second** end-to-end. Gunicorn gthread + ThreadPoolExecutor is adequate for single-name checks.

AI generation (`/api/ai-generate`) is slower by design (OpenAI + local funnel + N checks). UI batches of 20 × up to 5 = 100 external names; expect tens of seconds to a few minutes per full cycle depending on OpenAI latency and rate limits.

## Generation structure

Pipeline is sound:

1. Prompt → optional Brand DNA / prompt intelligence
2. OpenAI structured names + local lexical expander
3. Quality gates + family quotas + diversity
4. Parallel availability checks
5. Identity bundle classification + ranking

Quality is not "random spam" — banned roots/suffixes and structural scores exist. Local expander helps fill volume without more OpenAI spend.

## UX problems (user-visible)

1. **Recommended tab is almost always empty** because it requires every selected resource to be `claimable`/`purchasable`. Social platforms almost never produce claimable.
2. **`not_found` shown as "Не знайдено"** reads as failure; should be **Перспективно**.
3. **Links work** (open profile/search URLs) but status language is unclear.
4. **Buttons** Start/Stop/Continue are English in a Ukrainian UI.
5. No summary counts (confirmed / promising / conflict).

## Reliability problems

1. **Instagram 429** on live check — public scraping is fragile; need cache + backoff + lower concurrency.
2. **Name.com not configured** — `.com` stays `not_found` even when RDAP is empty.
3. Long names fail X validation (`invalid`) — generator should prefer ≤15 for X when X is required.

## Browser / "browser eye"

Production responses include a richer verification envelope (evidence fusion, socialscan, Fragment, WhatsMyName). The main UI template is still the simple `templates/index.html` and does not surface deep browser-enrichment UI. Advanced static assets under `static/` exist in the repo but are not wired into the current homepage template.

## Recommendations (priority)

1. P0: UI semantics (Перспективно + Recommended = confirmed∪promising)
2. P0: Configure Name.com on Railway
3. P1: Cap name length when X selected; retry/backoff Instagram
4. P1: Wire or remove unused static UI modules to avoid dual-UI confusion
5. P2: Async jobs for deep 20k external search
