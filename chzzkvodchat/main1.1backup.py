import requests
import json
import re
import sys
from pathlib import Path

MAX_VODS = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://chzzk.naver.com/",
    "Origin": "https://chzzk.naver.com"
}


def ms_to_hms(ms):
    sec = ms // 1000
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def extract_video_no(url):
    match = re.search(r"/video/(\d+)", url)

    if not match:
        return None

    return match.group(1)


def get_video_info(video_no):

    url = (
        f"https://api.chzzk.naver.com/"
        f"service/v3/videos/{video_no}"
    )

    r = requests.get(
        url,
        headers=HEADERS,
        timeout=10
    )

    r.raise_for_status()

    return r.json()["content"]


def get_base_dir():

    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    return Path(__file__).parent


def collect_urls():

    print("=" * 36)
    print("CHZZK VOD CHAT")
    print("=" * 36)
    print()
    print("VOD URL 입력")
    print("(URL 추가 입력 가능)")
    print("(빈 상태에서 Enter 입력 시 등록 완료)")
    print(f"(최대 {MAX_VODS}개)")
    print()

    urls = []
    seen_videos = set()

    while True:

        url = input("> ").strip()

        if not url:
            break

        video_no = extract_video_no(url)

        if not video_no:

            print()
            print("잘못된 URL 무시:")
            print(url)
            print()

            continue

        if video_no in seen_videos:

            print()
            print(f"중복 URL 제외: {video_no}")
            print()

            continue

        seen_videos.add(video_no)
        urls.append(video_no)

        if len(urls) >= MAX_VODS:

            print()
            print(
                f"최대 등록 개수({MAX_VODS}개)에 "
                f"도달했습니다."
            )

            break

    return urls


def build_job_list(video_numbers):

    jobs = []

    print()
    print("VOD 정보 조회 중...")
    print()

    for video_no in video_numbers:

        try:

            info = get_video_info(video_no)

            jobs.append({
                "video_no": video_no,
                "info": info
            })

        except Exception as e:

            print(
                f"{video_no} 조회 실패:"
            )

            print(e)
            print()

    return jobs


def show_job_preview(jobs):

    print()
    print("=" * 36)
    print(
        f"등록된 작업 : "
        f"{len(jobs)} / {MAX_VODS}"
    )
    print("=" * 36)
    print()

    for idx, job in enumerate(jobs, start=1):

        info = job["info"]

        channel_name = (
            info["channel"]["channelName"]
        )

        publish_date = (
            info["publishDate"][:10]
        )

        title = (
            info["videoTitle"]
        )

        print(f"[{idx}]")
        print()
        print(f"채널명 : {channel_name}")
        print(f"방송일 : {publish_date}")
        print(
            f"영상번호 : {job['video_no']}"
        )
        print()
        print("제목 :")
        print(title)
        print()
        print("-" * 36)
        print()

    while True:

        answer = input(
            "진행하시겠습니까? (Y/N) : "
        ).strip().lower()

        if answer in ["y", "yes"]:
            return True

        if answer in ["n", "no"]:
            return False

def collect_chats(
    video_no,
    duration_sec,
    current_index,
    total_jobs
):

    player_time = duration_sec * 1000
    duration_ms = player_time

    if duration_ms <= 0:
        duration_ms = 1

    all_chats = []
    seen_keys = set()

    print()
    print("=" * 36)
    print(
        f"[{current_index}/{total_jobs}] "
        f"채팅 수집 시작"
    )
    print("=" * 36)

    while True:

        url = (
            f"https://api.chzzk.naver.com/"
            f"service/v1/videos/"
            f"{video_no}/chats"
            f"?playerMessageTime={player_time}"
            f"&previousVideoChatSize=50"
        )

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=10
        )

        r.raise_for_status()

        data = r.json()["content"]

        chats = data["previousVideoChats"]

        if not chats:
            break

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

        oldest_time = min(
            chat["playerMessageTime"]
            for chat in chats
        )

        progress = (
            (duration_ms - player_time)
            / duration_ms
        ) * 100

        print(
            f"\r진행률 {progress:6.2f}%"
            f" | 채팅 {len(all_chats):,}개"
            f" | 현재위치 "
            f"{ms_to_hms(player_time)}",
            end="",
            flush=True
        )

        if oldest_time <= 0:
            break

        if oldest_time >= player_time:
            break

        player_time = oldest_time - 1

    print(
        "\r진행률 100.00%"
        f" | 채팅 {len(all_chats):,}개"
        " | 완료",
        end=""
    )

    print()

    all_chats.sort(
        key=lambda x: x["playerMessageTime"]
    )

    return all_chats

