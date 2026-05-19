from datetime import datetime, timezone
import time

from notion_client import Client
from notion_client.errors import APIResponseError, RequestTimeoutError

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

    def setup(self, heatmap_url=""):
        self._load_child_databases()
        self._ensure_dashboard(heatmap_url)
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
        for block in self._walk_blocks(self.page_id):
            if block.get("type") == "child_database":
                title_text = block["child_database"]["title"]
                required = REQUIRED_PROPERTIES.get(title_text)
                if not required:
                    continue
                queryable_id = self._queryable_database_id(block["id"])
                if self._database_has_properties(queryable_id, required):
                    self.databases[title_text] = queryable_id

    def _walk_blocks(self, block_id):
        for block in self._children(block_id):
            yield block
            if block.get("has_children"):
                yield from self._walk_blocks(block["id"])

    def _ensure_dashboard(self, heatmap_url):
        has_marker = False
        has_clean_intro = False
        has_clean_heatmap_heading = False
        for block in self._children(self.page_id):
            text = _plain_text_from_block(block)
            has_marker = has_marker or DASHBOARD_MARKER in text
            has_clean_intro = has_clean_intro or "微信读书同步面板" in text
            has_clean_heatmap_heading = has_clean_heatmap_heading or "阅读热力图" in text

        children = []
        if not has_marker:
            children.append(_heading_1("WeRead Link Notion"))
        if not has_clean_intro:
            children.append(_callout("一个轻量的微信读书同步面板：热力图、书库、笔记、每日阅读和同步快照会在这里自动维护。"))
        if not has_clean_heatmap_heading:
            children.append(_heading_2("阅读热力图"))

        if children:
            self._notion(self.client.blocks.children.append, block_id=self.page_id, children=children)
        if heatmap_url:
            self.update_heatmap(heatmap_url)

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
        return self._upsert(self.databases[NOTES_DB], "Note ID", note["id"], props)

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

    def _upsert(self, database_id, key_property, key, properties, title_key=False):
        if title_key:
            filter_value = {"property": key_property, "title": {"equals": key}}
        else:
            filter_value = {"property": key_property, "rich_text": {"equals": key}}
        response = self._query_database(database_id, filter_value)
        results = response.get("results") or []
        if results:
            return self._notion(self.client.pages.update, page_id=results[0]["id"], properties=properties)
        return self._notion(self.client.pages.create, parent=self._database_parent(database_id), properties=properties)

    def _query_database(self, database_id, filter_value):
        if self._uses_data_sources():
            return self._notion(self.client.data_sources.query, data_source_id=database_id, filter=filter_value, page_size=1)
        return self._notion(self.client.databases.query, database_id=database_id, filter=filter_value, page_size=1)

    def _database_parent(self, database_id):
        if self._uses_data_sources():
            return {"type": "data_source_id", "data_source_id": database_id}
        return {"database_id": database_id}

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

    def _notion(self, func, **kwargs):
        last_error = None
        for attempt in range(4):
            try:
                return func(**kwargs)
            except RequestTimeoutError as exc:
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


def _callout(text):
    return {
        "object": "block",
        "type": "callout",
        "callout": {"rich_text": _rt(text), "icon": {"type": "emoji", "emoji": "📚"}},
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
