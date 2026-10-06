#!/usr/bin/env python3
"""Summarize Indigo CMA/GEM trace events, with absolute CMA bitmap headroom."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    line_pattern = re.compile(r'^\s*(.+)-(\d+)\s+\[(\d+)\]\s+\S+\s+(\d+\.\d+):\s+(\w+):\s+(.*)$')
    field_pattern = re.compile(r'(\w+)=(-?(?:0x[0-9a-f]+|\d+))')
    events = []
    for line in args.trace.read_text().splitlines():
        match = line_pattern.match(line)
        if match:
            fields = {key: int(value, 16 if '0x' in value else 10)
                      for key, value in field_pattern.findall(match[6])}
            events.append({'task': match[1], 'pid': int(match[2]),
                           'time': float(match[4]), 'event': match[5], 'fields': fields,
                           'body': match[6]})
    pending = defaultdict(list)
    live = {}
    available = None
    total = None
    headroom = []
    snapshots = []
    allocated_pages = released_pages = successful_bos = failed_bos = 0
    freed_bos = []
    allocation_errors = []
    consistency_errors = []
    for event in events:
        kind, fields, pid = event['event'], event['fields'], event['pid']
        if kind == 'bo_create':
            pending[pid].append(fields)
        elif kind == 'bo_return':
            if not pending[pid]:
                consistency_errors.append('BO return without a traced entry')
                continue
            create = pending[pid].pop()
            pointer = fields['result']
            if pointer >= 0xfffff001 or pointer == 0:
                failed_bos += 1
            else:
                if pointer in live:
                    consistency_errors.append('BO address reused before a traced free')
                live[pointer] = create
                successful_bos += 1
        elif kind == 'bo_free':
            freed_bos.append(fields['bo'])
            live.pop(fields['bo'], None)
        elif kind == 'cma_alloc_start':
            if available is not None and available != fields['available_count']:
                consistency_errors.append({'expected_available_pages': available,
                                           'actual_available_pages': fields['available_count'],
                                           'time': event['time']})
            available, total = fields['available_count'], fields['total_count']
        elif kind == 'cma_alloc_finish':
            if fields['errorno'] == 0:
                allocated_pages += fields['count']
                if available is not None:
                    available -= fields['count']
            else:
                allocation_errors.append(event)
        elif kind == 'cma_release':
            released_pages += fields['count']
            if available is not None:
                available += fields['count']
        elif kind == 'tracing_mark_write':
            snapshots.append({'label': event['body'], 'available_mib':
                              available / 256 if available is not None else None})
        if available is not None:
            headroom.append(available / 256)
    sizes = Counter(event['fields']['size'] for event in events if event['event'] == 'bo_create')
    if any(pending.values()):
        consistency_errors.append('BO entry without a traced return')
    report = {'event_count': len(events), 'page_size_assumption_bytes': 4096,
              'cma_total_mib': total / 256 if total is not None else None,
              'cma_bitmap_available_mib_range': [min(headroom), max(headroom)] if headroom else None,
              'cma_bitmap_available_mib_at_end': available / 256 if available is not None else None,
              'new_cma_allocation_mib': allocated_pages / 256,
              'cma_release_mib_including_preexisting_buffers': released_pages / 256,
              'net_cma_allocation_change_mib': (allocated_pages - released_pages) / 256,
              'successful_bo_creates': successful_bos, 'failed_bo_creates': failed_bos,
              'bo_request_size_counts': dict(sorted(sizes.items())),
              'traced_new_bos_still_live_or_cached_bytes': sum(x['size'] for x in live.values()),
              'traced_new_bos_still_live_or_cached': [
                  {'pointer': hex(pointer), **create} for pointer, create in sorted(live.items())],
              'freed_bo_pointers_including_preexisting': [hex(pointer) for pointer in freed_bos],
              'cma_allocation_errors': allocation_errors, 'consistency_errors': consistency_errors,
              'marker_headroom': snapshots,
              'scope': 'Live-or-cached BOs are not classified as leaks. Objects predating the trace are not in the BO ledger. Headroom is CMA bitmap availability, not /proc/meminfo CmaFree or a guarantee of contiguous allocation success.'}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ('marker_headroom', 'scope',
                                     'traced_new_bos_still_live_or_cached',
                                     'freed_bo_pointers_including_preexisting')}, indent=2))


if __name__ == '__main__':
    main()
