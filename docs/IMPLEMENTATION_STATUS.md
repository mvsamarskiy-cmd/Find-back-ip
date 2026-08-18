# NameMachine implementation status

Updated for the Brand DNA browser release prepared from GitHub `main` commit
`d7d76981c7a917297cbe609a0412ccf32c7d37db` on 2026-08-18.

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
| ASCII-only names and empty-result rejection | PR #12 supersedes draft PR #8 | Included; old PR #8 is obsolete |
| Evidence envelope and optional official YouTube/X adapters | PR #9 | Included |
| Evidence-correct status vocabulary and ranking | Phase 2.1 release | Included |
| Single UI source of truth | Phase 2.1 release | Obsolete embedded v4.2 UI removed; `templates/index.html` is canonical |
| Name.com confirmation after `.com` RDAP screening | Registrar release | Implemented and tested; production credentials and live actionable proof remain pending |
| Per-search resource selection and dynamic `N/N` results | Selectable-resource release | Implemented for API, mobile UI, local persistence, and historical searches |
| API, browser-history, dependency, and security stabilization | PR #10 | Included |
| AI/check rate limits and bounded AI concurrency | PR #11 | Included |
| Clear UI handling of HTML/5xx responses | PR #13 | Included |
| Railway timeout-safe Gunicorn configuration and health check | commits `3a31297` through `0437175` | Included |
| Lightweight Git-based production rollback | PR #19 | Included; verified revert workflow preserves normal Git history and CI |
| Structured Brand DNA and safe public-website analysis contract | PR #20 | Included for API and naming context |
| Explicit search intent, natural-language guidance, and symmetric feedback reasons | PR #21 | Included in `main` |
| MUST-HAVE Identity Bundle classification and split result columns | PR #22 | Included in `main` |
| Adaptive multi-batch deep search with a 100-check safety cap | PR #23 | Included in `main` |
| Browser website analysis and editable Brand DNA project workflow | PR #24 | Implemented on release branch; requires final green CI and merge before production |

## Product-plan status

- Phase 1 is functionally complete and captures signed reasons on likes and
  dislikes so future generation has explicit positive and negative taste evidence.
- Phase 2 is partially complete: the full evidence status vocabulary, metadata,
  conservative `not_found` handling, deterministic tests, optional official
  YouTube/X adapters, and the optional Name.com registration adapter exist.
  Production Name.com credentials and a live actionable proof are pending;
  Telegram MTProto/Fragment and automated trademark collision evidence are not
  implemented.
- Phase 3 is materially advanced: resource selection, search intent, natural-
  language guidance, structured Brand DNA, safe website extraction, editable
  browser DNA review, MUST-HAVE vs optional resources, deterministic Identity
  Bundle classification, split result columns, and bounded adaptive deep search
  all exist. Website-derived DNA can be reviewed/corrected, is persisted in the
  local project/search history, and is sent to every adaptive batch. Deep search
  blocks exact and conservative phonetic near-duplicates and stops at the target
  or after at most 100 externally checked candidates. The full 20k funnel, family
  quotas, stronger visual/semantic/edit-distance deduplication, automated
  trademark collision evidence, and weighted Identity Bundle scoring remain
  pending.
- Phase 4 is not implemented. Projects, history, preferences, search intent,
  guidance, required-resource choices, adaptive search history, and Brand DNA are
  still browser-local rather than durable server-side data; PostgreSQL, migrations,
  accounts, idempotency, export, and server-side deletion are pending.
- Phase 5 is partially complete only at the web-process/release level: timeouts,
  health, bounded concurrency, rate limits, controlled errors, CI, branch cleanup,
  Git-based rollback, and a per-launch external-check safety cap exist. The queue,
  resumable server jobs, metrics, alerts, load tests, and atomic staging promotion
  are pending.

## Last confirmed production verification

The last fully recorded Railway live verification predates later GitHub releases:

- canonical Railway production used commit `043717542c9ad71174a14ffafe3074766a7d850e`;
- the then-current complete unit suite passed 43 tests;
- the production root and `/health` returned HTTP 200;
- a production AI request returned HTTP 200 in inspected deployment logs;
- no production HTTP 5xx responses were present in the inspected two-hour window;
- `resourceful-stillness` was the only attached project containing the
  `OPENAI_API_KEY` variable name and established `04fec` domain;
- the inspected duplicate projects had no variables, volumes, buckets, or custom
  domains.

Later GitHub releases must not be described as live-verified until the normal
post-deploy smoke and commit match are confirmed.

## Next implementation order

1. Add a legally careful trademark/collision evidence layer as a non-binary risk
   dimension; do not call a mark globally free from a missing exact result.
2. Improve Telegram evidence with MTProto/Fragment classification where a secure
   credential/service boundary is available.
3. Add stronger family quotas plus visual/semantic/edit-distance deduplication and
   weighted Identity Bundle scoring before scaling toward the full 20,000-candidate
   funnel.
4. Add durable PostgreSQL history with idempotency before scaling the full funnel.
5. Add queue/resumable jobs, metrics, alerts, and load tests.
