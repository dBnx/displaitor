#!/usr/bin/env python3
"""Build-artifact checks in a clean venv; no publishing or hardware access.

Run after ``python -m build``. Requires build, pip and mypy in this interpreter.
Optionally supply --simulator for an installed-wheel TCP rendering check.
"""
from __future__ import annotations

import argparse
import email.parser
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def run(arguments: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(arguments, cwd=cwd, env=env, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f'{arguments!r} failed:\n{result.stdout}\n{result.stderr}')
    return result.stdout


def audit(wheel: Path) -> set[str]:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        assert 'displaitor_tools/py.typed' in names
        for name in names:
            parts = PurePosixPath(name).parts
            assert not name.startswith('/') and '..' not in parts, name
            assert name.startswith(('displaitor_tools/', 'displaitor_tools-')), name
            assert not any(part.startswith('.') or part in ('names.txt', 'names.example.txt', '__pycache__') for part in parts), name
        metadata = next(name for name in names if name.endswith('.dist-info/METADATA'))
        record = email.parser.Parser().parsestr(archive.read(metadata).decode())
        assert record['Requires-Python'] == '>=3.12'
        dependencies = record.get_all('Requires-Dist', [])
        assert all(any(dependency.lower().startswith(expected) for dependency in dependencies)
                   for expected in ('pillow', 'pyserial', 'psutil'))
        assert any(name.endswith('.dist-info/entry_points.txt') for name in names)
    return names


def installed_smoke(python: Path, work: Path, env: dict[str, str]) -> None:
    payload = '''
import json
from pathlib import Path
import displaitor_tools
from displaitor_tools import Client, Layout, TextLayout, run_scene
from displaitor_tools.paths import ART, LAYOUTS, checkout_root
from displaitor_tools.companions.designs import DESIGNS, sprite
from displaitor_tools.scenes import NAMES, render
from displaitor_tools.weather.manual import Weather
assert 'site-packages' in displaitor_tools.__file__
for name in DESIGNS:
    for mood in ('idle', 'busy', 'hard'):
        assert sprite(name, 5, mood, action=.5).size == (64, 32)
for name in NAMES:
    assert render(name, 1.5).size == (64, 32)
for name in ('weather.json', 'pc_hub.json'):
    Layout(json.loads((LAYOUTS / name).read_text(encoding='utf-8')))
Weather()
try:
    checkout_root()
except RuntimeError as error:
    assert 'source checkout' in str(error)
else:
    raise AssertionError('wheel must not masquerade as a source checkout')
from displaitor_tools.assets.cozy import DEFAULT_OUTPUT
assert DEFAULT_OUTPUT == Path.cwd() / 'cozy-assets'
print('Installed imports, all pets/scenes, JSON layouts and safe output paths passed')
'''
    print(run([str(python), '-I', '-c', payload], cwd=work, env=env).strip())
    for arguments in ([], ['cozy', '--help'], ['companion', '--help'], ['weather', '--help'], ['pictures', '--help'],
                      ['dashboard', '--help'], ['canvas', '--help'], ['new-scene', '--help'],
                      ['preview', 'stats', '--help'], ['audio', 'synth', '--help']):
        assert 'usage:' in run([str(python), '-I', '-m', 'displaitor_tools', *arguments], cwd=work, env=env)
    console = python.parent / ('displaitor.exe' if os.name == 'nt' else 'displaitor')
    assert 'usage:' in run([str(console), '--help'], cwd=work, env=env)
    run([str(console), 'new-scene', 'my_scene.py'], cwd=work, env=env)
    starter = (work / 'my_scene.py').read_bytes()
    result = subprocess.run([str(console), 'new-scene', 'my_scene.py'], cwd=work, env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode != 0 and (work / 'my_scene.py').read_bytes() == starter
    assert '--port' in run([str(python), '-I', 'my_scene.py', '--help'], cwd=work, env=env)


def typing_smoke(python: Path, work: Path, env: dict[str, str]) -> None:
    config = work / 'mypy.ini'
    config.write_text('[mypy]\nstrict = True\n', encoding='utf-8')
    command = [sys.executable, '-m', 'mypy', '--config-file', str(config), '--python-executable', str(python)]
    run([*command, 'my_scene.py'], cwd=work, env=env)
    invalid = work / 'bad_types.py'
    invalid.write_text('from displaitor_tools import Client, run_scene\nClient(123)\nrun_scene(lambda t: 123)\n', encoding='utf-8')
    result = subprocess.run([*command, str(invalid)], cwd=work, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 1 and result.stdout.count('error:') >= 2, result.stdout + result.stderr
    print('Installed typing accepts starter and rejects incorrect client/renderer types')


def tcp_smoke(python: Path, binary: Path, work: Path, env: dict[str, str]) -> None:
    snapshot = work / 'installed.ppm'
    process = subprocess.Popen([str(binary), '--headless', '--canvas-listen', '127.0.0.1:0',
                                '--frames', '500', '--snapshot', str(snapshot)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    try:
        assert process.stdout is not None
        line = process.stdout.readline().strip()
        assert line.startswith('Canvas listening on 127.0.0.1:'), line
        target = 'tcp://' + line.split()[-1]
        payload = '''
from PIL import Image
from displaitor_tools import Client, TextLayout, run_scene
import sys
port = sys.argv[1]
with Client(port) as client:
    layout: TextLayout = {'text': {'old': dict(x=0,y=0,width=24,height=6,font='small',color='#FFFFFF',text='OLD')}}
    client.layout(layout)
    client.fill('#000000')
    client.show()
count = 0
def render(elapsed: float) -> Image.Image:
    global count
    count += 1
    return Image.new('RGB', (64,32), (count*40,120,80))
assert run_scene(render, port=port, frames=4, fps=20) == 4
Image.new('RGB', (64,64), (80,180,120)).save('photo.png')
import subprocess
subprocess.run([sys.executable, '-I', '-m', 'displaitor_tools', 'pictures', 'photo.png',
                '--port', port, '--frames', '2'], check=True, timeout=10)
'''
        run([str(python), '-I', '-c', payload, target], cwd=work, env=env)
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stdout + stderr
        check = '''
from PIL import Image
from displaitor_tools import image_frame
import sys
with Image.open(sys.argv[1]) as actual:
    expected = Image.new('RGB', (64,32))
    expected.paste((80,180,120), (16,0,48,32))
    assert image_frame(actual) == image_frame(expected)
'''
        run([str(python), '-I', '-c', check, str(snapshot)], cwd=work, env=env)
        print('Installed public runner and picture app matched actual Rust Canvas pixels and cleared the old HUD')
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist-dir', type=Path, default=ROOT / 'dist')
    parser.add_argument('--simulator', type=Path)
    args = parser.parse_args()
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    stem = project['name'].replace('-', '_') + '-' + project['version']
    wheel = (args.dist_dir / (stem + '-py3-none-any.whl')).resolve()
    source = (args.dist_dir / (stem + '.tar.gz')).resolve()
    expected = audit(wheel)
    env = {key: value for key, value in os.environ.items() if key not in ('PYTHONPATH', 'PYTHONHOME', 'MYPYPATH')}
    env['PYTHONNOUSERSITE'] = '1'
    with tempfile.TemporaryDirectory(prefix='displaitor-wheel-') as directory:
        work = Path(directory)
        source_root = work / 'source'
        source_root.mkdir()
        with tarfile.open(source) as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    assert member.isdir(), member.name
                    continue
                path = PurePosixPath(member.name)
                relative = '/'.join(path.parts[1:])
                assert relative in ('pyproject.toml', 'setup.cfg', 'PKG-INFO', 'README.md', 'tools/LIBRARY.md', 'tools/DISTRIBUTION-NOTICE.md') or relative.startswith(('tools/displaitor_tools/', 'tools/displaitor_tools.egg-info/')), relative
            archive.extractall(source_root, filter='data')
        rebuilt = work / 'rebuilt'
        run([sys.executable, '-m', 'build', '--wheel', '--outdir', str(rebuilt)],
            cwd=next(source_root.iterdir()), env=env)
        assert audit(rebuilt / wheel.name) == expected
        print('Wheel/source archive allowlists and wheel rebuild from source passed')
        wheelhouse = work / 'wheelhouse'
        run([sys.executable, '-m', 'pip', 'download', '--only-binary=:all:', '--dest', str(wheelhouse), str(wheel)], cwd=work, env=env)
        clean = work / 'venv'
        venv.EnvBuilder(with_pip=False, symlinks=os.name != 'nt').create(clean)
        python = clean / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        run([sys.executable, '-m', 'pip', '--python', str(python), 'install', '--no-index', '--find-links', str(wheelhouse), str(wheel)], cwd=work, env=env)
        run([sys.executable, '-m', 'pip', '--python', str(python), 'check'], cwd=work, env=env)
        installed_smoke(python, work, env)
        typing_smoke(python, work, env)
        if args.simulator:
            tcp_smoke(python, args.simulator.resolve(), work, env)
    print('Wheel validation passed without contacting hardware or publishing')


if __name__ == '__main__':
    main()