def save_chat_files(
    all_chats,
    channel_name,
    publish_date,
    video_no
):

    base_dir = get_base_dir()

    channel_name = sanitize_filename(
        channel_name
    )

    output_dir = (
        base_dir
        / "chat"
        / channel_name
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    file_stem = (
        f"{publish_date}_{video_no}"
    )

    json_path = (
        output_dir
        / f"{file_stem}.json"
    )

    txt_path = (
        output_dir
        / f"{file_stem}.txt"
    )

    with open(
        json_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            all_chats,
            f,
            ensure_ascii=False,
            indent=2
        )

    with open(
        txt_path,
        "w",
        encoding="utf-8"
    ) as f:

        for chat in all_chats:

            try:

                profile = json.loads(
                    chat["profile"]
                )

                nickname = (
                    profile["nickname"]
                )

            except:

                nickname = "Unknown"

            timestamp = ms_to_hms(
                chat["playerMessageTime"]
            )

            f.write(
                f'[{timestamp}]'
                f'[{nickname}] '
                f'"{chat["content"]}"\n'
            )

    return txt_path, json_path


def process_job(
    job,
    current_index,
    total_jobs
):

    info = job["info"]

    channel_name = (
        info["channel"]["channelName"]
    )

    publish_date = (
        info["publishDate"][:10]
    )

    duration_sec = (
        info["duration"]
    )

    video_no = (
        job["video_no"]
    )

    print()
    print("=" * 36)
    print(
        f"[{current_index}/{total_jobs}]"
    )
    print()
    print(
        f"채널명 : {channel_name}"
    )
    print(
        f"방송일 : {publish_date}"
    )
    print(
        "영상길이 : "
        f"{duration_sec // 3600:02d}:"
        f"{(duration_sec % 3600) // 60:02d}:"
        f"{duration_sec % 60:02d}"
    )
    print("=" * 36)

    all_chats = collect_chats(
        video_no,
        duration_sec,
        current_index,
        total_jobs
    )

    txt_path, json_path = (
        save_chat_files(
            all_chats,
            channel_name,
            publish_date,
            video_no
        )
    )

    print()
    print("=" * 36)
    print("수집 완료")
    print()
    print(
        f"총 채팅 : "
        f"{len(all_chats):,}개"
    )
    print()
    print("TXT :")
    print(txt_path)
    print()
    print("JSON :")
    print(json_path)
    print("=" * 36)
    print()


def main():

    video_numbers = collect_urls()

    if not video_numbers:

        print()
        print(
            "등록된 URL이 없습니다."
        )

        return

    jobs = build_job_list(
        video_numbers
    )

    if not jobs:

        print()
        print(
            "조회 가능한 VOD가 없습니다."
        )

        return

    proceed = (
        show_job_preview(jobs)
    )

    if not proceed:

        print()
        print(
            "작업이 취소되었습니다."
        )

        return

    total_jobs = len(jobs)

    for idx, job in enumerate(
        jobs,
        start=1
    ):

        try:

            process_job(
                job,
                idx,
                total_jobs
            )

        except Exception as e:

            print()
            print(
                f"[{idx}/{total_jobs}] "
                "작업 실패"
            )

            print(e)
            print()

    print("=" * 36)
    print("전체 작업 완료")
    print("=" * 36)


if __name__ == "__main__":
    main()