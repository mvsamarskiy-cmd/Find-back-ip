# R3 — Procedural Search Plan

R3 changes the default Availability Hunter exploration from broad adaptive naming
to an explicit, durable **root-by-root search procedure**.

## Why

A naming brainstorm benefits from diversity. An availability search does not.
When the goal is to find something claimable, jumping from `bottle` to an
abstract name to `jar` to an unrelated metaphor makes it impossible to know
whether a semantic neighborhood was actually explored.

R3 therefore separates two concepts:

- **taste adaptation** — likes/dislikes and previous good/bad examples;
- **search procedure** — which semantic root and transformation strategy is
  currently being tested against real providers.

Neither layer is allowed to alter verifier truth.

## Durable plan

Prompt Intelligence already produces `naming_roots`. R3 consumes those roots in
order and stores the current position in:

`job.preferences._procedural_runtime`

The runtime contains:

- ordered roots
- current root and root index
- current transformation strategy and strategy index
- checked/conflict/strict-match counts for the current strategy
- checked/conflict/strict-match counts for the current root
- total checks
- a bounded history of completed root/strategy steps and the reason for moving
- `exhausted` when all planned roots have been traversed

No chain-of-thought is stored or exposed. This is operational search state only.

## Strategy sequence

For each root the worker traverses:

1. `direct`
2. `compression`
3. `phonetic`
4. `blend`
5. `compound`

The root does **not** change until every strategy for that root has advanced.

Examples for a focus root `bottle`:

- direct — clean brandable developments visibly anchored to bottle
- compression — shorter forms
- phonetic — pronounceable structural developments, not one-letter mutations
- blend — bottle plus one related supporting root
- compound — concise semantic compounds around bottle

After the final strategy, the planner moves to the next semantic root, e.g.
`jar`, then `vessel`, etc.

## Evidence-based advancement

A strategy receives at least 20 actual verifier outcomes.

- If hard-collision rate is at least 80% after that sample, advance early with
  reason `high_collision`.
- Otherwise keep exploring it up to 40 verifier outcomes, then advance with
  reason `strategy_budget`.

This means heavily occupied territory is abandoned sooner, while lower-collision
territory is explored more deeply.

Hard conflicts are only `taken`, `reserved`, and `invalid` on required resources.
A strict match is only `claimable` on every required resource. `not_found` does
not become green and does not count as a strict match.

## Generation constraint

The worker converts the durable plan position into an explicit generation scope.
For direct/compression/phonetic stages the generator receives only the current
focus root as its literal lexical brief, preventing the local combinatorial
expander from mixing unrelated roots.

Blend/compound stages receive the focus root plus at most two supporting roots.
The semantic brief and user guidance remain available in guidance context so the
names stay related to the original task.

## API/UI

Availability Hunter now defaults to:

`search_strategy = procedural`

The old broad adaptive strategy is still available internally with
`search_strategy = adaptive`, which is useful as a compatibility path and will
later become the basis of a separately named Turbo mode.

The UI shows the actual worker state, e.g.:

`Шукаю корінь bottle · phonetic · 20 перевірок у цьому кроці`

This is real durable state from the job record, not a fake animation.

## Acceptance criteria

R3 is code-complete when tests prove:

1. Prompt Intelligence roots are preserved in order.
2. The planner starts on the first root and first strategy.
3. High collision advances strategy after the minimum evidence sample.
4. Lower-collision strategies receive the larger sample.
5. The root changes only after all strategies for the current root are traversed.
6. Strict matches, hard conflicts, and non-conflicting absence evidence remain
   distinct.
7. The browser shows the current durable root/strategy.
8. Existing non-Hunter/legacy jobs remain backward compatible.

R3 does not add `_`, dots, digits, or other identifier grammar variants. Those
remain a later user-controlled expansion stage as planned.
