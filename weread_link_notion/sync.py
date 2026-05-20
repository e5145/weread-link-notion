from datetime import date as date_type, datetime, timedelta
from pathlib import Path

from .heatmap import bucket_to_date, generate_heatmap
from .monthly import generate_monthly_chart
from .notion import NotionStore
from .profile import generate_reading_profile
from .utils import (
    date_iso_from_timestamp,
    datetime_iso_from_timestamp,
    seconds_to_minutes,
    stable_id,
    weread_reader_url,
)
from .weread import WeReadClient, WeReadGatewayError


def build_client(config):
    return WeReadClient(
        api_key=config.weread_api_key,
        skill_version=config.skill_version,
        timeout=config.request_timeout,
    )


def generate_heatmap_assets(config, year=None):
    year = year or datetime.now().year
    client = build_client(config)
    read_times = client.get_year_read_times(year)
    png_path = config.heatmap_path
    svg_path = str(Path(config.heatmap_path).with_suffix(".svg"))
    metadata_path = str(Path(config.heatmap_path).with_suffix(".json"))
    metadata = generate_heatmap(read_times, year, png_path, svg_path=svg_path, metadata_path=metadata_path)
    print(f"Generated heatmap: {png_path}", flush=True)
    print(f"Total: {metadata['total']}; active days: {metadata['active_days']}", flush=True)
    return metadata


def generate_monthly_chart_assets(config, year=None, month=None):
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    client = build_client(config)
    read_times = client.get_month_read_times(year, month)
    metadata_path = str(Path(config.monthly_chart_path).with_suffix(".json"))
    metadata = generate_monthly_chart(read_times, year, month, config.monthly_chart_path, metadata_path=metadata_path)
    print(f"Generated monthly reading chart: {config.monthly_chart_path}", flush=True)
    print(f"Total: {metadata['total']}; active days: {metadata['active_days']}", flush=True)
    return metadata


def generate_profile_assets(config):
    client = build_client(config)
    try:
        read_summary = client.get_read_summary("annually")
    except WeReadGatewayError as exc:
        print(f"Reading profile API failed, generating fallback profile: {exc}", flush=True)
        read_summary = {}
    metadata_path = str(Path(config.profile_path).with_suffix(".json"))
    metadata = generate_reading_profile(read_summary, config.profile_path, metadata_path=metadata_path)
    print(f"Generated reading profile: {config.profile_path}", flush=True)
    print(metadata["summary"], flush=True)
    return metadata


def run_sync(config):
    config.validate()
    client = build_client(config)
    store = NotionStore(config.notion_token, config.notion_page)
    store.setup(config.heatmap_url)

    shelf = client.get_shelf()
    notebooks = list(client.iter_notebooks()) if config.sync_notes else []
    books = normalize_books(shelf, notebooks)

    book_count = 0
    for book in books:
        store.upsert_book(book)
        book_count += 1

    read_times = client.get_year_read_times(datetime.now().year)
    daily_rows = normalize_daily_rows(read_times)
    daily_count = 0
    read_seconds = 0
    for row in daily_rows:
        store.upsert_daily(row)
        daily_count += 1
        read_seconds += row["seconds"]

    try:
        recommendation_data = client.get_recommendations(count=6)
    except WeReadGatewayError as exc:
        print(f"Recommendation API failed, continuing without recommended books: {exc}", flush=True)
        recommendation_data = {}
    recommendations = normalize_recommendations(recommendation_data)
    for recommendation in recommendations:
        store.upsert_recommendation(recommendation)

    note_count = 0
    notes = []
    if config.sync_notes:
        limited = notebooks[: config.max_notebooks] if config.max_notebooks > 0 else notebooks
        print(f"Syncing notes from {len(limited)} notebooks...", flush=True)
        for index, notebook in enumerate(limited, start=1):
            for note in iter_notes_for_notebook(client, notebook):
                notes.append(note)
                store.upsert_note(note)
                note_count += 1
                if note_count % 100 == 0:
                    print(f"Synced {note_count} notes...", flush=True)
            if index % 10 == 0:
                print(f"Processed {index}/{len(limited)} notebooks.", flush=True)

    streak_days = reading_streak(daily_rows)
    counts = {
        "books": book_count,
        "notes": note_count,
        "read_days": daily_count,
        "read_minutes": round(read_seconds / 60, 2),
        "recommendations": len(recommendations),
        "streak_days": streak_days,
    }
    store.rebuild_dashboard(
        counts,
        books,
        notes,
        daily_rows,
        recommendations,
        config.heatmap_url,
        config.profile_url,
        config.monthly_chart_url,
        config.dashboard_quote,
        streak_days,
    )
    store.create_sync_run(
        "success",
        counts,
        config.heatmap_url,
        config.profile_url,
        config.monthly_chart_url,
        "Sync completed.",
    )
    print(
        f"Synced {book_count} books, {note_count} notes, {daily_count} reading days, "
        f"{len(recommendations)} recommendations.",
        flush=True,
    )
    return counts


