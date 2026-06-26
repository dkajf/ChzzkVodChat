import requests
import json
import re
import sys
from pathlib import Path
from collections import defaultdict

MAX_VODS = 10
MIN_CHAT_COUNT = 10
MOVING_AVERAGE_MINUTES = 15
PREVIEW_TITLE_WIDTH = 18

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


def minute_to_hms(minute):
    return ms_to_hms(minute * 60000)


def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def extract_video_no(url):
    match = re.search(
        r"/video/(\d+)",
        url
    )

    if not match:
        return None

    return match.group(1)


def extract_file_stem(value):
    name = Path(value).name

    match = re.match(
        r"^(\d{4}-\d{2}-\d{2}_\d+)(?:\.(json|txt))?$",
        name
    )

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


def collect_inputs():

    print("=" * 36)
    print("CHZZK VOD CHAT")
    print("Version 1.2.1")
    print("=" * 36)
    print()
    print("VOD URL 또는 파일명 입력")
    print("(추가 입력 가능)")
    print("(빈 상태에서 Enter 입력 시 등록 완료)")
    print(f"(최대 {MAX_VODS}개)")
    print()

    mode = None
    inputs = []
    seen = set()

    while True:

        try:

            value = input("> ").strip()

        except EOFError:

            break

        if not value:
            break

        video_no = extract_video_no(value)
        file_stem = extract_file_stem(value)

        if video_no:
            value_mode = "url"
            key = video_no

        elif file_stem:
            value_mode = "analysis"
            key = file_stem

        else:
            print()
            print("잘못된 입력 무시:")
            print(value)
            print()

            continue

        if mode is None:
            mode = value_mode

        if value_mode != mode:
            print()
            print("다른 형식 입력 무시:")
            print(value)
            print()

            continue

        if key in seen:
            print()
            print("중복 입력 제외:")
            print(key)
            print()

            continue

        seen.add(key)
        inputs.append(key)

        if len(inputs) >= MAX_VODS:

            print()
            print(
                f"최대 등록 개수({MAX_VODS}개)에 "
                f"도달했습니다."
            )

            break

    return mode, inputs


def find_analysis_files(file_stems):

    base_dir = get_base_dir()

    chat_dir = base_dir / "chat"

    jobs = []

    print()
    print("분석 대상 조회 중...")
    print()

    for stem in file_stems:

        found = None

        for json_file in chat_dir.rglob("*.json"):

            if json_file.stem == stem:

                found = json_file
                break

        if found:

            jobs.append(found)

        else:

            print(f"{stem} 조회 실패")
            print()

    return jobs


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
    print("CHZZK VOD CHAT COLLECTOR")
    print("=" * 36)
    print()
    print("[수집 대상]")
    print()

    for idx, job in enumerate(jobs, start=1):

        info = job["info"]

        publish_date = (
            info["publishDate"][:10]
        )

        title = (
            info["videoTitle"]
        )

        title = shorten_text(
            title,
            PREVIEW_TITLE_WIDTH
        )

        print(
            f"{idx:02d}. {publish_date} | "
            f"{title:<{PREVIEW_TITLE_WIDTH}} | "
            f"{job['video_no']}"
        )

    print()
    print(f"총 대상 : {len(jobs)}개")
    print()
    print("=" * 36)
    print("채팅 수집을 시작하시겠습니까? (Y/N)")
    print("=" * 36)

    while True:

        answer = input("> ").strip().lower()

        if answer in ["y", "yes"]:
            return True

        if answer in ["n", "no"]:
            return False


def shorten_text(text, width):

    if len(text) <= width:
        return text

    if width <= 3:
        return text[:width]

    return text[:width - 3] + "..."


def show_analysis_preview(jobs):

    print()
    print("=" * 36)
    print("CHZZK VOD CHAT ANALYZER")
    print("=" * 36)
    print()
    print("[분석 대상]")
    print()

    for idx, path in enumerate(jobs, start=1):

        print(f"{idx:02d}. {path.stem}")

    print()
    print(f"총 파일 : {len(jobs)}개")
    print()
    print("키워드를 입력해주세요.")
    print()
    print(
        "Enter 입력 시 기본 키워드 'ㅋ'로 분석을 진행합니다."
    )
    print(
        "다른 키워드를 사용하려면 1~10자의 키워드를 입력해주세요."
    )
    print()

    keyword = input("> ").strip()

    if not keyword:
        keyword = "ㅋ"

    if len(keyword) > 10:
        keyword = keyword[:10]

    print()
    print(f"키워드 : {keyword}")
    print()
    print("=" * 36)
    print("채팅 분석을 시작하시겠습니까? (Y/N)")
    print("=" * 36)

    while True:

        answer = input("> ").strip().lower()

        if answer in ["y", "yes"]:
            return keyword

        if answer in ["n", "no"]:
            return None


