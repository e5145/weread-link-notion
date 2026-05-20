from datetime import datetime, timezone
import time

from notion_client import Client
from notion_client.errors import APIResponseError, RequestTimeoutError, UnknownHTTPResponseError

from .utils import (
    checkbox,
    date,
    extract_notion_page_id,
    number,
    rich_text,
    select,
    short_text,
    title,
    url,
)


DASHBOARD_MARKER = "WeRead Link Notion"
HEATMAP_MARKER = "WeRead Link Notion heatmap"
DASHBOARD_SNAPSHOT_PREFIX = "最近同步 ·"
DASHBOARD_TITLE_PREFIX = "微信读书阅读面板 ·"


BOOKS_DB = "书库"
NOTES_DB = "笔记"
DAILY_DB = "每日阅读"
RUNS_DB = "同步快照"

REQUIRED_PROPERTIES = {
    BOOKS_DB: ("书名", "Book ID"),
    NOTES_DB: ("内容", "Note ID"),
    DAILY_DB: ("日期",),
    RUNS_DB: ("同步时间",),
}


class NotionStore:
    def __init__(self, token, page):
        self.client = Client(auth=token, timeout_ms=90000)
        self.page_id = extract_notion_page_id(page)
        self.databases = {}
        self.page_cache = {}

    def setup(self, heatmap_url=""):
        self._load_child_databases()
        self._ensure_databases()
        return self.databases

    def _uses_data_sources(self):
        return hasattr(self.client, "data_sources")

    def _children(self, block_id):
        results = []
        cursor = None
        while True:
            kwargs = {"block_id": block_id, "page_size": 100}
            if cursor:
                kwargs["start_cursor"] = cursor
            response = self._notion(self.client.blocks.children.list, **kwargs)
            results.extend(response.get("results") or [])
            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")
        return results

    def _load_child_databases(self):
        self.databases = {}
        candidates = {name: [] for name in REQUIRED_PROPERTIES}
        for block in self._children(self.page_id):
            if block.get("type") == "child_database":
                title_text = block["child_database"]["title"]
                required = REQUIRED_PROPERTIES.get(title_text)
                if not required:
                    continue
                queryable_id = self._queryable_database_id(block["id"])
                has_schema = self._database_has_properties(queryable_id, required)
                row_count = self._database_row_count(queryable_id) if has_schema else 0
                candidates[title_text].append(
                    {
                        "block_id": block["id"],
                        "queryable_id": queryable_id,
                        "has_schema": has_schema,
                        "row_count": row_count,
                    }
                )

        for title_text, blocks in candidates.items():
            valid = [block for block in blocks if block["has_schema"]]
            if not valid:
                for block in blocks:
                    self._archive_block(block["block_id"])
                continue

            chosen = sorted(valid, key=lambda block: block["row_count"])[-1]
            self.databases[title_text] = chosen["queryable_id"]

            if len(valid) <= 1:
                continue
            for block in blocks:
                if block["block_id"] == chosen["block_id"]:
                    continue
                self._archive_block(block["block_id"])

    def _walk_blocks(self, block_id):
        for block in self._children(block_id):
            yield block
            if block.get("has_children") and block.get("type") != "child_database":
                yield from self._walk_blocks(block["id"])

    def rebuild_dashboard(self, counts, books, notes, daily_rows, heatmap_url=""):
        now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
        anchor_id = self._find_managed_dashboard_anchor_id()
        children = [
            _paragraph(
                "自动同步已经完成。完整数据在下方 4 个数据库中，这里只保留最常看的摘要和最近内容。"
            ),
            _paragraph(
                f"书库 {counts.get('books', 0)} 本  ·  "
                f"笔记 {counts.get('notes', 0)} 条  ·  "
                f"阅读日 {counts.get('read_days', 0)} 天  ·  "
                f"今年 {counts.get('read_minutes', 0)} 分钟"
            ),
        ]
        if heatmap_url:
            children.extend([_divider(), _image_payload(heatmap_url)])

        children.extend(
            [
                _divider(),
                _heading_3("最近阅读"),
            ]
        )
        for book in _recent_books(books):
            children.append(_bulleted_list_item(_format_book_preview(book)))
        if children[-1].get("type") == "heading_3":
            children.append(_bulleted_list_item("暂时没有最近阅读书籍。"))

        children.extend([_divider(), _heading_3("最近笔记")])
        for note in _recent_notes(notes):
            children.append(_bulleted_list_item(_format_note_preview(note)))
        if children[-1].get("type") == "heading_3":
            children.append(_bulleted_list_item("暂时没有笔记。"))

        children.extend([_divider(), _heading_3("最近阅读日")])
        for row in _recent_daily_rows(daily_rows):
            children.append(_bulleted_list_item(_format_daily_preview(row)))
        if children[-1].get("type") == "heading_3":
            children.append(_bulleted_list_item("暂时没有每日阅读数据。"))

        dashboard = _callout(
            f"{DASHBOARD_TITLE_PREFIX}{now}",
            icon="📖",
            color="blue_background",
            children=children,
        )
        kwargs = {"block_id": self.page_id, "children": [dashboard]}
        if anchor_id:
            kwargs["after"] = anchor_id
        response = self._notion(self.client.blocks.children.append, **kwargs)
        new_ids = {block["id"] for block in response.get("results") or []}
        self._cleanup_managed_dashboard(exclude_ids=new_ids)
        return response

    def _ensure_databases(self):
        specs = {
            BOOKS_DB: _books_schema(),
            NOTES_DB: _notes_schema(),
            DAILY_DB: _daily_schema(),
            RUNS_DB: _runs_schema(),
        }
        for name, schema in specs.items():
            if name not in self.databases:
                kwargs = {
                    "parent": {"type": "page_id", "page_id": self.page_id},
                    "title": [{"type": "text", "text": {"content": name}}],
                }
                if self._uses_data_sources():
                    kwargs["initial_data_source"] = {"properties": schema}
                else:
                    kwargs["properties"] = schema
                response = self._notion(self.client.databases.create, **kwargs)
                self.databases[name] = self._queryable_database_id_from_response(response)
            else:
                self._ensure_database_properties(self.databases[name], schema)

    def upsert_book(self, book):
        props = {
            "书名": title(book["title"]),
            "Book ID": rich_text(book["id"]),
            "类型": select(book.get("type")),
            "作者": rich_text(book.get("author")),
            "分类": rich_text(book.get("category")),
            "状态": select(book.get("status")),
            "进度": number(book.get("progress")),
            "阅读时长(分钟)": number(book.get("reading_minutes")),
            "最近阅读": date(book.get("last_read")),
            "私密": checkbox(book.get("secret")),
            "封面": url(book.get("cover")),
            "微信读书链接": url(book.get("weread_url")),
            "划线数": number(book.get("note_count")),
            "想法数": number(book.get("review_count")),
            "书签数": number(book.get("bookmark_count")),
            "排序": number(book.get("sort")),
        }
        return self._upsert(self.databases[BOOKS_DB], "Book ID", book["id"], props)

    def upsert_note(self, note):
        props = {
            "内容": title(note["content"]),
            "Note ID": rich_text(note["id"]),
            "Book ID": rich_text(note.get("book_id")),
            "书名": rich_text(note.get("book_title")),
            "类型": select(note.get("type")),
            "章节": rich_text(note.get("chapter")),
            "创建时间": date(note.get("created_at")),
            "位置": rich_text(note.get("range")),
            "链接": url(note.get("url")),
            "评分": number(note.get("star")),
        }
        return self._upsert(self.databases[NOTES_DB], "Note ID", note["id"], props, update_existing=False)

    def upsert_daily(self, row):
        props = {
            "日期": title(row["date"]),
            "Date": date(row["date"]),
            "阅读时长(秒)": number(row["seconds"]),
            "阅读时长(分钟)": number(round(row["seconds"] / 60, 2)),
            "Year": number(row["year"]),
            "Month": number(row["month"]),
            "Week": number(row["week"]),
        }
        return self._upsert(self.databases[DAILY_DB], "日期", row["date"], props, title_key=True)

    def create_sync_run(self, status, counts, heatmap_url="", message=""):
        now = datetime.now(timezone.utc).astimezone().isoformat()
        props = {
            "同步时间": title(now),
            "Status": select(status),
            "Books": number(counts.get("books")),
            "Notes": number(counts.get("notes")),
            "Read Days": number(counts.get("read_days")),
            "Read Minutes": number(counts.get("read_minutes")),
            "Heatmap": url(heatmap_url),
            "Message": rich_text(message),
        }
        return self._notion(self.client.pages.create, parent=self._database_parent(self.databases[RUNS_DB]), properties=props)

    def update_heatmap(self, heatmap_url):
        block = self._find_heatmap_block()
        if block:
            block_type = block.get("type")
            if block_type == "image":
                return self._notion(
                    self.client.blocks.update,
                    block_id=block["id"],
                    image=_image_content(heatmap_url),
                )
            if block_type == "embed":
                parent = block.get("parent") or {}
                parent_id = parent.get("page_id") or parent.get("block_id")
                if parent_id:
                    response = self._notion(
                        self.client.blocks.children.append,
                        block_id=parent_id,
                        after=block["id"],
                        children=[_image_payload(heatmap_url)],
                    )
                    self._notion(self.client.blocks.delete, block_id=block["id"])
                    return response
        return self._notion(self.client.blocks.children.append, block_id=self.page_id, children=[_image_payload(heatmap_url)])

    def _find_heatmap_block(self):
        for block in self._walk_blocks(self.page_id):
            block_type = block.get("type")
            if block_type == "image":
                caption = _plain_text(block.get("image", {}).get("caption") or [])
                external = block.get("image", {}).get("external") or {}
                if HEATMAP_MARKER in caption or "/assets/heatmap" in (external.get("url") or ""):
                    return block
            if block_type == "embed":
                embed_url = (block.get("embed") or {}).get("url", "")
                if embed_url.startswith("https://heatmap.malinkang.com/") or "/OUT_FOLDER/" in embed_url:
                    return block
        return None

    def _find_managed_dashboard_anchor_id(self):
        for block in self._children(self.page_id):
            if self._is_managed_dashboard_block(block):
                return block["id"]
        return None

    def _cleanup_managed_dashboard(self, exclude_ids=None):
        exclude_ids = exclude_ids or set()
        for block in self._children(self.page_id):
            if block["id"] in exclude_ids:
                continue
            if self._is_managed_dashboard_block(block):
                self._archive_block(block["id"])

    def _is_managed_dashboard_block(self, block):
        text = _plain_text_from_block(block)
        if text.startswith(DASHBOARD_TITLE_PREFIX):
            return True
        if text.startswith(DASHBOARD_SNAPSHOT_PREFIX):
            return True
        if DASHBOARD_MARKER in text:
            return True
        if "微信读书同步面板" in text or text == "阅读热力图":
            return True
        if block.get("type") == "image":
            return self._is_managed_heatmap_block(block)
        return False

    def _is_managed_heatmap_block(self, block):
        caption = _plain_text(block.get("image", {}).get("caption") or [])
        external = block.get("image", {}).get("external") or {}
        return HEATMAP_MARKER in caption or "/assets/heatmap" in (external.get("url") or "")

    def _upsert(self, database_id, key_property, key, properties, title_key=False, update_existing=True):
        cache_key = (database_id, key_property, "title" if title_key else "rich_text")
        if cache_key not in self.page_cache:
            self.page_cache[cache_key] = self._load_page_cache(database_id, key_property, title_key)
        cache = self.page_cache[cache_key]
        if key in cache:
            if not update_existing:
                return {"id": cache[key], "object": "page", "skipped": True}
            return self._notion(self.client.pages.update, page_id=cache[key], properties=properties)
        response = self._notion(self.client.pages.create, parent=self._database_parent(database_id), properties=properties)
        cache[key] = response["id"]
        return response

    def _query_database(self, database_id, start_cursor=None):
        kwargs = {"page_size": 100}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
        if self._uses_data_sources():
            return self._notion(self.client.data_sources.query, data_source_id=database_id, **kwargs)
        return self._notion(self.client.databases.query, database_id=database_id, **kwargs)

    def _database_row_count(self, database_id, limit=5000):
        count = 0
        cursor = None
        try:
            while True:
                response = self._query_database(database_id, cursor)
                count += len(response.get("results") or [])
                if count >= limit or not response.get("has_more"):
                    break
                cursor = response.get("next_cursor")
        except Exception:  # noqa: BLE001 - duplicate cleanup should not block syncing.
            return 0
        return count

    def _load_page_cache(self, database_id, key_property, title_key=False):
        cache = {}
        cursor = None
        while True:
            response = self._query_database(database_id, cursor)
            for page in response.get("results") or []:
                value = _property_text(page.get("properties", {}).get(key_property), title_key)
                if value:
                    cache[value] = page["id"]
            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")
        return cache

    def _database_parent(self, database_id):
        if self._uses_data_sources():
            return {"type": "data_source_id", "data_source_id": database_id}
        return {"database_id": database_id}

    def _is_direct_child_of_page(self, block):
        parent = block.get("parent") or {}
        page_id = (parent.get("page_id") or "").replace("-", "")
        return page_id == self.page_id

    def _queryable_database_id(self, database_id):
        if not self._uses_data_sources():
            return database_id
        response = self._notion(self.client.databases.retrieve, database_id=database_id)
        return self._queryable_database_id_from_response(response) or database_id

    def _queryable_database_id_from_response(self, response):
        if not self._uses_data_sources():
            return response["id"]
        data_sources = response.get("data_sources") or []
        if data_sources:
            return data_sources[0].get("id") or response["id"]
        return response["id"]

    def _database_properties(self, database_id):
        if self._uses_data_sources():
            response = self._notion(self.client.data_sources.retrieve, data_source_id=database_id)
        else:
            response = self._notion(self.client.databases.retrieve, database_id=database_id)
        return response.get("properties") or {}

    def _database_has_properties(self, database_id, property_names):
        try:
            properties = self._database_properties(database_id)
        except Exception:  # noqa: BLE001 - stale or inaccessible child databases should be ignored.
            return False
        return all(name in properties for name in property_names)

    def _ensure_database_properties(self, database_id, schema):
        properties = self._database_properties(database_id)
        missing = {
            name: definition
            for name, definition in schema.items()
            if name not in properties and "title" not in definition
        }
        if not missing:
            return None
        if self._uses_data_sources():
            return self._notion(self.client.data_sources.update, data_source_id=database_id, properties=missing)
        return self._notion(self.client.databases.update, database_id=database_id, properties=missing)

    def _archive_block(self, block_id):
        try:
            return self._notion(self.client.blocks.delete, block_id=block_id)
        except Exception:  # noqa: BLE001 - cleanup is best effort.
            return None

    def _notion(self, func, **kwargs):
        last_error = None
        for attempt in range(4):
            try:
                return func(**kwargs)
            except RequestTimeoutError as exc:
                last_error = exc
            except UnknownHTTPResponseError as exc:
                last_error = exc
            except APIResponseError as exc:
                code = getattr(getattr(exc, "code", ""), "value", getattr(exc, "code", ""))
                if code not in ("rate_limited", "internal_server_error", "service_unavailable"):
                    raise
                last_error = exc
            if attempt < 3:
                time.sleep(2 * (attempt + 1))
        raise last_error


