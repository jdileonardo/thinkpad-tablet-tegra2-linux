#!/usr/bin/env python3
"""Bounded GTK3 calendar rendering probe; run as the XFCE session user.

No account access, event fetching, autostart change or desktop configuration.
The window closes automatically. A draw callback is not a pixel validation.
"""
import argparse
import json
import os
import time
from datetime import date
from pathlib import Path

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gdk, GdkX11, GLib, Gtk  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() == 0 or not 10 <= args.seconds <= 3600:
        parser.error('Run as the desktop user for 10..3600 seconds')
    output = args.output.resolve()
    if not any(output.is_relative_to(Path(base)) for base in ('/tmp', '/run')):
        parser.error('Output must be under /tmp or /run')
    if output.exists():
        parser.error('Use a fresh output path')
    today = date.today()
    state = {'started_monotonic': time.monotonic(), 'draw_callbacks': 0,
             'date': today.isoformat(), 'window_id': None,
             'gtk_version': [Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version()],
             'pixel_validation': False, 'remote_calendar_integration': False}
    window = Gtk.Window(title='Calendar preview')
    window.set_default_size(620, 680)
    window.set_position(Gtk.WindowPosition.CENTER)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    box.set_border_width(24)
    window.add(box)
    title = Gtk.Label(label=today.strftime('%A, %B %d'))
    title.set_name('calendar-heading')
    box.pack_start(title, False, False, 0)
    calendar = Gtk.Calendar()
    calendar.select_month(today.month - 1, today.year)
    calendar.select_day(today.day)
    box.pack_start(calendar, True, True, 0)
    style = Gtk.CssProvider()
    style.load_from_data(b'calendar { font-size: 22px; padding: 12px; } '
                         b'#calendar-heading { font-size: 28px; }')
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), style,
                                            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def drawn(widget, context):
        state['draw_callbacks'] += 1
        if state['window_id'] is None:
            state['window_id'] = GdkX11.X11Window.get_xid(window.get_window())
            print(f"CALENDAR_DRAWN window={state['window_id']}", flush=True)
        return False

    def close(reason):
        if output.exists():
            return False
        state['close_reason'] = reason
        state['elapsed_seconds'] = time.monotonic() - state['started_monotonic']
        state['selected_date'] = list(calendar.get_date())
        state['draw_callback_observed'] = state['draw_callbacks'] > 0
        with output.open('x') as handle:
            json.dump(state, handle, indent=2)
            handle.write('\n')
        print(json.dumps(state), flush=True)
        Gtk.main_quit()
        return False

    window.connect('draw', drawn)
    window.connect('destroy', lambda widget: close('user_closed'))
    window.show_all()
    GLib.timeout_add_seconds(args.seconds, close, 'timer')
    Gtk.main()


if __name__ == '__main__':
    main()
