# NameMachine product plan

This document is the implementation order. Each phase must remain deployable,
backward compatible, and covered by tests before the next phase begins.

## Product objective

Find contextually strong names with the best evidence-backed composition across
`.com`, Instagram, Telegram, TikTok, YouTube, Facebook, and X. The product must
separate confirmed claimability from public-profile absence and unknown results.

## Ranking model

Candidates first pass hard gates for context, syntax, critical language risk,
and high collision risk. Survivors are ranked as a Pareto set across:

- contextual fit;
- brand quality and distinctiveness;
- pronounceability, spelling, and memorability;
- domain quality;
- confirmed and likely digital availability;
- collision and trademark risk;
- evidence confidence.

No estimated monetary value is shown without comparable market sales.

## Phase 1 — project feedback loop

- [x] Project-specific local profiles.
- [x] Like and dislike controls.
- [x] Structured reasons: sound, meaning, length, style, distinctiveness.
- [x] Feed bounded liked/disliked examples and reason weights into OpenAI.
- [x] Preserve existing browser history.
- [x] Ukrainian interface and AI explanations.
- [x] Unit tests without external-network dependence.

## Phase 2 — evidence-correct availability

- [x] Replace `available/taken/unknown` with `claimable`, `purchasable`, `taken`,
  `not_found`, `invalid`, `reserved`, `rate_limited`, and `unknown`.
- [x] Add source, check time, method, and confidence to every result.
- [x] Stop counting public 404 responses as confirmed free.
- [x] Add deterministic fixtures for known occupied and synthetic handles.
- [x] Add official YouTube and X lookup adapters where credentials permit.
- [ ] Add registrar availability confirmation after RDAP screening.
- [ ] Add Telegram MTProto and Fragment classification as a separate secured service.

## Phase 3 — mathematical generation funnel

- Convert the brief to structured Brand DNA.
- Generate diversified local candidate families.
- Funnel: 20,000 -> 6,000 structural -> 1,500 linguistic -> 300 collision ->
  100 external checks -> 20 final reports.
- Apply family quotas to prevent suffix monoculture.
- Add phonetic, visual, semantic, and edit-distance deduplication.
- Rank availability compositions from 2/7 through 7/7 with required-resource filters.

## Phase 4 — durable server history

- PostgreSQL projects, searches, candidates, checks, and feedback events.
- Versioned, reversible migrations.
- Anonymous local profile migration or authenticated accounts.
- Idempotency keys so retries cannot duplicate searches.
- Export and delete controls.

## Phase 5 — asynchronous scale and reliability

- Queue external checks outside web workers.
- Bounded concurrency per platform, caching, backoff, circuit breakers, and budgets.
- Progressive results and resumable jobs.
- Health, readiness, structured logs, latency/error metrics, and alerts.
- Load tests at 20, 100, and staged 20,000-candidate funnel sizes.
- Staging deployment, smoke tests, then atomic production promotion.

## Release invariant

Never deploy several architectural phases together. Every release must pass unit
tests, JavaScript syntax validation, a local Gunicorn health smoke test, and CI.
