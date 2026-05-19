from datetime import date, datetime, timedelta, timezone
import calendar
import html
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .utils import format_duration


COLORS = ["#EDEFF2", "#BFE7C4", "#78C486", "#3F9B57", "#1F6F3A"]
TEXT = "#22272E"
MUTED = "#667085"
BACKGROUND = "#FFFFFF"
BORDER = "#E5E7EB"


def bucket_to_date(timestamp):
    return datetime.fromtimestamp(int(timestamp), tz=timezone(timedelta(hours=8))).date()


def heat_level(seconds):
    seconds = int(seconds or 0)
    if seconds < 60:
        return 0
    if seconds < 30 * 60:
        return 1
    if seconds < 60 * 60:
        return 2
    if seconds < 120 * 60:
        return 3
    return 4


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def read_times_by_date(read_times):
    data = {}
    for key, value in read_times.items():
        data[bucket_to_date(key)] = int(value or 0)
    return data


def generate_heatmap(read_times, year, png_path, svg_path=None, metadata_path=None):
    data = read_times_by_date(read_times)
    first_day = date(year, 1, 1)
    last_day = date(year, 12, 31)
    grid_start = first_day - timedelta(days=first_day.weekday())
    grid_end = last_day + timedelta(days=6 - last_day.weekday())
    week_count = ((grid_end - grid_start).days // 7) + 1

    cell = 14
    gap = 4
    left = 72
    top = 68
    width = left + week_count * (cell + gap) + 36
    height = top + 7 * (cell + gap) + 64
    total = sum(value for day, value in data.items() if day.year == year)
    active_days = sum(1 for day, value in data.items() if day.year == year and value >= 60)

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=16, outline=hex_to_rgb(BORDER), fill=hex_to_rgb(BACKGROUND))
    draw.text((24, 18), f"WeRead {year}", fill=hex_to_rgb(TEXT), font=font)
    draw.text((24, 38), f"{format_duration(total)} · {active_days} active days", fill=hex_to_rgb(MUTED), font=font)

    for month in range(1, 13):
        month_day = date(year, month, 1)
        week_index = (month_day - grid_start).days // 7
        draw.text((left + week_index * (cell + gap), 48), calendar.month_abbr[month], fill=hex_to_rgb(MUTED), font=font)

    for day_index, label in ((0, "Mon"), (2, "Wed"), (4, "Fri")):
        y = top + day_index * (cell + gap) + 3
        draw.text((24, y), label, fill=hex_to_rgb(MUTED), font=font)

    cursor = grid_start
    while cursor <= grid_end:
        week_index = (cursor - grid_start).days // 7
        day_index = cursor.weekday()
        seconds = data.get(cursor, 0) if cursor.year == year else 0
        color = COLORS[heat_level(seconds)] if cursor.year == year else "#FAFAFA"
        x = left + week_index * (cell + gap)
        y = top + day_index * (cell + gap)
        draw.rounded_rectangle((x, y, x + cell, y + cell), radius=3, fill=hex_to_rgb(color))
        cursor += timedelta(days=1)

    png = Path(png_path)
    png.parent.mkdir(parents=True, exist_ok=True)
    image.save(png)

    if svg_path:
        _write_svg(Path(svg_path), data, year, grid_start, grid_end, week_count, total, active_days)

    metadata = {
        "year": year,
        "total_seconds": total,
        "total": format_duration(total),
        "active_days": active_days,
        "png": str(png_path).replace("\\", "/"),
    }
    if metadata_path:
        meta = Path(metadata_path)
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def _write_svg(path, data, year, grid_start, grid_end, week_count, total, active_days):
    cell = 10
    gap = 3
    left = 44
    top = 42
    width = left + week_count * (cell + gap) + 18
    height = top + 7 * (cell + gap) + 32
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="100%" height="100%" fill="{BACKGROUND}"/>',
        f'<text x="8" y="17" fill="{TEXT}" font-family="Arial,sans-serif" font-size="12">WeRead {year}: {html.escape(format_duration(total))}, {active_days} active days</text>',
    ]
    for month in range(1, 13):
        month_day = date(year, month, 1)
        week_index = (month_day - grid_start).days // 7
        parts.append(
            f'<text x="{left + week_index * (cell + gap)}" y="34" fill="{MUTED}" font-family="Arial,sans-serif" font-size="9">{calendar.month_abbr[month]}</text>'
        )
    cursor = grid_start
    while cursor <= grid_end:
        week_index = (cursor - grid_start).days // 7
        day_index = cursor.weekday()
        seconds = data.get(cursor, 0) if cursor.year == year else 0
        color = COLORS[heat_level(seconds)] if cursor.year == year else "#FAFAFA"
        x = left + week_index * (cell + gap)
        y = top + day_index * (cell + gap)
        title = html.escape(f"{cursor.isoformat()}: {format_duration(seconds)}")
        parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{color}"><title>{title}</title></rect>')
        cursor += timedelta(days=1)
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(parts), encoding="utf-8")
