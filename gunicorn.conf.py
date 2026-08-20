import os


def _bounded_int(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
# Keep one process by default so process-local rate limits/semaphores remain a
# single source of truth, but give that process multiple request threads.  A
# sync worker is unsafe here because an NDJSON generation stream can stay open
# for tens of seconds and otherwise blocks /health, session sync and the UI.
workers = _bounded_int("WEB_CONCURRENCY", 1, 1, 4)
worker_class = "gthread"
threads = _bounded_int("GUNICORN_THREADS", 4, 2, 16)
timeout = _bounded_int("GUNICORN_TIMEOUT", 180, 30, 600)
graceful_timeout = _bounded_int("GUNICORN_GRACEFUL_TIMEOUT", 30, 5, 120)
keepalive = _bounded_int("GUNICORN_KEEPALIVE", 5, 1, 30)
accesslog = "-"
errorlog = "-"
capture_output = True
