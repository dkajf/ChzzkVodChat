from dataclasses import replace
import json
import os
from pathlib import Path
import re
import tempfile
from .model import Chat, Metadata, hms, parse_time


def safe_name(value):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value).rstrip(". ")[:120] or "Unknown"
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        name = "_" + name
    return name


def broadcast_fields(meta):
    return (("채널", meta.channel), ("제목", meta.title), ("VOD ID", meta.vod_id or "미확인"),
            ("VOD URL", meta.url), ("방송 날짜", meta.broadcast_date), ("VOD 게시 날짜", meta.date),
            ("방송 시작", meta.start or "미확인"), ("방송 종료", meta.end or "미확인"),
            ("전체 방송 길이", hms(meta.duration_ms) if meta.duration_ms is not None else "미확인"))


def metadata_lines(meta, settings):
    yield "[방송 정보]"
    for key, value in broadcast_fields(meta):
        yield f"{key}: {str(value).replace(chr(10), ' ').replace(chr(13), ' ')}"
    yield "시간 표시: " + ("HH:MM:SS:00" if settings.premiere else "HH:MM:SS")
    yield ""


def chat_lines(chats, meta, settings):
    yield from metadata_lines(meta, settings)
    yield "[채팅 데이터]"
    for chat in chats:
        actual = chat.actual or "미확인"
        clock = f"[실제 시각: {actual}]" if settings.actual_time else ""
        timestamp = hms(chat.ms, settings.premiere)
        nickname = json.dumps(chat.nickname, ensure_ascii=False)[1:-1].replace("]", r"\u005d")
        yield f"[{timestamp}]{clock}[{nickname}] " + json.dumps(chat.text, ensure_ascii=False)


def load_txt(path, check=lambda: None):
    meta = Metadata()
    chats = []
    modern = False
    readable = False
    header = False
    pending = None
    with Path(path).open(encoding="utf-8-sig") as f:
        for number, line in enumerate(f, 1):
            if number % 1024 == 0:
                check()
            value = line.rstrip("\r\n")
            if pending is not None:
                ms, nickname, parts = pending
                if value.endswith('"'):
                    parts.append(value[:-1])
                    chats.append(Chat(ms, "\n".join(parts), nickname))
                    pending = None
                else:
                    parts.append(value)
                continue
            if value == "[방송 정보]" and not modern and not readable:
                header = True
                continue
            if value.startswith("# CVC2 ") and not modern:
                raw = json.loads(value[7:])
                meta = Metadata(**{k: v for k, v in raw.items() if k in Metadata.__dataclass_fields__})
                if meta.duration_ms is not None and (type(meta.duration_ms) is not int or meta.duration_ms < 0):
                    raise ValueError("잘못된 영상 길이 메타데이터")
                continue
            if value == "[채팅 데이터 CVC2]":
                modern = True
                header = False
                continue
            if value == "[채팅 데이터]":
                readable = True
                header = False
                continue
            if header and ": " in value:
                key, text = value.split(": ", 1)
                mapping = {"채널": "channel", "제목": "title", "VOD ID": "vod_id", "방송 날짜": "date", "VOD 게시 날짜": "date", "방송 시작": "start", "방송 종료": "end"}
                if key in mapping:
                    data = text if text != "미확인" else (None if key in ("방송 시작", "방송 종료") else ("" if key == "VOD ID" else text))
                    meta = replace(meta, **{mapping[key]: data})
                elif key == "전체 방송 길이" and text != "미확인":
                    meta = replace(meta, duration_ms=parse_time(text))
                continue
            if header:
                continue
            if modern:
                match = re.match(r'^\[\d{2,}:\d{2}:\d{2}(?::00)?\](?:\[실제 시각: [^\]]*\])?(\{.*\})$', value)
                if not match:
                    if value:
                        raise ValueError(f"{number}행: 손상된 채팅 행")
                    continue
                raw = json.loads(match[1])
                chat = Chat(**raw)
                if type(chat.ms) is not int or chat.ms < 0 or not isinstance(chat.text, str):
                    raise ValueError(f"{number}행: 잘못된 채팅 데이터")
                chats.append(chat)
            elif readable:
                match = re.fullmatch(r'\[(\d{2,}:\d{2}:\d{2})(?:\.(\d{3}))?(?::00)?\](?:\[실제 시각: ([^\]]*)\])?\[([^\]]*)\] (".*")', value)
                if not match:
                    if value:
                        raise ValueError(f"{number}행: 손상된 채팅 행")
                    continue
                ms = parse_time(match[1]) + int(match[2] or 0)
                nickname = json.loads('"' + match[4] + '"')
                actual = match[3] if match[3] != "미확인" else None
                chats.append(Chat(ms, json.loads(match[5]), nickname, actual))
            else:
                match = re.match(r'^\[(\d{2,}:\d{2}:\d{2}(?::00)?)\]\[(.*?)\] "(.*)$', value)
                if match:
                    timestamp = match[1]
                    if timestamp.count(":") == 3:
                        timestamp = timestamp[:-3]
                    if match[3].endswith('"'):
                        chats.append(Chat(parse_time(timestamp), match[3][:-1], match[2]))
                    else:
                        pending = (parse_time(timestamp), match[2], [match[3]])
    if pending is not None:
        raise ValueError("TXT 끝에 닫히지 않은 채팅 문자열이 있습니다")
    if not modern and not readable and not chats:
        raise ValueError("분석 가능한 채팅 TXT가 아닙니다")
    if not meta.vod_id:
        match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})_(\d+)(?: \(\d+\))?", Path(path).stem)
        if match:
            meta = replace(meta, vod_id=match[2], date=match[1], channel=Path(path).parent.name)
    return meta, chats


def save_lines(folder, stem, lines, check=lambda: None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=folder, suffix=".partial")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            for n, line in enumerate(lines):
                if n % 256 == 0:
                    check()
                f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        check()
        # Windows rename refuses replacement; other platforms use an atomic link.
        for index in range(100000):
            target = folder / (safe_name(stem) + (f" ({index})" if index else "") + ".txt")
            try:
                if os.name == "nt":
                    os.rename(temp, target)
                else:
                    os.link(temp, target)
                return target
            except FileExistsError:
                continue
        raise OSError("사용 가능한 파일 이름을 찾을 수 없습니다")
    finally:
        Path(temp).unlink(missing_ok=True)
