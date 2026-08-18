# R2 — Availability Hunter

R2 changes the durable large-search objective from **candidate volume** to a
**result goal** when the caller explicitly requests Availability Hunter mode.

## Product contract

Legacy large search remains supported:

- `target_count=500` means collect up to 500 durable candidate rows.

Availability Hunter is opt-in:

- `target_matches=3` means find 3 strict-free matches.
- `max_checks=500` means verify at most 500 persisted candidates while trying.
- the worker stops as soon as the strict result goal is reached.
- if the budget is exhausted first, the run finishes truthfully with
  `search_budget_exhausted`.

A strict-free match requires **every required resource** on the candidate to have
raw status `claimable`.

The following do **not** satisfy the free-result goal:

- `not_found`
- `unknown`
- `rate_limited`
- `purchasable` / marketplace inventory
- any hard conflict such as `taken`, `reserved`, or `invalid`

This preserves the fail-closed semantics introduced in R1.

## API

`POST /api/sessions/<session_id>/search-jobs`

Example Hunter fields:

```json
{
  "target_matches": 3,
  "max_checks": 500,
  "target_count": 500,
  "batch_size": 20
}
```

`target_count` is retained in the durable job schema for backward compatibility.
For Hunter jobs the API normalizes it to `max_checks`.

The goal is stored under `search_context.availability_hunter`, avoiding a live
PostgreSQL ALTER TABLE migration for this release.

## Durable progress

After every completed verification batch the worker recomputes the strict match
count from persisted candidate rows for the same `run_id`. This makes the result
goal crash/restart safe rather than relying on an in-memory counter.

Non-secret progress is written to:

`job.preferences._hunter_runtime`

with:

- `checked`
- `matches`
- `target_matches`
- `max_checks`
- `match_policy=claimable`
- `updated_at`

The browser can therefore show **matches** separately from **checks performed**.

## Stop reasons

Hunter terminal reasons:

- `target_matches_reached`
- `search_budget_exhausted`
- `user_cancelled`
- `worker_error`

Worker shutdown still returns the durable job to `pending` so another worker can
resume it.

## UI

The large-search panel is presented as **Пошук вільних**.

The user selects:

- desired strict-free result count: 1 / 3 / 5 / 10
- verification budget: 500 / 1,000 / 5,000 / 20,000

The goal line reports, for example:

`2/3 вільних · перевірено 184/500`

This is intentionally different from the old `184/500 candidates` progress.

## Acceptance criteria

R2 is code-complete when tests prove:

1. `claimable` on every required resource counts as a match.
2. `not_found` never counts as a strict-free match.
3. `purchasable` never counts as a free match.
4. the worker stops early on `target_matches_reached`.
5. the worker stops on `search_budget_exhausted` when no enough strict matches exist.
6. legacy candidate-volume jobs still preserve their old behavior.
7. Hunter progress survives worker restart because matches are recomputed from durable rows.

Production usefulness still depends on R1 strict claimability providers actually
being configured. In particular, Telegram green channel results require the
isolated Telegram evidence service, and `.com` green results require registrar
confirmation.
