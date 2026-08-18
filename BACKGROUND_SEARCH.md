# Durable background search

NameMachine can queue long searches in the same SQL database used by durable sessions.
The web service only creates, reads, and cancels jobs; it does not run long searches in
request threads.

## Runtime split

- Canonical web process remains `gunicorn telegram_bootstrap:app`.
- A separate trusted worker process runs `python search_worker.py`.
- Both processes must use the same `DATABASE_URL` / `NAMEMACHINE_DATABASE_URL`.
- The worker also needs the same verification/generation provider configuration as the web
  service when those providers are required.

The queue uses database leases and checkpoints after every generated/verified batch. A
worker shutdown returns the current job to `pending`; an unexpected crash can be recovered
once its lease expires. Candidates already written to the session are not discarded.

## Safety semantics

Background search does not weaken verification semantics. A verifier exception is stored as
`unknown`, never as available. Candidate names are deduplicated against the durable session,
and job creation requires the session capability token. The worker never stores or needs that
plaintext token.

## Deployment status

Merging this code does not by itself mean background search is active in production. Production
requires PostgreSQL to be configured in the canonical Railway project and a separate worker
service/process to be started there. Until both exist, the API reports its storage capability but
normal foreground streaming search remains the working path.
