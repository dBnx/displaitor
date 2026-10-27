#!/usr/bin/env python3
"""PC stats on Displaitor: run this script to select Canvas and start the hub.

CPU/RAM use psutil. GPU load/VRAM use AMD Linux sysfs, NVIDIA nvidia-smi, or
Windows GPU counters. Unsupported counters stay unknown. No root,
probe, UART, background service, or remote network listener is required.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import csv
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

try:
    from .canvas import Client, image_frame
except ImportError:
    from canvas import Client, image_frame

LAYOUT = Path(__file__).with_name("layouts") / "pc_hub.json"
COLORS = ("#28D7F7", "#AA8CFF", "#FFBA52")
METRICS = ("cpu", "ram", "gpu")
VRAM_COLOR = "#69EF8C"
METER_TRACK = "#1A2A39"
MIB, GIB = 1024 ** 2, 1024 ** 3

# CIM property names are independent of the Windows display language. Query
# adapter memory, not per-process memory (shared allocations would double-count).
WINDOWS_GPU_QUERY = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'
$engines = @(); $memory = @()
try {
    $engines = @(Get-CimInstance -Namespace root\cimv2 -ClassName Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine -Property Name,UtilizationPercentage |
        Select-Object Name,UtilizationPercentage)
} catch {}
try {
    $memory = @(Get-CimInstance -Namespace root\cimv2 -ClassName Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory -Property Name,DedicatedUsage |
        Select-Object Name,DedicatedUsage)
} catch {}
[pscustomobject]@{engines=$engines;memory=$memory} | ConvertTo-Json -Depth 4 -Compress
"""


