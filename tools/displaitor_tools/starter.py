"""Create a typed custom-scene script without replacing existing files."""
from __future__ import annotations
import argparse
from importlib.resources import files
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', nargs='?', type=Path, default=Path('my_scene.py'))
    args = parser.parse_args()
    source = files('displaitor_tools').joinpath('resources/examples/scene.py').read_text(encoding='utf-8')
    try:
        with args.path.open('x', encoding='utf-8', newline='\n') as output:
            output.write(source)
    except OSError as error:
        parser.exit(1, f'new-scene: {error}\n')
    print(f'Created {args.path}. Run: python "{args.path}" --port auto')
