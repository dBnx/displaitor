"""PC sensor sampling shared by the dashboard and companion apps."""
from __future__ import annotations

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

MIB, GIB = 1024 ** 2, 1024 ** 3

# CIM property names work across Windows display languages. Query adapter
# memory; summing process allocations would double-count shared allocations.
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


def percent(value: object) -> float | None:
    """Unavailable/invalid counters stay unavailable, rather than looking idle."""
    if not isinstance(value, (str, int, float)):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and 0 <= value <= 100 else None


def metric_color(value: float | None, base: str) -> str:
    if value is None:
        return "#FFFFFF"
    return "#FF665E" if value >= 95 else "#FFD166" if value >= 85 else base


def byte_count(value: object, unit: float=1) -> int | None:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        value = float(value) * unit
    except (TypeError, ValueError):
        return None
    return int(value) if math.isfinite(value) and value >= 0 else None


def find_nvidia() -> str | None:
    found = shutil.which("nvidia-smi")
    if found or sys.platform != "win32":
        return found
    candidates = [Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/nvidia-smi.exe"]
    for variable in ("ProgramW6432", "ProgramFiles"):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / "NVIDIA Corporation/NVSMI/nvidia-smi.exe")
    return next((str(path) for path in candidates if path.is_file()), None)


def find_powershell() -> str | None:
    root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    # Sysnative lets a 32-bit Python launch 64-bit PowerShell on 64-bit Windows.
    candidates = [root / folder / "WindowsPowerShell/v1.0/powershell.exe" for folder in ("Sysnative", "System32")]
    return next((str(path) for path in candidates if path.is_file()), None) or shutil.which("powershell.exe") or shutil.which("pwsh.exe")


@dataclass(frozen=True)
class GPUReading:
    utilization: float | None = None
    vram_used: int | None = None


def windows_readings(data: object) -> dict[str, GPUReading]:
    """One entry per adapter; busiest engine after summing its process shares."""
    engines: dict[tuple[str, str], float] = {}
    memory: dict[str, int] = {}
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
    def __init__(self, selection: str="auto", *, drm: Path=Path("/sys/class/drm")) -> None:
        self.path: Path | None = None
        self.command: list[str] | None = None
        self.windows = False
        self.adapter: str | None = None
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

    def read(self) -> GPUReading:
        try:
            if self.path is not None:
                def read(path: Path) -> str | None:
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
                    return readings.get(self.adapter, GPUReading()) if self.adapter is not None else GPUReading()
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
    def __init__(self, gpu: str="auto") -> None:
        try:
            import psutil
        except ImportError as error:
            raise RuntimeError("install dependencies: python -m pip install displaitor-tools") from error
        self.psutil = psutil
        self.gpu = GPU(gpu)
        self.psutil.cpu_percent(interval=None) # Prime the delta counter; discard the first reading.

    def sample(self) -> Sample:
        reading = self.gpu.read()
        return Sample(percent(self.psutil.cpu_percent(interval=None)),
                      percent(self.psutil.virtual_memory().percent), reading.utilization, datetime.now(), reading.vram_used)