def normalize_books(shelf, notebooks):
    note_counts = {}
    for item in notebooks:
        book = item.get("book") or {}
        book_id = str(item.get("bookId") or book.get("bookId") or "")
        if not book_id:
            continue
        note_counts[book_id] = {
            "note_count": item.get("noteCount") or 0,
            "review_count": item.get("reviewCount") or 0,
            "bookmark_count": item.get("bookmarkCount") or 0,
            "sort": item.get("sort"),
        }

    progress_map = {}
    for item in shelf.get("bookProgress") or []:
        book_id = str(item.get("bookId") or "")
        if book_id:
            progress_map[book_id] = item

    rows = []
    for item in shelf.get("books") or []:
        book_id = str(item.get("bookId") or "")
        if not book_id:
            continue
        counts = note_counts.get(book_id, {})
        progress = progress_map.get(book_id, {})
        finish = int(item.get("finishReading") or 0) == 1
        last_read = item.get("readUpdateTime") or item.get("updateTime")
        rows.append(
            {
                "id": book_id,
                "title": item.get("title") or item.get("book", {}).get("title") or book_id,
                "type": "电子书",
                "author": item.get("author"),
                "category": item.get("category"),
                "status": "读完" if finish else ("在读" if last_read else "未读"),
                "progress": 1 if finish else None,
                "reading_minutes": seconds_to_minutes(
                    progress.get("readingTime") or item.get("readingTime") or item.get("recordReadingTime")
                ),
                "last_read": date_iso_from_timestamp(last_read),
                "secret": int(item.get("secret") or 0) == 1,
                "cover": item.get("cover"),
                "weread_url": weread_reader_url(book_id),
                "note_count": counts.get("note_count"),
                "review_count": counts.get("review_count"),
                "bookmark_count": counts.get("bookmark_count"),
                "sort": counts.get("sort") or item.get("sort") or item.get("updateTime"),
            }
        )

    for item in shelf.get("albums") or []:
        album = item.get("albumInfo") or {}
        extra = item.get("albumInfoExtra") or {}
        album_id = str(album.get("albumId") or "")
        if not album_id:
            continue
        rows.append(
            {
                "id": "album:" + album_id,
                "title": album.get("name") or album_id,
                "type": "有声书",
                "author": album.get("authorName"),
                "category": "有声书",
                "status": "读完" if int(album.get("finish") or 0) == 1 else "在读",
                "progress": None,
                "reading_minutes": 0,
                "last_read": date_iso_from_timestamp(extra.get("lectureReadUpdateTime") or album.get("updateTime")),
                "secret": int(extra.get("secret") or 0) == 1,
                "cover": album.get("cover"),
                "weread_url": None,
                "note_count": 0,
                "review_count": 0,
                "bookmark_count": 0,
                "sort": album.get("updateTime"),
            }
        )

    if shelf.get("mp"):
        rows.append(
            {
                "id": "mp:articles",
                "title": "文章收藏",
                "type": "文章收藏",
                "author": "",
                "category": "文章",
                "status": "在读",
                "progress": None,
                "reading_minutes": 0,
                "last_read": None,
                "secret": True,
                "cover": None,
                "weread_url": None,
                "note_count": 0,
                "review_count": 0,
                "bookmark_count": 0,
                "sort": 0,
            }
        )
    return rows


