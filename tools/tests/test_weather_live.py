"""Cached weather, request budgets and D-pad views; no real provider or board."""
from __future__ import annotations

from copy import deepcopy
import io
from http.client import IncompleteRead
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from typing import cast

from PIL import Image

from displaitor_tools import canvas
from displaitor_tools.paths import ROOT
from displaitor_tools.weather import data, examples, views
from displaitor_tools.weather.icons import sprite


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


def press(*keys: str, active: bool = True, lost: bool = False) -> canvas.ButtonState:
    held = frozenset(keys)
    event = canvas.ButtonEvent(1, 1, held, held, frozenset(), active)
    return canvas.ButtonState(held, active, (event,), lost, False, 0, 1)


class DataTests(unittest.TestCase):
    def test_partial_values_and_three_distinct_forecasts(self) -> None:
        payload = examples.payload()
        report = data.parse(payload)
        self.assertEqual(report.current.temperature, 8)
        self.assertEqual(report.current.rain_mm, .4)
        self.assertEqual([d.low for d in report.days], [4, -2, 2])
        self.assertEqual(report.days[0].rain_chance, 80)
        self.assertEqual(report.days[1].status, 'Snow')
        current = cast(list[dict[str, object]], payload['current_condition'])[0]
        current.update(uvIndex=None, humidity='nan', precipMM='bad', windspeedKmph=-1)
        current.pop('FeelsLikeC')
        partial = data.parse(payload).current
        self.assertEqual((partial.uv, partial.humidity, partial.rain_mm, partial.wind, partial.feels_like), (None,) * 5)
        current['humidity'] = 10 ** 1000
        current['weatherDesc'] = [{'value': 'Rain\x00\x1b\x81 soon'}]
        parsed = data.parse(payload).current
        self.assertIsNone(parsed.humidity)
        self.assertEqual(parsed.status, 'Rain soon')
        for invalid in ({}, [], {'current_condition': []}, {'current_condition': [{}]}):
            with self.assertRaises(ValueError):
                data.parse(invalid)

    def test_unicode_location_and_encoded_url_and_response_limit(self) -> None:
        payload = examples.payload()
        payload['nearest_area'] = [{'areaName': [{'value': 'München'}]}]
        self.assertEqual(data.parse(payload).location, 'München')
        response = io.BytesIO(json.dumps(payload).encode())
        with patch.object(data, 'urlopen', return_value=response) as request:
            self.assertEqual(data.fetch('München/?'), payload)
            self.assertIn('M%C3%BCnchen%2F%3F?format=j1&lang=en', request.call_args.args[0].full_url)
            self.assertEqual(request.call_args.kwargs['timeout'], 8)
        with patch.object(data, 'urlopen', return_value=io.BytesIO(b'x' * (data.MAX_BYTES + 1))):
            with self.assertRaisesRegex(ValueError, 'too large'):
                data.fetch('London')
        with patch.object(data, 'urlopen', side_effect=IncompleteRead(b'partial')):
            with self.assertRaisesRegex(OSError, 'Incomplete weather response'):
                data.fetch('London')


