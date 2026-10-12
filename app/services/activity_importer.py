import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ActivitySource:
    id: str
    name: str
    url: str
    host: str


@dataclass
class ActivityCandidate:
    source_id: str
    source_name: str
    source_url: str
    title: str
    parsed_data: dict
    error_message: str | None = None


@dataclass
class SourceFetchResult:
    source_id: str
    source_name: str
    source_url: str
    status: str
    items_found: int = 0
    candidates: list[ActivityCandidate] = field(default_factory=list)
    error_message: str | None = None


ACTIVITY_SOURCES = (
    ActivitySource(
        id="slll",
        name="暨大終身學習與地方創生中心",
        url="https://ccweb.ncnu.edu.tw/SLLL/z958B653E5831540D4E4B6D3B52D5660E7D30list.asp",
        host="ccweb.ncnu.edu.tw",
    ),
    ActivitySource(
        id="ltrc",
        name="暨大語言教學中心",
        url="https://ltrc.ncnu.edu.tw/web/quiz/quiz_sign.jsp",
        host="ltrc.ncnu.edu.tw",
    ),
    ActivitySource(
        id="ctld",
        name="暨大教學發展中心",
        url="https://ctld.ncnu.edu.tw/",
        host="ctld.ncnu.edu.tw",
    ),
)
SOURCE_BY_ID = {source.id: source for source in ACTIVITY_SOURCES}
MAX_HTML_BYTES = 2_000_000
MAX_DETAIL_PAGES = 30
REQUEST_TIMEOUT_SECONDS = 12.0
USER_AGENT = "NCNUCampusActivityImporter/1.0 (public announcement import)"
ACTIVITY_KEYWORDS = re.compile(r"活動|講座|工作坊|研習|競賽|比賽|展演|演講|說明會|音樂會")


def is_allowed_source_url(url: str, source_id: str | None = None) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return False
    allowed_hosts = {SOURCE_BY_ID[source_id].host} if source_id in SOURCE_BY_ID else {
        source.host for source in ACTIVITY_SOURCES
    }
    return parsed.hostname in allowed_hosts


def _fetch_html(client: httpx.Client, url: str, source_id: str) -> bytes:
    if not is_allowed_source_url(url, source_id):
        raise ValueError("The URL is outside the configured official source host.")

    with client.stream("GET", url) as response:
        if response.status_code != 200:
            raise httpx.HTTPStatusError(
                f"Source returned HTTP {response.status_code}.",
                request=response.request,
                response=response,
            )
        if response.url.host != SOURCE_BY_ID[source_id].host:
            raise ValueError("The source response host does not match its allowlist.")
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > MAX_HTML_BYTES:
            raise ValueError("The source response exceeds the size limit.")
        content = bytearray()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > MAX_HTML_BYTES:
                raise ValueError("The source response exceeds the size limit.")
        return bytes(content)


def _error_summary(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code}"
    if isinstance(error, httpx.TimeoutException):
        return "連線逾時"
    if isinstance(error, ValueError):
        return str(error)[:300]
    return type(error).__name__


def _parse_datetime(text: str) -> str | None:
    value = " ".join(text.replace("\u00a0", " ").split())
    patterns = (
        re.compile(
            r"(?P<year>\d{3,4})\s*年\s*(?P<month>\d{1,2})\s*月\s*"
            r"(?P<day>\d{1,2})\s*日(?:[^0-9]{0,12}(?P<hour>\d{1,2}):(?P<minute>\d{2}))?"
        ),
        re.compile(
            r"(?P<year>\d{3,4})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})"
            r"(?:[ T]+(?P<hour>\d{1,2}):(?P<minute>\d{2}))?"
        ),
    )
    for pattern in patterns:
        match = pattern.search(value)
        if not match:
            continue
        parts = match.groupdict()
        year = int(parts["year"])
        if year < 1911:
            year += 1911
        hour = int(parts["hour"] or 0)
        minute = int(parts["minute"] or 0)
        try:
            return datetime(
                year,
                int(parts["month"]),
                int(parts["day"]),
                hour,
                minute,
            ).isoformat(timespec="minutes") + "+08:00"
        except ValueError:
            return None
    return None


