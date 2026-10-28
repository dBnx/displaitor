"""Page controls, fixed fields and the Python-to-Rust stats/audio boundary."""
from datetime import datetime
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

import canvas
import companion_designs
import companion_stats as stats
import pc_hub
import pixel_companion as app
from test_canvas_buttons import ScriptedSocket, ack

ROOT = Path(__file__).resolve().parents[1]


def press(*keys, active=True, lost=False):
    keys = frozenset(keys)
    event = canvas.ButtonEvent(1, 10, keys, keys, frozenset(), active)
    return canvas.ButtonState(keys, active, (event,), lost, False, 0, 10)


def activity(cpu=1, ram=64, gpu=96, vram=3.2, demo=False):
    sample = pc_hub.Sample(cpu, ram, gpu, datetime.now(),
                           vram_used=None if vram is None else round(vram * pc_hub.GIB), demo=demo)
    return app.Workload().update(sample)


class StatsTests(unittest.TestCase):
    def test_page_wraps_independently_of_pet_and_action_without_reactivating_canvas(self):
        pet = app.Companion('torchic')
        pet.buttons(press('a'))
        pet.phase = 4.0
        for expected in ('ram', 'gpu', 'vram', 'all', 'cpu'):
            self.assertTrue(pet.buttons(press('down')))
            self.assertEqual(pet.page, expected)
            self.assertEqual((pet.phase, pet.action_remaining, pet.cry_pending),
                             (4.0, companion_designs.ACTION_SECONDS, 'torchic'))
        self.assertTrue(pet.buttons(press('up')))
        self.assertEqual(pet.page, 'all')
        pet.buttons(press('right'))
        self.assertEqual((pet.design, pet.page), ('eevee', 'all'))
        self.assertIsNone(pet.cry_pending)
        for state in (press('up', 'down'), press('down', active=False), press('up', lost=True), press()):
            self.assertFalse(pet.buttons(state))
            self.assertEqual(pet.page, 'all')
        client = MagicMock()
        pet.install(client, activity(), activate=False)
        client.show.assert_not_called()

    def test_selected_reading_is_independent_of_busiest_counter(self):
        reading = activity()
        self.assertEqual((reading.source, reading.mood), ('GPU', 'hard'))
        expected = ('1%', '64%', '96%', '3.2G')
        for page, text in zip(stats.PAGES, expected):
            labels = stats.labels(reading, page, False)
            self.assertEqual(labels['metric'][0], text)
            self.assertEqual(labels['mood'][0], page.upper())
        self.assertEqual(activity(cpu=1, gpu=1, ram=100).mood, 'idle')
        self.assertEqual(stats.labels(reading, 'all', False), {
            'cpu': ('C   1%', 1), 'ram': ('R  64%', 64),
            'gpu': ('G  96%', 96), 'vram': ('V 3.2G', None)})
        for page in stats.PAGES:
            pet = app.Companion('eevee', page)
            pet.update(MagicMock(), reading, 0)
            for key, value in pet.last.items():
                if isinstance(key, tuple):
                    expected_color = '#FF665E' if key[0] in ('gpu', 'demo') or (page == 'gpu') else companion_designs.DESIGNS['eevee']
                    self.assertEqual(value, expected_color, (page, key))

    def test_missing_and_expired_counters_clear_readings_instead_of_showing_zero(self):
        reading = activity(gpu=None, vram=None)
        self.assertEqual(stats.labels(reading, 'gpu', False)['metric'][0], '--%')
        self.assertEqual(stats.labels(reading, 'vram', False)['metric'][0], '--')
        pet = app.Companion('treecko', 'all')
        pet.update(MagicMock(), activity(), 0)
        pet.update(MagicMock(), app.Workload().update(None), 0)
        self.assertEqual([pet.last[key] for key in ('cpu', 'ram', 'gpu', 'vram')],
                         ['C  --%', 'R  --%', 'G  --%', 'V   --'])
        for raw in (None, float('nan'), -1):
            self.assertEqual(stats.compact_vram(raw), '--')
        for raw in (0, 512 * pc_hub.MIB, pc_hub.GIB, 10 * pc_hub.GIB, 1024**5):
            self.assertLessEqual(len(stats.compact_vram(raw)), 4)

    def test_percent_sign_and_overview_prefixes_stay_anchored(self):
        for value in (0, 1, 9, 10, 99, 100, None):
            labels = stats.labels(activity(value, value, value), 'all', False)
            for name, prefix in zip(stats.PAGES[:3], 'CRG'):
                text = labels[name][0]
                self.assertEqual((len(text), text[0], text[-1]), (6, prefix, '%'))
        for page in stats.PAGES[:4]:
            field = companion_designs.layout('torchic', page)['text']['metric']
            self.assertEqual((field['x'], field['width'], field['align']), (40, 24, 'right'))
        pet = app.Companion('treecko', 'all')
        client = MagicMock()
        pet.install(client, activity(demo=True))
        self.assertEqual(pet.last['name'], 'DEMO')
        pet.update(client, activity(), 0)
        self.assertEqual(pet.last['name'], 'TREECKO')


