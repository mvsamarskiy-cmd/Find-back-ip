# Telegram claimability setup (NameMachine)

## What you get

| Mode | Result you can show |
|------|---------------------|
| Public only (current production default) | `taken` / `not_found` / `unknown` — **never** free green |
| Isolated MTProto service | true `claimable` via `channels.checkUsername` |

Public absence is **Перспективно**, not **Вільне**.

## Architecture (do not put session on web)

```
[ browser ] → [ web NameMachine ] → HTTPS Bearer → [ telegram-evidence service ] → Telethon MTProto
```

- **web**: only `TELEGRAM_EVIDENCE_URL` + `TELEGRAM_EVIDENCE_TOKEN`
- **telegram-evidence**: owns `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION_STRING`, probe channel, same token

## Step 1 — Telegram API app

1. Open https://my.telegram.org → **API development tools**
2. Create an application
3. Copy **api_id** and **api_hash**

## Step 2 — Probe channel

1. Create a private or public channel with the same account you will log in
2. Keep that channel; NameMachine **never renames or deletes it**
3. Note `@channelusername` **or** numeric channel id

## Step 3 — StringSession (local machine only)

```bash
pip install Telethon==1.44.0
export TELEGRAM_API_ID=...
export TELEGRAM_API_HASH=...
python tools/telegram_make_session.py
```

Paste the printed `TELEGRAM_SESSION_STRING` into Railway secrets. Never commit it.

## Step 4 — Railway service `telegram-evidence`

1. In project **resourceful-stillness** → **New Service** → same GitHub repo  
   (not a new project)
2. Config-as-code: `railway.telegram-evidence.json`  
   Start: `gunicorn telegram_claimability_service:app --config gunicorn.conf.py`
3. Variables on **this service only**:

| Variable | Value |
|----------|--------|
| `TELEGRAM_API_ID` | from my.telegram.org |
| `TELEGRAM_API_HASH` | from my.telegram.org |
| `TELEGRAM_SESSION_STRING` | from step 3 |
| `TELEGRAM_PROBE_CHANNEL` | `@yourprobe` or channel id |
| `TELEGRAM_EVIDENCE_TOKEN` | long random secret (e.g. 32+ bytes hex) |
| `TELEGRAM_CLAIMABILITY_CONCURRENCY` | `2` (default; raise carefully) |

4. Generate public domain for the service
5. Smoke:

```bash
curl -sS "https://<telegram-service>.up.railway.app/health"
# expect: "configured": true

curl -sS -H "Authorization: Bearer $TELEGRAM_EVIDENCE_TOKEN" \
  "https://<telegram-service>.up.railway.app/v1/username/telegram"
# known occupied handle → claimability.status occupied / taken path
```

## Step 5 — Wire public web

On service **web**:

| Variable | Value |
|----------|--------|
| `TELEGRAM_EVIDENCE_URL` | `https://<telegram-service>.up.railway.app` |
| `TELEGRAM_EVIDENCE_TOKEN` | **same** token as evidence service |

Redeploy web. Check non-secret diagnostics:

```bash
curl -sS "https://web-production-04fec.up.railway.app/api/verification/diagnostics" | jq '.providers, .strict_claimability'
```

Look for telegram `can_turn_green: true` under strict claimability resources.

## Step 6 — Acceptance

| Input | Expected |
|-------|----------|
| `ab` (too short) | `invalid` |
| `telegram` | `taken` |
| random free 8–12 char | `claimable` only if MTProto service confirms |
| Fragment collectible | `purchasable`, not free green |

## Safety

- FloodWait is normal under load — keep concurrency low
- Never log session string
- Never put session on the public web service
- 2FA on the Telegram account is fine for user login; store only StringSession after login
