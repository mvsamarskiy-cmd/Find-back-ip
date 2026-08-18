# NameMachine implementation status

Updated for the staged local funnel release prepared from GitHub `main` commit
`2455ac59b0ec97bde5472f234adb635998c419af` on 2026-08-18.

This file records what exists now. `PRODUCT_PLAN.md` remains the implementation
order for unfinished work.

## Completed release history

| Stage | Evidence in GitHub | Current state |
| --- | --- | --- |
| Live `.com`, Instagram, and Telegram checks | PR #1 | Included in `main` |
| AI generation plus seven-resource checking | Earlier PR #2 work, then integrated and extended on `main` | Included; old PR #2 is obsolete |
| Progressive checks, local history, copy and action controls | Earlier PR #3 work, then integrated and extended on `main` | Included; old PR #3 is obsolete |
| Project profiles, feedback, Ukrainian UI, product plan | PR #5 | Included |
| Social 404 results no longer treated as available | PR #6 | Included |
| Diversified candidate generation | PR #7 | Included |
| ASCII-only names and empty-result rejection | PR #12 supersedes draft PR #8 | Included |
| Evidence envelope and optional official YouTube/X adapters | PR #9 | Included |
| API/browser-history/security stabilization | PR #10 | Included |
| AI/check rate limits and bounded AI concurrency | PR #11 | Included |
| Clear UI handling of HTML/5xx responses | PR #13 | Included |
| Railway timeout-safe Gunicorn configuration and health check | commits `3a31297` through `0437175` | Included |
| Lightweight Git-based production rollback | PR #19 | Included |
| Structured Brand DNA and safe public-website analysis | PR #20 | Included |
| Explicit search intent, natural-language guidance, symmetric feedback | PR #21 | Included |
| MUST-HAVE Identity Bundle classification and split result columns | PR #22 | Included |
| Adaptive multi-batch deep search with a 100-check safety cap | PR #23 | Included |
| Browser website analysis and editable Brand DNA workflow | PR #24 | Included |
| Legally conservative trademark/collision risk contract | PR #25 | Included |
| Secured MTProto/Fragment Telegram evidence boundary | PR #26 | Included; live evidence service configuration pending |
| Weighted Identity Bundle Opportunity score | PR #27 | Included |
| Family quotas plus stronger visual/edit-distance dedupe | Subsequent Phase 3 releases | Included |
| Opportunity-score UI ranking | PR #29 | Included |
| Structural local quality prefilter | PR #30 | Included |
| Deterministic local lexical naming families | PR #31 | Included |
| Hybrid AI + local naming funnel with Cyrillic transliteration | PR #32 | Included |
| Multi-stage local structural/readability/internal-collision funnel | Current release | Implemented on release branch; requires green CI and merge |

## Product-plan status

- Phase 1 is functionally complete. Project-local likes/dislikes and signed reasons
  are persisted in the browser and fed into later generation.
- Phase 2 is materially advanced. Evidence-correct statuses, source metadata,
  optional official YouTube/X and Name.com adapters, a secured Telegram
  MTProto/Fragment boundary, and a non-binary trademark-risk contract exist.
  Production Name.com proof, deployment of the separate Telegram evidence service,
  and a permitted machine-readable trademark registry adapter remain pending.
- Phase 3 is materially advanced. Search intent, user guidance, Brand DNA,
  MUST-HAVE vs optional resources, adaptive batches, the 100-external-check cap,
  split result columns, Opportunity scoring, family quotas, conservative visual/
  phonetic/edit-distance dedupe, and a hybrid AI + local generator all exist. The
  local path now explores a much larger cheap deterministic space and reduces it
  through structural quality, readability/pronounceability proxy, and internal
  morphology-collision stages before the stricter product shortlist. This is not
  yet the full 20,000-candidate target: production-safe caps remain smaller until
  load tests and asynchronous jobs are available.
- Phase 4 is not implemented. Projects, searches, history, preferences, Brand DNA,
  and feedback remain browser-local. PostgreSQL, migrations, accounts,
  idempotency, export, and server-side deletion are pending.
- Phase 5 is partially complete only at the web-process/release level: timeouts,
  health, bounded concurrency, rate limits, controlled errors, CI, branch cleanup,
  Git-based rollback, and an external-check safety cap exist. Queue-backed jobs,
  resumability, metrics/alerts, load tests, and atomic staging promotion are
  pending.

## Last confirmed production verification

The last fully recorded Railway live verification predates later GitHub releases:

- canonical Railway production used commit `043717542c9ad71174a14ffafe3074766a7d850e`;
- the then-current complete unit suite passed 43 tests;
- the production root and `/health` returned HTTP 200;
- a production AI request returned HTTP 200 in inspected deployment logs;
- no production HTTP 5xx responses were present in the inspected two-hour window.

Later GitHub releases must not be described as live-verified until the normal
post-deploy smoke and commit match are confirmed.

## Next implementation order

1. Add durable PostgreSQL project/search/history storage plus idempotency so the
   now-larger funnel has server-side state and can survive browser/device changes.
2. Move long-running deep-search work into resumable queued jobs before raising
   production funnel caps toward 20,000 candidates.
3. Add load tests and funnel metrics, then tune stage sizes based on measured CPU,
   latency, external-call budget, and result quality.
4. Deploy/configure the separate Telegram evidence service with real MTProto and
   permitted Fragment observation capability.
5. Add a permitted machine-readable trademark registry adapter when an official or
   licensed data path is available.
