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
PROFILE_MARKER = "WeRead Link Notion reading profile"
MONTHLY_CHART_MARKER = "WeRead Link Notion monthly reading chart"
DASHBOARD_SNAPSHOT_PREFIX = "最近同步 ·"
DASHBOARD_TITLE_PREFIX = "微信读书阅读面板 ·"


BOOKS_DB = "书库"
NOTES_DB = "笔记"
DAILY_DB = "每日阅读"
RECOMMENDATIONS_DB = "推荐好书"
RUNS_DB = "同步快照"

REQUIRED_PROPERTIES = {
    BOOKS_DB: ("书名", "Book ID"),
    NOTES_DB: ("内容", "Note ID"),
    DAILY_DB: ("日期",),
    RECOMMENDATIONS_DB: ("书名", "Book ID"),
    RUNS_DB: ("同步时间",),
}


class NotionStore:
    def __init__(self, token, page):
        self.client = Client(auth=token, timeout_ms=90000)
        self.page_id = extract_notion_page_id(page)
        self.databases = {}
        self.page_cache = {}

    def setup(self, heatmap_url=""):
        self._set_page_chrome()
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

    def reset_page(self):
        self._set_page_chrome()
        for block in self._children(self.page_id):
            self._archive_block(block["id"])
        self.databases = {}
        self.page_cache = {}
        return self._notion(
            self.client.blocks.children.append,
            block_id=self.page_id,
            children=[_paragraph(f"{DASHBOARD_SNAPSHOT_PREFIX}reset anchor")],
        )

    def _set_page_chrome(self):
        try:
            return self._notion(
                self.client.pages.update,
                page_id=self.page_id,
                icon={"type": "emoji", "emoji": "📚"},
                properties={"title": title("书架")},
            )
        except Exception:  # noqa: BLE001 - page title/icon updates should not block syncing.
            return None

    def rebuild_dashboard(
        self,
        counts,
        books,
        notes,
        daily_rows,
        recommendations=None,
        heatmap_url="",
        profile_url="",
        monthly_chart_url="",
        dashboard_quote="看书真好",
        streak_days=0,
    ):
        now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
        anchor_id = self._find_managed_dashboard_anchor_id()
        dashboard_blocks = _dashboard_blocks(
            now,
            counts,
            books,
            notes,
            daily_rows,
            recommendations or [],
            heatmap_url,
            profile_url,
            monthly_chart_url,
            dashboard_quote,
            streak_days,
        )
        kwargs = {"block_id": self.page_id, "children": dashboard_blocks}
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
            RECOMMENDATIONS_DB: _recommendations_schema(),
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

    def upsert_recommendation(self, recommendation):
        props = {
            "书名": title(recommendation["title"]),
            "Book ID": rich_text(recommendation["id"]),
            "作者": rich_text(recommendation.get("author")),
            "分类": rich_text(recommendation.get("category")),
            "推荐理由": rich_text(recommendation.get("reason")),
            "评分": number(recommendation.get("rating")),
            "评分人数": number(recommendation.get("rating_count")),
            "评分标签": rich_text(recommendation.get("rating_label")),
            "在读人数": number(recommendation.get("reading_count")),
            "封面": url(recommendation.get("cover")),
            "微信读书链接": url(recommendation.get("weread_url")),
            "排序": number(recommendation.get("sort")),
        }
        return self._upsert(self.databases[RECOMMENDATIONS_DB], "Book ID", recommendation["id"], props)

    def create_sync_run(self, status, counts, heatmap_url="", profile_url="", monthly_chart_url="", message=""):
        now = datetime.now(timezone.utc).astimezone().isoformat()
        props = {
            "同步时间": title(now),
            "Status": select(status),
            "Books": number(counts.get("books")),
            "Notes": number(counts.get("notes")),
            "Read Days": number(counts.get("read_days")),
            "Read Minutes": number(counts.get("read_minutes")),
            "Recommendations": number(counts.get("recommendations")),
            "Streak Days": number(counts.get("streak_days")),
            "Heatmap": url(heatmap_url),
            "Reading Profile": url(profile_url),
            "Monthly Chart": url(monthly_chart_url),
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
                    image=_image_content(heatmap_url, HEATMAP_MARKER),
                )
            if block_type == "embed":
                parent = block.get("parent") or {}
                parent_id = parent.get("page_id") or parent.get("block_id")
                if parent_id:
                    response = self._notion(
                        self.client.blocks.children.append,
                        block_id=parent_id,
                        after=block["id"],
                        children=[_image_payload(heatmap_url, HEATMAP_MARKER)],
                    )
                    self._notion(self.client.blocks.delete, block_id=block["id"])
                    return response
        return self._notion(
            self.client.blocks.children.append,
            block_id=self.page_id,
            children=[_image_payload(heatmap_url, HEATMAP_MARKER)],
        )

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
        ids = self._managed_dashboard_block_ids()
        return ids[-1] if ids else None

    def _cleanup_managed_dashboard(self, exclude_ids=None):
        exclude_ids = exclude_ids or set()
        managed_ids = set(self._managed_dashboard_block_ids())
        for block in self._children(self.page_id):
            if block["id"] in exclude_ids:
                continue
            if block["id"] in managed_ids or self._is_managed_dashboard_block(block):
                self._archive_block(block["id"])

    def _managed_dashboard_block_ids(self):
        blocks = self._children(self.page_id)
        ids = []
        collecting = False
        for block in blocks:
            if block.get("type") == "child_database":
                if collecting:
                    break
                continue
            if self._is_managed_dashboard_block(block):
                collecting = True
            if collecting:
                ids.append(block["id"])
        if ids:
            return ids
        return [block["id"] for block in blocks if self._is_managed_dashboard_block(block)]

    def _is_managed_dashboard_block(self, block):
        text = _plain_text_from_block(block)
        if text.startswith(DASHBOARD_TITLE_PREFIX):
            return True
        if text.startswith(DASHBOARD_SNAPSHOT_PREFIX):
            return True
        if DASHBOARD_MARKER in text:
            return True
        if "微信读书同步面板" in text or text in ("阅读总览", "READING DASHBOARD", "阅读热力图"):
            return True
        if block.get("type") == "image":
            return self._is_managed_asset_block(block)
        return False

    def _is_managed_asset_block(self, block):
        caption = _plain_text(block.get("image", {}).get("caption") or [])
        external = block.get("image", {}).get("external") or {}
        asset_url = external.get("url") or ""
        return (
            HEATMAP_MARKER in caption
            or PROFILE_MARKER in caption
            or MONTHLY_CHART_MARKER in caption
            or "/assets/heatmap" in asset_url
            or "/assets/reading-profile" in asset_url
            or "/assets/monthly-reading" in asset_url
        )

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


