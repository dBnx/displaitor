#!/usr/bin/env python3
"""Manual SWD audio check; requires matching profiling firmware playing Nyan.

Requests firmware-timed counter captures after a settling interval, excluding
probe attachment pauses. Writes only AUDIO_CAPTURE and GAME_INPUT in RAM for
Select/mute and B/Stop; never programs firmware or opens a serial port.
Run only against an explicitly authorized board. Requires pyelftools/probe-rs.
"""

from __future__ import annotations
import argparse
import json
import shutil
import struct
import subprocess
import time
from pathlib import Path
from typing import TypedDict


class Capture(TypedDict):
    elapsed_firmware_s: float
    completed_blocks: int
    blocks_per_s: float
    fallbacks: int
    underruns: int
    last_irq_timer: str


class Snapshot(TypedDict):
    label: str
    words: tuple[int, ...]



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', required=True, type=Path)
    parser.add_argument('--probe', required=True, help='explicit VID:PID:serial selector')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--probe-rs', default=shutil.which('probe-rs'))
    args = parser.parse_args()
    from elftools.elf.elffile import ELFFile
    from elftools.elf.sections import SymbolTableSection
    if not args.probe_rs:
        parser.error('probe-rs is not on PATH; pass --probe-rs /path/to/probe-rs')
    with args.elf.open('rb') as source:
        section = ELFFile(source).get_section_by_name('.symtab')
        if not isinstance(section, SymbolTableSection):
            raise ValueError('ELF has no symbol table')
        symbols = {s.name: int(s['st_value']) for s in section.iter_symbols()}
    addresses = {name: symbols[name] for name in ('AUDIO_CAPTURE', 'GAME_INPUT')}
    assert all(0x20000000 <= address < 0x20040000 for address in addresses.values())
    args.output.mkdir(parents=True, exist_ok=True)
    common = [args.probe_rs, '--chip', 'RP2040', '--probe', args.probe, '--speed', '5000']
    snapshots: list[Snapshot] = []
    results: dict[str, object] = {'elf': str(args.elf.resolve()), 'addresses': addresses, 'snapshots': snapshots,
               'method': 'firmware timer window after 100ms settling; probe pauses excluded'}

    def command(operation: str, *parameters: str) -> None:
        completed = subprocess.run([common[0], operation, *common[1:], *parameters],
                                   check=True, capture_output=True, text=True, timeout=15)
        if completed.stderr:
            print(completed.stderr, end='')

    def input_mask(mask: int) -> None:
        command('write', 'b32', hex(addresses['GAME_INPUT']), str(mask))

    def tap(mask: int) -> None:
        input_mask(mask)
        time.sleep(.2)
        input_mask(0)
        time.sleep(.3)

    def capture(label: str) -> Capture:
        command('write', 'b32', hex(addresses['AUDIO_CAPTURE']), '3000000')
        # Firmware settles for 100ms after the request, then captures 3 seconds.
        # CLI attachment can pause cores; read only after that window finishes.
        time.sleep(4)
        path = args.output / (label + '.bin')
        command('read', 'b32', hex(addresses['AUDIO_CAPTURE']), '11',
                '--format', 'binary', '--output', str(path))
        words = struct.unpack('<11I', path.read_bytes())
        snapshots.append({'label': label, 'words': words})
        request, start, finish = words[:3]
        assert request == 0 and finish != 0, ('capture incomplete', words)
        elapsed = ((finish - start) & 0xffffffff) / 1_000_000
        assert 3 <= elapsed <= 3.01, ('capture timing', elapsed)
        before, after = words[3:7], words[7:11]
        for index in (0, 1, 3):
            assert before[index] <= after[index] < 0xffffffff, ('counter saturated/reset', words)
        delta = after[0] - before[0]
        result: Capture = {'elapsed_firmware_s': elapsed, 'completed_blocks': delta,
                  'blocks_per_s': delta / elapsed,
                  'fallbacks': after[1] - before[1], 'underruns': after[3] - before[3],
                  'last_irq_timer': hex(after[2])}
        results[label] = result
        return result

    try:
        input_mask(0)
        active = capture('active')
        assert 499 <= active['blocks_per_s'] <= 501, active
        assert active['fallbacks'] == 0 and active['underruns'] == 0, active
        tap(4)
        muted = capture('muted')
        assert muted['completed_blocks'] == 0 and muted['fallbacks'] == 0 and muted['underruns'] == 0, muted
        tap(4)
        resumed = capture('resumed')
        assert 499 <= resumed['blocks_per_s'] <= 501, resumed
        assert resumed['fallbacks'] == 0 and resumed['underruns'] == 0, resumed
        tap(2)
        stopped = capture('stopped')
        assert stopped['completed_blocks'] == 0 and stopped['fallbacks'] == 0 and stopped['underruns'] == 0, stopped
        results['passed'] = True
    except Exception as error:
        results['passed'] = False
        results['error'] = repr(error)
        raise
    finally:
        try:
            input_mask(0)
            results['synthetic_input_cleared'] = True
        except Exception as error:
            results['passed'] = False
            results['synthetic_input_cleared'] = False
            results['cleanup_error'] = repr(error)
            if 'error' not in results:
                raise
        finally:
            (args.output / 'audio-counters.json').write_text(json.dumps(results, indent=2) + '\n')
            print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
