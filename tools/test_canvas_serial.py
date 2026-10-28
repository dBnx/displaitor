"""Windows-style short COM reads preserve framing and the overall ACK timeout."""
from collections import deque
import struct
import unittest
from unittest.mock import patch

import canvas
from test_canvas_buttons import ack


class SerialPort:
    def __init__(self):
        self.timeout = None
        self.read_timeouts = []
        self.pending = deque()
        self.closed = False
        self.now = 0.0
        self.stall = False
        self.writes = []

    def write(self, data):
        self.writes.append(data)
        if data != b'\0' and not self.stall:
            raw = canvas.cobs_decode(data[:-1])
            sequence = struct.unpack('<H', raw[2:4])[0]
            # Empty reads both before and within an otherwise valid response.
            self.pending.extend((b'', b''))
            for byte in ack(sequence):
                self.pending.extend((bytes([byte]), b''))
        return len(data)

    def read(self, count):
        assert count == 1
        self.read_timeouts.append(self.timeout)
        value = self.pending.popleft() if self.pending else b''
        if not value:
            self.now += self.timeout
        return value

    def close(self):
        self.closed = True


class SerialTimeoutTests(unittest.TestCase):
    def test_short_windows_reads_preserve_a_fragmented_ack_and_full_write_timeout(self):
        import serial
        port = SerialPort()
        with patch.object(serial, 'Serial', return_value=port) as serial_type, \
             patch.object(canvas.time, 'monotonic', side_effect=lambda: port.now):
            with canvas.Client('COM6', timeout=3) as client:
                serial_type.assert_called_once_with('COM6', baudrate=115200, timeout=.05, write_timeout=3)
                self.assertEqual(client.info['layout_id'], 123)
                client.fill('#000000')
                self.assertGreater(port.now, .1)
                self.assertTrue(all(0 < t <= .05 for t in port.read_timeouts))
        self.assertTrue(port.closed)

    def test_partial_or_missing_ack_expires_at_the_overall_deadline_and_closes_once(self):
        import serial
        port = SerialPort()
        with patch.object(serial, 'Serial', return_value=port), \
             patch.object(canvas.time, 'monotonic', side_effect=lambda: port.now):
            client = canvas.Client('COM6', timeout=3)
            port.pending.clear()
            port.stall = True
            port.pending.extend((b'\x02', b'\x01'))  # An unfinished COBS packet.
            before = port.now
            writes = len(port.writes)
            with self.assertRaisesRegex(TimeoutError, 'did not acknowledge'):
                client.fill('#000000')
            self.assertAlmostEqual(port.now - before, 3)
            self.assertEqual(len(port.writes), writes + 1)  # No automatic retry.
            self.assertTrue(port.closed)
            self.assertIsNone(client.info)

    def test_a_shorter_configured_deadline_is_not_extended_to_fifty_ms(self):
        import serial
        port = SerialPort()
        port.stall = True
        with patch.object(serial, 'Serial', return_value=port) as serial_type, \
             patch.object(canvas.time, 'monotonic', side_effect=lambda: port.now):
            with self.assertRaises(TimeoutError):
                canvas.Client('COM6', timeout=.01)
            serial_type.assert_called_once_with('COM6', baudrate=115200, timeout=.01, write_timeout=.01)
        self.assertAlmostEqual(port.now, .01)
        self.assertTrue(port.closed)


if __name__ == '__main__':
    unittest.main()
