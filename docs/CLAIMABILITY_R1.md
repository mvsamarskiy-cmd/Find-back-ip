# R1 — strict claimability

This release separates **profile absence** from **registration/assignment proof**.
`not_found` is still never green. A green result requires a provider that directly
confirms claimability.

## Telegram strict green

NameMachine's public web process must not own a Telegram user session. Deploy
`telegram_claimability_service.py` as a separate private service using
`/railway.telegram-evidence.json`.

Required variables on the isolated Telegram service only:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION_STRING`
- `TELEGRAM_EVIDENCE_TOKEN`
- `TELEGRAM_PROBE_CHANNEL` — an existing channel/supergroup visible to the authorized session. It may be a current public `@username` or a numeric channel id. `TELEGRAM_PROBE_CHANNEL_ID` is accepted as a compatibility alias.

The configured probe channel is **never modified** by NameMachine. Telegram requires
an `InputChannel` argument for `channels.checkUsername`; the probe channel exists only
so Telegram can answer whether a candidate username can actually be assigned to a
channel/supergroup.

The public NameMachine web/worker services receive only:

- `TELEGRAM_EVIDENCE_URL` — HTTPS URL of the isolated service
- `TELEGRAM_EVIDENCE_TOKEN` — the shared bearer token

The service uses Telegram's user-only MTProto `channels.checkUsername` method and
normalizes outcomes to:

- `claimable` — direct channel-assignment success, eligible for strict green
- `occupied` — `USERNAME_OCCUPIED`
- `purchasable` — `USERNAME_PURCHASE_AVAILABLE`; link to Fragment, never free-green
- `invalid` — `USERNAME_INVALID`
- `unknown` — anything else, including a probe channel that cannot be used or a public-channel quota that blocks the check

`account.checkUsername` evidence remains accepted for backwards compatibility, but
an account-scope success is **not** enough for green. It is downgraded to
`not_found`/unconfirmed until channel assignment is directly proven.

Legacy evidence services that omit the `claimability` object remain supported, but
two `not_found` observations still do **not** become green.

## .com strict green

The existing .com flow remains fail-closed:

1. Verisign RDAP proves an existing registration (`taken`) or absence from RDAP.
2. If RDAP returns 404, NameMachine calls Name.com `domains:checkAvailability`
   with `purchaseType=registration` when `NAMECOM_USERNAME` and
   `NAMECOM_API_TOKEN` are configured.
3. A normal non-premium registration offer becomes `claimable`.
4. Premium/paid inventory becomes `purchasable`, not free-green.
5. Missing credentials, auth errors, rate limits, or malformed registrar responses
   remain `not_found`/`unknown`/`rate_limited` and never become green.

## Production acceptance checks

Before calling R1 complete in production, verify at least:

- Telegram invalid username → `invalid`
- Telegram known occupied username → `taken`
- Telegram Fragment-only username → `purchasable`
- Telegram genuinely assignable channel username → `claimable`
- Telegram account-only availability evidence → never strict green
- .com registered domain → `taken`
- .com standard registration available → `claimable`
- .com premium registration → `purchasable`
- no `not_found` result appears as strict green

Do not put Telegram session strings, Telegram API secrets, probe-channel access
hashes, or Name.com API credentials in source control, logs, screenshots, or
client-visible diagnostics.
