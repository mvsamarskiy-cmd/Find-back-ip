# NameMachine product plan

This document is the implementation order. Each phase must remain deployable,
backward compatible, and covered by tests before the next phase begins.

## Product objective

Find contextually strong names or brand-linked digital identity variants with the
best evidence-backed composition across `.com`, Instagram, Telegram, TikTok,
YouTube, Facebook, and X. The product must understand whether the user is creating
a new brand or preserving an existing one, and it must separate confirmed
claimability from public-profile absence and unknown results.

## Ranking model

Candidates first pass hard gates for context, explicit user constraints, syntax,
critical language risk, required-resource conflicts, and high collision risk.
Survivors are ranked as a Pareto set across:

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
- [x] Structured reasons for positive feedback: sound, meaning, length, style,
  distinctiveness.
- [x] Structured reasons for negative feedback, including genericness,
  complexity, similarity, and disliked endings.
- [x] Feed bounded liked/disliked examples and signed reason weights into OpenAI.
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
- [x] Add an optional official Name.com registration check after RDAP screening,
  with conservative credential, throttling, and malformed-response handling.
- [ ] Configure production Name.com credentials and verify a live
  `claimable`/`purchasable` result.
- [x] Add Telegram MTProto/Fragment classification behind a separate secured
  evidence-service boundary. The main web process never stores Telegram session
  credentials; it consumes a narrow HTTPS/token contract and preserves
  occupied/for-sale/reserved/not-found/rate-limit/unknown distinctions.
- [ ] Deploy/configure that external Telegram evidence service in production and
  verify live MTProto/Fragment observations. Until configured, the current public
  `t.me` checker remains the conservative fallback.
- [x] Add a trademark/collision risk contract as a separate non-binary dimension:
  territory + Nice classes + identical/similar sign + status/priority criteria,
  official EUIPO/WIPO/UPRP search routes, and deterministic scoring for trusted
  observations. No-hit is never labelled globally `free`.
- [ ] Add a permitted machine-readable trademark registry adapter that supplies
  trustworthy observations to that risk contract. Do not automate/scrape the WIPO
  Global Brand Database public search service, whose terms prohibit automated
  queries.

## Phase 3 — identity search and mathematical generation funnel

- [x] Let every search select any non-empty subset of the seven resources.
- [x] Persist the selection in browser history and use it as the exact `N/N`
  denominator in API and UI results.
- [x] Define explicit search intent: new brand, existing locked brand, or existing
  adaptable brand.
- [x] Add bounded natural-language guidance such as exclusions, length/style
  preferences, and other user instructions, with explicit instructions taking
  precedence over learned taste.
- [x] Persist search intent and guidance inside the local project/search history.
- [x] Define bounded structured Brand DNA and a `/api/brand-dna` compiler from a
  user brief and optional public website extract.
- [x] Add a conservative website-analysis boundary: HTTP(S) only, standard ports,
  public-address validation, manual redirect validation, response-size limits,
  visible-text extraction, and explicit prompt-injection isolation.
- [x] Allow AI naming endpoints to consume sanitized Brand DNA without breaking
  legacy brief-only calls.
- [x] Add website URL and Brand DNA review/edit controls to the browser UI, persist
  the edited DNA and source metadata inside the local project profile and search
  history, and send the current DNA into every adaptive generation batch.
- [x] Split requirements into MUST HAVE and optional resources so a candidate is
  rejected when a required identity resource conflicts but may survive an
  optional conflict.
- [x] Generate in feedback-aware batches and use prior conflict/success examples
  as bounded adaptive context; follow-up batches are explicitly instructed to
  leave saturated lexical and phonetic neighborhoods instead of producing trivial
  spelling or suffix mutations.
- [x] Search until enough strong identity bundles are found or a safety cap is
  reached. The browser performs up to five batches of at most 20 candidates, with
  an absolute cap of 100 externally checked candidates per launch.
- [x] Split results into `conflict` and `opportunity` columns while preserving an
  explicit unresolved state; each main column has an independent resource filter,
  and the opportunity column also filters confirmed vs promising evidence.
- [x] Implement a bounded deterministic local lexical-family expander outside
  OpenAI. It extracts literal roots from the brief/Brand DNA, transliterates
  Cyrillic project vocabulary deterministically, and creates semantic compounds,
  substantial root blends, midpoint blends, and compact three-root blends without
  one-letter typo mutation spam.
- [x] Feed the local lexical-family pool into the new-brand production shortlist
  before external checks. Existing locked/adaptable brand modes remain model-led
  so the local expander cannot accidentally invent a replacement brand.
- [x] Add a staged cheap local funnel before the production shortlist. The local
  generator can explore up to 4,000 raw deterministic candidates, then applies a
  structural gate, a readability/pronounceability proxy, and an internal
  morphology-collision gate before the existing strict dedupe/family-quota layer.
- [ ] Scale the staged funnel toward the long-term target of roughly
  `20,000 raw -> 6,000 structural -> 1,500 linguistic -> 300 internal collision ->
  100 external checks -> 20 final reports`. The implemented production-safe stage
  is intentionally smaller until load tests and asynchronous jobs exist.
- [x] Apply family quotas to prevent suffix monoculture.
- [x] Add conservative visual and edit-distance deduplication on top of exact,
  phonetic, and sequence-similarity filtering. Deeper semantic deduplication for
  the future large local funnel remains pending.
- [x] Rank full Identity Bundles across selected required and optional resources
  with a weighted Opportunity score. Required conflicts still dominate semantic
  classification, and `not_found` remains unconfirmed even when it contributes
  partial ranking utility.

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
