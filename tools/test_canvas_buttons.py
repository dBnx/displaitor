"""Canvas button SDK checks using a scripted socket; never opens a real port."""
from collections import deque
from dataclasses import FrozenInstanceError
import struct
import threading
import time
import unittest
from unittest.mock import patch
import zlib

import canvas


def wire(body):
    return canvas.cobs_encode(body + struct.pack("<I", zlib.crc32(body)))


def ack(sequence, status=0):
    return wire(struct.pack("<BBH5BI", 1, 0x80, sequence, status, 64, 32, 8, 64, 123))


def report(sequence, *, state=0x80, events=(), latest=None, flags=0,
           overwritten=0, now=1000, version=1, count=None):
    if latest is None:
        latest = events[-1][0] if events else 0
    body = struct.pack("<BBHBBBBIII", version, 0x81, sequence, 0, state, flags,
                       len(events) if count is None else count, latest, overwritten, now)
    return wire(body + b"".join(struct.pack("<IIB", *event) for event in events))


class ScriptedSocket:
    def __init__(self, scripts=(), *, slow=False):
        self.scripts = deque(scripts)
        self.requests = []
        self.pending = bytearray()
        self.closed = False
        self.slow = slow

    def settimeout(self, _):
        pass

    def setsockopt(self, *_):
        pass

    def close(self):
        self.closed = True

    def sendall(self, data):
        if data == b"\0":
            return
        if self.pending:
            raise AssertionError("request interleaved with an unfinished reply")
        raw = canvas.cobs_decode(data[:-1])
        version, command, sequence = struct.unpack("<BBH", raw[:4])
        if version != 1 or zlib.crc32(raw[:-4]) != struct.unpack("<I", raw[-4:])[0]:
            raise AssertionError("invalid request")
        self.requests.append((command, sequence, raw[4:-4]))
        if command != 10:
            self.pending.extend(ack(sequence))
        else:
            script = self.scripts.popleft()
            self.pending.extend(script(sequence) if callable(script) else report(sequence, **script))

    def recv(self, count):
        if self.slow:
            time.sleep(.0001)
        if not self.pending:
            raise TimeoutError("scripted reply exhausted")
        result = bytes(self.pending[:count])
        del self.pending[:count]
        return result


