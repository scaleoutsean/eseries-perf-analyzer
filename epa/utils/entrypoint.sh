#!/bin/sh
set -eu

INFLUX_HOST=localhost
INFLUX_PORT=8086

if [ -f /etc/influxdb/influxdb.conf ]; then
  BA=$(grep -E '^[[:space:]]*bind-address' /etc/influxdb/influxdb.conf 2>/dev/null | head -n1 || true)
  if [ -n "$BA" ]; then
    VAL=$(echo "$BA" | sed -E 's/.*= *"(.*)".*/\1/; s/.*= *([^\"].*)/\\1/')
    case "$VAL" in
      :*) INFLUX_PORT=${VAL#*:} ;;
      *:*) INFLUX_HOST=${VAL%%:*}; INFLUX_PORT=${VAL##*:} ;;
      *) INFLUX_HOST=$VAL ;;
    esac
  fi
fi

export INFLUX_HOST INFLUX_PORT
echo "[utils] Entrypoint: INFLUX_HOST=${INFLUX_HOST} INFLUX_PORT=${INFLUX_PORT}"
exec "$@"