class CryTests(unittest.TestCase):
    def test_a_emits_once_after_commit_and_old_firmware_disables_only_sound(self):
        for design in companion_designs.DESIGNS:
            pet = app.Companion(design)
            client = MagicMock()
            pet.install(client, activity())
            pet.buttons(press('a'))
            pet.update(client, activity(), 0)
            client.cry.assert_not_called()
            pet.play_pending_cry(client)
            pet.update(client, activity(), .1)
            pet.play_pending_cry(client)
            self.assertEqual(client.cry.call_count, int(design in companion_designs.POKEMON))
            if design in companion_designs.POKEMON:
                client.cry.assert_called_once_with(design)
                # The sound call follows the exit/commit of the scene scope.
                calls = [str(call) for call in client.mock_calls]
                self.assertLess(max(i for i, call in enumerate(calls[:calls.index(f"call.cry('{design}')")])
                                    if '__exit__' in call), calls.index(f"call.cry('{design}')"))
        pet = app.Companion('torchic')
        client = MagicMock()
        client.cry.side_effect = NotImplementedError()
        with patch('sys.stderr', new_callable=io.StringIO) as error:
            for _ in range(2):
                pet.buttons(press('a'))
                pet.play_pending_cry(client)
            self.assertEqual(error.getvalue().count('updated firmware'), 1)
        self.assertEqual(client.cry.call_count, 1)
        self.assertGreater(pet.action_remaining, 0)
        pet = app.Companion('treecko', sound=False)
        pet.buttons(press('a'))
        self.assertIsNone(pet.cry_pending)
        self.assertGreater(pet.action_remaining, 0)

    def test_lost_ack_reconnect_switch_and_inactive_states_do_not_replay_a_cry(self):
        pet = app.Companion('eevee')
        client = MagicMock()
        client.cry.side_effect = TimeoutError('lost ACK')
        pet.buttons(press('a'))
        with self.assertRaises(TimeoutError):
            pet.play_pending_cry(client)
        pet.play_pending_cry(client)
        self.assertEqual(client.cry.call_count, 1)
        pet.buttons(press('a'))
        pet.install(client, activity())
        self.assertIsNone(pet.cry_pending)
        for state in (press('a', active=False), press('a', lost=True)):
            pet.buttons(state)
            self.assertIsNone(pet.cry_pending)
        pet.buttons(press('a'))
        pet.buttons(press('left'))
        self.assertIsNone(pet.cry_pending)

    def test_sdk_payload_capability_detection_and_no_automatic_retry(self):
        connection = ScriptedSocket()
        with patch.object(canvas.socket, 'create_connection', return_value=connection):
            client = canvas.Client('tcp://127.0.0.1:7777')
        with client:
            for name, value in canvas.CRIES.items():
                client.cry(name)
                self.assertEqual(connection.requests[-1][::2], (11, bytes([value])))
            count = len(connection.requests)
            with self.assertRaises(ValueError):
                client.cry('invalid')
            self.assertEqual(len(connection.requests), count)
            original = connection.sendall
            def unsupported(data):
                original(data)
                command, sequence, _ = connection.requests[-1]
                if command == 11:
                    connection.pending[:] = ack(sequence, status=3)
            connection.sendall = unsupported
            with self.assertRaisesRegex(NotImplementedError, 'firmware update required'):
                client.cry('eevee')
            def dropped(data):
                original(data)
                connection.pending.clear()
            connection.sendall = dropped
            with self.assertRaises(TimeoutError):
                client.cry('torchic')
            self.assertTrue(connection.closed)
            self.assertEqual(connection.requests[-1][0], 11)


class SimulatorTests(unittest.TestCase):
    def test_real_wire_renders_all_five_pages_and_requests_one_effect(self):
        binary = ROOT / ('target/debug/simulaitor.exe' if sys.platform == 'win32' else 'target/debug/simulaitor')
        reading = activity()
        with tempfile.TemporaryDirectory() as directory:
            for page in stats.PAGES:
                with self.subTest(page=page):
                    snapshot = Path(directory) / (page + '.ppm')
                    process = subprocess.Popen([str(binary), '--headless', '--canvas-listen', '127.0.0.1:0',
                                                '--frames', '250', '--snapshot', str(snapshot)],
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    try:
                        line = process.stdout.readline().strip()
                        self.assertTrue(line.startswith('Canvas listening on 127.0.0.1:'), line)
                        with canvas.Client('tcp://' + line.split()[-1]) as client:
                            pet = app.Companion('treecko', 'all' if page != 'all' else 'cpu')
                            pet.install(client, reading)
                            pet.page_index = stats.PAGES.index(page)
                            pet.install(client, reading, activate=False)
                            pet.buttons(press('a'))
                            pet.update(client, reading, 0)
                            pet.play_pending_cry(client)
                        stdout, stderr = process.communicate(timeout=5)
                        self.assertEqual(process.returncode, 0, stdout + stderr)
                        self.assertIn('audio_requests=1 ', stdout)  # Simulator starts in Canvas; Show adds no sound.
                        with Image.open(snapshot) as image:
                            rendered = image.convert('RGB')
                        for slot in companion_designs.layout('treecko', page)['text'].values():
                            x, y, w, h = (slot[key] for key in ('x', 'y', 'width', 'height'))
                            self.assertTrue(any(rendered.crop((x, y, x+w, y+h)).tobytes()), (page, slot))
                        if page != 'all':
                            # The previous four-row overview cannot leave glyphs in this two-row gap.
                            self.assertFalse(any(rendered.crop((40, 18, 64, 20)).tobytes()))
                    finally:
                        if process.poll() is None:
                            process.terminate()
                            process.communicate(timeout=3)


if __name__ == '__main__':
    unittest.main()