class ButtonTests(unittest.TestCase):
    def connect(self, *scripts, slow=False):
        connection = ScriptedSocket(scripts, slow=slow)
        with patch.object(canvas.socket, "create_connection", return_value=connection):
            client = canvas.Client("tcp://127.0.0.1:7777")
        self.addCleanup(client.close)
        return client, connection

    def test_baseline_short_tap_order_snapshot_and_immutable_results(self):
        client, connection = self.connect(
            dict(state=0x80, latest=20),
            dict(events=((21, 50, 0x81), (22, 60, 0x80)), latest=22, now=70))
        info = client.info
        initial = client.buttons()
        self.assertTrue(initial.active)
        self.assertEqual(initial.events, ())
        state = client.buttons()
        self.assertEqual(state.held, frozenset())
        self.assertEqual([event.sequence for event in state.events], [21, 22])
        self.assertEqual([event.at_ms for event in state.events], [50, 60])
        self.assertEqual(state.events[0].pressed, frozenset({"a"}))
        self.assertEqual(state.events[1].released, frozenset({"a"}))
        self.assertEqual(state.at_ms, 70)
        self.assertIs(client.info, info)
        self.assertEqual([request[2] for request in connection.requests[1:]], [b"", struct.pack("<I", 20)])
        with self.assertRaises(FrozenInstanceError):
            state.active = False

    def test_paging_keeps_edge_baseline_and_cursor_wraps(self):
        client, connection = self.connect(
            dict(latest=0xFFFFFFFD),
            dict(state=0x80, events=((0xFFFFFFFE, 10, 0x81), (0xFFFFFFFF, 20, 0x80),
                                     (0, 30, 0x82), (1, 40, 0x80)), latest=3, flags=1),
            dict(events=((2, 50, 0x84), (3, 60, 0x80)), latest=3),
            dict(latest=3))
        client.buttons()
        first = client.buttons()
        self.assertTrue(first.more)
        second = client.buttons()
        self.assertEqual([event.sequence for event in first.events + second.events],
                         [0xFFFFFFFE, 0xFFFFFFFF, 0, 1, 2, 3])
        self.assertEqual(second.events[0].pressed, frozenset({"select"}))
        self.assertFalse(second.more)
        self.assertEqual(client.buttons().events, ())
        self.assertEqual([struct.unpack("<I", r[2])[0] for r in connection.requests[2:]],
                         [0xFFFFFFFD, 1, 3])

    def test_paging_uses_last_returned_state_not_current_snapshot(self):
        client, _ = self.connect(
            dict(latest=0),
            dict(state=0x80, events=((1, 10, 0x81),), latest=2, flags=1),
            dict(state=0x80, events=((2, 20, 0x80),), latest=2))
        client.buttons()
        client.buttons()
        self.assertEqual(client.buttons().events[0].released, frozenset({"a"}))

    def test_lost_discards_actions_and_resets_to_latest_snapshot(self):
        client, connection = self.connect(
            dict(latest=1),
            dict(state=0x82, events=((9, 90, 0x81),), latest=15, flags=3, overwritten=7),
            dict(events=((16, 100, 0x80),), latest=16, overwritten=7))
        client.buttons()
        lost = client.buttons()
        self.assertTrue(lost.lost)
        self.assertTrue(lost.more)
        self.assertEqual(lost.overwritten, 7)
        self.assertEqual(lost.held, frozenset({"b"}))
        self.assertEqual(lost.events, ())
        self.assertEqual(client.buttons().events[0].released, frozenset({"b"}))
        self.assertEqual(connection.requests[-1][2], struct.pack("<I", 15))

    def test_mode_edges_suppress_navigation_press_and_release(self):
        client, _ = self.connect(
            dict(state=1, latest=0),
            dict(events=((1, 10, 0x81), (2, 20, 0x80), (3, 30, 0x82),
                         (4, 40, 0x02)), state=2, latest=4),
            dict(events=((5, 50, 0),), state=0, latest=5))
        client.buttons()
        state = client.buttons()
        self.assertFalse(state.active)
        self.assertEqual(state.events[0].pressed, frozenset())
        self.assertEqual(state.events[0].released, frozenset())
        self.assertEqual(state.events[1].released, frozenset({"a"}))
        self.assertEqual(state.events[2].pressed, frozenset({"b"}))
        self.assertEqual(state.events[3].released, frozenset())
        self.assertFalse(state.events[3].active)
        self.assertEqual(client.buttons().events[0].released, frozenset({"b"}))

    def test_new_sessions_always_send_empty_baseline(self):
        first, first_socket = self.connect(dict(state=0x81, latest=9))
        second, second_socket = self.connect(dict(state=0x81, latest=9))
        self.assertEqual(first.buttons().events, ())
        self.assertEqual(second.buttons().events, ())
        self.assertEqual(first_socket.requests[-1][2], b"")
        self.assertEqual(second_socket.requests[-1][2], b"")

    def test_unknown_command_reports_firmware_update_without_changing_info(self):
        client, _ = self.connect(lambda sequence: ack(sequence, status=3))
        info = client.info
        with self.assertRaisesRegex(NotImplementedError, "firmware update required.*buttons"):
            client.buttons()
        self.assertIs(client.info, info)
        self.assertIsNone(client._button_cursor)

    def test_other_errors_keep_existing_value_error(self):
        client, _ = self.connect(lambda sequence: ack(sequence, status=4))
        with self.assertRaisesRegex(ValueError, "invalid value"):
            client.buttons()

    def test_failed_poll_preserves_cursor_for_a_pure_retry(self):
        client, connection = self.connect(
            dict(latest=10), lambda sequence: ack(sequence, status=4),
            dict(events=((11, 50, 0x81), (12, 60, 0x80)), latest=12))
        client.buttons()
        with self.assertRaises(ValueError):
            client.buttons()
        state = client.buttons()
        self.assertEqual([event.sequence for event in state.events], [11, 12])
        self.assertEqual(connection.requests[-2][2], connection.requests[-1][2])

    def test_parser_rejects_crc_sequence_version_count_length_and_oversized_packets(self):
        def noisy(sequence):
            damaged = bytearray(canvas.cobs_decode(report(sequence)[:-1]))
            damaged[-1] ^= 1
            return (canvas.cobs_encode(damaged)
                    + report((sequence + 1) & 0xFFFF)
                    + report(sequence, version=2)
                    + report(sequence, count=1)
                    + report(sequence, events=tuple((i, i, 0x80) for i in range(5)))
                    + b"x" * 10000 + b"\0"
                    + ack(sequence)
                    + report(sequence, latest=42, now=123))
        client, _ = self.connect(noisy)
        self.assertEqual(client.buttons().at_ms, 123)
        self.assertEqual(client._button_cursor, 42)

    def test_button_frames_cannot_acknowledge_drawing_commands(self):
        client, connection = self.connect()
        original = connection.sendall
        def respond(data):
            original(data)
            raw = canvas.cobs_decode(data[:-1])
            sequence = struct.unpack_from("<H", raw, 2)[0]
            connection.pending[:0] = report(sequence)
        connection.sendall = respond
        client.fill("#000000")
        self.assertEqual(client.info["layout_id"], 123)

    def test_shared_connection_serializes_button_polls_and_frame_writes(self):
        client, connection = self.connect(dict(latest=0), *(dict(latest=0) for _ in range(8)), slow=True)
        client.buttons()
        errors = []
        start = threading.Barrier(3)
        def run(operation):
            try:
                start.wait(timeout=2)
                for _ in range(8):
                    operation()
            except BaseException as error:
                errors.append(error)
        poller = threading.Thread(target=run, args=(client.buttons,))
        writer = threading.Thread(target=run, args=(lambda: client.frame(bytes(4096)),))
        poller.start()
        writer.start()
        start.wait(timeout=2)
        poller.join(timeout=3)
        writer.join(timeout=3)
        self.assertFalse(poller.is_alive() or writer.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(connection.requests), 18)
        self.assertEqual(client.info["width"], 64)


if __name__ == "__main__":
    unittest.main()
