"""Fixed COM settings, fragmented replies and bounded ACK deadlines; no board."""

from __future__ import annotations

from collections import deque
from collections.abc import Buffer
import struct
import unittest
from unittest.mock import patch

import serial
from serial.serialutil import SerialBase

from displaitor_tools import canvas
from tests.test_canvas_buttons import ack, report


class SerialPort(SerialBase):
    """Use pyserial's real settings setters; only the transport is simulated."""

    def __init__(self, *, timeout: float = .05) -> None:
        self.read_timeouts: list[float] = []
        self.reconfigurations: list[float | None] = []
        self.pending: deque[bytes] = deque()
        self.now = 0.0
        self.byte_latency = 0.0
        self.stall = False
        self.writes: list[bytes] = []
        self.close_count = 0
        super().__init__(port='COM6', timeout=timeout, write_timeout=3)

    def open(self) -> None:
        self.is_open = True

    def _reconfigure_port(self) -> None:
        # SerialBase.timeout invokes this even for an identical value. The
        # Windows backend reapplies COM settings here, not just a Python field.
        self.reconfigurations.append(self.timeout)

    @property
    def closed(self) -> bool:
        return not self.is_open

    def write(self, data: Buffer, /) -> int:
        data = bytes(memoryview(data))
        self.writes.append(data)
        if data != b'\0' and not self.stall:
            raw = canvas.cobs_decode(data[:-1])
            sequence = struct.unpack('<H', raw[2:4])[0]
            response = report(sequence) if raw[1] == 10 else ack(sequence)
            # Empty reads both before and within an otherwise valid response.
            self.pending.extend((b'', b''))
            for byte in response:
                self.pending.extend((bytes([byte]), b''))
        return len(data)

    def read(self, size: int = 1) -> bytes:
        assert size == 1
        timeout = self.timeout
        assert timeout is not None
        self.read_timeouts.append(timeout)
        value = self.pending.popleft() if self.pending else b''
        self.now += self.byte_latency if value else timeout
        return value

    def close(self) -> None:
        if self.is_open:
            self.close_count += 1
        self.is_open = False


class SerialTimeoutTests(unittest.TestCase):
    def test_pyserial_fixture_detects_even_identical_timeout_reconfiguration(self) -> None:
        # Guard against repeating the original plain-attribute mock, which hid
        # pyserial's reconfiguration side effect on every timeout assignment.
        port = SerialPort()
        try:
            port.timeout = .05
            self.assertEqual(port.reconfigurations, [.05])
        finally:
            port.close()

    def test_fragmented_ack_buttons_and_audio_keep_com_settings_fixed(self) -> None:
        port = SerialPort()
        with patch.object(serial, 'Serial', return_value=port) as serial_type, \
             patch.object(canvas.time, 'monotonic', side_effect=lambda: port.now):
            with canvas.Client('COM6', timeout=3) as client:
                serial_type.assert_called_once_with('COM6', baudrate=115200, timeout=.05, write_timeout=3)
                assert client.info is not None
                self.assertEqual(client.info['layout_id'], 123)
                client.fill('#000000')
                self.assertTrue(client.buttons().active)
                client.cry('eevee')
                self.assertGreater(port.now, .1)
                self.assertTrue(all(t == .05 for t in port.read_timeouts))
                self.assertEqual(port.reconfigurations, [])
                self.assertEqual(port.write_timeout, 3)
        self.assertTrue(port.closed)
        self.assertEqual(port.close_count, 1)

    def test_ack_in_last_poll_interval_does_not_reconfigure_com(self) -> None:
        port = SerialPort()
        with patch.object(serial, 'Serial', return_value=port), \
             patch.object(canvas.time, 'monotonic', side_effect=lambda: port.now):
            with canvas.Client('COM6', timeout=3) as client:
                # Start the next request's reply just inside its final 50 ms.
                # This also catches the incomplete "only assign if different"
                # fix, whose normal fast replies never change the timeout.
                port.pending.clear()
                port.stall = True
                port.byte_latency = .001
                port.pending.extend([b''] * 59)
                sequence = (client._sequence + 1) & 0xffff
                port.pending.extend(bytes([byte]) for byte in ack(sequence))
                before = port.now
                client.fill('#000000')
                self.assertGreater(port.now - before, 2.95)
                self.assertLess(port.now - before, 3)
                self.assertEqual(port.reconfigurations, [])
                self.assertEqual(port.timeout, .05)

    def test_missing_ack_deadline_is_bounded_and_closes_once_without_retry(self) -> None:
        port = SerialPort()
        with patch.object(serial, 'Serial', return_value=port), \
             patch.object(canvas.time, 'monotonic', side_effect=lambda: port.now):
            client = canvas.Client('COM6', timeout=3)
            port.pending.clear()
            port.stall = True
            port.pending.extend((b'\x02', b'\x01'))
            before, writes = port.now, len(port.writes)
            with self.assertRaisesRegex(TimeoutError, 'did not acknowledge'):
                client.fill('#000000')
            # A fixed polling read may cross the overall deadline by at most
            # one read interval. Avoid reconfiguring COM to trim that last poll.
            self.assertGreaterEqual(port.now - before, 3)
            self.assertLessEqual(port.now - before, 3.05 + 1e-9)
            self.assertEqual(port.reconfigurations, [])
            self.assertEqual(len(port.writes), writes + 1)
            self.assertTrue(port.closed)
            self.assertEqual(port.close_count, 1)
            self.assertIsNone(client.info)
            client.close()
            self.assertEqual(port.close_count, 1)

    def test_short_configured_deadline_uses_short_fixed_poll_at_open(self) -> None:
        port = SerialPort(timeout=.01)
        port.stall = True
        with patch.object(serial, 'Serial', return_value=port) as serial_type, \
             patch.object(canvas.time, 'monotonic', side_effect=lambda: port.now):
            with self.assertRaises(TimeoutError):
                canvas.Client('COM6', timeout=.01)
            serial_type.assert_called_once_with('COM6', baudrate=115200, timeout=.01, write_timeout=.01)
        self.assertAlmostEqual(port.now, .01)
        self.assertEqual(port.reconfigurations, [])
        self.assertTrue(port.closed)
        self.assertEqual(port.close_count, 1)


if __name__ == '__main__':
    unittest.main()
