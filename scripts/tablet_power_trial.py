#!/usr/bin/env python3
"""Bounded on-tablet CPU/backlight trial; restore settings on every exit."""
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path


POLICY = Path('/sys/devices/system/cpu/cpufreq/policy0')
BACKLIGHT = Path('/sys/class/backlight/backlight')
TEMP = Path('/sys/class/thermal/thermal_zone0/temp')


def read(path):
    return path.read_text().strip()


def write(path, value):
    path.write_text(str(value) + '\n')


def snapshot(label):
    temperature = int(read(TEMP))
    if temperature >= 45000:
        raise RuntimeError(f'Stopping below passive trip: {temperature} mC')
    clocks = Path('/sys/kernel/debug/clk/clk_summary').read_text()
    regulators = Path('/sys/kernel/debug/regulator/regulator_summary').read_text()
    return {
        'label': label,
        'monotonic_seconds': time.monotonic(),
        'temperature_millicelsius': temperature,
        'frequency_khz': int(read(POLICY / 'scaling_cur_freq')),
        'clock_lines': [line.strip() for line in clocks.splitlines()
                        if re.match(r'\s*(?:pll_x|cclk)\s', line)],
        'cpu_regulator_lines': [line.strip() for line in regulators.splitlines()
                                if 'vdd_sm1,vdd_cpu' in line],
    }


def main():
    result = {'cpu_samples': [], 'brightness_samples': [], 'passed': False}
    original = {name: read(POLICY / name) for name in
                ('scaling_governor', 'scaling_min_freq', 'scaling_max_freq')}
    brightness = read(BACKLIGHT / 'brightness')
    power = read(BACKLIGHT / 'bl_power')
    workers = []
    try:
        frequencies = [int(value) for value in
                       read(POLICY / 'scaling_available_frequencies').split()]
        result['available_frequencies_khz'] = frequencies
        result['original_cpu_settings'] = original
        result['cpu_samples'].append(snapshot('before'))
        write(POLICY / 'scaling_governor', 'userspace')
        # Stay inside the already running 1 GHz ceiling and original limits.
        trials = [frequency for frequency in (216000, 608000, 1000000)
                  if frequency in frequencies and
                  int(original['scaling_min_freq']) <= frequency <=
                  int(original['scaling_max_freq'])]
        if len(trials) != 3:
            raise RuntimeError('Expected stock trial frequencies unavailable')
        for frequency in trials:
            write(POLICY / 'scaling_setspeed', frequency)
            time.sleep(1)
            sample = snapshot(f'userspace-{frequency}')
            if sample['frequency_khz'] != frequency:
                raise RuntimeError(f'Frequency request did not take effect: {sample}')
            result['cpu_samples'].append(sample)
            data = b'\x5a' * (1024 * 1024)
            start = time.monotonic()
            for _ in range(8):
                hashlib.sha256(data).digest()
            sample['sha256_8mib_seconds'] = time.monotonic() - start

        write(POLICY / 'scaling_governor', original['scaling_governor'])
        for index in range(5):
            time.sleep(1)
            result['cpu_samples'].append(snapshot(f'idle-{index}'))
        workload = ('import hashlib,time; d=b"x"*1048576; '
                    'end=time.monotonic()+8\n'
                    'while time.monotonic()<end: hashlib.sha256(d).digest()')
        workers = [subprocess.Popen(['/usr/bin/python3', '-c', workload])
                   for _ in range(2)]
        for index in range(8):
            time.sleep(1)
            result['cpu_samples'].append(snapshot(f'load-{index}'))
        for worker in workers:
            worker.wait(timeout=5)
        workers = []
        for index in range(5):
            time.sleep(1)
            result['cpu_samples'].append(snapshot(f'settled-{index}'))

        for level in (2, 4, 7):
            write(BACKLIGHT / 'brightness', level)
            time.sleep(0.5)
            actual = int(read(BACKLIGHT / 'actual_brightness'))
            if actual != level:
                raise RuntimeError(f'Backlight readback mismatch: {level}, {actual}')
            result['brightness_samples'].append({
                'requested': level, 'actual': actual,
                'pwm': Path('/sys/kernel/debug/pwm').read_text(),
            })
        write(BACKLIGHT / 'bl_power', 4)
        time.sleep(1)
        result['blanked_pwm'] = Path('/sys/kernel/debug/pwm').read_text()
        result['passed'] = True
    except Exception as error:
        result['error'] = str(error)
    finally:
        for worker in workers:
            worker.terminate()
            worker.wait(timeout=5)
        write(POLICY / 'scaling_governor', original['scaling_governor'])
        write(BACKLIGHT / 'brightness', brightness)
        write(BACKLIGHT / 'bl_power', power)
        result['restored'] = {
            'governor': read(POLICY / 'scaling_governor'),
            'brightness': read(BACKLIGHT / 'brightness'),
            'bl_power': read(BACKLIGHT / 'bl_power'),
        }
        print(json.dumps(result, indent=2), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
