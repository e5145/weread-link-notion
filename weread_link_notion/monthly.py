from datetime import date
import calendar
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .heatmap import bucket_to_date, hex_to_rgb
from .utils import format_duration


BACKGROUND = "#F6F7F8"
CARD = "#FFFFFF"
INK = "#53565D"
MUTED = "#A4A8AE"
GRID = "#E6E8EB"
BLUE = "#35AEEF"


def generate_monthly_chart(read_times, year, month, png_path, metadata_path=None):
    values = _month_values(read_times, year, month)
    total = sum(values)
    active_days = sum(1 for seconds in values if seconds >= 60)
    month_label = f"{year}-{month:02d}"

    image = Image.new("RGB", (1280, 860), BACKGROUND)
    draw = ImageDraw.Draw(image)
    fonts = _fonts()

    draw.rounded_rectangle((34, 34, 1246, 826), radius=44, fill=CARD)
    draw.text((94, 100), "阅读时长分布", fill=INK, font=fonts["title"])
    _calendar_icon(draw, 1096, 102)

    chart_x = 110
    chart_y = 238
    chart_w = 980
    chart_h = 430
    max_hours = max(9, _nice_max_hours(max(values) / 3600 if values else 0))

    for hour in (0, max_hours / 3, max_hours * 2 / 3, max_hours):
        y = chart_y + chart_h - (hour / max_hours * chart_h if max_hours else 0)
        draw.line((chart_x, y, chart_x + chart_w, y), fill=hex_to_rgb(GRID), width=2)
        _draw_y_label(draw, chart_x + chart_w + 58, y - 16, hour, fonts)

    days = len(values)
    gap = max(9, chart_w / days * 0.48)
    bar_w = max(9, (chart_w - gap * (days - 1)) / days)
    for index, seconds in enumerate(values, start=1):
        hours = seconds / 3600
        bar_h = chart_h * hours / max_hours if max_hours else 0
        x = chart_x + (index - 1) * (bar_w + gap)
        bottom = chart_y + chart_h
        if bar_h < 3 and seconds > 0:
            bar_h = 7
        if bar_h > 0:
            draw.rounded_rectangle((x, bottom - bar_h, x + bar_w, bottom), radius=bar_w / 2, fill=hex_to_rgb(BLUE))
        elif index <= date.today().day or (year, month) < (date.today().year, date.today().month):
            draw.rounded_rectangle((x, bottom - 5, x + bar_w, bottom), radius=bar_w / 2, fill=hex_to_rgb(BLUE))

    for day in _x_ticks(days):
        x = chart_x + (day - 1) * (bar_w + gap) + bar_w / 2
        draw.text((x - 10, chart_y + chart_h + 34), str(day), fill=hex_to_rgb(MUTED), font=fonts["axis"])

    draw.text(
        (94, 730),
        f"{month_label} · {format_duration(total)} · {active_days} 个阅读日",
        fill=hex_to_rgb(MUTED),
        font=fonts["body"],
    )

    png = Path(png_path)
    png.parent.mkdir(parents=True, exist_ok=True)
    image.save(png)

    metadata = {
        "year": year,
        "month": month,
        "total_seconds": total,
        "total": format_duration(total),
        "active_days": active_days,
        "png": str(png_path).replace("\\", "/"),
    }
    if metadata_path:
        path = Path(metadata_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def _month_values(read_times, year, month):
    day_count = calendar.monthrange(year, month)[1]
    values = [0 for _ in range(day_count)]
    for timestamp, seconds in (read_times or {}).items():
        day = bucket_to_date(timestamp)
        if day.year == year and day.month == month:
            values[day.day - 1] += int(seconds or 0)
    return values


def _fonts():
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    font_path = next((path for path in candidates if Path(path).exists()), None)
    if not font_path:
        base = ImageFont.load_default()
        return {"title": base, "body": base, "axis": base}
    return {
        "title": ImageFont.truetype(font_path, 48),
        "body": ImageFont.truetype(font_path, 26),
        "axis": ImageFont.truetype(font_path, 30),
    }


def _calendar_icon(draw, x, y):
    shadow = "#EEF0F2"
    stroke = "#A5A8AD"
    draw.rounded_rectangle((x - 28, y - 28, x + 72, y + 72), radius=26, fill=shadow)
    draw.rounded_rectangle((x, y, x + 54, y + 54), radius=5, outline=hex_to_rgb(stroke), width=4)
    draw.line((x, y + 16, x + 54, y + 16), fill=hex_to_rgb(stroke), width=4)
    for dot_x in (x + 14, x + 28, x + 42):
        for dot_y in (y + 30, y + 43):
            draw.rounded_rectangle((dot_x - 2, dot_y - 2, dot_x + 2, dot_y + 2), radius=2, fill=hex_to_rgb(stroke))


def _draw_y_label(draw, x, y, hour, fonts):
    if hour <= 0:
        label = "0"
    else:
        label = f"{int(round(hour))}h"
    draw.text((x, y), label, fill=hex_to_rgb(MUTED), font=fonts["axis"])


def _nice_max_hours(value):
    if value <= 3:
        return 3
    if value <= 6:
        return 6
    return 9


def _x_ticks(day_count):
    ticks = [1, 5, 10, 15, 20, 25, 30]
    if day_count == 31:
        ticks.append(31)
    return [day for day in ticks if day <= day_count]