def _category_for(text: str) -> str:
    if re.search(r"工作坊|研習", text):
        return "workshop"
    if re.search(r"社團", text):
        return "club"
    if re.search(r"音樂會|展演|影展|展覽", text):
        return "culture"
    if re.search(r"運動|競賽|比賽", text):
        return "sports"
    if re.search(r"職涯|就業", text):
        return "career"
    if re.search(r"講座|演講|論壇", text):
        return "talk"
    return "other"


def _candidate(source: ActivitySource, url: str, title: str, **data) -> ActivityCandidate:
    clean_title = " ".join(title.split())[:255]
    return ActivityCandidate(
        source_id=source.id,
        source_name=source.name,
        source_url=url,
        title=clean_title,
        parsed_data={
            "title": clean_title,
            "description": data.get("description", ""),
            "location": data.get("location", ""),
            "organizer": data.get("organizer", source.name),
            "category": data.get("category") or _category_for(clean_title),
            "starts_at": data.get("starts_at"),
            "registration_deadline": data.get("registration_deadline"),
            "capacity": data.get("capacity"),
            "duration": data.get("duration", ""),
            "published_at": data.get("published_at"),
        },
    )


def _parse_slll_listing(source: ActivitySource, html: bytes) -> list[ActivityCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    seen_urls = set()
    for row in soup.select("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 5:
            continue
        values = [" ".join(cell.stripped_strings) for cell in cells]
        if values[1].strip() in {"活動編號", ""} or not values[3].strip():
            continue
        detail_link = row.select_one("a[href*='view.asp'][href*='RowID=']")
        if detail_link is None:
            continue
        detail_url = urljoin(source.url, detail_link["href"])
        if detail_url in seen_urls or not is_allowed_source_url(detail_url, source.id):
            continue
        seen_urls.add(detail_url)
        capacity_match = re.match(r"\s*(\d+)", values[6] if len(values) > 6 else "")
        candidates.append(
            _candidate(
                source,
                detail_url,
                values[3],
                organizer=values[2],
                starts_at=_parse_datetime(values[4]),
                capacity=int(capacity_match.group(1)) if capacity_match else None,
            )
        )
    return candidates


def _parse_ltrc_listing(source: ActivitySource, html: bytes) -> list[ActivityCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    seen_urls = set()
    status_labels = {"未開放報名", "報名截止", "我要報名"}
    for link in soup.select("a[href*='quiz_sign_in.jsp'][href*='np_id=']"):
        title = " ".join(link.stripped_strings)
        if not title or title in status_labels:
            continue
        detail_url = urljoin(source.url, link["href"])
        if detail_url in seen_urls or not is_allowed_source_url(detail_url, source.id):
            continue
        seen_urls.add(detail_url)
        candidates.append(_candidate(source, detail_url, title))
    return candidates


def _parse_ctld_listing(source: ActivitySource, html: bytes) -> list[ActivityCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    seen_urls = set()
    for link in soup.select("a[href*='/p/406-']"):
        title = " ".join(link.stripped_strings)
        if not title or not ACTIVITY_KEYWORDS.search(title):
            continue
        detail_url = urljoin(source.url, link["href"])
        if detail_url in seen_urls or not is_allowed_source_url(detail_url, source.id):
            continue
        seen_urls.add(detail_url)
        candidates.append(_candidate(source, detail_url, title))
    return candidates


def parse_listing(source_id: str, html: bytes) -> list[ActivityCandidate]:
    source = SOURCE_BY_ID[source_id]
    parser = {
        "slll": _parse_slll_listing,
        "ltrc": _parse_ltrc_listing,
        "ctld": _parse_ctld_listing,
    }[source_id]
    return parser(source, html)


def _labeled_value(text: str, label: str, following_labels: str) -> str:
    label_pattern = "|".join(re.escape(part) for part in label.split("|"))
    match = re.search(
        rf"(?:{label_pattern})\s*[:：]?\s*(.+?)(?={following_labels}|$)",
        text,
    )
    return " ".join(match.group(1).split()) if match else ""


def _extract_detail_data(source_id: str, html: bytes, base: ActivityCandidate) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.select("script, style, nav, footer, header, noscript"):
        element.decompose()
    text = " ".join(" ".join(soup.stripped_strings).split())
    parsed = dict(base.parsed_data)
    errors = []

    title_node = soup.select_one("h1, h2")
    if title_node and len(title_node.get_text(" ", strip=True)) > 4:
        parsed["title"] = base.title

    start_text = _labeled_value(
        text,
        "活動開始時間|活動日期|活動時間",
        r"活動結束時間|報名開始時間|報名結束時間|活動地點|活動說明|🌐|網址",
    )
    if not start_text:
        start_text = _labeled_value(
            text,
            "活動日期",
            r"活動網址|活動地點|活動說明|講者|主講人|⚠",
        )
    if start_text:
        parsed["starts_at"] = _parse_datetime(start_text) or parsed.get("starts_at")

    deadline_text = _labeled_value(
        text,
        "報名結束時間",
        r"時數|主講人|活動地點|申請為|名額限制|供餐",
    )
    if deadline_text:
        parsed["registration_deadline"] = _parse_datetime(deadline_text)

    location_text = _labeled_value(
        text,
        "活動地點|地點",
        r"申請為|活動連絡人|活動連絡電話|名額限制|供餐|費用|對象|活動說明|📅|🌐",
    )
    if location_text:
        parsed["location"] = location_text[:255]

    organizer_text = _labeled_value(
        text,
        "主辦單位|發佈單位|發布單位",
        r"發佈者|發布者|活動名稱|活動開始時間|活動日期|$",
    )
    if organizer_text:
        parsed["organizer"] = organizer_text[:255]

    capacity_match = re.search(r"名額限制\s*(\d+)", text)
    if capacity_match:
        parsed["capacity"] = int(capacity_match.group(1))

    duration_match = re.search(r"時數\s*(\d+(?:\.\d+)?)", text)
    if duration_match:
        parsed["duration"] = f"{duration_match.group(1)} 小時"

    if source_id == "ctld":
        parsed["description"] = text[:10000]
        parsed["organizer"] = organizer_text or base.source_name
    elif source_id == "slll":
        description = _labeled_value(
            text,
            "活動說明",
            r"是否是公務員終身學習|允許教職員參加|允許學生參加|是否是",
        )
        if description:
            parsed["description"] = description[:10000]
    else:
        parsed["description"] = text[:10000]

    if not parsed.get("starts_at"):
        errors.append("未能從公告辨識活動日期與時間，請管理員補填。")
    if not parsed.get("location"):
        errors.append("公告未提供可辨識的活動地點，請管理員補填。")
    if not parsed.get("description"):
        errors.append("公告未提供可辨識的活動內容，請管理員補填。")
    return {**parsed, "parse_errors": errors}


def fetch_source(source_id: str, known_urls: set[str] | None = None) -> SourceFetchResult:
    source = SOURCE_BY_ID[source_id]
    known_urls = known_urls or set()
    result = SourceFetchResult(
        source_id=source.id,
        source_name=source.name,
        source_url=source.url,
        status="failed",
    )
    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        ) as client:
            listing = _fetch_html(client, source.url, source.id)
            candidates = parse_listing(source.id, listing)
            result.items_found = len(candidates)
            detail_pages_fetched = 0
            for candidate in candidates:
                if candidate.source_url in known_urls:
                    result.candidates.append(candidate)
                    continue
                if detail_pages_fetched >= MAX_DETAIL_PAGES:
                    candidate.error_message = "來源公告數超過單次詳情抓取上限。"
                    candidate.parsed_data["parse_errors"] = [candidate.error_message]
                    result.candidates.append(candidate)
                    continue
                detail_pages_fetched += 1
                try:
                    detail_html = _fetch_html(client, candidate.source_url, source.id)
                    candidate.parsed_data = _extract_detail_data(
                        source.id,
                        detail_html,
                        candidate,
                    )
                except (httpx.HTTPError, ValueError) as error:
                    candidate.error_message = f"詳情頁讀取失敗：{_error_summary(error)}"
                    candidate.parsed_data["parse_errors"] = [candidate.error_message]
                result.candidates.append(candidate)
        result.status = "completed"
    except (httpx.HTTPError, ValueError) as error:
        result.error_message = f"來源讀取失敗：{_error_summary(error)}"
    return result