def _recommendations_schema():
    return {
        "书名": {"title": {}},
        "Book ID": {"rich_text": {}},
        "作者": {"rich_text": {}},
        "分类": {"rich_text": {}},
        "推荐理由": {"rich_text": {}},
        "评分": {"number": {"format": "number"}},
        "评分人数": {"number": {"format": "number"}},
        "评分标签": {"rich_text": {}},
        "在读人数": {"number": {"format": "number"}},
        "封面": {"url": {}},
        "微信读书链接": {"url": {}},
        "排序": {"number": {"format": "number"}},
    }


def _runs_schema():
    return {
        "同步时间": {"title": {}},
        "Status": {"select": {"options": _options(["success", "failure"])}},
        "Books": {"number": {"format": "number"}},
        "Notes": {"number": {"format": "number"}},
        "Read Days": {"number": {"format": "number"}},
        "Read Minutes": {"number": {"format": "number"}},
        "Recommendations": {"number": {"format": "number"}},
        "Streak Days": {"number": {"format": "number"}},
        "Heatmap": {"url": {}},
        "Reading Profile": {"url": {}},
        "Monthly Chart": {"url": {}},
        "Message": {"rich_text": {}},
    }


def _dashboard_blocks(
    now,
    counts,
    books,
    notes,
    daily_rows,
    recommendations,
    heatmap_url,
    profile_url,
    monthly_chart_url,
    dashboard_quote,
    streak_days,
):
    left_column = _bookshelf_left_column(
        now,
        counts,
        dashboard_quote,
        streak_days,
    )
    right_column = _bookshelf_right_column(
        counts,
        books,
        notes,
        daily_rows,
        recommendations,
        heatmap_url,
        profile_url,
        monthly_chart_url,
        streak_days,
    )
    return [
        _paragraph(f"{DASHBOARD_MARKER} · 自动同步于 {now}"),
        _column_list([left_column, right_column]),
        _divider(),
        _heading_2("数据库"),
        _paragraph("下面 5 个数据库保存完整数据。上面的书架面板只保留高频摘要，避免首页变成流水账。"),
    ]


