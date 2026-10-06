#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
export INDIGO_OPENTEGRA_BUILD=${INDIGO_OPENTEGRA_BUILD:-opentegra-dri3}
if [[ ! "$INDIGO_OPENTEGRA_BUILD" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo 'INDIGO_OPENTEGRA_BUILD must be a simple build-directory name' >&2
    exit 1
fi
source_dir=sources/xf86-video-opentegra
source_commit=$(python3 -c 'import json; print(json.load(open("sources.lock.json"))["xf86-video-opentegra"]["commit"])')
source_url=$(python3 -c 'import json; print(json.load(open("sources.lock.json"))["xf86-video-opentegra"]["url"])')
if [[ ! -e "$source_dir/.git" ]]; then
    git init "$source_dir"
    git -C "$source_dir" remote add origin "$source_url"
    git -C "$source_dir" fetch --depth 1 origin "$source_commit"
    git -C "$source_dir" checkout --detach FETCH_HEAD
fi
[[ $(git -C "$source_dir" rev-parse HEAD) == "$source_commit" ]]
python3 scripts/apply_mesa_patches.py "$source_dir" port/opentegra
builder_image=thinkpad-opentegra-build:2026-10-06
export INDIGO_BUILD_INPUTS_FROZEN=0
if [[ -f port/image-inputs.lock.json && ${INDIGO_REFRESH_BUILD_DEPS:-0} != 1 ]]; then
    builder_image=$(python3 scripts/pinned_build_container.py "$builder_image" --sdk)
    export INDIGO_BUILD_INPUTS_FROZEN=1
else
docker build -t "$builder_image" -f tools/Dockerfile.opentegra .
docker run --rm -v "$project_root:/work" thinkpad-opentegra-build:2026-10-06 sh -ec '
    mkdir -p /work/build/mesa-sysroot/etc/apk/keys
    cp /usr/share/apk/keys/armv7/* /work/build/mesa-sysroot/etc/apk/keys/
    apk --root /work/build/mesa-sysroot --arch armv7 --initdb --no-scripts \
        --repository https://dl-cdn.alpinelinux.org/alpine/edge/main \
        --repository https://dl-cdn.alpinelinux.org/alpine/edge/community \
        add musl-dev gcc linux-headers libdrm-dev xorg-server-dev pixman-dev libudev-zero-dev util-macros
'
fi
export INDIGO_BUILD_CONTAINER="$builder_image"
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$project_root:/work" \
    -e INDIGO_OPENTEGRA_BUILD \
    "$builder_image" sh -ec '
    export PKG_CONFIG_SYSROOT_DIR=/work/build/mesa-sysroot
    export PKG_CONFIG_LIBDIR=$PKG_CONFIG_SYSROOT_DIR/usr/lib/pkgconfig:$PKG_CONFIG_SYSROOT_DIR/usr/share/pkgconfig
    export ACLOCAL_PATH=$PKG_CONFIG_SYSROOT_DIR/usr/share/aclocal
    export CC="clang --target=armv7-alpine-linux-musleabihf --sysroot=$PKG_CONFIG_SYSROOT_DIR --gcc-toolchain=$PKG_CONFIG_SYSROOT_DIR/usr -fuse-ld=lld"
    export LD=ld.lld
    export CFLAGS="-O2 -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard"
    build_dir=/work/build/$INDIGO_OPENTEGRA_BUILD
    mkdir -p "$build_dir"
    cd /work/sources/xf86-video-opentegra
    autoreconf -fi
    cd "$build_dir"
    /work/sources/xf86-video-opentegra/configure \
        --host=armv7-alpine-linux-musleabihf --build=x86_64-alpine-linux-musl \
        --prefix=/opt/indigo-xorg/dri3 --disable-valgrind
    rm -f src/opentegra_drv.la
    make -j8
    make DESTDIR="$build_dir-install" install
    sha256sum src/.libs/opentegra_drv.so
    $CC $CFLAGS -Wall -Wextra -Werror /work/port/opentegra/gpu-present-check.c \
        -lEGL -lGLESv2 -lX11 -o /work/build/opentegra-dri3-gpu-present-check
    $CC $CFLAGS -Wall -Wextra -Werror /work/port/opentegra/dri3-share-check.c \
        -lxcb-dri3 -lxcb -o /work/build/opentegra-dri3-share-check
    $CC $CFLAGS -Wall -Wextra -Werror /work/port/opentegra/x-window-capture.c \
        -lX11 -o /work/build/opentegra-x-window-capture
    mkdir -p /work/build/compositor-probes
    wayland-scanner client-header $PKG_CONFIG_SYSROOT_DIR/usr/share/wayland-protocols/stable/xdg-shell/xdg-shell.xml \
        /work/build/compositor-probes/xdg-shell-client-protocol.h
    wayland-scanner private-code $PKG_CONFIG_SYSROOT_DIR/usr/share/wayland-protocols/stable/xdg-shell/xdg-shell.xml \
        /work/build/compositor-probes/xdg-shell-protocol.c
    $CC $CFLAGS -Wall -Wextra -Werror -I/work/build/compositor-probes \
        /work/port/opentegra/wayland-compositor-check.c /work/build/compositor-probes/xdg-shell-protocol.c \
        -lwayland-client -lX11 -o /work/build/opentegra-wayland-compositor-check
'
python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import subprocess

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

source = 'sources/xf86-video-opentegra'
build_dir = Path('build') / os.environ['INDIGO_OPENTEGRA_BUILD']
metadata = {
    'source_commit': subprocess.check_output(['git', '-C', source, 'rev-parse', 'HEAD'], text=True).strip(),
    'source_diff_sha256': hashlib.sha256(subprocess.check_output(['git', '-C', source, 'diff', '--binary', 'HEAD'])).hexdigest(),
    'patches': {p.name: sha(p) for p in sorted(Path('port/opentegra').glob('*.patch'))},
    'module_sha256': sha(build_dir / 'src/.libs/opentegra_drv.so'),
    'probe_sha256': sha('build/opentegra-dri3-gpu-present-check'),
    'probe_source_sha256': sha('port/opentegra/gpu-present-check.c'),
    'sharing_probe_sha256': sha('build/opentegra-dri3-share-check'),
    'sharing_probe_source_sha256': sha('port/opentegra/dri3-share-check.c'),
    'capture_probe_sha256': sha('build/opentegra-x-window-capture'),
    'capture_probe_source_sha256': sha('port/opentegra/x-window-capture.c'),
    'compositor_probe_sha256': sha('build/opentegra-wayland-compositor-check'),
    'compositor_probe_source_sha256': sha('port/opentegra/wayland-compositor-check.c'),
    'xdg_shell_protocol_sha256': sha('build/mesa-sysroot/usr/share/wayland-protocols/stable/xdg-shell/xdg-shell.xml'),
    'builder_sha256': sha('scripts/build_opentegra.sh'),
    'dockerfile_sha256': sha('tools/Dockerfile.opentegra'),
    'sdk_package_database_sha256': sha('build/mesa-sysroot/lib/apk/db/installed'),
    'compiler_flags': '-O2 -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard',
    'dependency_input_lock_sha256': sha('port/image-inputs.lock.json') if Path('port/image-inputs.lock.json').exists() else None,
    'builder_container_id': os.environ['INDIGO_BUILD_CONTAINER'],
    'full_dependency_pinning': os.environ['INDIGO_BUILD_INPUTS_FROZEN'] == '1',
    'dependency_pinning_kind': 'Immutable container and complete SDK binary snapshot',
    'presentation': 'DRI3 v1 linear buffers and Present copy with fake vblank; no page flips',
}
(build_dir.parent / (build_dir.name + '-build.json')).write_text(json.dumps(metadata, indent=2) + '\n')
PY
