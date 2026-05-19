from datetime import datetime
import socket
import time

import requests


GATEWAY_HOST = "i.weread.qq.com"
GATEWAY_URL = "https://i.weread.qq.com/api/agent/gateway"
_ORIGINAL_GETADDRINFO = socket.getaddrinfo
_IPV4_FORCED = False


class WeReadGatewayError(RuntimeError):
    pass


def force_gateway_ipv4():
    """GitHub-hosted runners can receive IPv6 first for WeRead without an IPv6 route."""
    global _IPV4_FORCED
    if _IPV4_FORCED:
        return

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if host == GATEWAY_HOST and family in (0, socket.AF_UNSPEC):
            return _ORIGINAL_GETADDRINFO(host, port, socket.AF_INET, type, proto, flags)
        return _ORIGINAL_GETADDRINFO(host, port, family, type, proto, flags)

    socket.getaddrinfo = getaddrinfo
    _IPV4_FORCED = True


class WeReadClient:
    def __init__(self, api_key, skill_version="1.0.3", timeout=30):
        if not api_key:
            raise ValueError("WEREAD_API_KEY is required.")
        force_gateway_ipv4()
        self.skill_version = skill_version
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
                "User-Agent": "weread-link-notion/1.0",
            }
        )

    def call(self, api_name, **params):
        payload = {"api_name": api_name, "skill_version": self.skill_version}
        payload.update(params)
        last_error = None
        for attempt in range(3):
            try:
                response = self.session.post(GATEWAY_URL, json=payload, timeout=self.timeout)
                if not response.ok:
                    message = response.text[:500].replace("\n", " ")
                    raise WeReadGatewayError(f"{api_name} HTTP {response.status_code}: {message}")
                data = response.json()
                self._raise_gateway_error(api_name, data)
                return data
            except Exception as exc:  # noqa: BLE001 - retry wrapper keeps caller simpler.
                last_error = exc
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        raise WeReadGatewayError(f"{api_name} failed after retries: {last_error}")

    @staticmethod
    def _raise_gateway_error(api_name, data):
        if isinstance(data, dict) and data.get("upgrade_info"):
            message = data["upgrade_info"].get("message", "WeRead skill version needs upgrade.")
            raise WeReadGatewayError(f"{api_name}: {message}")
        errcode = data.get("errcode") if isinstance(data, dict) else None
        if errcode not in (None, 0):
            message = data.get("errmsg") or data.get("message") or str(errcode)
            raise WeReadGatewayError(f"{api_name}: {message}")

    def get_shelf(self):
        return self.call("/shelf/sync")

    def iter_notebooks(self, page_size=100):
        seen = set()
        last_sort = None
        while True:
            params = {"count": page_size}
            if last_sort is not None:
                params["lastSort"] = last_sort
            data = self.call("/user/notebooks", **params)
            books = data.get("books") or []
            for item in books:
                book_id = item.get("bookId") or (item.get("book") or {}).get("bookId")
                marker = (book_id, item.get("sort"))
                if marker in seen:
                    continue
                seen.add(marker)
                yield item
            if not data.get("hasMore") or not books:
                break
            last_sort = books[-1].get("sort")
            if last_sort is None:
                break

    def get_bookmarks(self, book_id):
        return self.call("/book/bookmarklist", bookId=book_id)

    def iter_reviews(self, book_id, page_size=100):
        synckey = 0
        seen = set()
        while True:
            data = self.call("/review/list/mine", bookid=book_id, synckey=synckey, count=page_size)
            reviews = data.get("reviews") or []
            for item in reviews:
                review = item.get("review") or item
                review_id = review.get("reviewId") or item.get("reviewId")
                if review_id and review_id in seen:
                    continue
                if review_id:
                    seen.add(review_id)
                yield review
            if not data.get("hasMore") or not reviews:
                break
            next_key = data.get("synckey")
            if not next_key or next_key == synckey:
                break
            synckey = next_key

    def get_month_read_times(self, year, month):
        base_time = int(datetime(year, month, 1).timestamp())
        data = self.call("/readdata/detail", mode="monthly", baseTime=base_time)
        return data.get("readTimes") or {}

    def get_year_read_times(self, year):
        now = datetime.now()
        last_month = now.month if year == now.year else 12
        result = {}
        for month in range(1, last_month + 1):
            result.update(self.get_month_read_times(year, month))
        return {int(key): int(value or 0) for key, value in result.items()}

    def get_read_summary(self, mode="annually"):
        return self.call("/readdata/detail", mode=mode, baseTime=0)

    def get_book_info(self, book_id):
        return self.call("/book/info", bookId=book_id)
