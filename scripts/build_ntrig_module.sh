#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
builder_image=thinkpad-nura-build:2026-10-05
if [[ -f "$project_root/port/image-inputs.lock.json" ]]; then
  builder_image=$(python3 "$project_root/scripts/pinned_build_container.py" "$builder_image")
fi
mkdir -p "$project_root/build/ntrig-spi"
cp "$project_root/port/ntrig-spi/"* "$project_root/build/ntrig-spi/"
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$project_root:/work" \
  "$builder_image" make -C /work/sources/linux-nura \
  O=/work/build/linux-nura M=/work/build/ntrig-spi ARCH=arm LLVM=1 modules
