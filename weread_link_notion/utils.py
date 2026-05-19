from datetime import datetime, timezone, timedelta
import hashlib
import re


CN_TZ = timezone(timedelta(hours=8))


def short_text(value, limit=1900):
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def timestamp_to_dt(value):
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=CN_TZ)
    except (TypeError, ValueError, OSError):
        return None


def date_iso_from_timestamp(value):
    date = timestamp_to_dt(value)
    if not date:
        return None
    return date.date().isoformat()


def datetime_iso_from_timestamp(value):
    date = timestamp_to_dt(value)
    if not date:
        return None
    return date.isoformat()


def seconds_to_minutes(seconds):
    try:
        return round(int(seconds) / 60, 2)
    except (TypeError, ValueError):
        return 0


def format_duration(seconds):
    seconds = int(seconds or 0)
    minutes = seconds // 60
    hours = minutes // 60
    rest = minutes % 60
    if hours and rest:
        return f"{hours}h {rest}m"
    if hours:
        return f"{hours}h"
    if rest:
        return f"{rest}m"
    return "0m"


def stable_id(*parts):
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def rich_text(value):
    return {"rich_text": [{"type": "text", "text": {"content": short_text(value)}}]} if value else {"rich_text": []}


def title(value):
    text = short_text(value or "Untitled", 1900)
    return {"title": [{"type": "text", "text": {"content": text}}]}


def select(value):
    return {"select": {"name": value}} if value else {"select": None}


def number(value):
    if value is None or value == "":
        return {"number": None}
    try:
        return {"number": float(value)}
    except (TypeError, ValueError):
        return {"number": None}


def checkbox(value):
    return {"checkbox": bool(value)}


def url(value):
    return {"url": value or None}


def date(value):
    return {"date": {"start": value}} if value else {"date": None}


def extract_notion_page_id(value):
    match = re.search(
        r"([a-fA-F0-9]{32}|[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})",
        value or "",
    )
    if not match:
        raise ValueError("NOTION_PAGE must be a Notion page URL or page id.")
    return match.group(1).replace("-", "")


def weread_reader_url(book_id):
    book_id = str(book_id)
    digest = hashlib.md5(book_id.encode("utf-8")).hexdigest()
    result = digest[:3]
    code, chunks = _transform_book_id(book_id)
    result += code + "2" + digest[-2:]
    for index, chunk in enumerate(chunks):
        length = format(len(chunk), "x")
        if len(length) == 1:
            length = "0" + length
        result += length + chunk
        if index < len(chunks) - 1:
            result += "g"
    if len(result) < 20:
        result += digest[: 20 - len(result)]
    result += hashlib.md5(result.encode("utf-8")).hexdigest()[:3]
    return "https://weread.qq.com/web/reader/" + result


def _transform_book_id(book_id):
    if re.match(r"^\d*$", book_id):
        chunks = []
        for index in range(0, len(book_id), 9):
            chunks.append(format(int(book_id[index : min(index + 9, len(book_id))]), "x"))
        return "3", chunks
    result = "".join(format(ord(ch), "x") for ch in book_id)
    return "4", [result]
