"""Fixed-position current, forecast and overview views over cached weather data."""
from __future__ import annotations

import math

from ..canvas import ButtonState, Client
from ..models import Scene, TextSlot

from ..canvas import image_frame
from .data import State
from .icons import ANIMATION_FPS, FRAMES, condition, sprite

PAGES = ('now', 'forecast', 'info')
MINT = '#B8C8C0'
MUTED = '#607078'


def temperature(value: float | None) -> str:
    return '--°C' if value is None else f'{round(value)}°C'


def percentage(value: float | None) -> str:
    return '--%' if value is None else f'{round(value)}%'


def decimal(value: float | None) -> str:
    if value is None:
        return '--'
    return f'{value:.1f}'.rstrip('0').rstrip('.') if value < 99.95 else f'{value:.0f}'


def status_text(status: str) -> str:
    return {'rain': 'Rain', 'snow': 'Snow', 'storm': 'Storm', 'sunny': 'Sunny',
            'night': 'Night', 'cloudy': 'Cloudy', 'partly': 'Pt cloudy',
            'fog': 'Fog', 'unknown': 'Unknown'}[condition(status)]


def field(x: int, y: int, width: int, text: str='', *, medium: bool=False, color: str=MINT, align: str='left') -> TextSlot:
    return dict(x=x, y=y, width=width, height=10 if medium else 6,
                font='medium' if medium else 'small', color=color, background='#000000',
                align=align, text=text)


def layout(page: str) -> Scene:
    slots = {'title': field(2, 0, 36, color=MUTED),
             'feed': field(40, 26, 24, color=MUTED, align='right')}
    if page == 'now':
        slots.update(temperature=field(2, 9, 36, medium=True, align='right'),
                     status=field(2, 25, 36, color='#607D70'))
    else:
        slots.update({f'row{i}': field(0, 7 + i * 6, 40) for i in range(4)})
    return {'text': slots}


class Display:
    def __init__(self, page: str='now') -> None:
        self.page_index = PAGES.index(page)
        self.day_index = self.details = 0
        self.phase = 0.0
        self.last: dict[str, str | bytes] = {}
        self.installed: str | None = None
        self.state = State(None, 'WAIT')

    @property
    def page(self) -> str:
        return PAGES[self.page_index]

    def receive(self, state: State) -> None:
        self.state = state
        count = len(state.report.days) if state.report else 0
        if count:
            self.day_index = min(self.day_index, count - 1)

    def buttons(self, state: ButtonState) -> bool:
        if state.lost or not state.active:
            return False
        changed = False
        for event in state.events:
            if not event.active:
                continue
            up, down = 'up' in event.pressed, 'down' in event.pressed
            if up != down:
                self.page_index = (self.page_index + (1 if down else -1)) % len(PAGES)
                changed = True
            left, right = 'left' in event.pressed, 'right' in event.pressed
            if left != right:
                step = 1 if right else -1
                if self.page == 'forecast' and self.state.report and self.state.report.days:
                    self.day_index = (self.day_index + step) % len(self.state.report.days)
                    changed = True
                elif self.page == 'info':
                    self.details = (self.details + step) % 2
                    changed = True
        return changed

    def content(self) -> tuple[dict[str, str], str]:
        report = self.state.report
        current = report.current if report else None
        title = report.location.upper()[:9] if report else 'WEATHER'
        status = current.status if current else 'Unknown'
        texts = {'title': title, 'feed': self.state.label}
        if self.page == 'now':
            texts['temperature'] = temperature(current.temperature if current else None)
            texts['status'] = status_text(status) if current else 'Offline' if self.state.label in ('ERR', 'OLD') else 'Loading'
        elif self.page == 'forecast':
            day = report.days[self.day_index] if report and report.days else None
            texts['title'] = ('MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN')[day.date.weekday()] + day.date.strftime(' %d/%m') if day else 'FORECAST'
            status = day.status if day else 'Unknown'
            values = (('HI  ', temperature(day.high if day else None)),
                      ('LO  ', temperature(day.low if day else None)),
                      ('RISK', percentage(day.rain_chance if day else None)),
                      ('UV  ', decimal(day.uv if day else None)))
            texts.update({f'row{i}': label + value.rjust(6) for i, (label, value) in enumerate(values)})
        else:
            texts['title'] = f'INFO {self.details + 1}/2'
            today = report.days[0] if report and report.days else None
            if self.details == 0:
                values = (('TMP ', temperature(current.temperature if current else None)),
                          ('RAIN', decimal(current.rain_mm if current else None) + 'mm'),
                          ('UV  ', decimal(current.uv if current else None)),
                          ('HUM ', percentage(current.humidity if current else None)))
            else:
                wind = '--kmh' if not current or current.wind is None else f'{round(current.wind)}kmh'
                values = (('FEEL', temperature(current.feels_like if current else None)), ('WIND', wind),
                          ('RISK', percentage(today.rain_chance if today else None)),
                          ('UV/D', decimal(today.uv if today else None)))
            texts.update({f'row{i}': label + value.rjust(6) for i, (label, value) in enumerate(values)})
        return texts, status

    def install(self, client: Client, *, activate: bool=True) -> None:
        self.installed = None
        self.last.clear()
        self.update(client, 0, activate=activate)

    def update(self, client: Client, elapsed: float, *, activate: bool=False) -> None:
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('Weather elapsed time must be finite and nonnegative')
        self.phase = (self.phase + elapsed * ANIMATION_FPS) % FRAMES
        texts, status = self.content()
        background = image_frame(sprite(status, int(self.phase)))
        try:
            with client.transaction():
                if self.installed != self.page:
                    client.layout(layout(self.page))
                    self.last.clear()
                    self.installed = self.page
                if self.last.get('frame') != background:
                    client.frame(background)
                    self.last['frame'] = background
                for name, text in texts.items():
                    if self.last.get(name) != text:
                        client.text(name, text)
                        self.last[name] = text
                if activate:
                    client.show()
        except BaseException:
            self.installed = None
            self.last.clear()
            raise
