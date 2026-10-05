#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
if [ "$(id -u)" -eq 0 ]; then
    echo 'Run this script as the XFCE user inside their session.' >&2
    exit 1
fi
config_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}/indigo-tablet
mkdir -p "$config_dir"
old_shortcuts=${XDG_CONFIG_HOME:-"$HOME/.config"}/xfce4/xfconf/xfce-perchannel-xml/xfce4-keyboard-shortcuts.xml
if [ -f "$old_shortcuts" ] && [ ! -e "$config_dir/keyboard-before-indigo.xml" ]; then
    cp "$old_shortcuts" "$config_dir/keyboard-before-indigo.xml"
fi
shortcut() {
    property=/commands/custom/$1
    action="/usr/local/bin/indigo-buttons $2"
    if xfconf-query -c xfce4-keyboard-shortcuts -p "$property" >/dev/null 2>&1; then
        xfconf-query -c xfce4-keyboard-shortcuts -p "$property" -s "$action"
    else
        xfconf-query -c xfce4-keyboard-shortcuts -p "$property" -n -t string -s "$action"
    fi
}
shortcut HomePage home
shortcut XF86Back back
shortcut XF86WWW browser
shortcut XF86RotateWindows rotate
boolean_setting() {
    channel=$1
    property=$2
    if xfconf-query -c "$channel" -p "$property" >/dev/null 2>&1; then
        xfconf-query -c "$channel" -p "$property" -s false
    else
        xfconf-query -c "$channel" -p "$property" -n -t bool -s false
    fi
}
# User-requested convenience settings for this development tablet. LightDM
# already autologins; waking the display and resuming must not ask for a password.
boolean_setting xfce4-screensaver /lock/enabled
boolean_setting xfce4-power-manager /xfce4-power-manager/lock-screen-suspend-hibernate
touch "$config_dir/buttons-configured"
echo 'Configured tablet buttons and disabled desktop password locks'
