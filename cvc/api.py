import json
from datetime import datetime, timedelta, timezone
from collections import Counter
import requests
from .model import Chat, Metadata


class Cancelled(Exception):
    pass


class Api:
    base = "https://api.chzzk.naver.com"

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://chzzk.naver.com/", "Origin": "https://chzzk.naver.com"})

    def close(self):
        self.session.close()

    def get(self, path, cancel, params=None):
        error = None
        for attempt in range(3):
            if cancel.is_set():
                raise Cancelled()
            try:
                response = self.session.get(self.base + path, params=params, timeout=(5, 10))
                response.raise_for_status()
                value = response.json()
                content = value.get("content")
                if not isinstance(content, dict):
                    raise ValueError(f"API 응답 오류: {value.get('message', 'content 없음')}")
                return content
            except (requests.RequestException, ValueError) as e:
                error = e
                if isinstance(e, requests.HTTPError) and e.response is not None and 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    break
                if cancel.wait(0.5 * (attempt + 1)):
                    raise Cancelled()
        raise RuntimeError(f"API 요청 실패: {error}")

    def metadata(self, vod_id, cancel):
        data = self.get(f"/service/v3/videos/{vod_id}", cancel)
        duration = data.get("duration")
        duration = int(duration * 1000) if isinstance(duration, (int, float)) and duration > 0 else None
        start = end = None
        raw_start = data.get("liveOpenDate")
        if isinstance(raw_start, str) and raw_start.strip():
            try:
                kst = timezone(timedelta(hours=9), "KST")
                opened = datetime.fromisoformat(raw_start)
                opened = opened.replace(tzinfo=kst) if opened.tzinfo is None else opened.astimezone(kst)
                start = opened.strftime("%Y-%m-%d %H:%M:%S (KST)")
                if duration is not None:
                    ended = opened + timedelta(milliseconds=duration)
                    end = ended.strftime("%Y-%m-%d %H:%M:%S") + " (KST, 계산값: 방송 시작 + 영상 길이)"
            except (ValueError, OverflowError):
                pass
        # publishDate remains the legacy filename date, not the broadcast start.
        return Metadata(vod_id=vod_id, channel=(data.get("channel") or {}).get("channelName") or "미확인",
                        title=data.get("videoTitle") or "미확인", duration_ms=duration, start=start, end=end,
                        date=str(data.get("publishDate") or "미확인")[:10])

    def collect(self, meta, cancel, progress):
        if meta.duration_ms is None:
            raise ValueError("영상 길이를 알 수 없어 역방향 수집을 시작할 수 없습니다. 정보 조회를 재시도하세요")
        cursor = meta.duration_ms
        chats = []
        seen = Counter()
        size = 50
        while True:
            data = self.get(f"/service/v1/videos/{meta.vod_id}/chats", cancel,
                            {"playerMessageTime": cursor, "previousVideoChatSize": size})
            page = data.get("previousVideoChats")
            if not isinstance(page, list):
                raise ValueError("채팅 페이지 형식 오류")
            if not page:
                break
            oldest = min(int(c["playerMessageTime"]) for c in page)
            if oldest < 0 or oldest > cursor:
                raise ValueError("채팅 페이지 시간 범위 오류")
            if size > 50 and oldest == cursor and len(page) <= size // 2:
                raise RuntimeError("API 페이지 크기 확장 여부를 확인할 수 없어 동일 시각 채팅의 완전성을 보장할 수 없습니다")
            # Inclusive overlap keeps all messages at a boundary. Increase the page
            # when a timestamp fills it; fail explicitly if the API cannot advance.
            if oldest == cursor and len(page) >= size:
                if size >= 3200:
                    raise RuntimeError("동일 시각 채팅 페이지가 포화되어 완전성을 확인할 수 없습니다")
                size *= 2
                continue
            occurrence = Counter()
            boundary_keys = set()
            for raw in page:
                if cancel.is_set():
                    raise Cancelled()
                ms = int(raw["playerMessageTime"])
                if ms < 0 or ms > cursor:
                    raise ValueError("페이지 범위 밖 채팅")
                text = raw.get("content", "")
                identity = raw.get("messageId") or raw.get("videoChatId")
                key = ("id", str(identity)) if identity is not None else ("row", ms, raw.get("userIdHash"), text, raw.get("messageTime"))
                occurrence[key] += 1
                if ms == oldest:
                    boundary_keys.add(key)
                if identity is not None and occurrence[key] > 1:
                    continue
                if occurrence[key] <= seen[key]:
                    continue
                if not isinstance(text, str) or not text:
                    continue
                profile = raw.get("profile")
                try:
                    profile = json.loads(profile) if isinstance(profile, str) else profile
                    nickname = profile.get("nickname") or "Unknown"
                except (ValueError, AttributeError):
                    nickname = "Unknown"
                # messageTime semantics have not been verified against a live VOD.
                chats.append(Chat(ms, text, nickname))
            seen = Counter({key: occurrence[key] for key in boundary_keys})
            progress(len(chats), oldest, meta.duration_ms)
            if oldest == cursor:
                if len(page) < size:
                    cursor -= 1
                else:
                    raise RuntimeError("채팅 페이지가 진행되지 않습니다")
            else:
                cursor = oldest
            size = 50
            if cursor < 0:
                break
        chats.sort(key=lambda c: c.ms)
        return chats
