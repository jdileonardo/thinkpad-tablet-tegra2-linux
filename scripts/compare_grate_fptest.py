#!/usr/bin/env python3
"""Compare real-device Grate samples with the identical softpipe test run."""
import argparse
import json
from pathlib import Path
import re


def read_log(path):
    text = path.read_text()
    renderer = re.search(r'^# renderer: (.+)$', text, re.MULTILINE)
    samples = {}
    for match in re.finditer(
            r'^(\S+) (\d+),(\d+),(\d+),(\d+) err=(0x[0-9a-fA-F]+)$',
            text, re.MULTILINE):
        name = match[1]
        if name in samples:
            raise ValueError(f'{path}: duplicate sample {name}')
        samples[name] = {'rgba': [int(match[i]) for i in range(2, 6)],
                         'error': int(match[6], 16)}
    problems = [line for line in text.splitlines() if re.search(
        r'UNIMPLEMENTED|COMPILE_FAIL|LINK_FAIL|not translatable|out of temporary|'
        r'exceeds the|unhandled instruction', line)]
    return renderer[1] if renderer else None, samples, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hardware', type=Path)
    parser.add_argument('software', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tolerance', type=int, default=10)
    parser.add_argument('--expected-samples', type=int, default=331)
    args = parser.parse_args()
    if args.tolerance < 0 or args.expected_samples < 1:
        parser.error('tolerance must be nonnegative and expected samples positive')
    hw_renderer, hw, hw_problems = read_log(args.hardware)
    sw_renderer, sw, sw_problems = read_log(args.software)
    failed = {}
    for name in sorted(hw.keys() | sw.keys()):
        a, b = hw.get(name), sw.get(name)
        if (a is None or b is None or a['error'] or b['error'] or
                max(abs(x - y) for x, y in zip(a['rgba'], b['rgba'])) > args.tolerance):
            failed[name] = {'hardware': a, 'software': b}
    coverage = len(hw) == len(sw) == args.expected_samples and hw.keys() == sw.keys()
    valid = (hw_renderer == 'Tegra' and sw_renderer == 'softpipe' and
             coverage and not hw_problems and not sw_problems)
    result = {
        'hardware_renderer': hw_renderer, 'software_renderer': sw_renderer,
        'tolerance': args.tolerance, 'expected_samples': args.expected_samples,
        'hardware_samples': len(hw), 'software_samples': len(sw),
        'coverage_complete': coverage, 'logs_valid': valid,
        'passing': len(hw.keys() & sw.keys()) - sum(
            name in hw and name in sw for name in failed),
        'failing': len(failed), 'failed': failed,
        'hardware_diagnostics': hw_problems, 'software_diagnostics': sw_problems,
        'pass': valid and not failed,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{result['passing']} passing, {len(failed)} failing; "
          f"coverage={coverage}, logs_valid={valid}")
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
