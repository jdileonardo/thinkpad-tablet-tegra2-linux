#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
# Reuse the SDK/compiler from build_opentegra.sh; no package refresh here.
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$project_root:/work" \
    thinkpad-opentegra-build:2026-10-06 sh -ec '
    export PKG_CONFIG_SYSROOT_DIR=/work/build/mesa-sysroot
    export PKG_CONFIG_LIBDIR=$PKG_CONFIG_SYSROOT_DIR/usr/lib/pkgconfig
    clang --target=armv7-alpine-linux-musleabihf --sysroot=$PKG_CONFIG_SYSROOT_DIR \
        --gcc-toolchain=$PKG_CONFIG_SYSROOT_DIR/usr -fuse-ld=lld \
        -O2 -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard -Wall -Wextra -Werror \
        -I$PKG_CONFIG_SYSROOT_DIR/usr/include/libdrm /work/port/opentegra/graphics-stack-check.c \
        -lEGL -lGLESv2 -lgbm -ldrm -o /work/build/graphics-stack-check
    sha256sum /work/build/graphics-stack-check
    clang --target=armv7-alpine-linux-musleabihf --sysroot=$PKG_CONFIG_SYSROOT_DIR \
        --gcc-toolchain=$PKG_CONFIG_SYSROOT_DIR/usr -fuse-ld=lld \
        -O2 -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard -Wall -Wextra -Werror \
        -I/work/build/compositor-probes /work/port/opentegra/wayland-egl-check.c \
        /work/build/compositor-probes/xdg-shell-protocol.c \
        -lwayland-egl -lwayland-client -lEGL -lGLESv2 -o /work/build/wayland-egl-check
    sha256sum /work/build/wayland-egl-check
    '
python3 - <<'PY'
import hashlib
import json
from pathlib import Path
import subprocess

paths = (
    'port/opentegra/graphics-stack-check.c', 'port/opentegra/wayland-egl-check.c',
    'port/opentegra/qt-wayland-scenegraph-check.qml',
    'scripts/build_graphics_stack_probes.sh', 'scripts/tablet_native_weston_trial.py',
    'build/graphics-stack-check', 'build/wayland-egl-check',
    'build/compositor-probes/xdg-shell-protocol.c',
    'build/compositor-probes/xdg-shell-client-protocol.h',
    'build/mesa-sysroot/lib/apk/db/installed',
)
metadata = {
    'sha256': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths},
    'compiler_flags': '-O2 -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard -Wall -Wextra -Werror',
    'builder_image_id': subprocess.check_output([
        'docker', 'image', 'inspect', '--format', '{{.Id}}',
        'thinkpad-opentegra-build:2026-10-06'], text=True).strip(),
    'full_dependency_pinning': False,
}
Path('build/graphics-stack-probes.json').write_text(json.dumps(metadata, indent=2) + '\n')
PY
