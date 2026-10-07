#!/usr/bin/env python3
"""Prevent verified modules from disappearing or losing startup integration."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from image_kernel_modules import selected_modules, verify


class ModuleImageTests(unittest.TestCase):
    def setUp(self):
        self.target = 'kernel/drivers/cpufreq/tegra20-cpufreq.ko'
        source = 'build/linux-nura/drivers/cpufreq/tegra20-cpufreq.ko'
        module_hash = hashlib.sha256(b'module').hexdigest()
        self.lock = {'files': {source: module_hash,
                              'build/linux-nura/arch/arm/boot/zImage': 'kernel-hash'},
                     'extra_kernel_modules': {self.target: {
                         'source': source, 'autoload': 'tegra20-cpufreq',
                         'modalias': 'platform:tegra20-cpufreq',
                         'tested_module_sha256': module_hash,
                         'tested_kernel_sha256': 'kernel-hash'}}}
        self.prefix = '/usr/lib/modules/test/'
        self.contents = {'/etc/modules': b'evdev\ntegra20-cpufreq\n',
                         self.prefix + self.target: b'module',
                         self.prefix + 'modules.order': (self.target + '\n').encode(),
                         self.prefix + 'modules.dep': (self.target + ':\n').encode(),
                         self.prefix + 'modules.alias': b'alias platform:tegra20-cpufreq tegra20_cpufreq\n'}

    def test_corrupt_module_rejected(self):
        self.contents[self.prefix + self.target] = b'corrupted'
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            verify(self.contents.__getitem__, self.lock, 'test')

    def test_missing_startup_component_rejected(self):
        for path in ('/etc/modules', *(self.prefix + name for name in
                      ('modules.order', 'modules.dep', 'modules.alias'))):
            with self.subTest(path=path):
                broken = dict(self.contents, **{path: b''})
                with self.assertRaises(ValueError):
                    verify(broken.__getitem__, self.lock, 'test')

    def test_different_kernel_requires_new_hardware_checkpoint(self):
        changed = copy.deepcopy(self.lock)
        changed['files']['build/linux-nura/arch/arm/boot/zImage'] = 'new-kernel'
        with self.assertRaisesRegex(ValueError, 'Kernel differs'):
            selected_modules(changed)

    def test_module_cannot_be_written_outside_module_directory(self):
        changed = copy.deepcopy(self.lock)
        changed['extra_kernel_modules']['../../etc/inittab'] = changed['extra_kernel_modules'].pop(self.target)
        with self.assertRaisesRegex(ValueError, 'Invalid module path'):
            selected_modules(changed)

    def test_historical_lock_needs_no_new_module_files(self):
        self.assertEqual(verify(lambda _: self.fail('Unexpected image read'), {}, 'test'), {})


if __name__ == '__main__':
    unittest.main()
