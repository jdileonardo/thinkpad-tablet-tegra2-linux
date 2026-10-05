#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
state_dir=${XDG_STATE_HOME:-"$HOME/.local/state"}/indigo-tablet
mkdir -p "$state_dir"
printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${1:-missing}" >> "$state_dir/buttons.log"
case "${1:-}" in
    home) exec xdotool key --clearmodifiers ctrl+alt+d ;;
    back) exec xdotool key --clearmodifiers alt+Left ;;
    browser) exec exo-open --launch WebBrowser ;;
    rotate) exec /usr/local/bin/indigo-rotate toggle ;;
    *) echo 'usage: indigo-buttons home|back|browser|rotate' >&2; exit 2 ;;
esac
