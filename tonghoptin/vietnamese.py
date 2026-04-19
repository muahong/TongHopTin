"""Vietnamese date parsing and topic tagging."""

from __future__ import annotations

import re
from datetime import datetime, date, timedelta, timezone
from typing import Optional


VN_TZ = timezone(timedelta(hours=7))


def now_vn() -> datetime:
    """Current wall-clock time in Vietnam (GMT+7), as a naive datetime."""
    return datetime.now(VN_TZ).replace(tzinfo=None)


def to_vn_naive(dt: datetime) -> datetime:
    """Normalize any datetime to a naive GMT+7 wall-clock."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(VN_TZ).replace(tzinfo=None)
    return dt


# Vietnamese day-of-week names (for stripping from date strings)
WEEKDAY_PATTERN = r"(?:Thứ\s+(?:Hai|Ba|Tư|Năm|Sáu|Bảy)|Chủ\s+[Nn]hật),?\s*"

# Ordered from most specific to least specific
_DATE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "Thứ Bảy, 04/04/2026, 10:30 (GMT+7)" -- VnExpress detail
    (re.compile(
        rf"(?:{WEEKDAY_PATTERN})?(\d{{1,2}})[/\-](\d{{1,2}})[/\-](\d{{4}}),?\s*(\d{{1,2}}):(\d{{2}})"
    ), "dmy_hm"),

    # "04/04/2026" -- date only
    (re.compile(
        rf"(?:{WEEKDAY_PATTERN})?(\d{{1,2}})[/\-](\d{{1,2}})[/\-](\d{{4}})"
    ), "dmy"),

    # "3 tháng 4, 2026" or "3 tháng 4 năm 2026"
    (re.compile(
        r"(\d{1,2})\s+tháng\s+(\d{1,2}),?\s*(?:năm\s+)?(\d{4})"
    ), "vn_written"),

    # ISO: "2026-04-04T10:30:00" or "2026-04-04 10:30"
    (re.compile(
        r"(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})"
    ), "iso_hm"),

    # ISO date only: "2026-04-04"
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "iso"),
]

# Relative time patterns (Vietnamese)
_RELATIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(\d+)\s*phút\s*trước", re.IGNORECASE), "minutes"),
    (re.compile(r"(\d+)\s*giờ\s*trước", re.IGNORECASE), "hours"),
    (re.compile(r"(\d+)\s*ngày\s*trước", re.IGNORECASE), "days"),
    (re.compile(r"Hôm nay", re.IGNORECASE), "today"),
    (re.compile(r"Hôm qua", re.IGNORECASE), "yesterday"),
]


def parse_vietnamese_date(text: str, reference: Optional[datetime] = None) -> Optional[datetime]:
    """Parse a Vietnamese date string into a datetime.

    Vietnamese dates use DD/MM/YYYY (day first), not MM/DD/YYYY.
    """
    if not text:
        return None

    ref = reference or datetime.now()
    text = text.strip()

    # Try ISO 8601 in <time datetime="..."> first
    iso_match = re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', text)
    if iso_match:
        try:
            return datetime.fromisoformat(iso_match.group().replace("+07:00", "+07:00"))
        except ValueError:
            pass

    # Try relative time patterns
    for pattern, unit in _RELATIVE_PATTERNS:
        m = pattern.search(text)
        if m:
            if unit == "today":
                return ref.replace(hour=0, minute=0, second=0, microsecond=0)
            if unit == "yesterday":
                return (ref - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            amount = int(m.group(1))
            if unit == "minutes":
                return ref - timedelta(minutes=amount)
            if unit == "hours":
                return ref - timedelta(hours=amount)
            if unit == "days":
                return ref - timedelta(days=amount)

    # Try absolute date patterns
    for pattern, fmt in _DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        groups = m.groups()
        try:
            if fmt == "dmy_hm":
                day, month, year, hour, minute = int(groups[0]), int(groups[1]), int(groups[2]), int(groups[3]), int(groups[4])
                return datetime(year, month, day, hour, minute)
            elif fmt == "dmy":
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                return datetime(year, month, day)
            elif fmt == "vn_written":
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                return datetime(year, month, day)
            elif fmt == "iso_hm":
                year, month, day, hour, minute = int(groups[0]), int(groups[1]), int(groups[2]), int(groups[3]), int(groups[4])
                return datetime(year, month, day, hour, minute)
            elif fmt == "iso":
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                return datetime(year, month, day)
        except (ValueError, IndexError):
            continue

    return None


def is_target_date(dt: Optional[datetime], target: date) -> Optional[bool]:
    """Check if datetime matches target date. Returns None if dt is None (unknown)."""
    if dt is None:
        return None
    return dt.date() == target


# --- Vietnamese Topic Tagging ---

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "Chính trị": [
        "quốc hội", "chính phủ", "đảng", "bộ trưởng", "thủ tướng",
        "chủ tịch nước", "tổng bí thư", "ban chấp hành", "trung ương",
        "đại biểu", "nghị quyết", "chính sách",
    ],
    "Kinh tế": [
        "GDP", "lạm phát", "chứng khoán", "ngân hàng", "xuất khẩu",
        "nhập khẩu", "doanh nghiệp", "đầu tư", "bất động sản",
        "lãi suất", "tỷ giá", "thuế", "kinh tế",
    ],
    "Xã hội": [
        "dân sinh", "giao thông", "tai nạn", "môi trường", "dân cư",
        "an sinh", "xã hội", "đô thị", "nông thôn",
    ],
    "Công nghệ": [
        "AI", "trí tuệ nhân tạo", "smartphone", "ứng dụng", "bảo mật",
        "internet", "phần mềm", "chip", "robot", "công nghệ",
        "machine learning", "blockchain", "5G",
    ],
    "Giáo dục": [
        "học sinh", "sinh viên", "đại học", "thi", "điểm chuẩn",
        "giáo viên", "trường", "giáo dục", "tuyển sinh", "học phí",
    ],
    "Y tế": [
        "bệnh viện", "bác sĩ", "dịch bệnh", "vaccine", "sức khỏe",
        "thuốc", "y tế", "phẫu thuật", "ung thư", "COVID",
    ],
    "Thể thao": [
        "bóng đá", "SEA Games", "Olympic", "V-League", "đội tuyển",
        "World Cup", "cầu thủ", "HLV", "giải đấu", "thể thao",
        "tennis", "bơi lội",
    ],
    "Giải trí": [
        "phim", "ca sĩ", "nghệ sĩ", "gameshow", "âm nhạc",
        "diễn viên", "MV", "giải trí", "showbiz", "điện ảnh",
    ],
    "Quốc tế": [
        "Mỹ", "Trung Quốc", "Nga", "Ukraine", "ASEAN",
        "Liên Hợp Quốc", "NATO", "EU", "Nhật Bản", "Hàn Quốc",
        "quốc tế", "ngoại giao",
    ],
    "Pháp luật": [
        "tội phạm", "bắt giữ", "xét xử", "tòa án", "công an",
        "khởi tố", "truy tố", "pháp luật", "vi phạm", "hình sự",
    ],
}


def tag_article_topics(title: str, content_text: str) -> list[str]:
    """Assign topic tags based on Vietnamese keyword matching.

    Searches title + first 500 chars of content.
    An article can have multiple topics.
    """
    searchable = (title + " " + content_text[:500]).lower()
    matched = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw.lower() in searchable for kw in keywords):
            matched.append(topic)
    return matched if matched else ["Khác"]


# --- Interest-Based Scoring ---
# Weights derived from user's actual browsing history keyword analysis

INTEREST_KEYWORDS: dict[float, list[str]] = {
    3.0: [  # High interest - most read topics
        "trump", "dầu", "xăng", "điện", "kinh tế", "AI",
        "USD", "ngân hàng", "lãi suất", "trung quốc",
        "mỹ",  # USA context
    ],
    2.0: [  # Medium interest
        "vàng", "thuế", "xuất khẩu", "nhập khẩu", "VinFast",
        "EV", "chứng khoán", "bất động sản", "GDP",
        "tỷ giá", "doanh nghiệp", "đầu tư",
    ],
    1.0: [  # Lower but still relevant
        "công nghệ", "startup", "robot", "blockchain",
        "giao thông", "ô tô", "phần mềm", "5G",
        "xe điện", "năng lượng",
    ],
}


def score_article(title: str, content_text: str) -> float:
    """Score an article based on user interest keywords.

    Higher score = more relevant to user's reading habits.
    Searches title (weighted 2x) + first 500 chars of content.
    """
    title_lower = title.lower()
    content_lower = content_text[:500].lower()
    score = 0.0

    for weight, keywords in INTEREST_KEYWORDS.items():
        for kw in keywords:
            kw_lower = kw.lower()
            # Title matches weighted 2x
            if kw_lower in title_lower:
                score += weight * 2.0
            elif kw_lower in content_lower:
                score += weight

    return round(score, 1)


# --- Freshness Detection ---

def compute_freshness_adjustment(
    url: str,
    published_date: datetime,
    content_text: str,
    is_previously_seen: bool = False,
) -> float:
    """Compute freshness bonus/penalty for an article.

    Detects recycled articles (old content with fresh dates) and penalizes them.
    Boosts genuinely recent articles.

    Returns a float adjustment to add to the interest score.
    """
    adjustment = 0.0

    # Penalty: URL contains a date older than published_date
    url_date = _extract_date_from_url(url)
    if url_date and published_date:
        days_diff = (published_date.date() - url_date).days
        if days_diff > 2:
            # URL date is much older than claimed publish date → recycled
            adjustment -= 10.0

    # Penalty: previously seen in dedup DB
    if is_previously_seen:
        adjustment -= 5.0

    # Penalty: very short content (stub/teaser)
    if content_text and len(content_text.strip()) < 200:
        adjustment -= 3.0

    # Bonus: genuinely fresh articles
    if published_date:
        now = datetime.now()
        hours_ago = (now - published_date).total_seconds() / 3600
        if 0 <= hours_ago <= 3:
            adjustment += 4.0
        elif 0 <= hours_ago <= 6:
            adjustment += 2.0

    return round(adjustment, 1)


def _extract_date_from_url(url: str) -> Optional[date]:
    """Try to extract a date from URL path patterns like /2026/04/04/ or /20260404/."""
    # Pattern: /YYYY/MM/DD/
    m = re.search(r'/(\d{4})/(\d{1,2})/(\d{1,2})/', url)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # Pattern: /YYYYMMDD or -YYYYMMDD
    m = re.search(r'[/-](\d{4})(\d{2})(\d{2})', url)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None
