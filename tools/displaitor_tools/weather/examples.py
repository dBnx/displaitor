"""Explicit sample data for demo mode, tests and offline previews."""

from __future__ import annotations

def payload() -> dict[str, object]:
    return {
        'nearest_area': [{'areaName': [{'value': 'SAMPLE'}]}],
        'current_condition': [{'temp_C': '8', 'FeelsLikeC': '6', 'precipMM': '0.4',
                               'uvIndex': '2', 'humidity': '78', 'windspeedKmph': '12',
                               'weatherDesc': [{'value': 'Light rain'}]}],
        'weather': [
            {'date': stamp, 'mintempC': low, 'maxtempC': high,
             'hourly': [{'time': '1200', 'chanceofrain': chance, 'uvIndex': uv,
                         'weatherDesc': [{'value': status}]}]}
            for stamp, low, high, chance, uv, status in (
                ('2026-10-28', '4', '11', '80', '2', 'Light rain'),
                ('2026-10-29', '-2', '3', '60', '1', 'Snow'),
                ('2026-10-30', '2', '14', '10', '5', 'Sunny'))],
    }
