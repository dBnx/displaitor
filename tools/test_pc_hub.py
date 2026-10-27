"""PC hub checks: fixtures and loopback simulator only; never opens a serial port."""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, Mock, call, patch

import canvas
import pc_hub

ROOT = Path(__file__).resolve().parents[1]


def sample(cpu=42, ram=67, gpu=83):
    return pc_hub.Sample(cpu, ram, gpu, datetime(2026, 10, 19, 12, 34))


def port(device, vid=0x16c0, pid=0x27dd, serial_number="canvas-1", product="Displaitor Canvas"):
    return SimpleNamespace(device=device, vid=vid, pid=pid, serial_number=serial_number, product=product)


class HubTests(unittest.TestCase):
    def test_auto_selection_excludes_probe_uart_and_unrelated_shared_ids(self):
        probe = port("/dev/probe-uart", 0x2e8a, 0x000c, "TEST-PROBE-0001", "Debugprobe")
        unrelated = port("/dev/other", serial_number="other", product="Other device")
        with self.assertRaises(ConnectionError):
            pc_hub.resolve_port(ports=[probe, unrelated])
        self.assertEqual(pc_hub.resolve_port(ports=[probe, unrelated, port("/dev/canvas")]), "/dev/canvas")
        with self.assertRaisesRegex(ValueError, "multiple"):
            pc_hub.resolve_port(ports=[port("/dev/one"), port("/dev/two")])
        self.assertEqual(pc_hub.resolve_port("tcp://127.0.0.1:7777", ports=[]), "tcp://127.0.0.1:7777")

    def test_gpu_sysfs_handles_missing_invalid_and_temporarily_unreadable_counters(self):
        with tempfile.TemporaryDirectory() as directory, patch("pc_hub.sys.platform", "linux"):
            root = Path(directory)
            counter = root / "card1/device/gpu_busy_percent"
            counter.parent.mkdir(parents=True)
            counter.write_text("37\n")
            memory = counter.with_name("mem_info_vram_used")
            memory.write_text(str(256 * pc_hub.MIB))
            gpu = pc_hub.GPU("auto", drm=root)
            self.assertEqual(gpu.name, "AMD card1")
            self.assertEqual(gpu.read(), pc_hub.GPUReading(37, 256 * pc_hub.MIB))
            for invalid in ("nan", "101", "-1", "N/A", ""):
                counter.write_text(invalid)
                self.assertEqual(gpu.read(), pc_hub.GPUReading(None, 256 * pc_hub.MIB))
            counter.unlink()
            self.assertEqual(gpu.read().vram_used, 256 * pc_hub.MIB)
            memory.unlink()
            self.assertEqual(gpu.read(), pc_hub.GPUReading())
            self.assertEqual(pc_hub.GPU("none", drm=root).read(), pc_hub.GPUReading())
            with self.assertRaises(ValueError):
                pc_hub.GPU("card1", drm=root)

    def test_nvidia_utility_is_bounded_and_unavailable_is_not_zero(self):
        with patch("pc_hub.shutil.which", return_value="/fake/nvidia-smi"), \
             patch("pc_hub.subprocess.run") as run:
            gpu = pc_hub.GPU("nvidia:2")
            run.return_value = SimpleNamespace(returncode=0, stdout="78,2048.5\n")
            self.assertEqual(gpu.read(), pc_hub.GPUReading(78, int(2048.5 * pc_hub.MIB)))
            self.assertIn("--id=2", run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs["timeout"], 1)
            run.side_effect = subprocess.TimeoutExpired("nvidia-smi", 1)
            self.assertEqual(gpu.read(), pc_hub.GPUReading())
            run.side_effect = None
            run.return_value = SimpleNamespace(returncode=0, stdout="[Not Supported],N/A")
            self.assertEqual(gpu.read(), pc_hub.GPUReading())
            run.return_value = SimpleNamespace(returncode=0, stdout="78,N/A")
            self.assertEqual(gpu.read(), pc_hub.GPUReading(78))

    def test_vram_fits_eight_glyphs_and_never_fabricates_a_reading(self):
        for value, expected in [(None, "--"), (-1, "--"), (float("nan"), "--"),
                                (0, "0 MiB"), (512 * pc_hub.MIB, "512 MiB"),
                                (int(4.2 * pc_hub.GIB), "4.2 GiB"), (24 * pc_hub.GIB, "24 GiB")]:
            self.assertEqual(pc_hub.vram_text(value), expected)
        for value in (999.6 * pc_hub.MIB, 9.999 * pc_hub.GIB, 999.9 * pc_hub.GIB, 1024 ** 7):
            self.assertLessEqual(len(pc_hub.vram_text(value)), 8)

    def test_windows_com_fallback_requires_board_ids_and_handles_ambiguity(self):
        with patch("pc_hub.sys.platform", "win32"):
            unknown = port("COM12", serial_number=None, product=None)
            self.assertEqual(pc_hub.resolve_port(ports=[unknown]), "COM12")
            with self.assertRaisesRegex(ValueError, "multiple"):
                pc_hub.resolve_port(ports=[unknown, port("COM3", serial_number=None, product="USB Serial Device")])
            with self.assertRaises(ConnectionError):
                pc_hub.resolve_port(ports=[port("COM2", 0x2e8a, 0x000c, None, None)])

    def test_windows_busiest_engine_and_adapter_memory_stay_on_same_gpu(self):
        adapter = "luid_0x00000000_0x00001234_phys_0"
        other = "luid_0x00000000_0x00005678_phys_0"
        data = {"engines": [
            {"Name": f"pid_1_{adapter}_eng_0_engtype_3D", "UtilizationPercentage": 30},
            {"Name": f"pid_2_{adapter}_eng_0_engtype_3D", "UtilizationPercentage": 40},
            {"Name": f"pid_3_{adapter}_eng_1_engtype_Copy", "UtilizationPercentage": 60},
            {"Name": f"pid_4_{other}_eng_0_engtype_3D", "UtilizationPercentage": 99}],
            "memory": [{"Name": adapter, "DedicatedUsage": 2 * pc_hub.GIB},
                       {"Name": other, "DedicatedUsage": 8 * pc_hub.GIB}]}
        self.assertEqual(pc_hub.windows_readings(data), {adapter: pc_hub.GPUReading(70, 2 * pc_hub.GIB),
                                                       other: pc_hub.GPUReading(99, 8 * pc_hub.GIB)})
        with patch("pc_hub.sys.platform", "win32"), patch("pc_hub.find_nvidia", return_value=None), \
             patch("pc_hub.find_powershell", return_value="powershell.exe"), patch("pc_hub.subprocess.run") as run:
            import json
            self.assertTrue(pc_hub.GPU("auto").windows)
            gpu = pc_hub.GPU("windows:0")
            run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps(data))
            self.assertEqual(gpu.read(), pc_hub.GPUReading(70, 2 * pc_hub.GIB))
            self.assertEqual(run.call_args.kwargs["timeout"], 3)
            self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)
            # Losing that adapter must not silently switch to a different GPU.
            run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps({"memory": data["memory"][1:]}))
            self.assertEqual(gpu.read(), pc_hub.GPUReading())
            run.side_effect = subprocess.TimeoutExpired("powershell.exe", 3)
            self.assertEqual(gpu.read(), pc_hub.GPUReading())

    def test_windows_counters_preserve_partial_data_and_reject_missing_invalid_values(self):
        adapter = "luid_0x00000000_0x00000001_phys_0"
        data = {"engines": None, "memory": [{"Name": adapter, "DedicatedUsage": 0}]}
        self.assertEqual(pc_hub.windows_readings(data), {adapter: pc_hub.GPUReading(None, 0)})
        for invalid in ({}, [], {"engines": [None, {"Name": "garbage", "UtilizationPercentage": 80}],
                                "memory": [{"Name": adapter, "DedicatedUsage": -1}]}):
            self.assertEqual(pc_hub.windows_readings(invalid), {})

    def test_windows_finds_gpu_tools_outside_path(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "NVIDIA Corporation/NVSMI/nvidia-smi.exe"
            executable.parent.mkdir(parents=True)
            executable.touch()
            powershell = Path(directory) / "windows/Sysnative/WindowsPowerShell/v1.0/powershell.exe"
            powershell.parent.mkdir(parents=True)
            powershell.touch()
            with patch("pc_hub.sys.platform", "win32"), patch("pc_hub.shutil.which", return_value=None), \
                 patch.dict("os.environ", {"ProgramW6432": directory, "ProgramFiles": directory,
                                           "SystemRoot": str(Path(directory) / "windows")}):
                self.assertEqual(pc_hub.find_nvidia(), str(executable))
                self.assertEqual(pc_hub.find_powershell(), str(powershell))

    def test_named_layout_fits_and_switch_happens_once_after_upload(self):
        client = MagicMock()
        dashboard = pc_hub.Dashboard()
        self.assertNotIn("title", dashboard.layout["text"])
        self.assertEqual([dashboard.layout["text"][name + "_label"]["y"]
                          for name in (*pc_hub.METRICS, "vram")], [0, 8, 16, 24])
        self.assertEqual(pc_hub.Dashboard(demo=True).layout["text"]["cpu_label"]["text"], "CPU*")
        self.assertEqual(len(canvas.Layout(dashboard.layout).slots), 8)
        dashboard.install(client, sample())
        self.assertEqual(client.show.call_count, 1)
        self.assertEqual(len(client.frame.call_args.args[0]), 4096)
        self.assertEqual(client.text.call_args_list[-1].args, ("vram", "--"))
        dashboard.update(client, sample(cpu=100, gpu=None))
        self.assertEqual(client.show.call_count, 1)
        self.assertIn(call("cpu", "#FF665E", None), client.style.call_args_list)
        self.assertIn(call("cpu_label", "#FF665E", None), client.style.call_args_list)
        self.assertIn(call("gpu_label", "#FFFFFF", None), client.style.call_args_list)
        self.assertIn(call("gpu", " --%"), client.text.call_args_list)

    def test_commit_failure_invalidates_dashboard_cache(self):
        client = MagicMock()
        client.transaction.return_value.__exit__.side_effect = TimeoutError("commit outcome unknown")
        dashboard = pc_hub.Dashboard()
        with self.assertRaisesRegex(TimeoutError, "commit outcome unknown"):
            dashboard.update(client, sample())
        self.assertEqual(dashboard.last, {})
        client.transaction.return_value.__exit__.side_effect = None
        client.reset_mock()
        dashboard.update(client, sample())
        self.assertEqual(client.text.call_count, 4)
        self.assertEqual(client.style.call_count, 8)

    def test_cpu_counter_is_primed_and_invalid_percentages_remain_unknown(self):
        psutil = SimpleNamespace(cpu_percent=Mock(side_effect=[0, 37]),
                                 virtual_memory=Mock(return_value=SimpleNamespace(percent=67)))
        with patch.dict(sys.modules, {"psutil": psutil}):
            sampler = pc_hub.Sampler("none")
            measured = sampler.sample()
        self.assertEqual((measured.cpu, measured.ram, measured.gpu), (37, 67, None))
        self.assertEqual(psutil.cpu_percent.call_count, 2)
        for value in (None, float("nan"), float("inf"), -1, 101, "N/A"):
            self.assertIsNone(pc_hub.percent(value))


class HubSimulatorTests(unittest.TestCase):
    def test_reconnect_restores_unchanged_readings_on_a_fresh_simulator(self):
        from PIL import Image
        binary = ROOT / ("target/debug/simulaitor.exe" if sys.platform == "win32" else "target/debug/simulaitor")
        self.assertTrue(binary.exists(), "build simulaitor before running this suite")
        installed, restarted, stopped = threading.Event(), threading.Event(), threading.Event()
        target, processes, errors = [], [], []
        # Keep values identical across connections: stale text/style caches must
        # not hide missing uploads. Include warning and unavailable styles.
        reading = pc_hub.Sample(96, None, 38, datetime(2026, 10, 20, 12),
                                vram_used=int(4.2 * pc_hub.GIB), demo=True)

        class Finished(Exception):
            pass

        class FixedSampler:
            def __init__(self):
                self.gpu = SimpleNamespace(name="fixture")
                self.calls = 0

            def sample(self):
                self.calls += 1
                if self.calls == 2:
                    # The first complete install has returned. Let its real
                    # server exit, then resume against the disconnected socket.
                    installed.set()
                    if not restarted.wait(10):
                        raise RuntimeError("test did not restart the simulator")
                if self.calls == 4:
                    raise Finished()  # The second complete install has returned.
                return reading

        def resolve(_):
            if stopped.is_set():
                raise RuntimeError("test stopped")
            return target[0]

        def send():
            try:
                pc_hub.run(SimpleNamespace(demo=True, gpu="none", once=False, count=None,
                                           interval=.2, port="auto", timeout=.5))
            except Finished:
                pass
            except BaseException as error:
                if not stopped.is_set():
                    errors.append(error)

        with tempfile.TemporaryDirectory() as directory:
            def start(name, frames):
                snapshot = Path(directory) / (name + ".ppm")
                process = subprocess.Popen([str(binary), "--headless", "--canvas-listen", "127.0.0.1:0",
                                            "--frames", str(frames), "--snapshot", str(snapshot)],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes.append(process)
                line = process.stdout.readline().strip()
                self.assertTrue(line.startswith("Canvas listening on 127.0.0.1:"), line)
                target[:] = ["tcp://" + line.split()[-1]]
                return process, snapshot

            first, before = start("before", 150)
            worker = threading.Thread(target=send, name="hub-reconnect-test", daemon=True)
            # Only metric sampling and device discovery are fixtures. Client,
            # socket disconnect, protocol, scene storage and renderer are real.
            with patch("pc_hub.DemoSampler", FixedSampler), patch("pc_hub.resolve_port", resolve):
                try:
                    worker.start()
                    self.assertTrue(installed.wait(8), str(errors))
                    stdout, stderr = first.communicate(timeout=5)
                    self.assertEqual(first.returncode, 0, stdout + stderr)
                    second, after = start("after", 600)
                    restarted.set()
                    worker.join(timeout=5)
                    self.assertFalse(worker.is_alive(), "hub did not reconnect")
                    self.assertEqual(errors, [])
                    stdout, stderr = second.communicate(timeout=10)
                    self.assertEqual(second.returncode, 0, stdout + stderr)
                    with Image.open(before) as old, Image.open(after) as restored:
                        old, restored = old.convert("RGB"), restored.convert("RGB")
                        self.assertEqual(old.size, (64, 32))
                        colors = [canvas.color565("#%02X%02X%02X" % old.getpixel((x, y)))
                                  for y in range(6) for x in range(2, 18)]
                        self.assertIn(canvas.color565("#FF665E"), colors)
                        # Sample activity phase is unrelated to scene recovery.
                        old.putpixel((63, 28), (0, 0, 0))
                        restored.putpixel((63, 28), (0, 0, 0))
                        self.assertEqual(old.tobytes(), restored.tobytes())
                finally:
                    stopped.set()
                    restarted.set()
                    for process in processes:
                        if process.poll() is None:
                            process.terminate()
                        process.communicate(timeout=3)
                    worker.join(timeout=5)
                    self.assertFalse(worker.is_alive(), "hub worker leaked")

    def test_live_and_demo_cli_feed_the_real_protocol_and_renderer(self):
        from PIL import Image
        binary = ROOT / ("target/debug/simulaitor.exe" if sys.platform == "win32" else "target/debug/simulaitor")
        self.assertTrue(binary.exists(), "build simulaitor before running this suite")
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "hub.ppm"
            process = subprocess.Popen([str(binary), "--headless", "--canvas-listen", "127.0.0.1:0",
                                        "--frames", "450", "--snapshot", str(snapshot)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                line = process.stdout.readline().strip()
                self.assertTrue(line.startswith("Canvas listening on 127.0.0.1:"), line)
                target = "tcp://" + line.split()[-1]
                for mode in ([], ["--demo"]):
                    result = subprocess.run([sys.executable, str(ROOT / "tools/pc_hub.py"),
                                             "--port", target, "--once", "--gpu", "none"] + mode,
                                            capture_output=True, text=True, timeout=4)
                    self.assertEqual(result.returncode, 0, result.stderr)
                stdout, stderr = process.communicate(timeout=8)
                self.assertEqual(process.returncode, 0, stderr + stdout)
                with Image.open(snapshot) as image:
                    self.assertEqual(image.size, (64, 32))
                    for point, expected in [((48, 2), "#28D7F7"), ((51, 2), "#1A2A39"),
                                            ((54, 10), "#AA8CFF"), ((58, 18), "#FFBA52")]:
                        r, g, b = image.getpixel(point)
                        self.assertEqual(((r & 0xf8) << 8) | ((g & 0xfc) << 3) | (b >> 3),
                                         canvas.color565(expected))
                    for row, color in enumerate((*pc_hub.COLORS, pc_hub.VRAM_COLOR)):
                        glyphs = []
                        for y in range(row * 8, 6 + row * 8):
                            for x in range(2, 18):
                                r, g, b = image.getpixel((x, y))
                                glyphs.append(((r & 0xf8) << 8) | ((g & 0xfc) << 3) | (b >> 3))
                        self.assertIn(canvas.color565(color), glyphs)
                        self.assertTrue(set(glyphs) <= {0, canvas.color565(color)})
                    # The real render must keep the unoccupied background completely off.
                    for y in (6, 7, 14, 15, 22, 23, 30, 31):
                        self.assertTrue(all(image.getpixel((x, y)) == (0, 0, 0) for x in range(64)))
                    for x in (0, 1, 20, 21, 62):
                        self.assertTrue(all(image.getpixel((x, y)) == (0, 0, 0) for y in range(32)))
                    # VRAM uses its own green row with units, without a header.
                    self.assertTrue(any(image.getpixel((x, y))[1] > 100
                                        for x in range(22, 62) for y in range(24, 30)))
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=3)


if __name__ == "__main__":
    unittest.main()