class CacheTests(unittest.TestCase):
    def test_refresh_cache_restart_repeated_reads_and_location_isolation(self) -> None:
        clock, loader = Clock(), MagicMock(return_value=examples.payload())
        with tempfile.TemporaryDirectory() as directory:
            feed = data.Feed('Test city', directory=directory, loader=loader, clock=clock)
            self.assertEqual(feed.get().label, 'WAIT')
            feed.step()
            for _ in range(100):
                feed.get()
                feed.step()
            loader.assert_called_once_with('Test city')
            self.assertEqual(feed.get().label, 'LIVE')
            restarted = data.Feed('Test city', directory=directory, loader=loader, clock=clock)
            restarted.step()
            self.assertEqual(restarted.get().report, feed.get().report)
            self.assertEqual(loader.call_count, 1)
            clock.now += data.REFRESH - 1
            restarted.step()
            self.assertEqual(loader.call_count, 1)
            clock.now += 1
            restarted.step()
            self.assertEqual(loader.call_count, 2)
            other = data.Feed('Other city', directory=directory, loader=loader, clock=clock)
            self.assertIsNone(other.get().report)
            self.assertNotEqual(other.path, feed.path)
        with self.assertRaises(ValueError):
            data.Feed(refresh=1)

    def test_failed_request_backoff_survives_restart_without_fake_data(self) -> None:
        clock, loader = Clock(), MagicMock(side_effect=OSError('offline'))
        with tempfile.TemporaryDirectory() as directory:
            feed = data.Feed(directory=directory, loader=loader, clock=clock)
            feed.step()
            self.assertEqual(feed.get(), data.State(None, 'ERR'))
            restarted = data.Feed(directory=directory, loader=loader, clock=clock)
            restarted.step()
            self.assertEqual(loader.call_count, 1)
            clock.now += data.REFRESH
            restarted.step()
            self.assertEqual(loader.call_count, 2)
            clock.now += data.REFRESH * 2 - 1
            restarted.step()
            self.assertEqual(loader.call_count, 2)
            clock.now += 1
            restarted.step()
            self.assertEqual(loader.call_count, 3)

    def test_last_good_data_is_marked_stale_expires_and_recovers(self) -> None:
        clock, loader = Clock(), MagicMock(return_value=examples.payload())
        with tempfile.TemporaryDirectory() as directory:
            feed = data.Feed(directory=directory, loader=loader, clock=clock)
            feed.step()
            good = feed.get().report
            loader.side_effect = ValueError('bad provider JSON')
            clock.now += data.REFRESH
            feed.step()
            self.assertEqual(feed.get(), data.State(good, 'OLD'))
            clock.now += data.MAX_AGE
            self.assertEqual(feed.get(), data.State(None, 'OLD'))
            loader.side_effect = None
            feed.step()
            self.assertEqual(feed.get().label, 'LIVE')

    def test_background_request_does_not_block_snapshot_and_processes_coalesce(self) -> None:
        clock, entered, release = Clock(), threading.Event(), threading.Event()
        def slow_loader(location: str) -> object:
            entered.set()
            if not release.wait(2):
                raise OSError('test request timed out')
            return examples.payload()
        with tempfile.TemporaryDirectory() as directory:
            loader = MagicMock(side_effect=slow_loader)
            feed = data.Feed(directory=directory, loader=loader, clock=clock)
            worker = threading.Thread(target=feed.step)
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(feed.get().label, 'WAIT')
                second = data.Feed(directory=directory, loader=loader, clock=clock)
                second.step()
                self.assertEqual(loader.call_count, 1)
            finally:
                release.set()
                worker.join(2)
            self.assertFalse(worker.is_alive())
            second.step()
            self.assertEqual(second.get().label, 'LIVE')
            self.assertEqual(loader.call_count, 1)

    def test_corrupt_cache_and_stale_lease_can_recover(self) -> None:
        clock, loader = Clock(), MagicMock(return_value=examples.payload())
        with tempfile.TemporaryDirectory() as directory:
            feed = data.Feed(directory=directory, loader=loader, clock=clock)
            feed.path.write_text('{broken', encoding='utf-8')
            restarted = data.Feed(directory=directory, loader=loader, clock=clock)
            restarted.step()
            self.assertEqual(restarted.get().label, 'LIVE')
            self.assertFalse(restarted.lease.exists())
            clock.now += data.REFRESH
            restarted.lease.write_text('abandoned', encoding='utf-8')
            os.utime(restarted.lease, (clock.now - 121, clock.now - 121))
            restarted.step()
            restarted.step()
            self.assertEqual(loader.call_count, 2)
            self.assertFalse(restarted.lease.exists())


