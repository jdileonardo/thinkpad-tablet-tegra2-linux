#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$project_root/build/ram-test"
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$project_root:/work" thinkpad-port-build:2026-10-05 \
  arm-linux-gnueabihf-gcc -static -Os -s \
  /work/scripts/reboot_into_apx.c -o /work/build/ram-test/reboot-into-apx
