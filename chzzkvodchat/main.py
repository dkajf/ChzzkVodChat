import requests
import json
import re
from pathlib import Path


def ms_to_hms(ms):
    sec = ms // 1000
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


vod_url = input("VOD URL: ").strip()

match = re.search(r"/video/(\d+)", vod_url)

if not match:
    print("올바른 VOD URL이 아닙니다.")
    exit()

video_no = match.group(1)

headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://chzzk.naver.com/",
    "Origin": "https://chzzk.naver.com"
}

print("VOD 정보 조회 중...")

video_info_url = (
    f"https://api.chzzk.naver.com/service/v3/videos/{video_no}"
)

r = requests.get(
    video_info_url,
    headers=headers,
    timeout=10
)

r.raise_for_status()

video_info = r.json()["content"]

duration_sec = video_info["duration"]
player_time = duration_sec * 1000

print(
    f"영상 길이: "
    f"{duration_sec // 3600:02d}:"
    f"{(duration_sec % 3600) // 60:02d}:"
    f"{duration_sec % 60:02d}"
)

all_chats = []
seen_keys = set()

print("채팅 수집 시작")

while True:

    url = (
        f"https://api.chzzk.naver.com/service/v1/videos/"
        f"{video_no}/chats"
        f"?playerMessageTime={player_time}"
        f"&previousVideoChatSize=50"
    )

    r = requests.get(
        url,
        headers=headers,
        timeout=10
    )

    r.raise_for_status()

    data = r.json()["content"]

    chats = data["previousVideoChats"]

    if not chats:
        print("채팅 없음")
        break

    new_count = 0

    for chat in chats:

        key = (
            chat["playerMessageTime"],
            chat["userIdHash"],
            chat["content"]
        )

        if key in seen_keys:
            continue

        seen_keys.add(key)
        all_chats.append(chat)
        new_count += 1

    print(
        f"{new_count}개 추가 "
        f"(누적 {len(all_chats)}개)"
    )

    oldest_time = min(
        chat["playerMessageTime"]
        for chat in chats
    )

    print(
        f"현재={player_time} "
        f"→ 가장오래된={oldest_time}"
    )

    if oldest_time <= 0:
        print("시작 지점 도달")
        break

    if oldest_time >= player_time:
        print("더 이상 진행 불가")
        break

    player_time = oldest_time - 1

print(f"\n수집 완료: {len(all_chats)}개")

all_chats.sort(
    key=lambda x: x["playerMessageTime"]
)

import sys

if getattr(sys, "frozen", False):
    base_dir = Path(sys.executable).parent
else:
    base_dir = Path(__file__).parent

output_dir = base_dir / "chat"
output_dir.mkdir(parents=True, exist_ok=True)

json_path = output_dir / f"{video_no}_chat.json"
txt_path = output_dir / f"{video_no}_chat.txt"

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(
        all_chats,
        f,
        ensure_ascii=False,
        indent=2
    )

with open(txt_path, "w", encoding="utf-8") as f:

    for chat in all_chats:

        try:
            profile = json.loads(chat["profile"])
            nickname = profile["nickname"]
        except:
            nickname = "Unknown"

        timestamp = ms_to_hms(
            chat["playerMessageTime"]
        )

        f.write(
            f'[{timestamp}][{nickname}] "{chat["content"]}"\n'
        )

print("\nTXT 저장 완료")
print(txt_path)

print("\nJSON 저장 완료")
print(json_path)

input("\n엔터를 누르면 종료됩니다...")