def _books_schema():
    return {
        "书名": {"title": {}},
        "Book ID": {"rich_text": {}},
        "类型": {"select": {"options": _options(["电子书", "有声书", "文章收藏"])}},
        "作者": {"rich_text": {}},
        "分类": {"rich_text": {}},
        "状态": {"select": {"options": _options(["未读", "在读", "读完"])}},
        "进度": {"number": {"format": "percent"}},
        "阅读时长(分钟)": {"number": {"format": "number"}},
        "最近阅读": {"date": {}},
        "私密": {"checkbox": {}},
        "封面": {"url": {}},
        "微信读书链接": {"url": {}},
        "划线数": {"number": {"format": "number"}},
        "想法数": {"number": {"format": "number"}},
        "书签数": {"number": {"format": "number"}},
        "排序": {"number": {"format": "number"}},
    }


def _notes_schema():
    return {
        "内容": {"title": {}},
        "Note ID": {"rich_text": {}},
        "Book ID": {"rich_text": {}},
        "书名": {"rich_text": {}},
        "类型": {"select": {"options": _options(["划线", "想法"])}},
        "章节": {"rich_text": {}},
        "创建时间": {"date": {}},
        "位置": {"rich_text": {}},
        "链接": {"url": {}},
        "评分": {"number": {"format": "number"}},
    }


