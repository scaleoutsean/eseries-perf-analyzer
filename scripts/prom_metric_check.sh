#!/usr/bin/env bash

# Read PROMETHEUS_PORT from environment variable, default to 9080 if not set
PROMETHEUS_PORT="${PROMETHEUS_PORT:-9080}"

curl -s http://localhost:9080/metrics | awk '
/^# TYPE/ {
    if (last != "" && !has_val) print "Missing values for:", last;
    last=$3; has_val=0; next
}
/^[^#]/ { has_val=1 }
END {
    if (last != "" && !has_val) print "Missing values for:", last
}
'