def _options(names):
    colors = ["blue", "green", "yellow", "orange", "purple", "pink", "gray"]
    return [{"name": name, "color": colors[index % len(colors)]} for index, name in enumerate(names)]


def _bookshelf_left_column(now, counts, dashboard_quote, streak_days):
    return [
        _callout(dashboard_quote, icon="📖", color="green_background"),
        _callout(
            "菜单",
            icon="☰",
            color="gray_background",
            children=[_table_of_contents()],
        ),
        _heading_2("统计"),
        _metric_card("书库", f"{counts.get('books', 0)} 本", "完整书架在下方数据库", "📚"),
        _metric_card("笔记", f"{counts.get('notes', 0)} 条", "想法和划线分开预览", "✍️"),
        _metric_card("阅读日", f"{counts.get('read_days', 0)} 天", f"连续阅读 {streak_days} 天", "📅"),
        _metric_card("今年阅读", f"{counts.get('read_minutes', 0)} 分钟", "来自微信读书统计", "⏱️"),
        _heading_2("入口"),
        _database_card("推荐好书", "weread.skill 个性化推荐", "✨"),
        _database_card("书库", "书架、状态、最近阅读、封面和链接", "📚"),
        _database_card("笔记", "想法与划线，按书名和类型筛选", "📝"),
        _database_card("每日阅读", "热力图和当月阅读图的数据来源", "📈"),
        _database_card("同步快照", "每次运行状态与资源链接", "✅"),
        _paragraph(f"最后同步：{now}"),
    ]


def _bookshelf_right_column(
    counts,
    books,
    notes,
    daily_rows,
    recommendations,
    heatmap_url,
    profile_url,
    monthly_chart_url,
    streak_days,
):
    children = []
    if heatmap_url:
        children.append(_image_payload(heatmap_url, HEATMAP_MARKER))
    children.extend(
        [
            _heading_2("阅读时长"),
            _paragraph(f"连续阅读 {streak_days} 天 · 今年 {counts.get('read_minutes', 0)} 分钟"),
        ]
    )
    if monthly_chart_url:
        children.append(_image_payload(monthly_chart_url, MONTHLY_CHART_MARKER))
    else:
        children.extend(_bulleted_list_item(_format_daily_preview(row)) for row in _recent_daily_rows(daily_rows, limit=5))

    children.extend([_heading_2("最近在读")])
    recent_books = [_bulleted_list_item(_format_book_preview(book)) for book in _recent_books(books, limit=6)]
    children.extend(recent_books or [_bulleted_list_item("暂时没有最近阅读书籍。")])

    children.extend([_heading_2("推荐好书")])
    recommendation_blocks = [_bulleted_list_item(_format_recommendation_preview(item)) for item in recommendations[:6]]
    children.extend(recommendation_blocks or [_bulleted_list_item("暂时没有拿到推荐书籍，下次同步会继续尝试。")])

    children.extend([_heading_2("笔记")])
    thought_blocks = [_bulleted_list_item(_format_note_preview(note)) for note in _recent_thoughts(notes, limit=5)]
    children.extend(thought_blocks or [_bulleted_list_item("暂时没有想法笔记。")])

    children.extend([_heading_2("划线")])
    highlight_blocks = [_bulleted_list_item(_format_note_preview(note)) for note in _recent_highlights(notes, limit=5)]
    children.extend(highlight_blocks or [_bulleted_list_item("暂时没有划线。")])
    if profile_url:
        children.extend([_heading_2("阅读画像"), _image_payload(profile_url, PROFILE_MARKER)])
    return children


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