def _daily_schema():
    return {
        "日期": {"title": {}},
        "Date": {"date": {}},
        "阅读时长(秒)": {"number": {"format": "number"}},
        "阅读时长(分钟)": {"number": {"format": "number"}},
        "Year": {"number": {"format": "number"}},
        "Month": {"number": {"format": "number"}},
        "Week": {"number": {"format": "number"}},
    }


def _runs_schema():
    return {
        "同步时间": {"title": {}},
        "Status": {"select": {"options": _options(["success", "failure"])}},
        "Books": {"number": {"format": "number"}},
        "Notes": {"number": {"format": "number"}},
        "Read Days": {"number": {"format": "number"}},
        "Read Minutes": {"number": {"format": "number"}},
        "Heatmap": {"url": {}},
        "Message": {"rich_text": {}},
    }


def _options(names):
    colors = ["blue", "green", "yellow", "orange", "purple", "pink", "gray"]
    return [{"name": name, "color": colors[index % len(colors)]} for index, name in enumerate(names)]


def _heading_1(text):
    return {"object": "block", "type": "heading_1", "heading_1": {"rich_text": _rt(text)}}


def _heading_2(text):
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": _rt(text)}}


def _heading_3(text):
    return {"object": "block", "type": "heading_3", "heading_3": {"rich_text": _rt(text)}}


