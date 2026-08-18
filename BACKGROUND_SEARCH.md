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

The worker writes a non-secret database heartbeat while it is alive. `/api/background-search`
therefore separates `enabled` (durable storage exists) from `ready` (storage exists and at least
one recent worker heartbeat is present). The browser shows the large-search controls only when
the server is ready, unless it is already following an active job.

## Browser delivery

Long searches do not require the browser to keep one HTTP request open. The client polls job
metadata and reads `/api/sessions/<session_id>/candidate-feed` using a monotonically increasing
`received_seq` cursor. Only new candidate rows are transferred. They merge into the normal
session Feed, whose separate navigation layer keeps newest results at the top and renders a
bounded number of cards.

The built-in target choices are 500, 1,000, 5,000, and 20,000 candidates. Closing the page does
not cancel the job; reopening the same durable browser session can discover an active job and
continue pulling candidate deltas.

## Safety semantics

Background search does not weaken verification semantics. A verifier exception is stored as
`unknown`, never as available. Candidate names are deduplicated against the durable session,
and job creation/candidate-feed reads require the session capability token. The worker never
stores or needs that plaintext token. Worker diagnostics expose heartbeat time/count only, not
worker identifiers or database credentials.

## Deployment status

Merging this code does not by itself mean background search is active in production. Production
requires PostgreSQL to be configured in the canonical Railway project and a separate worker
service/process to be started there. Until both exist, the large-search controls stay hidden and
normal foreground streaming search remains the working path.
