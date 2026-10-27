"""Host-only protocol/helper checks. Never opens a serial port."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import threading
from unittest.mock import Mock, patch
import unittest
import zlib

import canvas

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "tools/layouts/weather.json"


class HelperTests(unittest.TestCase):
    def test_cobs_full_range_and_block_boundaries(self):
        for data in [b"", b"\0", bytes(range(256)), b"a" * 254, b"a" * 255, bytes(4096), b"\xff" * 4104]:
            encoded = canvas.cobs_encode(data)
            self.assertNotIn(0, encoded[:-1])
            self.assertEqual(canvas.cobs_decode(encoded[:-1]), data)
        for data in [b"\0", b"\x04ab"]:
            with self.assertRaises(ValueError):
                canvas.cobs_decode(data)

    def test_colour_and_utf8_validation(self):
        self.assertEqual(canvas.color565("#FF0000"), 0xF800)
        self.assertEqual(canvas.color565("#00FF00"), 0x07E0)
        self.assertEqual(canvas.color565("#0000FF"), 0x001F)
        self.assertEqual(canvas.text_bytes("18°C"), b"18\xc2\xb0C")
        for color in ["red", "#123", "#00000_", "#-00001", None]:
            with self.assertRaises(ValueError):
                canvas.color565(color)
        for text in ["🦀", "\n", "a" * 65, "é" * 33]:
            with self.assertRaises(ValueError):
                canvas.text_bytes(text)

    def test_layout_identifiers_include_names_order_and_properties(self):
        original = canvas.Layout({"text": {"one": {}, "two": {}}})
        self.assertEqual(original.id, canvas.Layout({"text": {"one": {}, "two": {}}}).id)
        self.assertNotEqual(original.id, canvas.Layout({"text": {"two": {}, "one": {}}}).id)
        self.assertNotEqual(original.id, canvas.Layout({"text": {"three": {}, "two": {}}}).id)
        self.assertNotEqual(original.id, canvas.Layout({"text": {"one": {"color": "#FF0000"}, "two": {}}}).id)
        self.assertEqual(original.id, zlib.crc32(original.payload[4:]))
        with self.assertRaises(ValueError):
            original.reference("unknown")

    def test_invalid_layouts_fail_before_connection(self):
        for data in [{}, {"text": []}, {"text": {"bad": {"font": "giant"}}},
                     {"text": {"bad": {"x": 64}}}, {"text": {"bad": {"width": 0}}},
                     {"text": {"bad": {"x": True}}}, {"text": {"bad": {"colour": "#FFFFFF"}}},
                     {"text": {str(i): {} for i in range(9)}}]:
            with self.assertRaises(ValueError):
                canvas.Layout(data)

    def test_right_alignment_reserves_cells_and_includes_policy_in_layout_id(self):
        source = {"text": {"value": {"width": 24, "font": "medium", "text": "100%"}}}
        left = canvas.Layout(source)
        source["text"]["value"]["align"] = "left"
        self.assertEqual(left.id, canvas.Layout(source).id)
        source["text"]["value"]["align"] = "right"
        right = canvas.Layout(source)
        self.assertNotEqual(left.id, right.id)  # Even when initial text fills the box.
        for value, expected in (("1%", b"  1%"), ("10%", b" 10%"), ("100%", b"100%"),
                                ("--%", b" --%"), ("", b"    ")):
            self.assertEqual(right.encode_text("value", value), expected)
        for value in ("1000%", "bad\n", "🦀"):
            with self.assertRaises(ValueError):
                right.encode_text("value", value)
        # Character cells, rather than UTF-8 byte counts, determine padding.
        temperature = canvas.Layout(LAYOUT)
        for value in ("1°C", "18°C", "-1°C", "-18°C", "-100°C", "-2.5°C"):
            encoded = temperature.encode_text("temperature", value)
            self.assertEqual(len(encoded.decode("utf-8")), 6)
            self.assertTrue(encoded.endswith("°C".encode()))
        for definition in ({"align": "center"}, {"align": "right", "width": 3},
                           {"align": "right", "width": 16, "text": "12345"}):
            with self.assertRaises(ValueError):
                canvas.Layout({"text": {"bad": definition}})

    def test_image_fit_alpha_and_channel_order(self):
        from PIL import Image
        image = Image.new("RGBA", (64, 32), (255, 0, 0, 255))
        self.assertEqual(canvas.image_frame(image), b"\0\xf8" * 2048)
        self.assertEqual(canvas.image_frame(Image.new("RGBA", (64, 32), (255, 255, 255, 0))), bytes(4096))
        square = Image.new("RGB", (8, 8), (0, 255, 0))
        contain = canvas.image_frame(square)
        self.assertEqual(contain[:32], bytes(32))
        self.assertEqual(canvas.image_frame(square, fit="cover"), b"\xe0\x07" * 2048)


class TransactionTests(unittest.TestCase):
    def client(self):
        client = canvas.Client.__new__(canvas.Client)
        client._lock = threading.RLock()
        client._transaction_depth = 0
        client._transaction_failed = False
        client._connection = Mock()
        client._layout = canvas.Layout({"text": {"old": {}}})
        client.info = {"layout_id": client._layout.id}
        client._exchange = Mock(return_value={"layout_id": 123})
        return client

    def test_named_updates_use_alignment_and_reject_overflow_before_writing(self):
        client = self.client()
        client.layout({"text": {"value": {"width": 24, "font": "medium", "align": "right", "text": "1%"}}})
        self.assertTrue(client._exchange.call_args.args[1].endswith(b"  1%"))
        client._exchange.reset_mock()
        client.text("value", "100%")
        self.assertEqual(client._exchange.call_args.args[1], client._layout.reference("value") + b"100%")
        client.text("value", "1%")
        self.assertEqual(client._exchange.call_args.args[1], client._layout.reference("value") + b"  1%")
        client._exchange.reset_mock()
        with self.assertRaisesRegex(ValueError, "fits at most 4"):
            with client.transaction():
                client.text("value", "1000%")
        self.assertEqual([c.args[0] for c in client._exchange.call_args_list], [7, 9])

    def test_nested_success_commits_once_and_exception_restores_host_mapping(self):
        client = self.client()
        old_layout, old_info = client._layout, client.info
        with self.assertRaisesRegex(ValueError, "cancel"):
            with client.transaction():
                client.layout({"text": {"new": {}}})
                with client.transaction():
                    client.text("new", "staged")
                raise ValueError("cancel")
        self.assertIs(client._layout, old_layout)
        self.assertIs(client.info, old_info)
        self.assertEqual([c.args[0] for c in client._exchange.call_args_list], [7, 2, 3, 9])
        client._exchange.reset_mock()
        with client.transaction():
            with client.transaction():
                client.fill("#FF0000")
        self.assertEqual([c.args[0] for c in client._exchange.call_args_list], [7, 5, 8])

    def test_caught_inner_or_validation_error_still_aborts_outer_transaction(self):
        for nested in (True, False):
            client = self.client()
            with self.assertRaisesRegex(RuntimeError, "earlier operation failed"):
                with client.transaction():
                    try:
                        if nested:
                            with client.transaction():
                                raise ValueError("inner failed")
                        else:
                            client.text("old", "\n")
                    except ValueError:
                        pass
            self.assertEqual([c.args[0] for c in client._exchange.call_args_list], [7, 9])

    def test_caught_image_and_stream_failures_poison_transaction(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            image = directory / "valid.png"
            Image.new("RGB", (64, 32)).save(image)
            corrupt = directory / "corrupt.png"
            corrupt.write_bytes(b"not an image")
            cases = [
                lambda client: client.background(directory / "missing.png"),
                lambda client: client.background(image, fit="invalid"),
                lambda client: client.stream([image], fps=0),
                lambda client: client.stream([corrupt]),
                lambda client: client.stream([image], fit="invalid"),
                lambda client: client.stream([]),
            ]
            for operation in cases:
                client = self.client()
                with self.assertRaisesRegex(RuntimeError, "earlier operation failed"):
                    with client.transaction():
                        client.fill("#FF0000")
                        try:
                            operation(client)
                        except (OSError, ValueError):
                            pass
                self.assertEqual([c.args[0] for c in client._exchange.call_args_list], [7, 5, 9])

    def test_async_streaming_inside_transaction_fails_promptly_and_poisons_scope(self):
        # A subprocess deadline ensures regressions cannot deadlock the test suite.
        script = """
