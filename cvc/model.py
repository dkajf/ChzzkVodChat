from dataclasses import dataclass
import re
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class Metadata:
    vod_id: str = ""
    channel: str = "미확인"
    title: str = "미확인"
    duration_ms: int | None = None
    start: str | None = None
    end: str | None = None
    date: str = "미확인"

    @property
    def url(self):
        return f"https://chzzk.naver.com/video/{self.vod_id}" if self.vod_id else "미확인"

    @property
    def broadcast_date(self):
        return self.start[:10] if self.start else "미확인"


@dataclass(frozen=True, slots=True)
class Chat:
    ms: int
    text: str
    nickname: str = "Unknown"
    actual: str | None = None


@dataclass(frozen=True)
class Selection:
    start_ms: int = 0
    end_ms: int | None = None
    keyword: str = "ㅋ"


def hms(ms, premiere=False):
    sec = int(ms) // 1000
    return f"{sec // 3600:02d}:{sec // 60 % 60:02d}:{sec % 60:02d}" + (":00" if premiere else "")


def parse_time(value):
    value = value.strip()
    if re.fullmatch(r"\d{4}|\d{6}", value):
        value = value.zfill(6)
        value = f"{value[:-4]}:{value[-4:-2]}:{value[-2:]}"
    if not re.fullmatch(r"\d{2,}:\d{2}:\d{2}", value):
        raise ValueError("HH:MM:SS 또는 숫자 4자리(MMSS)·6자리(HHMMSS)를 입력하세요")
    h, m, s = map(int, value.split(":"))
    if m > 59 or s > 59:
        raise ValueError("분·초는 0~59입니다")
    return (h * 3600 + m * 60 + s) * 1000


def video_id(value):
    p = urlsplit(value.strip())
    match = re.fullmatch(r"/video/(\d+)/?", p.path)
    if p.scheme not in ("http", "https") or p.netloc != "chzzk.naver.com" or not match:
        raise ValueError("치지직 VOD URL을 입력하세요")
    return str(int(match[1]))


def selection(start, end, keyword, automatic, duration):
    a = parse_time(start) if start.strip() else 0
    b = None if automatic else parse_time(end)
    word = keyword.strip() or "ㅋ"
    if len(word) > 10:
        raise ValueError("키워드는 최대 10자입니다")
    limit = duration if b is None else b
    if limit is not None and (a >= limit or (duration is not None and limit > duration)):
        raise ValueError("시작 < 종료이며 영상 길이 이내여야 합니다")
    return Selection(a, b, word)
