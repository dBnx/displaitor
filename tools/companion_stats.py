"""Five fixed-width HUD pages over one already-sampled set of PC readings."""
from __future__ import annotations

try:
    from .pc_hub import GIB, MIB, byte_count, percent
except ImportError:
    from pc_hub import GIB, MIB, byte_count, percent

PAGES = ("cpu", "ram", "gpu", "vram", "all")


def compact_vram(value):
    """Used dedicated memory, at most four glyphs; M/G/T are binary units."""
    value = byte_count(value)
    if value is None:
        return "--"
    for divisor, suffix in ((MIB, "M"), (GIB, "G"), (GIB * 1024, "T")):
        scaled = value / divisor
        if scaled < 999.5:
            number = f"{scaled:.1f}" if suffix != "M" and scaled < 9.95 else f"{scaled:.0f}"
            return number + suffix
    return ">99T"


def readings(activity):
    sample = activity.sample
    values = {name: percent(getattr(sample, name, None)) for name in ("cpu", "ram", "gpu")}
    # Also support callers that supply the original Activity-only API.
    if sample is None and activity.source.lower() in values:
        values[activity.source.lower()] = percent(activity.value)
    values["vram"] = byte_count(getattr(sample, "vram_used", None))
    return values


def percentage(value):
    return "--%" if value is None else f"{value:.0f}%"


def fields(color, page):
    if page not in PAGES:
        raise ValueError("unknown companion stats page")
    if page == "all":
        return {name: dict(x=40, y=8 + row * 6, width=24, height=6,
                           font="small", color=color, text=label + "  --%")
                for row, (name, label) in enumerate(zip(PAGES[:4], "CRGV"))}
    return {
        "metric": dict(x=40, y=8, width=24, height=10, font="medium", align="right",
                       color=color, text="--" if page == "vram" else "--%"),
        "mood": dict(x=40, y=20, width=24, height=6, font="small", color=color, text=page.upper()),
        "demo": dict(x=40, y=26, width=24, height=6, font="small", color=color, text="WAIT"),
    }


def labels(activity, page, playing):
    values = readings(activity)
    if page == "all":
        result = {name: (f"{label} {percentage(values[name]):>4}", values[name])
                  for name, label in zip(PAGES[:3], "CRG")}
        result["vram"] = (f"V {compact_vram(values['vram']):>4}", None)
        return result
    value = values[page]
    text = compact_vram(value) if page == "vram" else percentage(value)
    status = "DEMO" if activity.demo else "PLAY" if playing else {
        "unknown": "WAIT", "idle": "IDLE", "busy": "WORK", "hard": "HARD"}[activity.mood]
    warning = value if page != "vram" else None
    return {"metric": (text, warning), "mood": (page.upper(), warning),
            "demo": (status, percent(activity.value))}
