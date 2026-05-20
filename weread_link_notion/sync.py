from datetime import datetime
from pathlib import Path

from .heatmap import bucket_to_date, generate_heatmap
from .notion import NotionStore
from .utils import (
    date_iso_from_timestamp,
    datetime_iso_from_timestamp,
    seconds_to_minutes,
    stable_id,
    weread_reader_url,
)
from .weread import WeReadClient


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

    counts = {
        "books": book_count,
        "notes": note_count,
        "read_days": daily_count,
        "read_minutes": round(read_seconds / 60, 2),
    }
    store.rebuild_dashboard(counts, books, notes, daily_rows, config.heatmap_url)
    store.create_sync_run("success", counts, config.heatmap_url, "Sync completed.")
    print(f"Synced {book_count} books, {note_count} notes, {daily_count} reading days.", flush=True)
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
