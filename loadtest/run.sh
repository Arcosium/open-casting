#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
label=${1:-after}
[[ "$label" =~ ^[a-zA-Z0-9_-]+$ ]] || exit 2
out="_workspace/load/$(date +%Y%m%d-%H%M%S)-$label"
mkdir -p "$out"
chmod 777 "$out"
uptime > "$out/uptime-before.txt"
trap 'uptime > "$out/uptime-after.txt"' EXIT
set +e
# Only the load generator gets 2 CPUs. The app stays at 0.5 CPU.
docker run --rm --name open-casting-k6 --cpus 2 --memory 512m --network open-casting_default \
  -v "$PWD/loadtest:/scripts:ro" -v "$PWD/$out:/results" \
  grafana/k6:1.6.1 run /scripts/spike.js > "$out/k6.log" 2>&1

status=$?
printf '%s\n' "$status" > "$out/exit-code.txt"
# A threshold breach records the knee; other failures still fail the launcher.
if [[ "$status" != 0 && "$status" != 99 ]]; then exit "$status"; fi
printf 'Results: %s (k6 exit %s)\n' "$out" "$status"
