#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
mesa_commit=$(python3 -c 'import json; print(json.load(open("sources.lock.json"))["mesa-grate"]["commit"])')
mesa_url=$(python3 -c 'import json; print(json.load(open("sources.lock.json"))["mesa-grate"]["url"])')
mesa_source="sources/mesa-grate-${mesa_commit:0:12}"
if [[ ! -e "$mesa_source/.git" ]]; then
    git init "$mesa_source"
    git -C "$mesa_source" remote add origin "$mesa_url"
    git -C "$mesa_source" fetch --depth 1 origin "$mesa_commit"
    git -C "$mesa_source" checkout --detach FETCH_HEAD
fi
[[ $(git -C "$mesa_source" rev-parse HEAD) == "$mesa_commit" ]]
for patch in "$project_root"/port/mesa/*.patch; do
    if git -C "$mesa_source" apply --check "$patch" 2>/dev/null; then
        git -C "$mesa_source" apply "$patch"
    else
        git -C "$mesa_source" apply --reverse --check "$patch"
    fi
done
mesa_diff_sha256=$(git -C "$mesa_source" diff | sha256sum | cut -d ' ' -f 1)
docker build -t thinkpad-mesa-build:2026-10-05 -f tools/Dockerfile.mesa .
# A separate ARM musl sysroot keeps build dependencies off the running tablet.
docker run --rm -v "$project_root:/work" thinkpad-mesa-build:2026-10-05 sh -ec '
    mkdir -p /work/build/mesa-sysroot/etc/apk/keys
    cp /usr/share/apk/keys/armv7/* /work/build/mesa-sysroot/etc/apk/keys/
    apk --root /work/build/mesa-sysroot --arch armv7 --initdb --no-scripts \
        --repository https://dl-cdn.alpinelinux.org/alpine/edge/main \
        --repository https://dl-cdn.alpinelinux.org/alpine/edge/community \
        add musl-dev gcc g++ linux-headers libdrm-dev expat-dev libx11-dev \
        libxext-dev libxdamage-dev libxfixes-dev libxxf86vm-dev libxrandr-dev \
        libxcb-dev libxshmfence-dev zlib-dev zstd-dev wayland-dev wayland-protocols
'
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$project_root:/work" \
    -e "MESA_SOURCE=/work/$mesa_source" -e "MESA_PREFIX=/opt/indigo-mesa/${mesa_commit:0:12}" \
    -e "MESA_COMMIT=$mesa_commit" -e "MESA_DIFF_SHA256=$mesa_diff_sha256" \
    thinkpad-mesa-build:2026-10-05 sh -ec '
    setup_extra=
    cross_hash=$({ sha256sum /work/port/mesa/armv7-musl.ini; printf "%s\n" "$MESA_SOURCE" "$MESA_PREFIX"; } | sha256sum | cut -d " " -f 1)
    if [ -f /work/build/mesa-grate/meson-private/coredata.dat ]; then
        setup_extra=--reconfigure
        if [ "$cross_hash" != "$(cat /work/build/mesa-grate-cross.sha256 2>/dev/null || true)" ]; then
            setup_extra=--wipe
        fi
    fi
    meson setup $setup_extra /work/build/mesa-grate "$MESA_SOURCE" \
        --cross-file /work/port/mesa/armv7-musl.ini \
        --prefix "$MESA_PREFIX" --libdir lib --buildtype release \
        --wrap-mode nofallback -Dgallium-drivers=grate,softpipe -Dvulkan-drivers= \
        -Dllvm=disabled -Ddraw-use-llvm=false -Dplatforms=x11,wayland -Dglx=dri \
        -Degl=enabled -Dgbm=enabled -Dglvnd=disabled -Dgallium-va=disabled \
        -Dvalgrind=disabled -Dbuild-tests=false -Dgallium-vdpau=disabled -Dlegacy-x11=dri2
    printf "%s\n" "$cross_hash" > /work/build/mesa-grate-cross.sha256
    meson compile -C /work/build/mesa-grate -j 8
    DESTDIR=/work/build/mesa-grate-install meson install -C /work/build/mesa-grate --no-rebuild --strip
    prefix=/work/build/mesa-grate-install$MESA_PREFIX
    clang --target=armv7-alpine-linux-musleabihf --sysroot=/work/build/mesa-sysroot \
        --gcc-toolchain=/work/build/mesa-sysroot/usr -fuse-ld=lld \
        -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard -O2 -Wall -Wextra \
        -I"$prefix/include" /work/port/mesa/gpu-pixel-check.c \
        -L"$prefix/lib" -Wl,-rpath-link,"$prefix/lib" -lEGL -lGLESv2 -lgbm -lX11 \
        -o /work/build/gpu-pixel-check
    python3 - "$MESA_SOURCE" "$prefix" << "PY"
import hashlib, json, os, subprocess, sys
from pathlib import Path
source, prefix = map(Path, sys.argv[1:])
metadata = {
    "source_commit": os.environ["MESA_COMMIT"],
    "source_diff_sha256": os.environ["MESA_DIFF_SHA256"],
    "patches": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path("/work/port/mesa").glob("*.patch"))},
    "cross_file_sha256": hashlib.sha256(Path("/work/port/mesa/armv7-musl.ini").read_bytes()).hexdigest(),
    "compiler": subprocess.check_output(["clang", "--version"], text=True).splitlines()[0],
    "drivers": ["grate", "softpipe"], "llvm": False, "x11_dri2": True,
}
(prefix / "share").mkdir(exist_ok=True)
(prefix / "share/indigo-build.json").write_text(json.dumps(metadata, indent=2) + "\n")
PY
    tar -C /work/build/mesa-grate-install -czf /work/build/mesa-grate-armv7.tar.gz .$MESA_PREFIX
'
