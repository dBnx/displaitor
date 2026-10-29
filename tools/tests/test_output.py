"""Exhaustive output LUT and actual Canvas wire/renderer checks; no board."""

from __future__ import annotations

from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import serial

from displaitor_tools import canvas
from displaitor_tools.output import OutputGamma, USB_GAMMA
from displaitor_tools.paths import ROOT
from tests.test_canvas_buttons import ScriptedSocket
from tests.test_canvas_serial import SerialPort


class GammaTests(unittest.TestCase):
    def test_all_rgb565_values_match_reference_power_curve_without_channel_bleed(self) -> None:
        # Independent scalar reference, including primary/secondary endpoints,
        # arbitrary mixed colours and exact little-endian byte order.
        for exponent in (1.0, 1.8, 2.4, 2.6, 2.8, 3.0):
            gamma = OutputGamma(exponent)
            raw = struct.pack('<65536H', *range(65536))
            expected = []
            for value in range(65536):
                r, g, b = value >> 11, value >> 5 & 63, value & 31
                expected.append(round((r / 31) ** exponent * 31) << 11 |
                                round((g / 63) ** exponent * 63) << 5 |
                                round((b / 31) ** exponent * 31))
            self.assertEqual(gamma.frame(raw), struct.pack('<65536H', *expected))
            self.assertEqual([gamma.color(value) for value in range(65536)], expected)
        self.assertIs(OutputGamma(1).frame(raw), raw)
        self.assertEqual(OutputGamma(2.4).color(0), 0)
        self.assertEqual(OutputGamma(2.4).color(65535), 65535)
        self.assertLess(OutputGamma(2.4).color(canvas.color565('#808080')), canvas.color565('#808080'))

    def test_usb_defaults_correct_once_and_manual_override_is_identity(self) -> None:
        for override, exponent in ((None, USB_GAMMA), (1.0, 1.0), (2.2, 2.2)):
            port = SerialPort()
            color = canvas.color565('#A08060')
            with patch.object(serial, 'Serial', return_value=port):
                with canvas.Client('COM6', gamma=override) as client:
                    self.assertEqual(client.gamma, exponent)
                    client.fill('#A08060')
                    client.frame(struct.pack('<H', color) * 2048)
                requests = [canvas.cobs_decode(data[:-1]) for data in port.writes if data != b'\0']
                wanted = struct.pack('<H', OutputGamma(exponent).color(color))
                self.assertEqual(requests[-2][4:-4], wanted)
                self.assertEqual(requests[-1][4:-4], wanted * 2048)
                self.assertEqual(port.reconfigurations, [])

    def test_all_colour_commands_share_output_transform_and_layout_identity(self) -> None:
        source = {'text': {'value': {'color': '#808080', 'background': '#604020', 'text': '1%'}}}
        for exponent in (None, 1.0, 2.4):
            connection = ScriptedSocket()
            gamma = OutputGamma(exponent or 1.0)
            with patch.object(canvas.socket, 'create_connection', return_value=connection):
                with canvas.Client('tcp://127.0.0.1:7777', source, gamma=exponent) as client:
                    self.assertEqual(client.gamma, exponent or 1.0)
                    client.layout(source)
                    layout = canvas.Layout(source, output=gamma)
                    self.assertEqual(connection.requests[-1][2], layout.payload)
                    # Do not merely compare two Layout objects: inspect the
                    # actual 16-bit foreground/background words in the record.
                    self.assertEqual(struct.unpack_from('<H', layout.payload, 15)[0],
                                     gamma.color(canvas.color565('#808080')))
                    self.assertEqual(struct.unpack_from('<H', layout.payload, 18)[0],
                                     gamma.color(canvas.color565('#604020')))
                    client.style('value', '#808080', '#604020')
                    self.assertEqual(connection.requests[-1][2], layout.reference('value') +
                                     struct.pack('<HBH', gamma.color(canvas.color565('#808080')), 1,
                                                 gamma.color(canvas.color565('#604020'))))
                    client.style('value', '#808080')
                    self.assertEqual(connection.requests[-1][2][-3:], bytes(3))
                    client.text('value', '100%')
                    self.assertEqual(connection.requests[-1][2], layout.reference('value') + b'100%')

    def test_invalid_gamma_rejected_before_any_connection(self) -> None:
        with patch.object(canvas.socket, 'create_connection') as connect, patch.object(serial, 'Serial') as serial_open:
            for exponent in (0, -1, float('nan'), float('inf')):
                for target in ('COM6', 'tcp://127.0.0.1:7777'):
                    with self.assertRaisesRegex(ValueError, 'gamma'):
                        canvas.Client(target, gamma=exponent)
            connect.assert_not_called()
            serial_open.assert_not_called()

    def test_explicit_gamma_frame_and_text_render_in_real_canvas_without_double_application(self) -> None:
        binary = ROOT / ('target/debug/simulaitor.exe' if sys.platform == 'win32' else 'target/debug/simulaitor')
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / 'gamma.ppm'
            process = subprocess.Popen([str(binary), '--headless', '--canvas-listen', '127.0.0.1:0',
                                        '--frames', '130', '--snapshot', str(snapshot)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                assert process.stdout is not None
                line = process.stdout.readline().strip()
                self.assertTrue(line.startswith('Canvas listening on 127.0.0.1:'), line)
                with canvas.Client('tcp://' + line.split()[-1], gamma=2.4) as client:
                    with client.transaction():
                        client.layout({'text': {'label': {'x': 40, 'y': 0, 'width': 24, 'height': 6,
                                                         'color': '#808080', 'background': '#604020', 'text': 'A'}}})
                        client.frame(canvas.image_frame(Image.new('RGB', (64, 32), '#A08060')))
                        client.show()
                stdout, stderr = process.communicate(timeout=6)
                self.assertEqual(process.returncode, 0, stdout + stderr)
                with Image.open(snapshot) as image:
                    colors = set(struct.unpack('<2048H', canvas.image_frame(image)))
                    self.assertEqual(colors, {OutputGamma(2.4).color(canvas.color565(color))
                                              for color in ('#A08060', '#808080', '#604020')})
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=3)


if __name__ == '__main__':
    unittest.main()
