#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
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
docker build -t thinkpad-opentegra-build:2026-10-06 -f tools/Dockerfile.opentegra .
docker run --rm -v "$project_root:/work" thinkpad-opentegra-build:2026-10-06 sh -ec '
    mkdir -p /work/build/mesa-sysroot/etc/apk/keys
    cp /usr/share/apk/keys/armv7/* /work/build/mesa-sysroot/etc/apk/keys/
    apk --root /work/build/mesa-sysroot --arch armv7 --initdb --no-scripts \
        --repository https://dl-cdn.alpinelinux.org/alpine/edge/main \
        --repository https://dl-cdn.alpinelinux.org/alpine/edge/community \
        add musl-dev gcc linux-headers libdrm-dev xorg-server-dev pixman-dev libudev-zero-dev util-macros
'
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$project_root:/work" \
    thinkpad-opentegra-build:2026-10-06 sh -ec '
    export PKG_CONFIG_SYSROOT_DIR=/work/build/mesa-sysroot
    export PKG_CONFIG_LIBDIR=$PKG_CONFIG_SYSROOT_DIR/usr/lib/pkgconfig:$PKG_CONFIG_SYSROOT_DIR/usr/share/pkgconfig
    export ACLOCAL_PATH=$PKG_CONFIG_SYSROOT_DIR/usr/share/aclocal
    export CC="clang --target=armv7-alpine-linux-musleabihf --sysroot=$PKG_CONFIG_SYSROOT_DIR --gcc-toolchain=$PKG_CONFIG_SYSROOT_DIR/usr -fuse-ld=lld"
    export LD=ld.lld
    export CFLAGS="-O2 -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard"
    mkdir -p /work/build/opentegra-dri3
    cd /work/sources/xf86-video-opentegra
    autoreconf -fi
    cd /work/build/opentegra-dri3
    /work/sources/xf86-video-opentegra/configure \
        --host=armv7-alpine-linux-musleabihf --build=x86_64-alpine-linux-musl \
        --prefix=/opt/indigo-xorg/dri3 --disable-valgrind
    rm -f src/opentegra_drv.la
    make -j8
    make DESTDIR=/work/build/opentegra-dri3-install install
    sha256sum src/.libs/opentegra_drv.so
    $CC $CFLAGS -Wall -Wextra -Werror /work/port/opentegra/gpu-present-check.c \
        -lEGL -lGLESv2 -lX11 -o /work/build/opentegra-dri3-gpu-present-check
'
python3 - <<'PY'
import hashlib
import json
from pathlib import Path
import subprocess

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

source = 'sources/xf86-video-opentegra'
metadata = {
    'source_commit': subprocess.check_output(['git', '-C', source, 'rev-parse', 'HEAD'], text=True).strip(),
    'source_diff_sha256': hashlib.sha256(subprocess.check_output(['git', '-C', source, 'diff', '--binary', 'HEAD'])).hexdigest(),
    'patches': {p.name: sha(p) for p in sorted(Path('port/opentegra').glob('*.patch'))},
    'module_sha256': sha('build/opentegra-dri3/src/.libs/opentegra_drv.so'),
    'probe_sha256': sha('build/opentegra-dri3-gpu-present-check'),
    'probe_source_sha256': sha('port/opentegra/gpu-present-check.c'),
    'builder_sha256': sha('scripts/build_opentegra.sh'),
    'dockerfile_sha256': sha('tools/Dockerfile.opentegra'),
    'sdk_package_database_sha256': sha('build/mesa-sysroot/lib/apk/db/installed'),
    'compiler_flags': '-O2 -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard',
    'full_dependency_pinning': False,
    'presentation': 'DRI3 v1 linear buffers and Present copy with fake vblank; no page flips',
}
Path('build/opentegra-dri3-build.json').write_text(json.dumps(metadata, indent=2) + '\n')
PY
