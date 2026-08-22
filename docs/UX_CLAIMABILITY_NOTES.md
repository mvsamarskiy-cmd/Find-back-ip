# UX claimability notes (agent/ux-claimability-funnel-v1)

## Status labels (user-facing)

| API status | UI label | Meaning |
|---|---|---|
| `claimable` | **Вільне** | Registrar/service confirmed registration |
| `purchasable` | **Можна купити** | Authoritative purchase path |
| `not_found` | **Перспективно** | No public profile/domain found; claimability unconfirmed |
| `taken` / `reserved` / `invalid` | **Зайняте** | Conflict |
| `unknown` / `rate_limited` | **Не підтверджено** | Incomplete evidence |

## Recommended tab

Includes both **confirmed** (`all claimable/purchasable`) and **promising** (only `not_found` + confirmed, zero conflicts).

Social platforms (Instagram, TikTok, Facebook, X) cannot become true green without an official assignment API. Showing them as promising is honest and useful.

## Local funnel scale

`candidate_funnel.py` defaults raised toward product plan targets:

- raw: 20,000
- structural: 6,000
- linguistic: 1,500
- collision shortlist: 300

External network checks remain capped (100 per launch in the browser UI) until async jobs exist.

## Railway prerequisites for true greens

1. `NAMECOM_USERNAME` + `NAMECOM_API_TOKEN` → `.com` claimable
2. Telegram evidence service (`TELEGRAM_EVIDENCE_URL` + token) → Telegram claimable
3. Optional: `YOUTUBE_API_KEY`, `X_BEARER_TOKEN` for stronger occupancy evidence

## Dependencies readiness

`requirements.txt` already includes:

- SQLAlchemy + psycopg → Phase 4 server history
- Flask-Limiter[redis] → multi-worker rate limits
- Telethon → Telegram evidence path
- socialscan → extra username probes

Disk capacity for 20k local candidates is fine; the bottleneck is **external API rate limits and claimability providers**, not local CPU/disk.
