#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
profile=${1:-reference}
case "$profile" in
    reference) build_tag=mesa-grate; patch_dir=port/mesa ;;
    candidate) build_tag=mesa-grate-candidate; patch_dir=port/mesa/candidate ;;
    *) echo 'Usage: build_mesa_grate.sh [reference|candidate]' >&2; exit 1 ;;
esac
mesa_commit=$(python3 -c 'import json,sys; print(json.load(open("sources.lock.json"))[sys.argv[1]]["commit"])' "$build_tag")
mesa_url=$(python3 -c 'import json,sys; print(json.load(open("sources.lock.json"))[sys.argv[1]]["url"])' "$build_tag")
mesa_source="sources/mesa-grate-${mesa_commit:0:12}"
if [[ ! -e "$mesa_source/.git" ]]; then
    git init "$mesa_source"
    git -C "$mesa_source" remote add origin "$mesa_url"
    git -C "$mesa_source" fetch --depth 1 origin "$mesa_commit"
    git -C "$mesa_source" checkout --detach FETCH_HEAD
fi
[[ $(git -C "$mesa_source" rev-parse HEAD) == "$mesa_commit" ]]
shopt -s nullglob
for patch in "$project_root"/"$patch_dir"/*.patch; do
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
    -e "MESA_BUILD_TAG=$build_tag" -e "MESA_PATCH_DIR=/work/$patch_dir" \
    thinkpad-mesa-build:2026-10-05 sh -ec '
    setup_extra=
    build_dir=/work/build/$MESA_BUILD_TAG
    install_dir=/work/build/$MESA_BUILD_TAG-install
    legacy_options=
    if grep -q "gallium-vdpau" "$MESA_SOURCE/meson.options"; then
        legacy_options=-Dgallium-vdpau=disabled
    fi
    cross_hash=$({ sha256sum /work/port/mesa/armv7-musl.ini; printf "%s\n" "$MESA_SOURCE" "$MESA_PREFIX"; } | sha256sum | cut -d " " -f 1)
    if [ -f "$build_dir/meson-private/coredata.dat" ]; then
        setup_extra=--reconfigure
        if [ "$cross_hash" != "$(cat "$build_dir-cross.sha256" 2>/dev/null || true)" ]; then
            setup_extra=--wipe
        fi
    fi
    meson setup $setup_extra "$build_dir" "$MESA_SOURCE" \
        --cross-file /work/port/mesa/armv7-musl.ini \
        --prefix "$MESA_PREFIX" --libdir lib --buildtype release \
        --wrap-mode nofallback -Dgallium-drivers=grate,softpipe -Dvulkan-drivers= \
        -Dllvm=disabled -Ddraw-use-llvm=false -Dplatforms=x11,wayland -Dglx=dri \
        -Degl=enabled -Dgbm=enabled -Dglvnd=disabled -Dgallium-va=disabled \
        -Dvalgrind=disabled -Dbuild-tests=false $legacy_options -Dlegacy-x11=dri2
    printf "%s\n" "$cross_hash" > "$build_dir-cross.sha256"
    meson compile -C "$build_dir" -j 8
    DESTDIR="$install_dir" meson install -C "$build_dir" --no-rebuild --strip
    prefix=$install_dir$MESA_PREFIX
    clang --target=armv7-alpine-linux-musleabihf --sysroot=/work/build/mesa-sysroot \
        --gcc-toolchain=/work/build/mesa-sysroot/usr -fuse-ld=lld \
        -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard -O2 -Wall -Wextra \
        -I"$prefix/include" /work/port/mesa/gpu-pixel-check.c \
        -L"$prefix/lib" -Wl,-rpath-link,"$prefix/lib" -lEGL -lGLESv2 -lgbm -lX11 \
        -o /work/build/$MESA_BUILD_TAG-gpu-pixel-check
    if [ "$MESA_BUILD_TAG" = mesa-grate ]; then
        cp /work/build/$MESA_BUILD_TAG-gpu-pixel-check /work/build/gpu-pixel-check
    fi
    if [ "$MESA_BUILD_TAG" = mesa-grate-candidate ]; then
        mkdir -p "$prefix/bin"
        isolation_source=$build_dir/fptest-sfu-isolation.c
        cp "$MESA_SOURCE/src/gallium/drivers/grate/tests/fptest.c" "$isolation_source"
        patch "$isolation_source" < /work/port/mesa/tests/sfu-isolation.patch
        for probe in fptest vstest quadtest blendtest fptest-sfu-isolation; do
            probe_source=$MESA_SOURCE/src/gallium/drivers/grate/tests/$probe.c
            if [ "$probe" = fptest-sfu-isolation ]; then
                probe_source=$isolation_source
            fi
            clang --target=armv7-alpine-linux-musleabihf --sysroot=/work/build/mesa-sysroot \
                --gcc-toolchain=/work/build/mesa-sysroot/usr -fuse-ld=lld \
                -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard -O2 -Wall -Wextra \
                -I"$prefix/include" "$probe_source" \
                -L"$prefix/lib" -Wl,-rpath-link,"$prefix/lib" -lEGL -lGLESv2 \
                -o "$prefix/bin/$probe"
        done
    fi
    python3 - "$MESA_SOURCE" "$prefix" << "PY"
import hashlib, json, os, subprocess, sys
from pathlib import Path
source, prefix = map(Path, sys.argv[1:])
metadata = {
    "source_commit": os.environ["MESA_COMMIT"],
    "source_diff_sha256": os.environ["MESA_DIFF_SHA256"],
    "patches": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(os.environ["MESA_PATCH_DIR"]).glob("*.patch"))},
    "test_patches": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path("/work/port/mesa/tests").glob("*.patch"))} if os.environ["MESA_BUILD_TAG"] == "mesa-grate-candidate" else {},
    "builder_sha256": hashlib.sha256(Path("/work/scripts/build_mesa_grate.sh").read_bytes()).hexdigest(),
    "pixel_probe_sha256": hashlib.sha256(Path("/work/port/mesa/gpu-pixel-check.c").read_bytes()).hexdigest(),
    "cross_file_sha256": hashlib.sha256(Path("/work/port/mesa/armv7-musl.ini").read_bytes()).hexdigest(),
    "compiler": subprocess.check_output(["clang", "--version"], text=True).splitlines()[0],
    "drivers": ["grate", "softpipe"], "llvm": False, "x11_dri2": True,
}
(prefix / "share").mkdir(exist_ok=True)
(prefix / "share/indigo-build.json").write_text(json.dumps(metadata, indent=2) + "\n")
PY
    tar -C "$install_dir" -czf /work/build/$MESA_BUILD_TAG-armv7.tar.gz .$MESA_PREFIX
'
