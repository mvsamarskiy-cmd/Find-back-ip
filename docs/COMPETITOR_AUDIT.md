# Competitive audit: naming and domain discovery

Reviewed 17 August 2026 from official product and help pages. Exact proprietary
ranking formulas are not public; inferred mechanics below are explicitly marked.

## Confirmed product mechanics

| Product | Officially visible mechanics | Useful lesson |
|---|---|---|
| Namelix | Custom AI model; short/keyword/extension priority; blacklist, maximum length, randomness and multi-TLD controls | Generation needs explicit creative controls, not one generic prompt |
| Namecheap Beast Mode | Bulk search up to 5,000 inputs; price, TLD, prefix/suffix and domain-hack filters | Generate cheaply, filter locally, then run authoritative registrar checks |
| Atom | Detailed brief; about 100 ranked ideas in about 30 seconds; available domains; premium marketplace and human contests | A broad candidate pool should be reduced to an explained shortlist |
| Wix | Description, brand personality, follow-up questions, rationale and domain options | Convert a free-text brief into structured Brand DNA |
| Shopify | AI brief-to-name flow with instant domain availability and registration | Keep the path from discovery to registration short |
| Looka | Length filter, domain and social checks, alternatives with prefixes/suffixes, instant logo exploration | Show useful variants and visual context after a strong root is selected |
| BrandCrowd | Description, length and style controls; industry alignment and domain availability | Make length/style first-class constraints |
| GoDaddy | AI naming connected directly to domain registration and launch assets | Availability must lead to an actionable next step |

## Inferred common architecture

The following is an inference from the product behavior, not a claim about
private source code:

1. Parse keywords, industry, audience, tone and constraints.
2. Generate a broad pool using templates, lexical transforms and/or a language model.
3. Apply syntax, length, memorability and collision filters.
4. Deduplicate exact, spelling, phonetic and family-level variants.
5. Check a much smaller shortlist against authoritative domain inventory.
6. Rank by fit, brand quality, availability, confidence and commercial actionability.
7. Learn from saved/disliked choices or explicit refinements.

## NameMachine advantage and gaps

Advantages: Ukrainian explanations, project-scoped feedback, seven-resource
composition target, explicit uncertainty, and a planned 20,000-candidate funnel.

Highest-priority gaps:

1. Diversified candidate families and deterministic near-duplicate removal.
2. Structured Brand DNA and user controls for length, style, required words,
   forbidden fragments and creative distance.
3. Evidence-correct domain/handle states with source, timestamp and confidence.
4. Cheap local screening before any external checks.
5. Asynchronous jobs, caching and bounded concurrency for large funnels.

## Implemented in the first competitor-informed increment

- One bounded AI request creates a pool up to twice the requested shortlist.
- The prompt enforces five different naming families and discourages suffix monoculture.
- Local normalization removes invalid, exact, visually close and conservative
  phonetic duplicates before any availability request.
- The final count remains capped at 20 and the pool at 40, preserving current
  request and deployment limits.

## Official sources

- https://namelix.com/
- https://namelix.com/app/
- https://www.namecheap.com/domains/bulk-domain-search/
- https://www.namecheap.com/guru-guides/multiple-domain-names/
- https://www.atom.com/business-name-generator
- https://support.wix.com/en/article/wix-business-launcher-creating-a-new-business-name
- https://www.shopify.com/tools/business-name-generator
- https://looka.com/business-name-generator/
- https://www.brandcrowd.com/business-name-generator
- https://www.godaddy.com/business-name-generator
