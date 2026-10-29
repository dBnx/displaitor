"""wttr.in data, persistent refresh/backoff state and a single background worker.

One j1 request supplies every view. Disk state survives reconnects/restarts; a
short-lived lease coalesces processes. Rendering never performs network I/O.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Self, TypedDict
from ..models import Pathish

from dataclasses import dataclass
from datetime import date
import hashlib
from http.client import HTTPException
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

REFRESH = 1800
MIN_REFRESH = 900
MAX_AGE = 6 * 3600
HTTP_TIMEOUT = 8
MAX_BYTES = 1024 * 1024


class CacheRecord(TypedDict):
    v: int
    payload: object
    fetched_at: float | None
    next_attempt: float
    failures: int
    error: bool


@dataclass(frozen=True)
class Conditions:
    temperature: float | None = None
    feels_like: float | None = None
    rain_mm: float | None = None
    uv: float | None = None
    humidity: float | None = None
    wind: float | None = None
    status: str = 'Unknown'


@dataclass(frozen=True)
class Day:
    date: date
    low: float | None
    high: float | None
    rain_chance: float | None
    uv: float | None
    status: str


@dataclass(frozen=True)
class Report:
    current: Conditions
    days: tuple[Day, ...]
    location: str


@dataclass(frozen=True)
class State:
    report: Report | None
    label: str


def number(value: object, low: float, high: float) -> float | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, float)):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if math.isfinite(result) and low <= result <= high else None


def _text(rows: object, default: str) -> str:
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return default
    value = rows[0].get('value')
    if not isinstance(value, str):
        return default
    printable = ''.join(character if 32 <= ord(character) <= 126 or 160 <= ord(character) <= 255
                        else ' ' if character.isspace() or ord(character) < 160 else '?'
                        for character in value)
    return ' '.join(printable.split())[:80] or default


def parse(payload: object) -> Report:
    if not isinstance(payload, dict):
        raise ValueError('Invalid weather response')
    rows = payload.get('current_condition')
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise ValueError('Weather response has no current conditions')
    row = rows[0]
    current = Conditions(number(row.get('temp_C'), -150, 150), number(row.get('FeelsLikeC'), -150, 150),
                         number(row.get('precipMM'), 0, 1000), number(row.get('uvIndex'), 0, 50),
                         number(row.get('humidity'), 0, 100), number(row.get('windspeedKmph'), 0, 500),
                         _text(row.get('weatherDesc'), 'Unknown'))
    if current.temperature is None and current.status == 'Unknown':
        raise ValueError('Weather response has no usable current reading')
    days = []
    forecast = payload.get('weather', [])
    for row in forecast[:3] if isinstance(forecast, list) else ():
        if not isinstance(row, dict):
            continue
        try:
            stamp = date.fromisoformat(row.get('date', ''))
        except (ValueError, TypeError):
            continue
        hourly = row.get('hourly', [])
        hourly = [h for h in hourly[:24] if isinstance(h, dict)] if isinstance(hourly, list) else []
        # A representative midday condition; a day's chance is its maximum
        # forecast precipitation probability, never a fabricated current value.
        midday: dict[str, object] = min(hourly, key=lambda h: abs((number(h.get('time'), 0, 2300) or 0) - 1200), default={})
        chances = [number(h.get(key), 0, 100) for h in hourly for key in ('chanceofrain', 'chanceofsnow')]
        uv = [number(h.get('uvIndex'), 0, 50) for h in hourly]
        uv.append(number(row.get('uvIndex'), 0, 50))
        days.append(Day(stamp, number(row.get('mintempC'), -150, 150), number(row.get('maxtempC'), -150, 150),
                        max((n for n in chances if n is not None), default=None),
                        max((n for n in uv if n is not None), default=None),
                        _text(midday.get('weatherDesc'), 'Unknown')))
    area = payload.get('nearest_area')
    location = _text(area[0].get('areaName'), 'WEATHER') if isinstance(area, list) and area and isinstance(area[0], dict) else 'WEATHER'
    return Report(current, tuple(sorted(days, key=lambda d: d.date)), location)


def fetch(location: str) -> object:
    url = 'https://wttr.in/' + quote(location, safe='') + '?format=j1&lang=en'
    request = Request(url, headers={'User-Agent': 'Displaitor-Weather/1.0', 'Accept': 'application/json'})
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT) as response:
            raw = response.read(MAX_BYTES + 1)
    except HTTPException as error:
        raise OSError('Incomplete weather response') from error
    if len(raw) > MAX_BYTES:
        raise ValueError('Weather response is too large')
    return json.loads(raw.decode('utf-8'))


def cache_directory() -> Path:
    if os.name == 'nt' and os.environ.get('LOCALAPPDATA'):
        return Path(os.environ['LOCALAPPDATA']) / 'Displaitor' / 'weather'
    return Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'displaitor' / 'weather'


class Feed:
    def __init__(self, location: str='', *, directory: Pathish | None=None, refresh: float=REFRESH, loader: Callable[[str], object]=fetch, clock: Callable[[], float]=time.time) -> None:
        if not math.isfinite(refresh) or refresh < MIN_REFRESH:
            raise ValueError('Weather refresh must be at least 900 seconds')
        if not isinstance(location, str) or len(location) > 150:
            raise ValueError('Weather location must be at most 150 characters')
        self.location, self.refresh, self.loader, self.clock = location.strip(), refresh, loader, clock
        directory = Path(directory) if directory is not None else cache_directory()
        directory.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(self.location.casefold().encode()).hexdigest()[:24]
        self.path = directory / (key + '.json')
        self.lease = directory / (key + '.lock')
        self.guard = threading.Lock()
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.record: CacheRecord = {'v': 1, 'payload': None, 'fetched_at': None, 'next_attempt': 0, 'failures': 0, 'error': False}
        self.report: Report | None = None
        self._load()

    def _load(self) -> None:
        try:
            if self.path.stat().st_size > MAX_BYTES + 4096:
                return
            record = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(record, dict) or record.get('v') != 1:
                return
            next_attempt = number(record.get('next_attempt'), 0, self.clock() + max(86400, self.refresh))
            fetched = number(record.get('fetched_at'), 0, self.clock())
            failures = number(record.get('failures'), 0, 100)
            if next_attempt is None or failures is None or not isinstance(record.get('error'), bool):
                return
            report = parse(record['payload']) if record.get('payload') is not None else None
            with self.guard:
                self.record = CacheRecord(v=1, payload=record.get('payload'), next_attempt=next_attempt, fetched_at=fetched, failures=int(failures), error=record['error'])
                self.report = report
        except (OSError, ValueError, TypeError, KeyError):
            pass

    def _save(self) -> None:
        descriptor, name = tempfile.mkstemp(prefix=self.path.stem + '-', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                json.dump(self.record, output, separators=(',', ':'))
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def _claim(self) -> bool:
        try:
            descriptor = os.open(self.lease, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                if self.clock() - self.lease.stat().st_mtime > 120:
                    self.lease.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        os.close(descriptor)
        return True

    def step(self) -> None:
        """Perform at most one due request; useful synchronously in offline tests."""
        if not self._claim():
            self._load()
            return
        try:
            self._load()  # Recheck state written by another process before the lease.
            with self.guard:
                now = self.clock()
                if now < self.record['next_attempt']:
                    return
                # Reserve the interval on disk BEFORE HTTP: a crash/restart
                # cannot turn a slow or failed endpoint into a request loop.
                self.record['next_attempt'] = now + self.refresh
                self._save()
            try:
                payload = self.loader(self.location)
                report = parse(payload)
            except (OSError, ValueError, TypeError) as error:
                with self.guard:
                    failures = min(100, self.record['failures'] + 1)
                    self.record['failures'] = failures
                    self.record['error'] = True
                    self.record['next_attempt'] = self.clock() + max(self.refresh, min(21600, self.refresh * 2 ** min(failures - 1, 5)))
                # Keep error messages off the panel and preserve the last good reading.
                self.last_error = str(error)
            else:
                with self.guard:
                    self.report = report
                    self.record['payload'] = payload
                    self.record['fetched_at'] = self.clock()
                    self.record['failures'] = 0
                    self.record['error'] = False
                    self.record['next_attempt'] = self.clock() + self.refresh
            with self.guard:
                self._save()
        finally:
            self.lease.unlink(missing_ok=True)

    def get(self) -> State:
        with self.guard:
            age = None if self.record['fetched_at'] is None else max(0, self.clock() - self.record['fetched_at'])
            if self.report is None:
                return State(None, 'ERR' if self.record['error'] else 'WAIT')
            if age is None or age > MAX_AGE:
                return State(None, 'OLD')
            return State(self.report, 'OLD' if self.record['error'] or age > self.refresh * 2 else 'LIVE')

    def _worker(self) -> None:
        while not self.stop.is_set():
            try:
                self.step()
            except OSError:
                # A local cache failure must not spin or kill the UI thread.
                with self.guard:
                    self.record['error'] = True
                    self.record['next_attempt'] = self.clock() + self.refresh
            self.stop.wait(5)

    def __enter__(self) -> Self:
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=1)
