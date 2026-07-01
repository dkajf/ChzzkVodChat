import requests
import json
import re
import sys
from pathlib import Path
from collections import defaultdict

try:
    import msvcrt
except ImportError:
    msvcrt = None


class EscapeInput(Exception):
    pass

CONFIG_FORMAT = "1"
SETTINGS_FILE_NAME = "CHZZK_VOD_CHAT_Settings.txt"

DEFAULT_SETTINGS = {
    "ConfigFormat": CONFIG_FORMAT,
    "MaxVods": 30,
    "OutputFolder": "chat",
    "DefaultKeyword": "ㅋ",
    "MaxKeywordRepeat": 5,
    "TopMinimumChatCount": 0,
    "MovingAverageMinutes": 15,
    "TopCount": 10,
    "PreviewTitleWidth": 18,
    "SaveDetailLog": True
}

SETTINGS = DEFAULT_SETTINGS.copy()

SETTING_RULES = {
    "MaxVods": {
        "type": "int",
        "min": 1,
        "max": 30
    },
    "OutputFolder": {
        "type": "string",
        "min_length": 1,
        "max_length": 100
    },
    "DefaultKeyword": {
        "type": "string",
        "min_length": 1,
        "max_length": 10
    },
    "MaxKeywordRepeat": {
        "type": "int",
        "min": 0,
        "max": 100
    },
    "TopMinimumChatCount": {
        "type": "int",
        "min": 0,
        "max": 1000000
    },
    "MovingAverageMinutes": {
        "type": "int",
        "min": 1,
        "max": 60
    },
    "TopCount": {
        "type": "int",
        "min": 1,
        "max": 100
    },
    "PreviewTitleWidth": {
        "type": "int",
        "min": 5,
        "max": 100
    },
    "SaveDetailLog": {
        "type": "bool"
    }
}

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


def minute_to_hms_offset(minute, offset_sec):
    return format_time_seconds(offset_sec + minute * 60)


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


def parse_hms(value):
    if not re.match(r"^\d{2}:\d{2}:\d{2}$", value):
        return None

    parts = value.split(":")

    try:
        hours, minutes, seconds = map(int, parts)

    except ValueError:
        return None

    if hours < 0 or minutes < 0 or seconds < 0:
        return None

    if minutes >= 60 or seconds >= 60:
        return None

    return hours * 3600 + minutes * 60 + seconds


