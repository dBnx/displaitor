"""One installed or checkout-local launcher; implementations and optional imports load on demand."""

from __future__ import annotations

from collections.abc import Sequence
import argparse
from importlib import import_module
import sys


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description='Displaitor host apps and development tools.')
    commands = root.add_subparsers(dest='command', required=True)
    for name, module, help_text in (
        ('new-scene', '.starter', 'create a typed custom-scene script'),
        ('pictures', '.apps.pictures', 'display pictures or a slideshow with d-pad browsing'),
        ('companion', '.apps.companion', 'live pets, stats and button actions'),
        ('dashboard', '.apps.pc_hub', 'live PC dashboard'),
        ('weather', '.apps.weather', 'weather display and animations'),
        ('cozy', '.apps.cozy', 'fullscreen farm, winter, Okami, Witcher, reef and fireplace scenes'),
        ('canvas', '.canvas', 'Canvas drawing and button interface'),
    ):
        commands.add_parser(name, help=help_text, add_help=False).set_defaults(module=module)
    for group, help_text, entries in (
        ('assets', 'generate firmware media with Python', (('cozy', '.assets.cozy', 'bake full-panel cozy animations into Flash assets'),)),
        ('audio', 'generate firmware audio assets with Python', (('synth', '.audio.synth', 'generate cries as QOA and WAV'),
         ('fixtures', '.audio.fixtures', 'reproduce reference decoder fixtures'))),
        ('preview', 'offline art studies and preview exports', (
            ('stats', '.previews.stats', 'stats gallery, pet GIFs and sound video'),
            ('designs', '.previews.designs', 'design gallery and sprite sheets'),
            ('activity', '.previews.activity', 'live pet activity and action GIFs'),
            ('weather', '.previews.weather', 'weather views and animated forecasts, with offline sample data'),
            ('cozy', '.previews.cozy', 'seamless full-panel cozy scene GIFs'),
            ('play', '.previews.play', 'prop-play studies'),
            ('collections', '.previews.collections', 'alternative casts'),
            ('alternatives', '.previews.alternatives', 'alternative designs'),
        )),
        ('hardware', 'explicit, manual board diagnostics', (('audio', '.hardware.audio', 'SWD audio profiling'),)),
    ):
        child = commands.add_parser(group, help=help_text)
        actions = child.add_subparsers(dest='action', required=True)
        for name, module, description in entries:
            actions.add_parser(name, help=description, add_help=False).set_defaults(module=module)
    return root


def main(argv: Sequence[str] | None=None) -> None:
    args = sys.argv[1:] if argv is None else list(argv)
    command_parser = parser()
    if not args:
        command_parser.print_help()
        return
    selected, remaining = command_parser.parse_known_args(args)
    # Existing modules own their options and validation, including --help.
    previous = sys.argv
    sys.argv = [previous[0] + ' ' + ' '.join(args[:len(args) - len(remaining)]), *remaining]
    try:
        import_module(selected.module, __package__).main()
    finally:
        sys.argv = previous
