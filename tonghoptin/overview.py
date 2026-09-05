"""Deterministic, source-attributed daily overview; no invented summaries."""
import re
import unicodedata
from html import unescape
from urllib.parse import urlsplit, unquote


def plain_text(text):
    for _ in range(3):
        decoded = unescape(text)
        if decoded == text:
            break
        text = decoded
    return unicodedata.normalize("NFC", text)


def fold(text):
    return "".join(c for c in unicodedata.normalize("NFD", plain_text(text).lower().replace("đ", "d").replace("-", " ")) if not unicodedata.combining(c))


CATEGORIES = [
    ("politics", "Chính trị", "Chính sách, quản trị và đối ngoại", "chinh tri|quoc hoi|chinh phu|thu tuong|bo chinh tri|ngoai giao|tong bi thu|chu tich nuoc"),
    ("economy", "Kinh tế", "Thị trường, doanh nghiệp và tài chính", "kinh te|kinh doanh|tai chinh|doanh nghiep|chung khoan|bat dong san|ngan hang|gia vang|thuong mai|dau tu|co phieu|trai phieu|ty gia|xuat khau|nhap khau|doanh thu|loi nhuan|thue|bat dong san|thi truong"),
    ("society", "Xã hội", "Đời sống, pháp luật và cộng đồng", "xa hoi|doi song|thoi su|phap luat|giao thong|dan sinh|lao dong|cong an|bat giu|khoi to|toa an|tai nan|lua dao|cuu ho|chay nha|nguoi dan"),
    ("culture", "Văn hóa", "Nghệ thuật, giải trí và di sản", "van hoa|giai tri|dien anh|am nhac|nghe si|di san|ca si|hoa hau|nhac si|dien vien|phim"),
    ("sports", "Thể thao", "Thi đấu, đội tuyển và vận động viên", "the thao|bong da|bong ro|tennis|cau long|world cup|olympic|v league|premier league|doi tuyen|hlv|clb|vo dich"),
    ("world", "Thế giới", "Các diễn biến quốc tế", "the gioi|quoc te|ukraine|nga|israel|iran|trung quoc|my|trieu tien"),
    ("technology", "Công nghệ", "Khoa học, công nghệ và đổi mới", "cong nghe|khoa hoc|so hoa|tri tue nhan tao|ai|chuyen doi so"),
    ("health", "Sức khỏe", "Y tế và chăm sóc sức khỏe", "suc khoe|y te|benh vien|dich benh|bac si"),
    ("education", "Giáo dục", "Trường học, học tập và tuyển sinh", "giao duc|tuyen sinh|hoc sinh|sinh vien|dai hoc|khai giang|nam hoc|truong hoc|giao vien|hoc phi"),
    ("environment", "Môi trường", "Khí hậu, thiên nhiên và du lịch", "moi truong|khi hau|thoi tiet|du lich|bao lu|thien tai|mua lon|ngap lut|sat lo|bao so"),
    ("other", "Tin khác", "Những tin chưa phân loại", ""),
]


def category_for(article):
    # Publisher category is stronger evidence than incidental body keywords.
    if re.search(r"\b(?:quoc hoi|thu tuong|bo chinh tri|tong bi thu|chu tich nuoc)\b", fold(article.title)):
        return "politics"
    for text in [article.source_category, article.title, unquote(urlsplit(article.url).path)]:
        value = fold(text)
        for key, _, _, words in CATEGORIES[:-1]:
            if re.search(r"\b(?:" + words + r")\b", value):
                return key
    lead = fold(article.content_text[:600])
    scores = [(len(re.findall(r"\b(?:" + words + r")\b", lead)), key) for key, _, _, words in CATEGORIES[:-1]]
    score, key = max(scores, key=lambda item: item[0])
    if score >= 2:
        return key
    if article.source_site.removeprefix("www.") in {"cafef.vn", "cafebiz.vn", "vietnambusinessinsider.vn", "tapchikinhtetaichinh.vn", "mekongasean.vn", "thesaigontimes.vn"}:
        return "economy"
    return "other"


def build_overview(articles):
    days = {}
    for article in articles:
        day = article.published_date.date().isoformat()
        groups = days.setdefault(day, {})
        category = category_for(article)
        stories = groups.setdefault(category, {})
        title_key = re.sub(r"\W+", " ", fold(article.title)).strip() or article.url
        if title_key not in stories:
            text = plain_text(article.content_text).strip()
            text = re.sub(r"^(?:(?:Facebook|Twitter|Lưu bài viết|In bài|Copy link|TIN MỚI)\s*)+", "", text)
            sentences = re.split(r"(?<=[.!?])\s+", text)
            brief = " ".join(sentences[:2])
            if len(brief) > 380:
                brief = brief[:377].rsplit(" ", 1)[0] + "…"
            stories[title_key] = {"title": plain_text(article.title), "brief": brief, "articles": [], "time": article.published_date.strftime("%H:%M")}
        stories[title_key]["articles"].append(article.url_hash)
    editorial_days = {}
    from tonghoptin.editorial import load_edition
    for day in days:
        edition = load_edition([a for a in articles if a.published_date.date().isoformat() == day])
        if edition:
            edited = {}
            for story in edition['stories']:
                edited.setdefault(story['category'], {})[story['id']] = story
            days[day] = edited
            editorial_days[day] = {key: edition.get(key) for key in ('created_at', 'method', 'group_model', 'rewrite_model', 'source_count', 'day_brief', 'category_briefs')}
    return {"editorial": editorial_days, "categories": [{"id": k, "name": n, "description": d} for k, n, d, _ in CATEGORIES],
            "days": {day: {key: list(stories.values()) for key, stories in groups.items()} for day, groups in sorted(days.items(), reverse=True)}}