def percent(value):
    """Unavailable/invalid counters stay unavailable, rather than looking idle."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and 0 <= value <= 100 else None


def metric_color(value, base):
    if value is None:
        return "#FFFFFF"
    return "#FF665E" if value >= 95 else "#FFD166" if value >= 85 else base


def resolve_port(target="auto", ports=None):
    if target != "auto":
        return target
    if ports is None:
        try:
            from serial.tools.list_ports import comports
        except ImportError as error:
            raise RuntimeError("install dependencies: pip install -r tools/requirements.txt") from error
        ports = comports()
    matches = sorted({p.device for p in ports
                      if (p.vid, p.pid) == (0x16C0, 0x27DD)
                      and (p.serial_number == "canvas-1" or p.product == "Displaitor Canvas"
                           or (sys.platform == "win32" and not p.serial_number
                               and p.product in (None, "USB Serial Device")))})
    if not matches:
        raise ConnectionError("waiting for Displaitor native USB data connection (the probe's UART is not Canvas)")
    if len(matches) != 1:
        raise ValueError("multiple Displaitors found; choose --port " + " or ".join(matches))
    return matches[0]


def byte_count(value, unit=1):
    try:
        value = float(value) * unit
    except (TypeError, ValueError):
        return None
    return int(value) if math.isfinite(value) and value >= 0 else None


def vram_text(value):
    """Used dedicated memory with explicit binary units, within eight glyphs."""
    value = byte_count(value)
    if value is None:
        return "--"
    for divisor, suffix in ((MIB, "MiB"), (GIB, "GiB"), (GIB * 1024, "TiB")):
        scaled = value / divisor
        if scaled < 999.5:
            return f"{scaled:.1f} {suffix}" if suffix != "MiB" and scaled < 9.95 else f"{scaled:.0f} {suffix}"
    return "TOO BIG"


def find_nvidia():
    found = shutil.which("nvidia-smi")
    if found or sys.platform != "win32":
        return found
    candidates = [Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/nvidia-smi.exe"]
    for variable in ("ProgramW6432", "ProgramFiles"):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / "NVIDIA Corporation/NVSMI/nvidia-smi.exe")
    return next((str(path) for path in candidates if path.is_file()), None)


def find_powershell():
    root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    # Sysnative lets a 32-bit Python launch 64-bit PowerShell on 64-bit Windows.
    candidates = [root / folder / "WindowsPowerShell/v1.0/powershell.exe" for folder in ("Sysnative", "System32")]
    return next((str(path) for path in candidates if path.is_file()), None) or shutil.which("powershell.exe") or shutil.which("pwsh.exe")


@dataclass(frozen=True)
class GPUReading:
    utilization: float | None = None
    vram_used: int | None = None


def windows_readings(data):
    """One entry per adapter; busiest engine after summing its process shares."""
    engines, memory = {}, {}
    if not isinstance(data, dict):
        return {}
    for row in data.get("engines", []) or []:
        if not isinstance(row, dict):
            continue
        match = re.fullmatch(r"(?:pid_\d+_)?(luid_0x[\da-f]+_0x[\da-f]+_phys_\d+)_eng_(\d+)(?:_.*)?", str(row.get("Name", "")), re.I)
        value = percent(row.get("UtilizationPercentage"))
        if match and value is not None:
            key = (match[1].lower(), match[2])
            engines[key] = engines.get(key, 0) + value
    for row in data.get("memory", []) or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("Name", "")).lower()
        value = byte_count(row.get("DedicatedUsage"))
        if re.fullmatch(r"luid_0x[\da-f]+_0x[\da-f]+_phys_\d+", name) and value is not None:
            memory[name] = value
    adapters = set(memory) | {key[0] for key in engines}
    readings = {}
    for adapter in sorted(adapters):
        loads = [value for (key, _), value in engines.items() if key == adapter]
        readings[adapter] = GPUReading(min(100.0, max(loads)) if loads else None, memory.get(adapter))
    return readings


class GPU:
    """Read-only backends. NVIDIA has a 1s deadline; Windows CIM has 3s."""
    def __init__(self, selection="auto", *, drm=Path("/sys/class/drm")):
        self.path = None
        self.command = None
        self.windows = False
        self.adapter = None
        self.adapter_index = 0
        self.name = "unavailable"
        if selection == "none":
            return
        if selection == "auto" and sys.platform != "win32":
            cards = sorted(p for p in drm.glob("card*") if re.fullmatch(r"card\d+", p.name))
            for card in cards:
                candidate = card / "device/gpu_busy_percent"
                if candidate.is_file() or (card / "device/mem_info_vram_used").is_file():
                    self.path, self.name = candidate, f"AMD {card.name}"
                    return
        elif re.fullmatch(r"card\d+", selection):
            self.path = drm / selection / "device/gpu_busy_percent"
            if not self.path.is_file() and not self.path.with_name("mem_info_vram_used").is_file():
                raise ValueError(f"{selection} has no GPU counters; use --gpu auto or none")
            self.name = f"AMD {selection}"
            return
        elif selection != "auto" and not re.fullmatch(r"(?:nvidia|windows):\d+", selection):
            raise ValueError("--gpu must be auto, none, cardN, nvidia:N, or windows:N")
        utility = find_nvidia()
        if utility and not selection.startswith("windows:"):
            index = selection.split(":")[1] if selection.startswith("nvidia:") else "0"
            self.command = [utility, f"--id={index}", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"]
            self.name = f"NVIDIA {index}"
        elif sys.platform == "win32" and (selection == "auto" or selection.startswith("windows:")):
            utility = find_powershell()
            if utility:
                self.adapter_index = int(selection.split(":")[1]) if ":" in selection else 0
                self.command = [utility, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", WINDOWS_GPU_QUERY]
                self.windows = True
                self.name = f"Windows adapter {self.adapter_index}"
            elif selection != "auto":
                raise ValueError("PowerShell was not found; use --gpu auto or none")
        elif selection != "auto":
            raise ValueError("requested GPU backend is unavailable; use --gpu auto or none")

    def read(self):
        try:
            if self.path is not None:
                def read(path):
                    try: return path.read_text().strip()
                    except OSError: return None
                return GPUReading(percent(read(self.path)), byte_count(read(self.path.with_name("mem_info_vram_used"))))
            if self.command is not None:
                flags = 0x08000000 if sys.platform == "win32" else 0 # CREATE_NO_WINDOW
                result = subprocess.run(self.command, capture_output=True, text=True, encoding="utf-8-sig", errors="replace",
                                        timeout=3 if self.windows else 1, check=False, creationflags=flags)
                if result.returncode != 0:
                    return GPUReading()
                if self.windows:
                    readings = windows_readings(json.loads(result.stdout))
                    if self.adapter is None and len(readings) > self.adapter_index:
                        self.adapter = list(readings)[self.adapter_index]
                        self.name = f"Windows {self.adapter}"
                    return readings.get(self.adapter, GPUReading())
                fields = next(csv.reader([result.stdout.strip()]))
                if len(fields) == 2:
                    return GPUReading(percent(fields[0].strip()), byte_count(fields[1].strip(), MIB))
        except (OSError, ValueError, csv.Error, subprocess.TimeoutExpired):
            pass
        return GPUReading()


@dataclass(frozen=True)
class Sample:
    cpu: float | None
    ram: float | None
    gpu: float | None
    updated: datetime
    vram_used: int | None = None
    demo: bool = False


class Sampler:
    def __init__(self, gpu="auto"):
        try:
            import psutil
        except ImportError as error:
            raise RuntimeError("install dependencies: pip install -r tools/requirements.txt") from error
        self.psutil = psutil
        self.gpu = GPU(gpu)
        self.psutil.cpu_percent(interval=None) # Prime the delta counter; discard the first reading.

    def sample(self):
        reading = self.gpu.read()
        return Sample(percent(self.psutil.cpu_percent(interval=None)),
                      percent(self.psutil.virtual_memory().percent), reading.utilization, datetime.now(), reading.vram_used)


class DemoSampler:
    """Labelled synthetic data for preview/testing; never mistaken for live stats."""
    def __init__(self):
        self.index = 0
        self.gpu = GPU("none")
        self.gpu.name = "DEMO"

    def sample(self):
        phase = self.index
        self.index += 1
        return Sample(42 + 30 * math.sin(phase / 4), 67 + 8 * math.sin(phase / 9),
                      83 + 15 * math.sin(phase / 5), datetime.now(), vram_used=int(4.2 * GIB), demo=True)


def background(sample, pulse):
    from PIL import Image, ImageDraw
    # Unlit LEDs behind every glyph: dark desktop colours still glow on a matrix.
    image = Image.new("RGB", (64, 32), "#000000")
    draw = ImageDraw.Draw(image)
    if pulse:
        draw.point((63, 28), fill=VRAM_COLOR)
    for row, (name, base) in enumerate(zip(METRICS, COLORS)):
        value = percent(getattr(sample, name))
        y = row * 8
        color = metric_color(value, base)
        draw.rectangle((42, y + 2, 61, y + 5), fill=METER_TRACK)
        if value is None:
            for x in range(42, 62, 3):
                draw.point((x, y + 3), fill=color)
        else:
            width = round(value / 5)
            if width:
                draw.rectangle((42, y + 2, 41 + width, y + 5), fill=color)
            for x in (45, 49, 53, 57):
                draw.line((x, y + 2, x, y + 5), fill="#000000")
    return image_frame(image)


class Dashboard:
    def __init__(self, demo=False):
        self.layout = json.loads(LAYOUT.read_text(encoding="utf-8"))
        if demo:
            self.layout["text"]["cpu_label"]["text"] = "CPU*"
        self.last = {}
        self.pulse = False

    def install(self, client, sample):
        try:
            with client.transaction():
                self.last.clear()
                # Prepare the retained scene before explicitly selecting Canvas.
                client.layout(self.layout)
                self.update(client, sample)
                try:
                    client.show()
                except ValueError as error:
                    if "unknown command" in str(error):
                        raise RuntimeError("firmware update required: this board does not support Canvas show") from error
                    raise
        except BaseException:
            self.last.clear()
            raise

    def update(self, client, sample):
        try:
            with client.transaction():
                self.pulse = not self.pulse
                client.frame(background(sample, self.pulse))
                for name, base in zip(METRICS, COLORS):
                    value = percent(getattr(sample, name))
                    text = " --%" if value is None else f"{value:3.0f}%"
                    color = metric_color(value, base)
                    if self.last.get((name, "color")) != color:
                        client.style(name, color, None)
                        client.style(name + "_label", color, None)
                        self.last[(name, "color")] = color
                    if self.last.get(name) != text:
                        client.text(name, text)
                        self.last[name] = text
                color = VRAM_COLOR if byte_count(sample.vram_used) is not None else "#FFFFFF"
                if self.last.get(("vram", "color")) != color:
                    client.style("vram", color, None)
                    client.style("vram_label", color, None)
                    self.last[("vram", "color")] = color
                vram = vram_text(sample.vram_used)
                if self.last.get("vram") != vram:
                    client.text("vram", vram)
                    self.last["vram"] = vram
        except BaseException:
            self.last.clear()
            raise


def run(args):
    sampler = DemoSampler() if args.demo else Sampler(args.gpu)
    dashboard = Dashboard(demo=args.demo)
    limit = 1 if args.once else args.count
    sent = 0
    time.sleep(min(.25, args.interval)) # Give the first CPU delta a real sampling interval.
    while limit is None or sent < limit:
        try:
            target = resolve_port(args.port)
            with Client(target, timeout=args.timeout) as client:
                dashboard.install(client, sampler.sample())
                sent += 1
                print(f"PC hub -> {target}; GPU: {sampler.gpu.name}; every {args.interval:g}s. Ctrl+C stops.", flush=True)
                while limit is None or sent < limit:
                    time.sleep(args.interval)
                    dashboard.update(client, sampler.sample())
                    sent += 1
                    # No frame queue or catch-up burst; acknowledged I/O may lower the rate.
        except (OSError, ValueError) as error:
            if isinstance(error, ValueError) and "layout mismatch" not in str(error):
                raise
            if limit is not None:
                raise
            print(f"pc_hub: {error}; retrying in 2s", flush=True)
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="auto", help="auto (native Displaitor USB only), serial path, or tcp://127.0.0.1:7777")
    parser.add_argument("--interval", type=float, default=2, help="seconds between updates, at least 0.2 (default: 2)")
    parser.add_argument("--timeout", type=float, default=3, help="acknowledgement timeout in seconds")
    parser.add_argument("--gpu", default="auto", help="auto, none, AMD cardN, nvidia:N, or Windows windows:N")
    parser.add_argument("--demo", action="store_true", help="synthetic metrics for preview (CPU* marks demo data)")
    finite = parser.add_mutually_exclusive_group()
    finite.add_argument("--once", action="store_true", help="send one snapshot and exit; connection errors fail immediately")
    finite.add_argument("--count", type=int, help="send N snapshots and exit; connection errors fail immediately")
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval < .2:
        parser.error("--interval must be finite and at least 0.2 seconds")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    if args.count is not None and args.count <= 0:
        parser.error("--count must be positive")
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nPC hub stopped; the display retains the last sample.")
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"pc_hub: {error}\n")


if __name__ == "__main__":
    main()
