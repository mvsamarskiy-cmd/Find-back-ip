# NameMachine implementation status

Verified against GitHub `main` commit `043717542c9ad71174a14ffafe3074766a7d850e`
and the Railway deployment of the same commit on 2026-08-17/18.

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
| API, browser-history, dependency, and security stabilization | PR #10 | Included |
| AI/check rate limits and bounded AI concurrency | PR #11 | Included |
| Clear UI handling of HTML/5xx responses | PR #13 | Included |
| Railway timeout-safe Gunicorn configuration and health check | commits `3a31297` through `0437175` | Included and deployed |

## Product-plan status

- Phase 1 is complete.
- Phase 2 is partially complete: the full evidence status vocabulary, metadata,
  conservative `not_found` handling, deterministic tests, and optional official
  YouTube/X adapters exist. Registrar confirmation, Telegram MTProto, and
  Fragment classification are not implemented.
- Phase 3 is partially complete: bounded multi-family generation and basic
  deduplication exist. Brand DNA, the 20,000-candidate funnel, full component
  scoring, and required-resource ranking are not implemented.
- Phase 4 is not implemented. Projects, history, and preferences remain in the
  current browser; PostgreSQL, migrations, accounts, idempotency, export, and
  server-side deletion are pending.
- Phase 5 is partially complete only at the web-process level: timeouts, health,
  bounded concurrency, rate limits, and controlled errors exist. The queue,
  resumable jobs, metrics, alerts, load tests, and atomic staging promotion are
  pending.

## Verification performed before Railway cleanup

- GitHub `main` and canonical Railway deployment use commit
  `043717542c9ad71174a14ffafe3074766a7d850e`.
- The complete unit suite passes: 43 tests.
- The production root and `/health` return HTTP 200.
- A production AI request returned HTTP 200 in the deployment logs.
- No production HTTP 5xx responses were present in the inspected two-hour window.
- `resourceful-stillness` is the only attached project containing the
  `OPENAI_API_KEY` variable name and the established `04fec` domain.
- The 15 duplicate projects have no variables, volumes, buckets, or custom
  domains. Their only services point to this same repository.

## Next implementation order

1. Finish Phase 2 correctness and evidence states.
2. Add durable PostgreSQL history with idempotency before scaling generation.
3. Implement the mathematical generation funnel in small, independently tested
   releases.
4. Add the queue, progressive jobs, metrics, and alerts.
5. Design secure Telegram authorization before any MTProto or Fragment work.