def _table_of_contents():
    return {
        "object": "block",
        "type": "table_of_contents",
        "table_of_contents": {"color": "default"},
    }


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


def _column_list(columns):
    if len(columns) == 1:
        columns = [columns[0], [_paragraph("")]]
    return {
        "object": "block",
        "type": "column_list",
        "column_list": {"children": [_column(children) for children in columns]},
    }


def _column(children):
    return {
        "object": "block",
        "type": "column",
        "column": {"children": children},
    }


def _metric_card(label, value, hint, icon):
    return _callout(f"{label}\n{value}\n{hint}", icon=icon, color="gray_background")


def _database_card(title_text, body, icon):
    return _callout(f"{title_text}\n{body}", icon=icon, color="default")


def _recent_reading_column(books):
    children = [_heading_3("最近阅读")]
    children.extend(_bulleted_list_item(_format_book_preview(book)) for book in _recent_books(books, limit=5))
    if len(children) == 1:
        children.append(_bulleted_list_item("暂时没有最近阅读书籍。"))
    return children


def _monthly_chart_column(daily_rows, monthly_chart_url):
    children = [_heading_3("当月阅读时长分布")]
    if monthly_chart_url:
        children.append(_image_payload(monthly_chart_url, MONTHLY_CHART_MARKER))
        return children
    children.extend(_bulleted_list_item(_format_daily_preview(row)) for row in _recent_daily_rows(daily_rows, limit=5))
    if len(children) == 1:
        children.append(_bulleted_list_item("暂时没有每日阅读数据。"))
    return children


def _recent_notes_column(notes):
    children = [_heading_3("最近笔记")]
    children.extend(_bulleted_list_item(_format_note_preview(note)) for note in _recent_thoughts(notes, limit=5))
    if len(children) == 1:
        children.append(_bulleted_list_item("暂时没有想法笔记。"))
    return children


def _recent_highlights_column(notes):
    children = [_heading_3("最近划线")]
    children.extend(_bulleted_list_item(_format_note_preview(note)) for note in _recent_highlights(notes, limit=5))
    if len(children) == 1:
        children.append(_bulleted_list_item("暂时没有划线。"))
    return children


def _image_payload(image_url, caption):
    return {
        "object": "block",
        "type": "image",
        "image": _image_content(image_url, caption),
    }


def _image_content(image_url, caption):
    return {
        "external": {"url": image_url},
        "caption": _rt(caption),
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


def _recent_thoughts(notes, limit=5):
    return [note for note in _recent_notes(notes, limit=100) if note.get("type") == "想法"][:limit]


def _recent_highlights(notes, limit=5):
    return [note for note in _recent_notes(notes, limit=100) if note.get("type") == "划线"][:limit]


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


def _format_recommendation_preview(recommendation):
    parts = [f"《{recommendation.get('title') or '未命名'}》"]
    if recommendation.get("author"):
        parts.append(str(recommendation["author"]))
    if recommendation.get("rating"):
        parts.append(f"{recommendation['rating']} 分")
    if recommendation.get("reason"):
        parts.append(str(recommendation["reason"]))
    elif recommendation.get("category"):
        parts.append(str(recommendation["category"]))
    return " · ".join(parts)
