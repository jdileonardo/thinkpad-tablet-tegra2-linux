#!/usr/bin/env python3
"""Export recorded port patches to local upstream branches without changing HEAD.

Uses disposable Git indexes. Refuses edits outside the recorded patch series,
except the kernel board DTS and its Makefile entry, which are exported together.
Does not push, switch checkouts, or change their real indexes.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

PROJECT = Path(__file__).resolve().parents[1]


def main():
    lock = json.loads((PROJECT / 'sources.lock.json').read_text())
    output = PROJECT / 'build/source-exports'
    output.mkdir(parents=True, exist_ok=True)
    definitions = [
        ('linux-nura', 'linux-nura', sorted((PROJECT / 'port').glob('000[12]-*.patch'))),
        ('xf86-video-opentegra', 'xf86-video-opentegra', sorted((PROJECT / 'port/opentegra').glob('*.patch'))),
        ('mesa-grate-candidate', 'mesa-grate-ad06de32d309', sorted((PROJECT / 'port/mesa/candidate').glob('*.patch'))),
    ]
    manifest = {}
    for key, directory, patches in definitions:
        source = PROJECT / 'sources' / directory
        base = lock[key]['commit']
        branch = 'indigo/xfce-bringup'
        def git(*args, env=None, data=None):
            return subprocess.check_output(['git', '-C', str(source), *args], env=env, input=data)
        if git('rev-parse', 'HEAD').decode().strip() != base:
            raise RuntimeError(f'{key}: build checkout HEAD differs from pinned base')
        if not patches:
            raise RuntimeError(f'{key}: empty patch series')
        with tempfile.TemporaryDirectory(prefix='indigo-source-export-') as temporary:
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / 'series-index'))
            git('read-tree', base, env=env)
            trees = []
            for patch in patches:
                git('apply', '--cached', str(patch), env=env)
                trees.append((patch.stem, git('write-tree', env=env).decode().strip()))
            if key == 'linux-nura':
                git('add', '--', 'arch/arm/boot/dts/nvidia/Makefile',
                    'arch/arm/boot/dts/nvidia/tegra20-lenovo-indigo.dts', env=env)
                trees.append(('Add Lenovo Indigo board device tree',
                              git('write-tree', env=env).decode().strip()))
            actual_env = dict(env, GIT_INDEX_FILE=str(Path(temporary) / 'actual-index'))
            git('read-tree', base, env=actual_env)
            git('add', '-u', env=actual_env)
            if key == 'linux-nura':
                git('add', '--', 'arch/arm/boot/dts/nvidia/tegra20-lenovo-indigo.dts', env=actual_env)
            actual_tree = git('write-tree', env=actual_env).decode().strip()
            if trees[-1][1] != actual_tree:
                raise RuntimeError(f'{key}: working edits differ from recorded patches/board files')
            existing = subprocess.run(['git', '-C', str(source), 'rev-parse', '--verify',
                                       f'refs/heads/{branch}'], capture_output=True, text=True)
            old = existing.stdout.strip() if existing.returncode == 0 else '0' * 40
            if existing.returncode == 0:
                git('merge-base', '--is-ancestor', base, old)
                old_tree = git('rev-parse', old + '^{tree}').decode().strip()
                matching = [index for index, (_, tree) in enumerate(trees) if tree == old_tree]
                if not matching:
                    raise RuntimeError(f'{key}: existing export branch differs from recorded patch prefixes; preserve it first')
                tip = old
                for title, tree in trees[matching[-1] + 1:]:
                    tip = git('commit-tree', tree, '-p', tip, data=(title + '\n').encode()).decode().strip()
                if tip != old:
                    git('update-ref', f'refs/heads/{branch}', tip, old)
            else:
                tip = base
                for title, tree in trees:
                    tip = git('commit-tree', tree, '-p', tip, data=(title + '\n').encode()).decode().strip()
                git('update-ref', f'refs/heads/{branch}', tip, old)
        exported = output / key
        exported.mkdir(exist_ok=True)
        git('format-patch', '--output-directory', str(exported), f'{base}..{tip}')
        files = sorted(exported.glob('*.patch'))
        manifest[key] = {'upstream_url': lock[key]['url'], 'base_commit': base,
                         'branch': branch, 'tip_commit': tip, 'tree': actual_tree,
                         'build_checkout_head_unchanged': git('rev-parse', 'HEAD').decode().strip() == base,
                         'patches_sha256': {str(p.relative_to(PROJECT)):
                                           hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
        print(f'{key}: {branch} at {tip}, {len(files)} commits; checkout unchanged')
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
