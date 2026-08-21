#!/bin/sh
set -eu

if [ "${TOR_SEARCH_ENABLED:-1}" = "1" ]; then
  mkdir -p /tmp/tor-data
  chown debian-tor:debian-tor /tmp/tor-data
  tor \
    --User debian-tor \
    --SocksPort 127.0.0.1:9050 \
    --DataDirectory /tmp/tor-data \
    --Log "notice stdout" &
fi

exec gunicorn browser_eye_ready:app --bind 0.0.0.0:8080 --workers 1 --threads 8 --timeout 40
