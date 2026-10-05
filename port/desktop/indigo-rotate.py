#!/usr/bin/env python3
"""Rotate the Indigo X11 display and input together; optionally follow its KXTF9."""
import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROTATIONS = ('normal', 'left', 'inverted', 'right')
MATRICES = {
    'normal': (1, 0, 0, 0, 1, 0, 0, 0, 1),
    'left': (0, -1, 1, 1, 0, 0, 0, 0, 1),
    'inverted': (-1, 0, 1, 0, -1, 1, 0, 0, 1),
    'right': (0, 1, 0, -1, 0, 1, 0, 0, 1),
}
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'indigo-tablet/rotation.json'


def command(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=15)


def settings():
    if CONFIG.exists():
        return json.loads(CONFIG.read_text())
    return {'automatic': False, 'rotation': 'normal', 'reference': None, 'reference_rotation': 'normal'}


def save(config):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG.with_suffix('.tmp')
    temporary.write_text(json.dumps(config, indent=2) + '\n')
    temporary.replace(CONFIG)


def display():
    for line in command('xrandr', '--query').splitlines():
        match = re.match(r'^(\S+) connected(?: primary)? (\d+x\d+\+\d+\+\d+)(.*)', line)
        if match and not match[1].startswith('HDMI'):
            words = match[3].split('(', 1)[0].split()
            rotation = words[0] if words and words[0] in ROTATIONS else 'normal'
            return match[1], rotation
    raise RuntimeError('No active built-in Indigo display found')


def inputs():
    result = []
    for line in command('xinput', 'list', '--short').splitlines():
        if 'N-Trig Indigo ' in line and 'pointer' in line:
            match = re.search(r'id=(\d+)', line)
            if match:
                result.append(match[1])
    if not result:
        raise RuntimeError('No Indigo touch/pen input devices found')
    return result


def get_matrix(device):
    for line in command('xinput', 'list-props', device).splitlines():
        if 'Coordinate Transformation Matrix (' in line:
            return tuple(float(value.strip()) for value in line.split(':', 1)[1].split(','))
    raise RuntimeError(f'Input {device} has no coordinate transformation matrix')


def set_matrix(device, matrix):
    command('xinput', 'set-prop', device, 'Coordinate Transformation Matrix', *map(str, matrix))


def rotate(rotation):
    output, previous = display()
    devices = inputs()
    old = {device: get_matrix(device) for device in devices}
    try:
        command('xrandr', '--output', output, '--rotate', rotation)
        for device in devices:
            set_matrix(device, MATRICES[rotation])
        if display()[1] != rotation:
            raise RuntimeError('Display did not accept rotation')
        for device in devices:
            if get_matrix(device) != MATRICES[rotation]:
                raise RuntimeError(f'Input {device} did not accept rotation')
    except Exception:
        command('xrandr', '--output', output, '--rotate', previous)
        for device, matrix in old.items():
            set_matrix(device, matrix)
        raise
    print(f'rotation={rotation}; synchronized {len(devices)} touch/pen inputs', flush=True)


def sensor():
    for path in Path('/sys/bus/iio/devices').glob('iio:device*'):
        if (path / 'name').read_text().strip() == 'kxtf9':
            return path
    raise RuntimeError('KXTF9 accelerometer is not available')


def read_gravity():
    path = sensor()
    scale = float((path / 'in_accel_scale').read_text())
    return tuple(float((path / f'in_accel_{axis}_raw').read_text()) * scale for axis in 'xyz')


def gravity_direction(vector):
    x, y, z = vector
    # Keep the last orientation when flat, tilted too far, or near a diagonal.
    if abs(z) > 7.5 or max(abs(x), abs(y)) < 5.0 or abs(abs(x) - abs(y)) < 2.0:
        return None
    if abs(y) > abs(x):
        return 0 if y < 0 else 2
    return 1 if x > 0 else 3


def sensor_rotation(direction, config):
    if direction is None or config.get('reference') is None:
        return None
    base = ROTATIONS.index(config['reference_rotation'])
    # Raw gravity and Xrandr rotation run in opposite directions. Physical
    # quarter-turn tests on Indigo confirmed the old sign inverted landscape.
    return ROTATIONS[(base - direction + config['reference']) % 4]


def notify(message):
    try:
        subprocess.run(['notify-send', 'Tablet rotation', message], timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def watch():
    # The lock is separate from rotation.json so atomic state replacement is safe.
    lock = CONFIG.with_suffix('.watch.lock')
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('w') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        previous_candidate, repetitions = None, 0
        known_inputs = ()
        while True:
            try:
                config = settings()
                candidate = sensor_rotation(gravity_direction(read_gravity()), config) if config['automatic'] else None
                repetitions = repetitions + 1 if candidate == previous_candidate else 1
                previous_candidate = candidate
                if candidate and repetitions >= 3 and display()[1] != candidate:
                    rotate(candidate)
                current_inputs = tuple(inputs())
                if current_inputs != known_inputs:
                    # libinput creates pen tool pointers when a powered pen first
                    # enters proximity; align those newly created tools as well.
                    rotate(display()[1])
                    known_inputs = current_inputs
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                print(f'rotation watcher: {error}', file=sys.stderr, flush=True)
                time.sleep(2)
            time.sleep(0.3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=(*ROTATIONS, 'cycle', 'auto', 'lock', 'toggle', 'calibrate', 'watch', 'status', 'restore'))
    args = parser.parse_args()
    if args.action == 'watch':
        watch()
        return
    config = settings()
    if args.action == 'status':
        print(json.dumps({'settings': config, 'display': display(), 'gravity': read_gravity()}, indent=2))
        return
    if args.action == 'calibrate':
        direction = gravity_direction(read_gravity())
        if direction is None:
            raise RuntimeError('Hold the tablet upright for rotation calibration')
        config['reference'] = direction
        config['reference_rotation'] = display()[1]
        config['rotation'] = display()[1]
        save(config)
        print('Recorded current upright display and gravity reference')
        return
    if args.action in ROTATIONS or args.action == 'cycle':
        rotation = args.action if args.action in ROTATIONS else ROTATIONS[(ROTATIONS.index(display()[1]) + 1) % 4]
        rotate(rotation)
        config.update(rotation=rotation, automatic=False)
    elif args.action == 'restore':
        rotate(config['rotation'])
        return
    else:
        automatic = args.action == 'auto' or (args.action == 'toggle' and not config['automatic'])
        if args.action == 'toggle' and config.get('reference') is None:
            rotation = ROTATIONS[(ROTATIONS.index(display()[1]) + 1) % 4]
            rotate(rotation)
            config.update(rotation=rotation, automatic=False)
            save(config)
            notify('Display rotated')
            return
        if automatic and config.get('reference') is None:
            raise RuntimeError('Calibrate the upright display before enabling automatic rotation')
        if automatic:
            target = sensor_rotation(gravity_direction(read_gravity()), config)
            if target:
                rotate(target)
            notify('Automatic rotation enabled')
        else:
            config['rotation'] = display()[1]
            notify('Rotation locked')
        config['automatic'] = automatic
    save(config)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        notify(str(error))
        raise SystemExit(1)
