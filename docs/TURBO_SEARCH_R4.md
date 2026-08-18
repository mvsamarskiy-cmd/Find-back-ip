# R4 — Turbo Search

Turbo is a user-selectable Availability Hunter strategy for the case where the
human does not care which semantic neighborhood produces the result and wants
the system to search broadly for something it can **strictly prove claimable**.

## Modes

The search panel now exposes two product modes:

- **Процедурно** — one semantic root at a time using the durable R3 plan.
- **Turbo** — broad adaptive exploration across the interpreted naming space.

Both modes still use the same R2 result goal:

`find target_matches within max_checks`

and both preserve R1 verifier truth.

## Strict truth is unchanged

Turbo does not make weak evidence green.

Only a candidate with raw status `claimable` on every required resource counts
as a strict-free match.

The following remain non-green:

- `not_found`
- `unknown`
- `rate_limited`
- `purchasable`
- `taken`
- `reserved`
- `invalid`

If the selected platform has no authoritative claimability provider configured,
Turbo can legitimately return zero green results after exhausting its budget.
That is preferred to a false availability claim.

## Broad generation behavior

Turbo deliberately does not install the R3 `procedural_search` runtime. Instead,
it uses the existing adaptive generator with extra guidance to:

- maximize lexical/phonetic breadth;
- avoid lingering on one occupied root;
- avoid tiny mutations of failed names;
- optimize for strict-free yield rather than producing a visually varied
  brainstorm list for the user.

All generated and verified rows are still persisted.

## Primary feed contract

For the active Turbo run the primary user feed shows only candidates for which
`allGreen(row)` is true.

Example:

`Turbo · 3 вільних · перевірено 284 · відсіяно 281`

The 281 rejected/unconfirmed rows are **not deleted**. They remain in durable
session storage for:

- audit
- reports
- verifier analysis
- feedback/search learning

They simply do not clutter the customer's main Turbo feed.

This distinction is important: Turbo is a presentation/search-objective mode,
not a data-destruction mode.

## Persistence after reopen

The job stores `search_context.search_strategy = turbo` and
`search_context.turbo_search.enabled = true`. The browser poller restores the
current `backgroundSearch.search_strategy` from durable job state, so the strict
Turbo feed can be reconstructed after reopening the page.

## Acceptance criteria

R4 is code-complete when tests prove:

1. The user can select Procedural or Turbo.
2. Turbo jobs are tagged durably as `search_strategy=turbo`.
3. Turbo does not create a procedural root plan.
4. Turbo keeps the strict Availability Hunter target/budget semantics.
5. The primary Turbo feed filters the current Turbo run to `allGreen` rows only.
6. Non-green rows remain durable rather than being discarded.
7. No UI code promotes `not_found` or `purchasable` to free.
8. Reopening a job can restore the Turbo strategy from server state.
