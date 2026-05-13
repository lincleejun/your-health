"""Tests for ``health.report.render``."""

from __future__ import annotations

from health.report.render import (
    render_kpi_table,
    render_section,
    render_sparkline,
    render_trend_bullet,
)


def test_kpi_table_renders_header_and_rows() -> None:
    table = render_kpi_table([("Steps", "12,345"), ("RHR", "55 bpm")])
    lines = table.splitlines()
    assert lines[0] == "| metric | value |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| Steps | 12,345 |"
    assert lines[3] == "| RHR | 55 bpm |"


def test_kpi_table_empty_rows() -> None:
    table = render_kpi_table([])
    lines = table.splitlines()
    assert lines == ["| metric | value |", "| --- | --- |"]


def test_trend_bullet_happy_path() -> None:
    out = render_trend_bullet("RHR", 55.0, 56.3, 58.1, unit="bpm", precision=1)
    assert out == "- **RHR**: 55.0 bpm (7d avg 56.3, 28d avg 58.1)"


def test_trend_bullet_no_unit() -> None:
    out = render_trend_bullet("HRV", 42.0, 41.0, 40.0)
    assert out == "- **HRV**: 42.0 (7d avg 41.0, 28d avg 40.0)"


def test_trend_bullet_none_values_render_as_dash() -> None:
    out = render_trend_bullet("RHR", None, None, None, unit="bpm")
    dash = chr(0x2013)  # en-dash, the missing-value glyph
    assert out == f"- **RHR**: {dash} bpm (7d avg {dash}, 28d avg {dash})"


def test_trend_bullet_precision_zero() -> None:
    out = render_trend_bullet("Steps", 12345.6, 11000.4, 10000.0, precision=0)
    assert out == "- **Steps**: 12346 (7d avg 11000, 28d avg 10000)"


def test_sparkline_basic_ramp() -> None:
    out = render_sparkline([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    assert out == "▁▂▃▄▅▆▇█"


def test_sparkline_with_none_uses_middle_dot() -> None:
    out = render_sparkline([1.0, None, 8.0])
    assert len(out) == 3
    assert out[1] == "·"
    assert out[0] == "▁"
    assert out[2] == "█"


def test_sparkline_empty_input() -> None:
    assert render_sparkline([]) == ""


def test_sparkline_constant_values() -> None:
    out = render_sparkline([5.0, 5.0, 5.0])
    # All identical → choose lowest block consistently
    assert len(out) == 3
    assert set(out) == {"▁"}


def test_sparkline_downsamples_to_width() -> None:
    values: list[float | None] = [float(i) for i in range(20)]
    out = render_sparkline(values, width=5)
    assert len(out) == 5


def test_section_default_level() -> None:
    out = render_section("Activity", "body text")
    assert out == "## Activity\n\nbody text\n"


def test_section_custom_level() -> None:
    out = render_section("Title", "x", level=1)
    assert out == "# Title\n\nx\n"
    out3 = render_section("Sub", "y", level=3)
    assert out3 == "### Sub\n\ny\n"