from test_canvas import TransactionTests
client = TransactionTests().client()
try:
    with client.transaction():
        try:
            with client.streaming([]):
                raise AssertionError('streaming started inside transaction')
        except RuntimeError as error:
            assert 'outside the transaction' in str(error), str(error)
except RuntimeError as error:
    assert 'earlier operation failed' in str(error), str(error)
else:
    raise AssertionError('transaction committed after rejected streaming')
assert [c.args[0] for c in client._exchange.call_args_list] == [7, 9]
"""
        result = subprocess.run([sys.executable, "-c", script], cwd=ROOT / "tools",
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_concurrent_writer_waits_until_entire_transaction_commits(self):
        client = self.client()
        started, finished = threading.Event(), threading.Event()
        def write():
            started.set()
            client.fill("#0000FF")
            finished.set()
        with client.transaction():
            client.fill("#FF0000")
            thread = threading.Thread(target=write)
            thread.start()
            self.assertTrue(started.wait(1))
            self.assertFalse(finished.wait(.05))
            client.text("old", "scene")
        thread.join(timeout=1)
        self.assertTrue(finished.is_set())
        self.assertEqual([c.args[0] for c in client._exchange.call_args_list], [7, 5, 3, 8, 5])

    def test_commit_timeout_invalidates_connection_and_cached_device_info(self):
        client = self.client()
        connection = client._connection
        client._exchange.side_effect = [{"layout_id": 123}, TimeoutError("uncertain commit")]
        with self.assertRaisesRegex(TimeoutError, "uncertain commit"):
            with client.transaction():
                pass
        connection.close.assert_called_once()
        self.assertIsNone(client.info)
        self.assertIsNone(client._connection)
        with self.assertRaisesRegex(ConnectionError, "closed"):
            client.fill("#000000")

    def test_old_firmware_has_clear_update_error_without_nonatomic_fallback(self):
        connection = Mock()
        def reply(request):
            if request == b"\0":
                return
            raw = canvas.cobs_decode(request[:-1])
            response = bytes((1, 0x80)) + raw[2:4] + bytes((3, 64, 32, 8, 64)) + bytes(4)
            connection.recv.side_effect = [bytes((b,)) for b in canvas.cobs_encode(
                response + canvas.struct.pack("<I", zlib.crc32(response)))]
        connection.sendall.side_effect = reply
        with patch.object(canvas.socket, "create_connection", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "firmware update required.*transactions"):
                canvas.Client("tcp://127.0.0.1:7777")
        connection.close.assert_called_once()


class SimulatorTests(unittest.TestCase):
    """Real Rust engine/renderer and Python client, connected only over loopback."""
    def test_end_to_end_background_named_text_stream_reconnect_and_snapshot(self):
        binary = ROOT / ("target/debug/simulaitor.exe" if sys.platform == "win32" else "target/debug/simulaitor")
        if not binary.exists():
            self.fail("first run: cargo build -p simulaitor --no-default-features")
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            snapshot = directory / "frame.ppm"
            process = subprocess.Popen([str(binary), "--headless", "--canvas-listen", "127.0.0.1:0",
                                        "--frames", "240", "--snapshot", str(snapshot)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                line = process.stdout.readline().strip()
                self.assertTrue(line.startswith("Canvas listening on 127.0.0.1:"), line)
                target = "tcp://" + line.split()[-1]
                with canvas.Client(target) as client:
                    self.assertEqual(client.info["width"], 64)
                    with client.transaction():
                        client.layout(LAYOUT)
                        with client.transaction():
                            client.fill("#0000FF")
                    old_info, old_layout = client.info, client._layout
                    with self.assertRaisesRegex(ValueError, "cancel scene"):
                        with client.transaction():
                            client.layout({"text": {"abandoned": {}}})
                            self.assertNotEqual(client.info["layout_id"], old_info["layout_id"])
                            client.fill("#FF0000")
                            raise ValueError("cancel scene")
                    self.assertIs(client._layout, old_layout)
                    self.assertEqual(client._request(0), old_info)
                    client.text("temperature", "21°C")
                    client.style("temperature", "#FF0000")
                    self.assertEqual(client._request(0)["layout_id"], canvas.Layout(LAYOUT).id)
                    frame = directory / "green.png"
                    Image.new("RGB", (64, 32), (0, 255, 0)).save(frame)
                    client.background(frame)
                    # Stream two actual GIF frames and update text concurrently on one client.
                    animation = directory / "frames.gif"
                    Image.new("RGB", (64, 32), (255, 0, 0)).save(animation, save_all=True,
                              append_images=[Image.new("RGB", (64, 32), (0, 0, 255))], duration=50, loop=0)
                    with client.streaming(animation, fps=60):
                        client.text("status", "LIVE")
                        time.sleep(0.08)
                    client.frame(b"\x1f\0" * 2048)
                    # Keep this transport/renderer fixture independent of the
                    # example layout's palette.
                    client.style("title", "#FFFFFF", "#000000")
                    client.text("title", "A")
                    # Layout mismatch NACK does not damage the retained scene.
                    wrong = canvas.Layout({"text": {"wrong": {}}})
                    with self.assertRaisesRegex(ValueError, "layout mismatch"):
                        client._request(3, wrong.reference("wrong") + b"NO")
                # Fresh helper connection maps names without replacing the uploaded scene.
                with canvas.Client(target, LAYOUT) as client:
                    client.text("temperature", "9")
                    client.style("status", "#00FF00", "#FF0000")
                # CLI uses the same protocol and explicit target.
                result = subprocess.run([sys.executable, str(ROOT / "tools/canvas.py"), "--port", target,
                                         "--layout", str(LAYOUT), "text", "status", "OK"],
                                        capture_output=True, text=True, timeout=3)
                self.assertEqual(result.returncode, 0, result.stderr)
                stdout, stderr = process.communicate(timeout=6)
                self.assertEqual(process.returncode, 0, stderr + stdout)
                with Image.open(snapshot) as image:
                    self.assertEqual(image.size, (64, 32))
                    self.assertEqual(image.getpixel((63, 31)), (0, 0, 255))
                    pixels = image.tobytes()
                    colors = set(zip(pixels[0::3], pixels[1::3], pixels[2::3]))
                    self.assertTrue({(255, 255, 255), (255, 0, 0), (0, 255, 0)} <= colors)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=3)


if __name__ == "__main__":
    unittest.main()
