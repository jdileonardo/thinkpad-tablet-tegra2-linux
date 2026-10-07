#!/bin/sh
set -eu
trap 'code=$?; echo INSTALL_RUNNER_EXIT=$code' EXIT
while ! grep -q '^STAGE_EXIT=' /run/internal-stage.log; do sleep 10; done
grep -qx STAGE_EXIT=0 /run/internal-stage.log
grep -qx STAGE_READY /run/internal-stage.log
rc-service lightdm stop
sync
sh /tmp/user-area-install.sh --apply
