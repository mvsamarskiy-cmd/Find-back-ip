# NameMachine verification architecture

## The product claim

NameMachine verifies evidence about an exact normalized `@username`. It must
never treat a missing public page, a search-engine miss, or an AI opinion as
proof that the username can be registered.

Three questions are reported separately:

1. **Exact handle occupancy** — is this exact `@username` attached to an account?
2. **Claimability** — can a user register it now, rather than it being reserved,
   suspended, premium, invalid, or otherwise blocked?
3. **Brand collision** — do display names, companies, products, domains,
   trademarks, apps, or indexed pages create a confusingly similar identity?

## Evidence order

1. Validate each platform's syntax and reserved-name rules.
2. Query an official exact-handle API when available.
3. Inspect the canonical public profile as supporting evidence.
4. Search independent web indexes for the exact handle and brand variants.
5. Search domains, company/product pages, app stores, and trademark databases.
6. Let OpenAI classify and summarize the collected evidence with citations.
7. For a finalist, require a manual claim/registration step before calling it
   confirmed claimable.

AI may generate queries, detect aliases, compare display names, identify false
positives, and explain conflicts. AI is never itself the authoritative source
for occupancy or claimability.

## Platform matrix

| Resource | Best exact-handle evidence | Meaning of a miss | Production requirement |
|---|---|---|---|
| `.com` | Verisign RDAP, then registrar availability | likely unregistered, not yet purchasable-confirmed | registrar API for final confirmation |
| YouTube | Data API `channels.list(forHandle=...)` | no channel found; claimability still unconfirmed | `YOUTUBE_API_KEY` |
| X | API v2 user lookup by username | no user found; reserved/suspended remains possible | `X_BEARER_TOKEN` and eligible plan |
| Telegram | MTProto `contacts.resolveUsername` | not occupied, but may be reserved/premium/Fragment | isolated Telegram service and account session |
| Instagram | public profile plus eligible Meta professional-account evidence | arbitrary personal handles are not covered by a universal official API | evidence aggregation and manual final claim |
| Facebook | Pages search/public page evidence | does not cover every username or reservation state | evidence aggregation and manual final claim |
| TikTok | public profile; official access is restricted to approved products/scopes | absence is not claimability | evidence aggregation and manual final claim |

## Status model

- `occupied_confirmed`: exact official or strong canonical evidence.
- `not_found`: the queried source did not find the exact handle.
- `claimable_confirmed`: verified in the platform's registration flow.
- `reserved`, `invalid`, `rate_limited`, `blocked`, `unknown`, `conflict`.

The existing `available/taken/unknown` field remains temporarily for UI
compatibility. Every result additionally includes `occupancy`, `claimability`,
`source`, `method`, `confidence`, and `checked_at`.

## Search and OpenAI research

Use Brave Search as an independent current web index and optionally Google
Programmable Search while it remains supported. Queries should include exact
profile URLs, quoted `@username`, plain brand spelling, spaced variants,
transliterations, and high-risk near matches. Search absence only lowers
collision risk; it never confirms availability.

OpenAI web search belongs in an asynchronous research job for shortlisted
candidates. It should return cited sources and a collision report, not mutate
the platform availability status. This keeps the interactive seven-resource
check fast, inexpensive, and resilient.

## Safe release order

1. Evidence metadata and official YouTube/X adapters.
2. UI evidence drawer and contradiction warnings.
3. Search-index collision report for finalists.
4. OpenAI cited synthesis for finalists.
5. Isolated Telegram MTProto/Fragment service.
6. Registrar confirmation and manual claim checklist.
7. Queue, cache, circuit breakers, observability, and load tests before scale.
