from pathlib import Path
import json
import math
import re

from PIL import Image, ImageDraw, ImageFont

from .utils import format_duration


BACKGROUND = "#F7F7F4"
CARD = "#FFFFFF"
INK = "#232522"
MUTED = "#6D706A"
LINE = "#DFDDD5"
GREEN = "#2F7D51"
BLUE = "#45AEDE"
AMBER = "#FFBE69"
ROSE = "#FF806A"
CYAN = "#45D6E4"
LIME = "#8CF45D"


def generate_reading_profile(read_summary, png_path, metadata_path=None):
    profile = normalize_profile(read_summary)
    image = Image.new("RGB", (1120, 1480), BACKGROUND)
    draw = ImageDraw.Draw(image)
    fonts = _fonts()

    draw.text((42, 34), "阅读画像", fill=INK, font=fonts["title"])
    draw.text((42, 84), profile["summary"], fill=MUTED, font=fonts["body"])

    cards = [
        (42, 132, 500, 360, _draw_category_card),
        (578, 132, 500, 360, _draw_time_card),
        (42, 526, 500, 360, _draw_book_distribution_card),
        (578, 526, 500, 360, _draw_review_distribution_card),
        (42, 920, 500, 360, _draw_author_card),
        (578, 920, 500, 360, _draw_publisher_card),
    ]
    for x, y, width, height, renderer in cards:
        _card(draw, x, y, width, height)
        renderer(draw, profile, x, y, width, height, fonts)

    png = Path(png_path)
    png.parent.mkdir(parents=True, exist_ok=True)
    image.save(png)

    metadata = {
        "summary": profile["summary"],
        "prefer_category_word": profile["prefer_category_word"],
        "prefer_time_word": profile["prefer_time_word"],
        "png": str(png_path).replace("\\", "/"),
    }
    if metadata_path:
        path = Path(metadata_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def normalize_profile(data):
    data = data or {}
    total_seconds = int(data.get("totalReadTime") or 0)
    read_days = int(data.get("readDays") or 0)
    read_stat = data.get("readStat") or []
    categories = []
    for item in data.get("preferCategory") or []:
        label = item.get("categoryTitle") or item.get("parentCategoryTitle")
        if not label:
            continue
        value = float(item.get("val") or item.get("readingTime") or item.get("readingCount") or 0)
        categories.append({"label": label, "value": value})
    categories = _top_values(categories, 6, ["文学", "历史", "影视原著", "社会小说", "玄幻小说", "男生小说"])

    prefer_time = [int(value or 0) for value in (data.get("preferTime") or [])]
    if len(prefer_time) < 24:
        prefer_time = _sample_time_distribution()

    authors = [item.get("name") for item in data.get("preferAuthor") or [] if item.get("name")]
    publishers = [item.get("name") for item in data.get("preferPublisher") or [] if item.get("name")]
    for item in data.get("preferCp") or []:
        info = item.get("copyrightInfo") or {}
        if info.get("name"):
            publishers.append(info["name"])

    return {
        "summary": f"{format_duration(total_seconds)} · {read_days} 个阅读日",
        "prefer_category_word": data.get("preferCategoryWord") or "偏好阅读文学",
        "prefer_time_word": data.get("preferTimeWord") or "偏好下午与夜晚阅读",
        "categories": categories,
        "prefer_time": prefer_time,
        "authors": authors[:16] or ["江南", "马伯庸", "金庸", "鲁迅", "赫尔曼·黑塞", "刘慈欣", "当年明月"],
        "publishers": publishers[:16] or ["果麦文化", "北京市报刊发行局", "博集新媒", "磨铁数盟", "人民文学出版社", "译林出版社"],
        "book_distribution": _distribution_from_categories(categories),
        "review_distribution": _review_distribution(read_stat),
    }


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
        return {"title": base, "h2": base, "body": base, "small": base, "big": base}
    return {
        "title": ImageFont.truetype(font_path, 42),
        "h2": ImageFont.truetype(font_path, 26),
        "body": ImageFont.truetype(font_path, 20),
        "small": ImageFont.truetype(font_path, 16),
        "big": ImageFont.truetype(font_path, 36),
    }


def _card(draw, x, y, width, height):
    draw.rounded_rectangle((x, y, x + width, y + height), radius=24, fill=CARD, outline=LINE, width=1)


def _draw_category_card(draw, profile, x, y, width, height, fonts):
    draw.text((x + 28, y + 24), profile["prefer_category_word"], fill=INK, font=fonts["h2"])
    center = (x + width // 2, y + 206)
    radius = 112
    labels = [item["label"] for item in profile["categories"]]
    values = [item["value"] for item in profile["categories"]]
    max_value = max(values) if values else 1
    points = []
    for index, value in enumerate(values):
        angle = -math.pi / 2 + 2 * math.pi * index / len(values)
        length = radius * (0.25 + 0.75 * (value / max_value if max_value else 0))
        points.append((center[0] + math.cos(angle) * length, center[1] + math.sin(angle) * length))

    for scale in (1, 0.66, 0.33):
        grid = []
        for index in range(len(values)):
            angle = -math.pi / 2 + 2 * math.pi * index / len(values)
            grid.append((center[0] + math.cos(angle) * radius * scale, center[1] + math.sin(angle) * radius * scale))
        draw.polygon(grid, outline="#E6E7E2")
    if points:
        draw.polygon(points, fill="#BFE8F7", outline=BLUE)
    for index, label in enumerate(labels):
        angle = -math.pi / 2 + 2 * math.pi * index / len(values)
        tx = center[0] + math.cos(angle) * (radius + 38)
        ty = center[1] + math.sin(angle) * (radius + 24)
        draw.text((tx - 32, ty - 8), label[:6], fill=MUTED, font=fonts["small"])


def _draw_time_card(draw, profile, x, y, width, height, fonts):
    draw.text((x + 28, y + 24), profile["prefer_time_word"], fill=INK, font=fonts["h2"])
    values = profile["prefer_time"]
    max_value = max(values) if values else 1
    chart_x = x + 44
    chart_y = y + 102
    chart_w = width - 88
    chart_h = 190
    draw.line((chart_x, chart_y, chart_x, chart_y + chart_h), fill="#E6E7E2")
    draw.line((chart_x, chart_y + chart_h, chart_x + chart_w, chart_y + chart_h), fill="#E6E7E2")
    gap = 5
    bar_w = max(4, (chart_w - gap * (len(values) - 1)) / len(values))
    for index, value in enumerate(values):
        ratio = value / max_value if max_value else 0
        bar_h = max(7, chart_h * ratio)
        bx = chart_x + index * (bar_w + gap)
        color = _blend(AMBER, "#A66AF0", index / max(1, len(values) - 1))
        draw.rounded_rectangle((bx, chart_y + chart_h - bar_h, bx + bar_w, chart_y + chart_h), radius=6, fill=color)
    for label, offset in (("06:00", 0), ("12:00", 0.33), ("18:00", 0.66), ("24:00", 1)):
        draw.text((chart_x + chart_w * offset - 20, chart_y + chart_h + 16), label, fill=MUTED, font=fonts["small"])


def _draw_book_distribution_card(draw, profile, x, y, width, height, fonts):
    draw.text((x + 28, y + 24), "书籍分布", fill=INK, font=fonts["h2"])
    _donut(draw, x + width // 2, y + 178, 82, profile["book_distribution"], [AMBER, ROSE, BLUE, "#8BD7F6"])
    _legend(draw, x + 48, y + 278, profile["book_distribution"], [AMBER, ROSE, BLUE, "#8BD7F6"], fonts)


def _draw_review_distribution_card(draw, profile, x, y, width, height, fonts):
    draw.text((x + 28, y + 24), "点评分布", fill=INK, font=fonts["h2"])
    _donut(draw, x + width // 2, y + 178, 82, profile["review_distribution"], [LIME, CYAN])
    _legend(draw, x + 72, y + 278, profile["review_distribution"], [LIME, CYAN], fonts)


def _draw_author_card(draw, profile, x, y, width, height, fonts):
    draw.text((x + 28, y + 24), "偏好作者", fill=INK, font=fonts["h2"])
    _word_cloud(draw, profile["authors"], x + 48, y + 106, width - 96, height - 140, fonts)


def _draw_publisher_card(draw, profile, x, y, width, height, fonts):
    draw.text((x + 28, y + 24), "偏好版权方", fill=INK, font=fonts["h2"])
    _word_cloud(draw, profile["publishers"], x + 48, y + 106, width - 96, height - 140, fonts)


def _donut(draw, cx, cy, radius, items, colors):
    total = sum(item["value"] for item in items) or 1
    start = -90
    for index, item in enumerate(items):
        extent = 360 * item["value"] / total
        draw.pieslice((cx - radius, cy - radius, cx + radius, cy + radius), start, start + extent, fill=colors[index % len(colors)])
        start += extent
    draw.ellipse((cx - 44, cy - 44, cx + 44, cy + 44), fill=CARD)
    draw.text((cx - 24, cy - 20), str(int(total)), fill=INK, font=ImageFont.load_default())


def _legend(draw, x, y, items, colors, fonts):
    for index, item in enumerate(items[:4]):
        yy = y + index * 26
        draw.ellipse((x, yy + 4, x + 12, yy + 16), fill=colors[index % len(colors)])
        draw.text((x + 20, yy), item["label"], fill=MUTED, font=fonts["small"])
        draw.text((x + 260, yy), str(int(item["value"])), fill=INK, font=fonts["small"])


def _word_cloud(draw, words, x, y, width, height, fonts):
    sizes = [fonts["big"], fonts["h2"], fonts["h2"], fonts["body"], fonts["body"], fonts["small"]]
    cursor_x = x + 8
    cursor_y = y + 28
    for index, word in enumerate(words[:14]):
        font = sizes[min(index, len(sizes) - 1)]
        bbox = draw.textbbox((0, 0), word, font=font)
        word_w = bbox[2] - bbox[0]
        if cursor_x + word_w > x + width - 8:
            cursor_x = x + 8
            cursor_y += 44
        draw.text((cursor_x, cursor_y), word, fill=_blend(BLUE, "#AADBEA", min(0.85, index / 12)), font=font)
        cursor_x += word_w + 18


def _top_values(items, limit, fallback_labels):
    if not items:
        return [{"label": label, "value": value} for label, value in zip(fallback_labels, [90, 70, 62, 45, 38, 32])]
    return sorted(items, key=lambda item: item["value"], reverse=True)[:limit]


def _distribution_from_categories(categories):
    if categories:
        return [{"label": item["label"], "value": max(1, item["value"])} for item in categories[:4]]
    fallback = ["好评如潮", "触类入门", "值得一读", "硬核干货"]
    return [{"label": label, "value": value} for label, value in zip(fallback, [21, 20, 11, 8])]


def _review_distribution(stats):
    total = 0
    for item in stats or []:
        if "评" in (item.get("stat") or "") or "笔记" in (item.get("stat") or ""):
            total += _first_number(item.get("counts"))
    if total:
        recommended = max(1, round(total * 0.67))
        return [{"label": "推荐", "value": recommended}, {"label": "认为一般", "value": max(1, total - recommended)}]
    return [{"label": "推荐", "value": 4}, {"label": "认为一般", "value": 2}]


def _first_number(value):
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else 0


def _sample_time_distribution():
    return [2, 4, 13, 15, 15, 14, 19, 22, 24, 17, 10, 12, 13, 28, 34, 38, 29, 9, 4, 2, 1, 1, 1, 1]


def _blend(start, end, ratio):
    ratio = max(0, min(1, ratio))
    a = tuple(int(start.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    b = tuple(int(end.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    c = tuple(round(a[i] + (b[i] - a[i]) * ratio) for i in range(3))
    return "#{:02x}{:02x}{:02x}".format(*c)
