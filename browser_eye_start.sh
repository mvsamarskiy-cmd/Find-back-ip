#!/bin/sh
set -eu

if [ "${TOR_SEARCH_ENABLED:-1}" = "1" ]; then
  echo "[browser-eye-tor] preparing local Tor SOCKS transport"
  install -d -m 0700 -o debian-tor -g debian-tor /tmp/tor-data

  TOR_ARGS="-f /dev/null --User debian-tor --SocksPort 127.0.0.1:9050 --DataDirectory /tmp/tor-data --Log notice stdout"
  echo "[browser-eye-tor] verifying Tor configuration"
  # shellcheck disable=SC2086
  tor --verify-config $TOR_ARGS

  echo "[browser-eye-tor] starting Tor daemon"
  # shellcheck disable=SC2086
  tor $TOR_ARGS &
  TOR_PID=$!
  echo "[browser-eye-tor] pid=${TOR_PID}"

  i=0
  while [ "$i" -lt 80 ]; do
    if ! kill -0 "$TOR_PID" 2>/dev/null; then
      echo "[browser-eye-tor] Tor exited before SOCKS became ready" >&2
      wait "$TOR_PID" || true
      break
    fi
    if python -c 'import socket; s=socket.create_connection(("127.0.0.1",9050),0.2); s.close()' 2>/dev/null; then
      echo "[browser-eye-tor] SOCKS5 listener ready on 127.0.0.1:9050"
      break
    fi
    i=$((i + 1))
    sleep 0.1
  done
fi

exec gunicorn browser_eye_ready:app --bind 0.0.0.0:8080 --workers 1 --threads 8 --timeout 40
