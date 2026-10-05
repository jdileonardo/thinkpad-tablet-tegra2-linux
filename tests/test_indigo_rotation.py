#!/usr/bin/env python3
"""Check rotation geometry, gravity hysteresis, and input failure rollback."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import call, patch

spec = importlib.util.spec_from_file_location('indigo_rotate', Path(__file__).resolve().parents[1] / 'port/desktop/indigo-rotate.py')
rotate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rotate)


class RotationTests(unittest.TestCase):
    def test_corner_mapping(self):
        expected = {
            'normal': ((0, 0), (1, 0), (1, 1), (0, 1)),
            'left': ((1, 0), (1, 1), (0, 1), (0, 0)),
            'inverted': ((1, 1), (0, 1), (0, 0), (1, 0)),
            'right': ((0, 1), (0, 0), (1, 0), (1, 1)),
        }
        for orientation, points in expected.items():
            m = rotate.MATRICES[orientation]
            for (x, y), target in zip(expected['normal'], points):
                self.assertEqual((m[0]*x+m[1]*y+m[2], m[3]*x+m[4]*y+m[5]), target)
                self.assertEqual(m[6]*x+m[7]*y+m[8], 1)

    def test_gravity_and_ambiguous_positions(self):
        for index, vector in enumerate(((0, -9.8, 0), (9.8, 0, 0), (0, 9.8, 0), (-9.8, 0, 0))):
            self.assertEqual(rotate.gravity_direction(vector), index)
        for vector in ((0, 0, 9.8), (6.9, 6.9, 0), (1, -2, 3), (8, 0, 8)):
            self.assertIsNone(rotate.gravity_direction(vector))

    def test_calibrated_orientation(self):
        config = {'reference': 0, 'reference_rotation': 'left'}
        for direction, orientation in enumerate(('left', 'normal', 'right', 'inverted')):
            self.assertEqual(rotate.sensor_rotation(direction, config), orientation)
        # With buttons at the bottom, opposite sideways holds must select
        # opposite landscape rotations, matching the physical panel axes.
        self.assertEqual(rotate.sensor_rotation(rotate.gravity_direction((9.8, 0, 0)), config), 'normal')
        self.assertEqual(rotate.sensor_rotation(rotate.gravity_direction((-9.8, 0, 0)), config), 'inverted')
        self.assertIsNone(rotate.sensor_rotation(None, config))
        self.assertIsNone(rotate.sensor_rotation(0, {'reference': None}))

    def test_display_and_inputs_restore_after_partial_failure(self):
        identity = rotate.MATRICES['normal']
        failed = False

        def set_matrix(device, matrix):
            nonlocal failed
            if device == 'pen' and matrix == rotate.MATRICES['left'] and not failed:
                failed = True
                raise RuntimeError('pen update rejected')

        with patch.object(rotate, 'display', return_value=('Unknown-0', 'normal')), \
             patch.object(rotate, 'inputs', return_value=['touch', 'pen']), \
             patch.object(rotate, 'get_matrix', return_value=identity), \
             patch.object(rotate, 'command') as command, \
             patch.object(rotate, 'set_matrix', side_effect=set_matrix) as matrices:
            with self.assertRaisesRegex(RuntimeError, 'pen update rejected'):
                rotate.rotate('left')
            command.assert_has_calls([
                call('xrandr', '--output', 'Unknown-0', '--rotate', 'left'),
                call('xrandr', '--output', 'Unknown-0', '--rotate', 'normal'),
            ])
            self.assertEqual(matrices.call_args_list[-2:], [call('touch', identity), call('pen', identity)])


if __name__ == '__main__':
    unittest.main()
