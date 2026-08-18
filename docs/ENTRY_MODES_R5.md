# R5 — First-class entry workflows

R5 separates fundamentally different naming tasks before generation starts.
The user no longer has to express every workflow through one generic prompt.

## Four entry modes

### 1. Створити бренд (`brand`)

Use when a new commercial/project brand name is being created.

- generation mode is explicitly locked to `new_brand`;
- the selected digital resources are verified;
- Prompt Intelligence still extracts semantics and naming roots, but it cannot
  reinterpret the task as an existing-brand search;
- later Brand Collision work will attach company/web/trademark screening to this
  workflow.

### 2. Нікнейми / домени (`identity`)

Use when the brand already exists and its name must not be replaced.

- an explicit existing brand name is required;
- generation mode is locked to `existing_brand_fixed`;
- the generator creates brand-linked digital-identity variants;
- selected resources are verified normally.

### 3. Придумати назву (`generic_name`)

A standalone name/nickname generator for arbitrary entities such as:

- game identity
- bot
- character
- channel
- project
- object
- codename
- other non-brand naming tasks

This mode calls `/api/generic-names` and **does not run availability providers**.
Generated rows are tagged `product_mode=generic_name` and `checked=false`.
Likes, dislikes, comments, shortlist, and direction anchors are retained for
subsequent generations.

The client report for this mode explicitly describes ideas rather than verified
availability and warns that domains/socials/companies/trademarks were not checked.

### 4. Інше (`other`)

Free-form workflow. The user describes what they have and what they need.
Prompt Intelligence remains authoritative here and may infer new-brand naming,
fixed existing identity, or adaptable existing identity from the prose.

## Explicit mode authority

Explicit user selection is stronger than AI inference.

R5 sends a bounded internal marker in the existing guidance field:

`[[nm-mode-lock:new_brand]]`

or

`[[nm-mode-lock:existing_brand_fixed]]`

`entry_mode_backend.py` removes this marker before final generation guidance and
restores the explicit mode after Prompt Intelligence has extracted semantic
structure. This preserves useful AI roots/intent analysis without allowing the
model to override a direct user choice.

The same wrapper is installed in both the web process and the durable worker.
No PostgreSQL schema migration is required.

## Compatibility

Sessions created before R5 default to `other`, preserving their old free-form
behavior. Existing verified rows remain compatible.

R5 does not implement company/trademark registry clearance; that is R6.
R5 also does not implement underscores/dots/digits or platform-specific variant
grammars; that remains a later user-controlled expansion stage.
