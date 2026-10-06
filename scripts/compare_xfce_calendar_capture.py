#!/usr/bin/env python3
"""Compare the complete calendar client capture with the rotated DRM scanout.

Host-side analysis requires Pillow. This checks display transport of the
captured client pixels; it does not validate every possible calendar state.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from PIL import Image, ImageChops


def pixels(image):
    # Accommodate host Pillow versions before get_flattened_data was added.
    method = getattr(image, 'get_flattened_data', image.getdata)
    return method()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('client', type=Path)
    parser.add_argument('scanout', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with Image.open(args.client) as source:
        window = source.convert('RGB')
    with Image.open(args.scanout) as source:
        scanout = source.convert('RGB')
    colors = list(pixels(window))
    anchor = min(Counter(colors).items(), key=lambda item: item[1])[0]
    anchor_index = colors.index(anchor)
    ax, ay = anchor_index % window.width, anchor_index // window.width
    found = []
    for turns, operation in ((1, Image.Transpose.ROTATE_90), (3, Image.Transpose.ROTATE_270)):
        logical = scanout.transpose(operation)
        for index, color in enumerate(pixels(logical)):
            if color != anchor:
                continue
            left, top = index % logical.width - ax, index // logical.width - ay
            if left < 0 or top < 0 or left + window.width > logical.width or top + window.height > logical.height:
                continue
            actual = logical.crop((left, top, left + window.width, top + window.height))
            difference = ImageChops.difference(actual, window)
            mismatch = sum(rgb != (0, 0, 0) for rgb in pixels(difference))
            found.append({'scanout_quarter_turns_ccw_for_comparison': turns,
                          'client_left': left, 'client_top': top,
                          'client_width': window.width, 'client_height': window.height,
                          'pixels_compared': window.width * window.height,
                          'mismatched_pixels': mismatch, 'exact_match': mismatch == 0})
            if mismatch == 0:
                break
        if found and found[-1]['exact_match']:
            break
    report = {'comparison': 'Complete Xorg client readback against the active DRM framebuffer, aligned for display rotation',
              'alignment_method': 'Locate a least frequent RGB value from the client image, then compare every RGB pixel in each candidate rectangle',
              'matches': found, 'exact_client_match_found': any(x['exact_match'] for x in found)}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not report['exact_client_match_found']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
