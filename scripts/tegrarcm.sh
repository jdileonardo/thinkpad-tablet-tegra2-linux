#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# Container dependencies and USB access only; no privileged container is needed.
docker run --rm --network none \
  --mount type=bind,src=/dev/bus/usb,dst=/dev/bus/usb \
  --device-cgroup-rule='c 189:* rwm' \
  -v "$project_root:/work" \
  thinkpad-port-build:2026-10-05 \
  /work/sources/tegrarcm/src/tegrarcm "$@"