def show_analysis_complete_menu():

    print()
    print("=" * 36)
    print("분석이 완료되었습니다.")
    print("=" * 36)
    print()
    print("1. 처음으로 돌아가기")
    print("2. 종료")
    print()

    while True:

        answer = input("선택 : ").strip()

        if answer == "1":
            return True

        if answer == "2":
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


def load_chat_json(json_path):

    with open(
        json_path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def get_analysis_duration_sec(json_path):

    video_no = (
        json_path.stem
        .split("_")[-1]
    )

    try:

        info = get_video_info(
            video_no
        )

        return info["duration"]

    except:

        return None


def analyze_chat(
    chats,
    keyword,
    duration_sec=None
):

    minute_data = defaultdict(
        lambda: {
            "chat": 0,
            "keyword": 0
        }
    )

    for chat in chats:

        minute = (
            chat["playerMessageTime"]
            // 60000
        )

        minute_data[minute]["chat"] += 1

        if keyword in chat["content"]:

            minute_data[minute][
                "keyword"
            ] += 1

    results = []

    total_minutes = 0

    if duration_sec is not None:

        total_minutes = (
            (duration_sec + 59)
            // 60
        )

    if minute_data:

        total_minutes = max(
            total_minutes,
            max(minute_data.keys()) + 1
        )

    for minute in range(
        total_minutes
    ):

        chat_count = (
            minute_data[minute]["chat"]
        )

        keyword_count = (
            minute_data[minute]["keyword"]
        )

        keyword_rate = 0

        if chat_count:

            keyword_rate = (
                keyword_count
                / chat_count
            ) * 100

        results.append({
            "minute": minute,
            "chat": chat_count,
            "keyword": keyword_count,
            "keyword_rate": keyword_rate
        })

    return results


def calculate_average(results):

    total_chat = sum(
        row["chat"]
        for row in results
    )

    overall_average = 0

    broadcast_minutes = len(
        results
    )

    if broadcast_minutes:

        overall_average = (
            total_chat
            / broadcast_minutes
        )

    for idx, row in enumerate(results):

        neighbors = []

        for i in range(
            max(0, idx - MOVING_AVERAGE_MINUTES),
            idx
        ):

            neighbors.append(
                results[i]["chat"]
            )

        moving_average = 0

        if neighbors:

            moving_average = (
                sum(neighbors)
                / len(neighbors)
            )

        increase = 0

        if moving_average > 0:

            increase = (
                (
                    row["chat"]
                    - moving_average
                )
                / moving_average
            ) * 100

        overall_rate = 0

        if overall_average > 0:

            overall_rate = (
                row["chat"]
                / overall_average
            ) * 100

        row["moving_average"] = (
            moving_average
        )

        row["increase"] = increase

        row["overall_rate"] = (
            overall_rate
        )

    return overall_average


def build_top_lists(results):

    ranked_results = [
        row
        for row in results
        if row["chat"] >= MIN_CHAT_COUNT
    ]

    chat_top = sorted(
        results,
        key=lambda row: (
            -row["chat"],
            row["minute"]
        )
    )[:10]

    increase_top = sorted(
        ranked_results,
        key=lambda row: (
            -round_number(row["increase"]),
            row["minute"]
        )
    )[:10]

    keyword_count_top = sorted(
        ranked_results,
        key=lambda row: (
            -row["keyword"],
            row["minute"]
        )
    )[:10]

    keyword_rate_top = sorted(
        ranked_results,
        key=lambda row: (
            -row["keyword_rate"],
            -row["keyword"],
            row["minute"]
        )
    )[:10]

    return (
        chat_top,
        increase_top,
        keyword_count_top,
        keyword_rate_top
    )


def format_percent(value):
    return f"{round_number(value)}%"


def round_number(value):

    if value >= 0:
        return int(value + 0.5)

    return int(value - 0.5)


def format_increase(value):
    rounded = round_number(value)

    return f"{rounded:+d}% {get_increase_marker(value):<3}"


def get_keyword_rate_marker(value):

    if value >= 30:
        return "▲▲▲"

    if value >= 20:
        return "▲▲"

    if value >= 10:
        return "▲"

    return "-"


def get_increase_marker(value):

    if value >= 100:
        return "▲▲▲"

    if value >= 60:
        return "▲▲"

    if value >= 30:
        return "▲"

    return "-"


def format_top_row(row):

    return (
        f"채팅 {row['chat']:>4,} | "
        f"키워드 {row['keyword']:>3,} "
        f"({row['keyword_rate']:>5.1f}%) "
        f"{get_keyword_rate_marker(row['keyword_rate']):<3} | "
        f"평균 {format_increase(row['increase']):>8}"
    )


def format_detail_row(row):

    return (
        f"채팅 {row['chat']:>4,} | "
        f"키워드 {row['keyword']:>3,} "
        f"({row['keyword_rate']:>5.1f}%) "
        f"{get_keyword_rate_marker(row['keyword_rate']):<3} | "
        f"평균 {format_increase(row['increase']):>8}"
    )


def build_analysis_text(
    file_stem,
    results,
    overall_average,
    keyword
):

    total_chat = sum(
        row["chat"]
        for row in results
    )

    (
        chat_top,
        increase_top,
        keyword_count_top,
        keyword_rate_top
    ) = build_top_lists(
        results
    )

    lines = []

    lines.append("=" * 36)
    lines.append("CHZZK VOD CHAT ANALYZER")
    lines.append("=" * 36)
    lines.append("")
    lines.append("파일명")
    lines.append(file_stem)
    lines.append("")
    lines.append("총 채팅")
    lines.append(f"{total_chat:,}")
    lines.append("")
    lines.append("전체 평균 채팅")
    lines.append(f"{round_number(overall_average):,}")
    lines.append("")
    lines.append("이동평균 기준")
    lines.append(f"최근 {MOVING_AVERAGE_MINUTES}분")
    lines.append("")
    lines.append("랭킹 최소 채팅")
    lines.append(f"{MIN_CHAT_COUNT:,}")
    lines.append("")
    lines.append("분석 키워드")
    lines.append(keyword)
    lines.append("")
    lines.append("=" * 36)
    lines.append("채팅량 TOP10")
    lines.append("=" * 36)
    lines.append("")

    append_top_section(lines, chat_top)

    lines.append("=" * 36)
    lines.append("이동평균 증가율 TOP10")
    lines.append("=" * 36)
    lines.append("")

    append_top_section(lines, increase_top)

    lines.append("=" * 36)
    lines.append("키워드 개수 TOP10")
    lines.append("=" * 36)
    lines.append("")

    append_top_section(lines, keyword_count_top)

    lines.append("=" * 36)
    lines.append("키워드 비율 TOP10")
    lines.append("=" * 36)
    lines.append("")

    append_top_section(lines, keyword_rate_top)

    lines.append("=" * 36)
    lines.append("상세로그")
    lines.append("=" * 36)
    lines.append("")

    for row in results:

        lines.append(
            f"[{minute_to_hms(row['minute'])}]"
        )
        lines.append(
            format_detail_row(row)
        )
        lines.append("")

    return "\n".join(lines)


def append_top_section(lines, rows):

    for idx, row in enumerate(rows, start=1):

        lines.append(
            f"{idx}. [{minute_to_hms(row['minute'])}]"
        )
        lines.append(
            format_top_row(row)
        )
        lines.append("")


def save_analysis_file(
    json_path,
    text
):

    output_path = (
        json_path.parent
        / f"{json_path.stem}_analysis.txt"
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(text)

    return output_path


def process_analysis_job(
    json_path,
    keyword
):

    chats = load_chat_json(
        json_path
    )

    duration_sec = get_analysis_duration_sec(
        json_path
    )

    results = analyze_chat(
        chats,
        keyword,
        duration_sec
    )

    overall_average = (
        calculate_average(
            results
        )
    )

    text = build_analysis_text(
        json_path.stem,
        results,
        overall_average,
        keyword
    )

    return save_analysis_file(
        json_path,
        text
    )


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


def process_url_mode(video_numbers):

    jobs = build_job_list(
        video_numbers
    )

    if not jobs:

        print()
        print(
            "조회 가능한 VOD가 없습니다."
        )

        return False

    proceed = (
        show_job_preview(jobs)
    )

    if not proceed:

        print()
        print(
            "작업이 취소되었습니다."
        )

        return False

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

    return True


def process_analysis_mode(file_stems):

    jobs = find_analysis_files(
        file_stems
    )

    if not jobs:

        print()
        print(
            "분석 가능한 파일이 없습니다."
        )

        return False

    keyword = show_analysis_preview(
        jobs
    )

    if keyword is None:

        print()
        print(
            "작업이 취소되었습니다."
        )

        return False

    for path in jobs:

        try:

            output_path = process_analysis_job(
                path,
                keyword
            )

            print()
            print(path.stem)
            print("분석 완료")
            print(output_path)

        except Exception as e:

            print()
            print(f"{path.stem} 분석 실패")
            print(e)
            print()

    return True


def main():

    while True:

        mode, inputs = collect_inputs()

        if not inputs:

            print()
            print(
                "등록된 입력이 없습니다."
            )

            return

        if mode == "url":

            completed = process_url_mode(
                inputs
            )

        else:

            completed = process_analysis_mode(
                inputs
            )

        if not completed:
            return

        if mode != "analysis":

            print("=" * 36)
            print("전체 작업 완료")
            print("=" * 36)
            return

        restart = show_analysis_complete_menu()

        if not restart:
            return

        print()


if __name__ == "__main__":
    main()