def _paragraph(text):
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rt(text)}}


def _divider():
    return {"object": "block", "type": "divider", "divider": {}}


def _bulleted_list_item(text):
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rt(text)},
    }


def _quote(text, children=None):
    payload = {"rich_text": _rt(text), "color": "default"}
    if children:
        payload["children"] = children
    return {"object": "block", "type": "quote", "quote": payload}


def _callout(text, icon="📚", color="default", children=None):
    payload = {
        "rich_text": _rt(text),
        "icon": {"type": "emoji", "emoji": icon},
        "color": color,
    }
    if children:
        payload["children"] = children
    return {
        "object": "block",
        "type": "callout",
        "callout": payload,
    }


def _image_payload(heatmap_url):
    return {
        "object": "block",
        "type": "image",
        "image": _image_content(heatmap_url),
    }


def _image_content(heatmap_url):
    return {
        "external": {"url": heatmap_url},
        "caption": _rt(HEATMAP_MARKER),
    }


def _rt(text):
    return [{"type": "text", "text": {"content": short_text(text)}}]


def _plain_text(items):
    return "".join(item.get("plain_text", "") for item in items)


def _plain_text_from_block(block):
    block_type = block.get("type")
    if not block_type:
        return ""
    payload = block.get(block_type) or {}
    return _plain_text(payload.get("rich_text") or payload.get("caption") or [])


