#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$project_root/build/ntrig-spi"
cp "$project_root/port/ntrig-spi/"* "$project_root/build/ntrig-spi/"
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$project_root:/work" \
  thinkpad-nura-build:2026-10-05 make -C /work/sources/linux-nura \
  O=/work/build/linux-nura M=/work/build/ntrig-spi ARCH=arm LLVM=1 modules
