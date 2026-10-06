#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
builder_image=thinkpad-nura-build:2026-10-05
default_build=ntrig-spi
if [[ -f "$project_root/port/image-inputs.lock.json" ]]; then
  builder_image=$(python3 "$project_root/scripts/pinned_build_container.py" "$builder_image")
  default_build=$(python3 - "$project_root/port/image-inputs.lock.json" <<'PY'
import json
import sys
from pathlib import Path
print(Path(json.loads(Path(sys.argv[1]).read_text()).get(
    'ntrig_module', 'build/ntrig-spi/ntrig_indigo.ko')).parent.name)
PY
  )
fi
build_name=${INDIGO_NTRIG_BUILD:-$default_build}
[[ "$build_name" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Invalid N-Trig build directory' >&2; exit 1; }
mkdir -p "$project_root/build/$build_name"
cp "$project_root/port/ntrig-spi/"* "$project_root/build/$build_name/"
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$project_root:/work" \
  "$builder_image" make -C /work/sources/linux-nura \
  O=/work/build/linux-nura M="/work/build/$build_name" ARCH=arm LLVM=1 modules
