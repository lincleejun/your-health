"""Markdown rendering primitives for health reports.

Pure formatting — no metric logic. Every helper returns a string.
"""

from __future__ import annotations

from collections.abc import Iterable

_BLOCKS = "▁▂▃▄▅▆▇█"
_MISSING_CELL = "·"
_MISSING_VALUE = "–"  # noqa: RUF001 reason: en-dash is the rendered missing-value glyph


def render_kpi_table(rows: list[tuple[str, str]]) -> str:
    """Markdown 2-column table: ``| metric | value |``.

    ``rows`` is a list of ``(label, value)`` pairs. Empty ``rows`` still emits
    the header + separator. No escaping is performed — callers are responsible
    for not embedding pipe characters in labels or values.
    """
    lines = ["| metric | value |", "| --- | --- |"]
    lines.extend(f"| {label} | {value} |" for label, value in rows)
    return "\n".join(lines)


def _fmt(value: float | None, *, precision: int) -> str:
    if value is None:
        return _MISSING_VALUE
    return f"{value:.{precision}f}"


def render_trend_bullet(
    label: str,
    value: float | None,
    mean_7d: float | None,
    mean_28d: float | None,
    *,
    unit: str = "",
    precision: int = 1,
) -> str:
    """Single-line bullet: ``- **<label>**: <v> <unit> (7d avg <m7>, 28d avg <m28>)``.

    ``None`` values render as en-dash. The unit is omitted entirely when empty.
    """
    v = _fmt(value, precision=precision)
    m7 = _fmt(mean_7d, precision=precision)
    m28 = _fmt(mean_28d, precision=precision)
    head = f"- **{label}**: {v}"
    if unit:
        head = f"{head} {unit}"
    return f"{head} (7d avg {m7}, 28d avg {m28})"


def _downsample(values: list[float | None], width: int) -> list[float | None]:
    """Take the last ``width`` cells. Documented choice: trailing window."""
    if len(values) <= width:
        return values
    return values[-width:]


def render_sparkline(
    values: Iterable[float | None],
    *,
    width: int | None = None,
) -> str:
    """Unicode block sparkline using ``▁▂▃▄▅▆▇█``.

    ``None`` becomes a middle-dot ``·``. If ``width`` is given and there are
    more values than ``width``, take the trailing ``width`` cells. Empty
    input returns the empty string. If all non-None values are identical,
    every cell renders as the lowest block.
    """
    items = list(values)
    if not items:
        return ""
    if width is not None and width > 0:
        items = _downsample(items, width)

    real = [v for v in items if v is not None]
    if not real:
        return _MISSING_CELL * len(items)

    lo = min(real)
    hi = max(real)
    span = hi - lo
    last = len(_BLOCKS) - 1
    out: list[str] = []
    for v in items:
        if v is None:
            out.append(_MISSING_CELL)
            continue
        if span == 0:
            out.append(_BLOCKS[0])
            continue
        idx = round((v - lo) / span * last)
        idx = max(0, min(last, idx))
        out.append(_BLOCKS[idx])
    return "".join(out)


def render_section(title: str, body: str, *, level: int = 2) -> str:
    """Wrap a section: ``<#...> <title>\\n\\n<body>\\n``.

    ``level`` controls the number of ``#`` characters. Clamped to >= 1.
    """
    hashes = "#" * max(1, level)
    return f"{hashes} {title}\n\n{body}\n"
