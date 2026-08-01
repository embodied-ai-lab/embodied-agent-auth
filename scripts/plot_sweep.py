#!/usr/bin/env python3
"""Render the reported-distance sweep as one PNG figure.

Usage:
    python3 scripts/plot_sweep.py --sweep-dir results/attack_sweep-<stamp>-<id>

Reads ``summary.json`` written by ``scripts/sweep_summary.py`` and writes
``sweep.png`` beside it. One row per reported distance, showing the STOP and
PROCEED counts and the median inference latency. Pillow is the only dependency,
and it is already installed by ``make setup``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

WIDTH = 900
ROW_HEIGHT = 34
TOP = 96
BOTTOM = 56
LEFT_LABEL = 130
BAR_LEFT = 150
BAR_RIGHT = 620
LATENCY_X = 660

BACKGROUND = (255, 255, 255)
INK = (24, 24, 27)
MUTED = (113, 113, 122)
GRID = (228, 228, 231)
STOP_COLOR = (37, 99, 235)
PROCEED_COLOR = (220, 38, 38)
INVALID_COLOR = (161, 161, 170)

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def load_font(size: int) -> Any:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def sorted_distances(distances: dict[str, Any]) -> list[tuple[float, str, dict]]:
    rows: list[tuple[float, str, dict]] = []
    for label, record in distances.items():
        try:
            value = float(label)
        except ValueError:
            value = float("inf")
        rows.append((value, label, record))
    return sorted(rows, key=lambda row: (row[0], row[1]))


def render(summary: dict[str, Any], destination: Path) -> Path:
    distances = summary.get("distances") or {}
    rows = sorted_distances(distances)
    height = TOP + max(len(rows), 1) * ROW_HEIGHT + BOTTOM
    image = Image.new("RGB", (WIDTH, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    title_font = load_font(20)
    label_font = load_font(14)
    small_font = load_font(12)

    draw.text(
        (24, 22),
        "Reported-distance sweep: live VLM action by false distance",
        font=title_font,
        fill=INK,
    )
    total = summary.get("total_trials", 0)
    invalid = summary.get("invalid_trials", 0)
    draw.text(
        (24, 50),
        f"{total} trials, {invalid} execution-invalid, "
        f"{len(rows)} reported distances",
        font=small_font,
        fill=MUTED,
    )

    legend_x = 24
    for color, name in (
        (STOP_COLOR, "STOP"),
        (PROCEED_COLOR, "PROCEED"),
        (INVALID_COLOR, "invalid"),
    ):
        draw.rectangle([legend_x, 70, legend_x + 12, 82], fill=color)
        draw.text((legend_x + 18, 68), name, font=small_font, fill=MUTED)
        legend_x += 18 + int(draw.textlength(name, font=small_font)) + 22

    draw.text((LATENCY_X, 68), "median latency", font=small_font, fill=MUTED)

    max_trials = max((int(record.get("trials") or 0) for _, _, record in rows), default=1)
    max_trials = max(max_trials, 1)
    span = BAR_RIGHT - BAR_LEFT

    for index, (_, label, record) in enumerate(rows):
        y = TOP + index * ROW_HEIGHT
        middle = y + ROW_HEIGHT // 2
        draw.line([BAR_LEFT, y + ROW_HEIGHT - 1, BAR_RIGHT, y + ROW_HEIGHT - 1],
                  fill=GRID)
        draw.text(
            (LEFT_LABEL - int(draw.textlength(f"{label} m", font=label_font)), middle - 8),
            f"{label} m",
            font=label_font,
            fill=INK,
        )

        stop = int(record.get("stop") or 0)
        proceed = int(record.get("proceed") or 0)
        invalid_count = int(record.get("invalid") or 0)
        cursor = BAR_LEFT
        for count, color in (
            (stop, STOP_COLOR),
            (proceed, PROCEED_COLOR),
            (invalid_count, INVALID_COLOR),
        ):
            if count <= 0:
                continue
            width = max(int(span * count / max_trials), 3)
            draw.rectangle([cursor, y + 7, cursor + width, y + 25], fill=color)
            text = str(count)
            text_width = int(draw.textlength(text, font=small_font))
            if width >= text_width + 8:
                draw.text(
                    (cursor + (width - text_width) // 2, middle - 7),
                    text,
                    font=small_font,
                    fill=BACKGROUND,
                )
            cursor += width + 2

        median = record.get("median_latency_ms")
        rendered = f"{float(median):.0f} ms" if median is not None else "n/a"
        draw.text((LATENCY_X, middle - 8), rendered, font=label_font, fill=MUTED)

    if not rows:
        draw.text((24, TOP), "No sweep trials were recorded.", font=label_font, fill=INK)

    draw.text(
        (24, height - 36),
        "Bar length is the trial count. STOP and PROCEED are empirical live-model "
        "outcomes, not a deterministic rule.",
        font=small_font,
        fill=MUTED,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sweep-dir",
        type=Path,
        required=True,
        help="attack sweep results directory containing summary.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output PNG path; defaults to <sweep-dir>/sweep.png",
    )
    args = parser.parse_args()

    summary_path = args.sweep_dir / "summary.json"
    if not summary_path.is_file():
        print(f"ERROR: {summary_path} not found.")
        return 2
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: {summary_path} is not valid JSON: {exc.msg}")
        return 2
    if not isinstance(summary, dict):
        print(f"ERROR: {summary_path} is not a JSON object.")
        return 2

    destination = args.output or (args.sweep_dir / "sweep.png")
    render(summary, destination)
    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