def format_time_seconds(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_approx_minutes(seconds):
    minutes = round(seconds / 60)

    if minutes < 1:
        minutes = 1

    return f"약 {minutes}분"


def prompt_input(prompt="> "):
    if msvcrt is not None:
        sys.stdout.write(prompt)
        sys.stdout.flush()

        buffer = []

        while True:
            key = msvcrt.getwch()

            if key in ["\r", "\n"]:
                sys.stdout.write("\n")
                return "".join(buffer)

            if key == "\x1b":
                raise EscapeInput()

            if key == "\x08":
                if buffer:
                    buffer.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue

            if key in ["\x00", "\xe0"]:
                msvcrt.getwch()
                continue

            buffer.append(key)
            sys.stdout.write(key)
            sys.stdout.flush()

    return input(prompt)


def get_chat_duration_sec(chats):
    if not chats:
        return 0

    return max(
        chat["playerMessageTime"] for chat in chats
    ) // 1000


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


def get_settings_path():

    return get_base_dir() / SETTINGS_FILE_NAME


def get_setting(name):

    return SETTINGS[name]


def build_settings_text(settings):

    bool_value = "True"

    if not settings["SaveDetailLog"]:
        bool_value = "False"

    return "\n".join([
        "# ==========================================",
        "# CHZZK VOD CHAT Settings",
        "# ==========================================",
        "",
        f"ConfigFormat={settings['ConfigFormat']}",
        "",
        "[Collect]",
        "",
        "; 한 번에 등록할 수 있는 최대 VOD 개수입니다.",
        "; 권장 범위 : 1 ~ 30",
        f"MaxVods={settings['MaxVods']}",
        "",
        "; 채팅 파일(.json/.txt)이 저장될 폴더입니다.",
        "; 프로그램 실행 폴더를 기준으로 생성됩니다.",
        f"OutputFolder={settings['OutputFolder']}",
        "",
        "",
        "[Analyze]",
        "",
        "; 분석 실행 시 기본으로 사용할 키워드입니다.",
        "; 입력 없이 Enter를 누르면 이 키워드가 사용됩니다.",
        f"DefaultKeyword={settings['DefaultKeyword']}",
        "",
        "; 하나의 채팅에서 동일 키워드를 최대 몇 번까지 카운트할지 설정합니다.",
        "; 0으로 설정하면 제한 없이 모두 카운트합니다.",
        f"MaxKeywordRepeat={settings['MaxKeywordRepeat']}",
        "",
        "; TOP 구간에 포함하기 위한 최소 채팅 수를 설정합니다.",
        "; 0으로 설정하면 방송 전체 평균 채팅 수를 자동으로 사용합니다.",
        f"TopMinimumChatCount={settings['TopMinimumChatCount']}",
        "",
        "; 이동 평균 계산에 사용할 이전 구간(분)입니다.",
        "; 값이 클수록 평균이 부드럽게 계산됩니다.",
        f"MovingAverageMinutes={settings['MovingAverageMinutes']}",
        "",
        "",
        "[Display]",
        "",
        "; 각 TOP 목록에 출력할 최대 개수입니다.",
        f"TopCount={settings['TopCount']}",
        "",
        "; 미리보기에서 표시할 방송 제목의 최대 글자 수입니다.",
        "; 길어질 경우 자동으로 ... 처리합니다.",
        f"PreviewTitleWidth={settings['PreviewTitleWidth']}",
        "",
        "; 분석 결과 파일에 상세 로그를 포함할지 설정합니다.",
        "; False로 설정하면 TOP 결과만 저장합니다.",
        f"SaveDetailLog={bool_value}",
        ""
    ])


def save_settings(settings):

    settings_path = get_settings_path()

    with open(
        settings_path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(build_settings_text(settings))


def print_settings_notice(message):

    print()
    print(message)
    print(f"설정 파일: {SETTINGS_FILE_NAME}")
    print("필요하면 메모장으로 수정할 수 있습니다.")
    print()


def create_settings_if_not_exists():

    settings_path = get_settings_path()

    if settings_path.exists():
        return False

    save_settings(DEFAULT_SETTINGS)

    print_settings_notice("설정 파일이 생성되었습니다.")

    return True


def load_settings():

    settings_path = get_settings_path()
    loaded = {}

    try:

        with open(
            settings_path,
            "r",
            encoding="utf-8"
        ) as f:

            for line in f:

                value = line.strip()

                if not value:
                    continue

                if value.startswith("#") or value.startswith(";"):
                    continue

                if value.startswith("[") and value.endswith("]"):
                    continue

                if "=" not in value:
                    continue

                key, raw_value = value.split("=", 1)
                loaded[key.strip()] = raw_value.strip()

    except Exception as e:

        loaded["_LoadError"] = str(e)

    return loaded


def validate_config_format(raw_settings):

    return raw_settings.get("ConfigFormat") == CONFIG_FORMAT


def format_setting_error(key, value, reason, default_value):

    return (
        f"{key} = {value}\n"
        f"-> {reason}\n"
        f"-> 기본값({default_value})으로 변경되었습니다."
    )


def parse_int_setting(key, value, rule, errors):

    default_value = DEFAULT_SETTINGS[key]

    try:
        number = int(value)

    except (TypeError, ValueError):
        errors.append(
            format_setting_error(
                key,
                value,
                "정수만 입력 가능합니다.",
                default_value
            )
        )
        return default_value

    if number < rule["min"] or number > rule["max"]:
        errors.append(
            format_setting_error(
                key,
                value,
                f"허용 범위({rule['min']}~{rule['max']})를 벗어났습니다.",
                default_value
            )
        )
        return default_value

    return number


def parse_bool_setting(key, value, errors):

    default_value = DEFAULT_SETTINGS[key]

    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()

    if normalized == "true":
        return True

    if normalized == "false":
        return False

    errors.append(
        format_setting_error(
            key,
            value,
            "True 또는 False만 입력 가능합니다.",
            default_value
        )
    )

    return default_value


def parse_string_setting(key, value, rule, errors):

    default_value = DEFAULT_SETTINGS[key]

    if value is None:
        value = ""

    text = str(value).strip()

    if len(text) < rule["min_length"]:
        errors.append(
            format_setting_error(
                key,
                value,
                "빈 값은 사용할 수 없습니다.",
                default_value
            )
        )
        return default_value

    if len(text) > rule["max_length"]:
        errors.append(
            format_setting_error(
                key,
                value,
                f"허용 길이({rule['max_length']}자)를 벗어났습니다.",
                default_value
            )
        )
        return default_value

    if key == "OutputFolder":

        output_path = Path(text)

        if output_path.is_absolute() or ".." in output_path.parts:
            errors.append(
                format_setting_error(
                    key,
                    value,
                    "프로그램 실행 폴더 안의 상대 경로만 사용할 수 있습니다.",
                    default_value
                )
            )
            return default_value

    return text


def validate_setting_value(key, value, errors):

    rule = SETTING_RULES[key]

    if rule["type"] == "int":
        return parse_int_setting(
            key,
            value,
            rule,
            errors
        )

    if rule["type"] == "bool":
        return parse_bool_setting(
            key,
            value,
            errors
        )

    return parse_string_setting(
        key,
        value,
        rule,
        errors
    )


def validate_settings(raw_settings):

    if "_LoadError" in raw_settings:
        print_settings_notice(
            "설정 파일을 읽을 수 없어 최신 형식으로 재생성했습니다."
        )
        print(raw_settings["_LoadError"])

        restored = DEFAULT_SETTINGS.copy()
        save_settings(restored)
        return restored

    if not validate_config_format(raw_settings):
        print_settings_notice(
            "설정 파일 형식이 현재 버전과 달라 최신 형식으로 초기화했습니다."
        )

        restored = DEFAULT_SETTINGS.copy()
        save_settings(restored)
        return restored

    settings = DEFAULT_SETTINGS.copy()
    errors = []

    for key in SETTING_RULES:

        value = raw_settings.get(key)

        if value is None:
            errors.append(
                format_setting_error(
                    key,
                    "(없음)",
                    "설정값이 존재하지 않습니다.",
                    DEFAULT_SETTINGS[key]
                )
            )
            continue

        settings[key] = validate_setting_value(
            key,
            value,
            errors
        )

    if errors:
        print()
        print("다음 설정값이 올바르지 않아 기본값으로 복원했습니다.")
        print()

        for error in errors:
            print(error)
            print()

    save_settings(settings)

    return settings


def initialize_settings():

    create_settings_if_not_exists()

    raw_settings = load_settings()

    return validate_settings(raw_settings)


def collect_inputs():

    max_vods = get_setting("MaxVods")

    print("=" * 36)
    print("CHZZK VOD CHAT")
    print("Version 1.2.5")
    print("=" * 36)
    print()
    print("VOD URL 또는 분석 파일명을 입력하세요.")
    print("- URL: 채팅 수집")
    print("- 파일명: 분석(txt 이름 가능)")
    print("  실제 분석은 txt 파일을 사용합니다.")
    print("- 빈 Enter: 시작")
    print(f"최대 {max_vods}개 URL")
    print("ESC를 누를 시 프로그램이 종료됩니다.")
    print()

    mode = None
    inputs = []
    seen = set()

    while True:

        try:

            value = prompt_input("> ").strip()

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
            print("입력 형식을 확인해주세요.")
            print("VOD URL 또는 chat 폴더의 txt 파일명을 입력할 수 있습니다.")
            print(value)
            print()

            continue

        if mode is None:
            mode = value_mode

        if value_mode != mode:
            print()
            print("URL과 파일명은 한 번에 섞어서 입력할 수 없습니다.")
            print("현재 입력은 건너뜁니다:")
            print(value)
            print()

            continue

        if key in seen:
            print()
            print("이미 등록된 입력입니다:")
            print(key)
            print()

            continue

        seen.add(key)
        inputs.append(key)

        if value_mode == "analysis":
            break

        if len(inputs) >= max_vods:

            print()
            print(
                f"최대 등록 개수({max_vods}개)에 "
                f"도달했습니다."
            )

            break

    return mode, inputs


def find_analysis_files(file_stems):

    base_dir = get_base_dir()

    chat_dir = base_dir / get_setting("OutputFolder")

    jobs = []

    print()
    print("분석 대상 조회 중...")
    print()

    if not chat_dir.exists():
        print(f"{chat_dir} 폴더가 없습니다.")
        print("먼저 VOD URL로 채팅을 수집하거나 설정의 OutputFolder를 확인해주세요.")
        print()
        return jobs

    txt_files = {}

    for txt_file in chat_dir.rglob("*.txt"):
        txt_files.setdefault(
            txt_file.stem,
            txt_file
        )

    for stem in file_stems:

        found = txt_files.get(stem)

        if found:

            jobs.append(found)

        else:

            print(f"{stem} 파일을 찾을 수 없습니다.")
            print("chat 폴더 안의 txt 파일명을 입력해주세요.")
            print("분석에는 txt 파일이 필요합니다.")
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

    preview_title_width = get_setting("PreviewTitleWidth")

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
            preview_title_width
        )

        print(
            f"{idx:02d}. {publish_date} | "
            f"{title:<{preview_title_width}} | "
            f"{job['video_no']}"
        )

    print()
    print(f"총 대상 : {len(jobs)}개")
    print()
    print("=" * 36)
    print("채팅 수집을 시작하시겠습니까? (Y/N)")
    print("=" * 36)

    while True:

        answer = prompt_input("> ").strip().lower()

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


def show_analysis_preview(json_path, duration_sec):

    print()
    print("=" * 36)
    print("CHZZK VOD CHAT ANALYZER")
    print("=" * 36)
    print()

    while True:

        print("분석 시작 시간 입력")
        print("예시 : 00:00:00")
        print("(미입력 시 00:00:00)")
        start_value = prompt_input("> ").strip()

        if not start_value:
            start_sec = 0
        else:
            start_sec = parse_hms(start_value)

            if start_sec is None:
                print()
                print("잘못된 시간 형식입니다. HH:MM:SS 형식으로 입력해주세요.")
                print()
                continue

            if start_sec < 0:
                print()
                print("음수 시간은 입력할 수 없습니다.")
                print()
                continue

            if duration_sec is not None and start_sec > duration_sec:
                print()
                print("영상 길이를 초과하는 시간입니다.")
                print()
                continue

        while True:

            print()
            print("분석 종료 시간 입력")
            print("예시 : 00:00:00")
            print(
                f"(미입력 시 {format_time_seconds(duration_sec)})"
            )
            end_value = prompt_input("> ").strip()

            if not end_value:
                end_sec = duration_sec
            else:
                end_sec = parse_hms(end_value)

                if end_sec is None:
                    print()
                    print("잘못된 시간 형식입니다. HH:MM:SS 형식으로 입력해주세요.")
                    print()
                    continue

                if end_sec < 0:
                    print()
                    print("음수 시간은 입력할 수 없습니다.")
                    print()
                    continue

                if duration_sec is not None and end_sec > duration_sec:
                    print()
                    print("영상 길이를 초과하는 시간입니다.")
                    print()
                    continue

            if start_sec > end_sec:
                print()
                print("시작 시간이 종료 시간보다 늦습니다. 다시 입력해주세요.")
                print()
                break

            break

        if start_sec > end_sec:
            continue

        print()
        print("키워드를 입력해주세요.")
        print()
        print(
            f"Enter 입력 시 기본 키워드 "
            f"'{get_setting('DefaultKeyword')}'로 분석을 진행합니다."
        )
        print(
            "다른 키워드를 사용하려면 1~10자의 키워드를 입력해주세요."
        )
        print()

        keyword = prompt_input("> ").strip()

        if not keyword:
            keyword = get_setting("DefaultKeyword")

        if len(keyword) > 10:
            keyword = keyword[:10]

        print()
        print("=========================================")
        print("파일명")
        print(json_path.stem)
        print()
        print("분석 구간")
        print(
            f"{format_time_seconds(start_sec)} ~ {format_time_seconds(end_sec)}"
        )
        print()
        print("키워드")
        print(keyword)
        print()
        print("예상 분석 대상")
        print(
            format_approx_minutes(end_sec - start_sec)
        )
        print("=========================================")
        print("계속 진행하시겠습니까? (Y/N)")
        print("=" * 36)

        while True:

            answer = prompt_input("> ").strip().lower()

            if answer in ["y", "yes"]:
                return keyword, start_sec, end_sec

            if answer in ["n", "no"]:
                print()
                print("메인 메뉴로 돌아갑니다.")
                return None


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
            f"\r{progress:6.2f}%"
            f" | {len(all_chats):,}개"
            f" | "
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
        "\r100.00%"
        f" | {len(all_chats):,}개"
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
        / get_setting("OutputFolder")
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

    json_path.unlink()

    return txt_path, json_path


def load_chat_json(json_path):

    with open(
        json_path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def load_chat_txt(txt_path):

    chats = []

    with open(
        txt_path,
        "r",
        encoding="utf-8-sig"
    ) as f:

        for line in f:

            value = line.rstrip("\n")

            match = re.match(
                r"^\[(\d{2}:\d{2}:\d{2})\]\[[^\]]*\] (.*)$",
                value
            )

            if not match:
                continue

            seconds = parse_hms(
                match.group(1)
            )

            if seconds is None:
                continue

            content = match.group(2)

            if len(content) >= 2 and content[0] == '"' and content[-1] == '"':
                content = content[1:-1]

            chats.append({
                "playerMessageTime": seconds * 1000,
                "content": content
            })

    return chats


def validate_chat_json(chats):

    if not isinstance(chats, list):
        return "JSON 최상위 값이 채팅 목록(list)이 아닙니다."

    if not chats:
        return "채팅 데이터가 비어 있습니다."

    for idx, chat in enumerate(
        chats,
        start=1
    ):

        if not isinstance(chat, dict):
            return f"{idx}번째 채팅 데이터가 객체 형식이 아닙니다."

        if "playerMessageTime" not in chat:
            return f"{idx}번째 채팅에 playerMessageTime 값이 없습니다."

        if "content" not in chat:
            return f"{idx}번째 채팅에 content 값이 없습니다."

        if not isinstance(chat["playerMessageTime"], int):
            return f"{idx}번째 채팅의 playerMessageTime 값이 정수가 아닙니다."

        if not isinstance(chat["content"], str):
            return f"{idx}번째 채팅의 content 값이 문자열이 아닙니다."

    return None


def load_analysis_chats(txt_path):

    try:
        chats = load_chat_txt(txt_path)

    except (OSError, UnicodeError) as e:
        return None, f"파일을 읽을 수 없습니다: {e}"

    validation_error = validate_chat_json(chats)

    if validation_error:
        return None, validation_error

    return chats, None


def get_analysis_duration_sec(chat_path):

    video_no = (
        chat_path.stem
        .split("_")[-1]
    )

    try:

        info = get_video_info(
            video_no
        )

        return info["duration"]

    except:

        return None


def count_keyword_occurrences(content, keyword):
    if not keyword or not content:
        return 0

    max_keyword_repeat = get_setting("MaxKeywordRepeat")

    count = 0
    start = 0

    while True:
        idx = content.find(keyword, start)

        if idx < 0:
            break

        count += 1

        if max_keyword_repeat > 0 and count >= max_keyword_repeat:
            return max_keyword_repeat

        start = idx + len(keyword)

    return count


def analyze_chat(
    chats,
    keyword,
    start_sec=0,
    end_sec=None
):

    minute_data = defaultdict(
        lambda: {
            "chat": 0,
            "keyword": 0
        }
    )

    if end_sec is None:
        end_sec = get_chat_duration_sec(chats)

    start_ms = start_sec * 1000
    end_ms = end_sec * 1000

    for chat in chats:

        chat_time = chat["playerMessageTime"]

        if chat_time < start_ms:
            continue

        if chat_time >= end_ms:
            continue

        minute = (
            (chat_time - start_ms)
            // 60000
        )

        minute_data[minute]["chat"] += 1

        keyword_count = count_keyword_occurrences(
            chat["content"],
            keyword
        )

        if keyword_count:
            minute_data[minute][
                "keyword"
            ] += keyword_count

    results = []

    total_minutes = 0

    if end_sec is not None:
        total_minutes = (
            (end_sec - start_sec + 59)
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

    moving_average_minutes = get_setting("MovingAverageMinutes")

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
            max(0, idx - moving_average_minutes),
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


def build_top_lists(results, overall_average):

    top_count = get_setting("TopCount")
    top_minimum_chat_count = get_setting("TopMinimumChatCount")

    if top_minimum_chat_count <= 0:
        top_minimum_chat_count = overall_average

    ranked_results = [
        row
        for row in results
        if row["chat"] >= top_minimum_chat_count
    ]

    candidate_count = top_count * 3

    chat_top = sorted(
        ranked_results,
        key=lambda row: (
            -row["chat"],
            row["minute"]
        )
    )[:candidate_count]

    increase_top = sorted(
        ranked_results,
        key=lambda row: (
            -round_number(row["increase"]),
            row["minute"]
        )
    )[:candidate_count]

    keyword_count_top = sorted(
        ranked_results,
        key=lambda row: (
            -row["keyword"],
            row["minute"]
        )
    )[:candidate_count]

    keyword_rate_top = sorted(
        ranked_results,
        key=lambda row: (
            -row["keyword_rate"],
            -row["keyword"],
            row["minute"]
        )
    )[:candidate_count]

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
        f"키워드 {row['keyword']:>3,} | "
        f"비율 {row['keyword_rate']:>5.1f}% "
        f"{get_keyword_rate_marker(row['keyword_rate']):<3} | "
        f"증가 {format_increase(row['increase']):>8}"
    )


def format_detail_row(row):

    return (
        f"채팅 {row['chat']:>4,} | "
        f"키워드 {row['keyword']:>3,} | "
        f"비율 {row['keyword_rate']:>5.1f}% "
        f"{get_keyword_rate_marker(row['keyword_rate']):<3} | "
        f"증가 {format_increase(row['increase']):>8}"
    )


def format_time_range(start_minute, end_minute, start_sec=0):
    return (
        f"{minute_to_hms_offset(start_minute, start_sec)} "
        f"~ {minute_to_hms_offset(end_minute, start_sec)}"
    )


def build_merged_segments(rows):

    segments = []

    for row in sorted(rows, key=lambda item: item["minute"]):

        if not segments:
            segments.append({
                "start_minute": row["minute"],
                "end_minute": row["minute"],
                "rows": [row]
            })
            continue

        segment = segments[-1]

        if row["minute"] <= segment["end_minute"] + 1:
            segment["rows"].append(row)
            segment["end_minute"] = max(
                segment["end_minute"],
                row["minute"]
            )
            continue

        segments.append({
            "start_minute": row["minute"],
            "end_minute": row["minute"],
            "rows": [row]
        })

    return segments


def merge_ranked_rows(rows, max_items=10):
    selected_rows = []
    candidate_index = 0

    while len(selected_rows) < max_items and candidate_index < len(rows):
        selected_rows.append(
            rows[candidate_index]
        )
        candidate_index += 1

    segments = build_merged_segments(
        selected_rows
    )

    while len(segments) < max_items and candidate_index < len(rows):
        selected_rows.append(
            rows[candidate_index]
        )
        candidate_index += 1

        segments = build_merged_segments(
            selected_rows
        )

    if len(segments) > max_items:
        segments = segments[:max_items]

    return sorted(
        segments,
        key=lambda segment: segment["start_minute"]
    )


def build_analysis_text(
    file_stem,
    results,
    overall_average,
    keyword,
    start_sec,
    end_sec
):

    moving_average_minutes = get_setting("MovingAverageMinutes")
    top_count = get_setting("TopCount")
    save_detail_log = get_setting("SaveDetailLog")

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
        results,
        overall_average
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
    lines.append(f"최근 {moving_average_minutes}분")
    lines.append("")
    lines.append("분석 키워드")
    lines.append(keyword)
    lines.append("")
    lines.append("분석 구간")
    lines.append(
        f"{format_time_seconds(start_sec)} ~ {format_time_seconds(end_sec)}"
    )
    lines.append("")
    lines.append("=" * 36)
    lines.append(f"채팅량 TOP{top_count}")
    lines.append("=" * 36)
    lines.append("")

    append_top_section(lines, chat_top, start_sec)

    lines.append("=" * 36)
    lines.append(f"이동평균 증가율 TOP{top_count}")
    lines.append("=" * 36)
    lines.append("")

    append_top_section(lines, increase_top, start_sec)

    lines.append("=" * 36)
    lines.append(f"키워드 개수 TOP{top_count}")
    lines.append("=" * 36)
    lines.append("")

    append_top_section(lines, keyword_count_top, start_sec)

    lines.append("=" * 36)
    lines.append(f"키워드 비율 TOP{top_count}")
    lines.append("=" * 36)
    lines.append("")

    append_top_section(lines, keyword_rate_top, start_sec)

    if save_detail_log:

        lines.append("=" * 36)
        lines.append("상세로그")
        lines.append("=" * 36)
        lines.append("")

        for row in results:

            lines.append(
                f"[{minute_to_hms_offset(row['minute'], start_sec)}]"
            )
            lines.append(
                format_detail_row(row)
            )
            lines.append("")

    return "\n".join(lines)


def append_top_section(lines, rows, start_sec=0):

    segments = merge_ranked_rows(
        rows,
        get_setting("TopCount")
    )

    for idx, segment in enumerate(segments, start=1):

        if len(segment["rows"]) > 1:
            time_range = format_time_range(
                segment["start_minute"],
                segment["end_minute"],
                start_sec
            )

            lines.append(
                f"{idx}. [{time_range}]"
            )
            lines.append("")

            for row in sorted(segment["rows"], key=lambda item: item["minute"]):
                lines.append(
                    f"   [{minute_to_hms_offset(row['minute'], start_sec)}]"
                )
                lines.append(
                    format_detail_row(row)
                )
                lines.append("")

            continue

        row = segment["rows"][0]

        lines.append(
            f"{idx}. [{minute_to_hms_offset(row['minute'], start_sec)}]"
        )
        lines.append(
            format_top_row(row)
        )
        lines.append("")


def save_analysis_file(
    chat_path,
    text
):

    output_path = (
        chat_path.parent
        / f"{chat_path.stem}_analysis.txt"
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(text)

    return output_path


def process_analysis_job(
    chat_path,
    chats,
    keyword,
    start_sec,
    end_sec
):

    results = analyze_chat(
        chats,
        keyword,
        start_sec,
        end_sec
    )

    overall_average = (
        calculate_average(
            results
        )
    )

    text = build_analysis_text(
        chat_path.stem,
        results,
        overall_average,
        keyword,
        start_sec,
        end_sec
    )

    return save_analysis_file(
        chat_path,
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

    txt_path, _ = (
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
    print(
        f"총 채팅 : "
        f"{len(all_chats):,}개"
    )
    print()
    print("TXT:")
    print(txt_path)
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
        print("URL이 올바른지 확인한 뒤 다시 입력해주세요.")

        return True

    proceed = (
        show_job_preview(jobs)
    )

    if not proceed:

        print()
        print(
            "메인 메뉴로 돌아갑니다."
        )

        return True

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
            print("다음 VOD가 있으면 계속 진행합니다.")
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
        print("chat 폴더 안의 txt 파일명을 입력해주세요.")
        print("분석에는 txt 파일이 필요합니다.")

        return True

    chat_path = jobs[0]
    chats, load_error = load_analysis_chats(
        chat_path
    )

    if load_error:
        print()
        print(f"{chat_path.stem} 분석 파일을 읽을 수 없습니다.")
        print(load_error)
        print("채팅 수집으로 생성된 txt 파일인지 확인해주세요.")
        print()
        return True

    duration_sec = get_analysis_duration_sec(
        chat_path
    )

    if duration_sec is None:
        duration_sec = get_chat_duration_sec(
            chats
        )

    preview = show_analysis_preview(
        chat_path,
        duration_sec
    )

    if preview is None:
        return True

    keyword, start_sec, end_sec = preview

    try:

        output_path = process_analysis_job(
            chat_path,
            chats,
            keyword,
            start_sec,
            end_sec
        )

        print()
        print("분석 완료")
        print(chat_path.stem)
        print("결과:")
        print(output_path)

    except Exception as e:

        print()
        print(f"{chat_path.stem} 분석 실패")
        print(e)
        print("파일 내용 또는 분석 시간을 확인한 뒤 다시 시도해주세요.")
        print()

    return True


def main():

    global SETTINGS

    try:

        SETTINGS = initialize_settings()

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

            print()
            print("메인 메뉴로 돌아갑니다.")
            print()

    except EscapeInput:
        print()
        print("프로그램을 종료합니다.")


if __name__ == "__main__":
    main()
