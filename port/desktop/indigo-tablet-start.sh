#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
state_dir=${XDG_STATE_HOME:-"$HOME/.local/state"}/indigo-tablet
mkdir -p "$state_dir"
config_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}/indigo-tablet
if [ ! -e "$config_dir/buttons-configured" ]; then
    /usr/local/bin/setup-indigo-desktop
fi
/usr/local/bin/indigo-rotate restore >> "$state_dir/rotation.log" 2>&1 || true
exec /usr/local/bin/indigo-rotate watch >> "$state_dir/rotation.log" 2>&1