def normalize_daily_rows(read_times):
    rows = []
    for timestamp, seconds in sorted(read_times.items()):
        seconds = int(seconds or 0)
        if seconds <= 0:
            continue
        day = bucket_to_date(timestamp)
        iso_year, iso_week, _ = day.isocalendar()
        rows.append(
            {
                "date": day.isoformat(),
                "seconds": seconds,
                "year": iso_year,
                "month": day.month,
                "week": iso_week,
            }
        )
    return rows


def normalize_recommendations(data):
    rows = []
    for index, item in enumerate((data or {}).get("books") or [], start=1):
        book = item.get("bookInfo") or item.get("book") or item
        if isinstance(book.get("bookInfo"), dict):
            book = book["bookInfo"]
        book_id = str(book.get("bookId") or item.get("bookId") or "")
        if not book_id:
            continue
        rating = _normalize_rating(item.get("newRating") or book.get("newRating"))
        rating_detail = item.get("newRatingDetail") or book.get("newRatingDetail") or {}
        rows.append(
            {
                "id": book_id,
                "title": book.get("title") or item.get("title") or book_id,
                "author": book.get("author") or item.get("author"),
                "cover": book.get("cover") or item.get("cover"),
                "intro": book.get("intro") or item.get("intro"),
                "category": book.get("category") or item.get("category"),
                "reason": item.get("reason") or book.get("reason"),
                "reading_count": _to_number(item.get("readingCount") or book.get("readingCount")),
                "rating": rating,
                "rating_count": _to_number(item.get("newRatingCount") or book.get("newRatingCount")),
                "rating_label": rating_detail.get("title"),
                "sort": item.get("searchIdx") or book.get("searchIdx") or index,
                "weread_url": weread_reader_url(book_id),
            }
        )
    return rows


def reading_streak(daily_rows):
    dates = set()
    for row in daily_rows:
        try:
            dates.add(date_type.fromisoformat(row["date"]))
        except (KeyError, TypeError, ValueError):
            continue
    if not dates:
        return 0
    cursor = max(dates)
    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def iter_notes_for_notebook(client, notebook):
    book = notebook.get("book") or {}
    book_id = str(notebook.get("bookId") or book.get("bookId") or "")
    if not book_id:
        return
    book_title = book.get("title") or notebook.get("title") or book_id

    bookmark_data = client.get_bookmarks(book_id)
    chapter_map = {}
    for chapter in bookmark_data.get("chapters") or []:
        chapter_map[chapter.get("chapterUid")] = chapter.get("title")

    for mark in bookmark_data.get("updated") or []:
        if int(mark.get("type") or 1) == 0:
            continue
        content = mark.get("markText") or ""
        if not content.strip():
            continue
        note_id = "bookmark:" + str(mark.get("bookmarkId") or stable_id(book_id, content, mark.get("createTime")))
        yield {
            "id": note_id,
            "content": content,
            "book_id": book_id,
            "book_title": book_title,
            "type": "划线",
            "chapter": chapter_map.get(mark.get("chapterUid")) or "",
            "created_at": datetime_iso_from_timestamp(mark.get("createTime")),
            "range": mark.get("range"),
            "url": weread_reader_url(book_id),
            "star": None,
        }

    for review in client.iter_reviews(book_id):
        content = review.get("content") or review.get("abstract") or ""
        if not content.strip():
            continue
        note_id = "review:" + str(review.get("reviewId") or stable_id(book_id, content, review.get("createTime")))
        yield {
            "id": note_id,
            "content": content,
            "book_id": book_id,
            "book_title": book_title,
            "type": "想法",
            "chapter": review.get("chapterName") or "",
            "created_at": datetime_iso_from_timestamp(review.get("createTime")),
            "range": review.get("range"),
            "url": weread_reader_url(book_id),
            "star": None if review.get("star") in (None, -1) else review.get("star"),
        }


def _normalize_rating(value):
    number = _to_number(value)
    if number is None:
        return None
    if number > 10:
        return round(number / 10, 1)
    return number


def _to_number(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