def _property_text(prop, title_key=False):
    if not prop:
        return ""
    if title_key:
        return _plain_text(prop.get("title") or [])
    return _plain_text(prop.get("rich_text") or [])


def _recent_books(books, limit=8):
    return sorted(
        books,
        key=lambda book: (book.get("last_read") or "", book.get("sort") or 0),
        reverse=True,
    )[:limit]


def _recent_notes(notes, limit=10):
    return sorted(notes, key=lambda note: note.get("created_at") or "", reverse=True)[:limit]


def _recent_daily_rows(rows, limit=7):
    return sorted(rows, key=lambda row: row.get("date") or "", reverse=True)[:limit]


def _format_book_preview(book):
    parts = [f"《{book.get('title') or '未命名'}》"]
    if book.get("author"):
        parts.append(str(book["author"]))
    if book.get("last_read"):
        parts.append("最近 " + str(book["last_read"]))
    minutes = book.get("reading_minutes")
    if minutes:
        parts.append(f"{minutes} 分钟")
    return " · ".join(parts)


def _format_note_preview(note):
    book_title = note.get("book_title") or "未知书籍"
    note_type = note.get("type") or "笔记"
    content = short_text(note.get("content"), 90).replace("\n", " ")
    return f"{book_title} · {note_type} · {content}"


def _format_daily_preview(row):
    minutes = round((row.get("seconds") or 0) / 60, 2)
    return f"{row.get('date')} · {minutes} 分钟"