class ViewTests(unittest.TestCase):
    def scene(self) -> views.Display:
        scene = views.Display()
        scene.receive(data.State(data.parse(examples.payload()), 'DEMO'))
        return scene

    def test_dpad_pages_days_details_and_invalid_events(self) -> None:
        scene = self.scene()
        self.assertTrue(scene.buttons(press('down')))
        self.assertEqual(scene.page, 'forecast')
        for day in (1, 2, 0):
            self.assertTrue(scene.buttons(press('right')))
            self.assertEqual(scene.day_index, day)
        scene.buttons(press('left'))
        self.assertEqual(scene.day_index, 2)
        scene.buttons(press('down'))
        self.assertEqual(scene.page, 'info')
        scene.buttons(press('right'))
        self.assertEqual(scene.details, 1)
        for invalid in (press('up', active=False), press('up', lost=True), press('up', 'down'), press()):
            self.assertFalse(scene.buttons(invalid))
            self.assertEqual(scene.page, 'info')
        scene.buttons(press('down'))
        self.assertEqual(scene.page, 'now')
        scene.buttons(press('up'))
        self.assertEqual(scene.page, 'info')

    def test_fields_fit_and_missing_values_never_mean_zero(self) -> None:
        scene = self.scene()
        for page in views.PAGES:
            scene.page_index = views.PAGES.index(page)
            for details in (0, 1):
                scene.details = details
                text, _ = scene.content()
                boxes = canvas.Layout(views.layout(page))
                for name, value in text.items():
                    slots = views.layout(page)['text']
                    columns = slots[name]['width'] // (6 if slots[name]['font'] == 'medium' else 4)
                    self.assertLessEqual(len(value), columns, (page, name, value))
                    boxes.encode_text(name, value)
        scene.receive(data.State(None, 'ERR'))
        scene.page_index = 0
        self.assertEqual(scene.content()[0]['temperature'], '--°C')
        scene.page_index = 1
        self.assertIn('--%', scene.content()[0]['row2'])
        self.assertEqual(scene.content()[0]['feed'], 'ERR')

    def test_pages_preserve_local_back_animation_and_recover_failed_commit(self) -> None:
        scene, client = self.scene(), MagicMock()
        scene.install(client)
        client.show.assert_called_once()
        client.reset_mock()
        scene.buttons(press('down'))
        scene.buttons(press('right'))  # Tomorrow: snow.
        scene.update(client, 0)
        self.assertEqual(client.frame.call_args.args[0], canvas.image_frame(sprite('Snow', 0)))
        client.show.assert_not_called()
        client.transaction.return_value.__exit__.side_effect = TimeoutError('uncertain commit')
        with self.assertRaises(TimeoutError):
            scene.update(client, .1)
        self.assertIsNone(scene.installed)
        self.assertEqual(scene.last, {})
        client.transaction.return_value.__exit__.side_effect = None
        client.reset_mock()
        scene.update(client, 0)
        client.layout.assert_called_once()
        client.show.assert_not_called()

    def test_invalid_elapsed_does_not_mutate_or_publish_the_scene(self) -> None:
        scene, client = self.scene(), MagicMock()
        for elapsed in (-1.0, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                scene.update(client, elapsed)
        self.assertEqual(scene.phase, 0)
        client.transaction.assert_not_called()

    def test_each_page_renders_through_the_real_canvas_protocol(self) -> None:
        binary = ROOT / ('target/debug/simulaitor.exe' if sys.platform == 'win32' else 'target/debug/simulaitor')
        with tempfile.TemporaryDirectory() as directory:
            for page in views.PAGES:
                with self.subTest(page=page):
                    snapshot = Path(directory) / (page + '.ppm')
                    process = subprocess.Popen([str(binary), '--headless', '--canvas-listen', '127.0.0.1:0',
                                                '--frames', '180', '--snapshot', str(snapshot)],
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    try:
                        assert process.stdout is not None
                        line = process.stdout.readline().strip()
                        self.assertTrue(line.startswith('Canvas listening on 127.0.0.1:'), line)
                        with canvas.Client('tcp://' + line.split()[-1]) as client:
                            scene = self.scene()
                            scene.install(client)
                            scene.page_index = views.PAGES.index(page)
                            scene.update(client, 0)
                        stdout, stderr = process.communicate(timeout=6)
                        self.assertEqual(process.returncode, 0, stdout + stderr)
                        with Image.open(snapshot) as image:
                            rendered = canvas.image_frame(image)
                        expected = canvas.image_frame(sprite('Light rain', 0))
                        for y in range(24):
                            start, end = (y * 64 + 40) * 2, (y * 64 + 64) * 2
                            self.assertEqual(rendered[start:end], expected[start:end])
                    finally:
                        if process.poll() is None:
                            process.terminate()
                            process.communicate(timeout=3)


if __name__ == '__main__':
    unittest.main()
