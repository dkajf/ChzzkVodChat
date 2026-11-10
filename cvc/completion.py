"""Small receipts for successfully published URL results."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import tempfile
import re
from .model import hms
from .storage import safe_name


def receipt_path(job):
    key = hashlib.sha256(job.metadata.vod_id.encode("utf-8")).hexdigest()
    return Path(job.settings.output_dir) / ".cvc_completed" / (key + ".json")


def completed(job):
    if job.source is not None:
        return False
    try:
        data = json.loads(receipt_path(job).read_text(encoding="utf-8"))
        if data.get("selection") != asdict(job.selection):
            return False
        for wanted, kind in ((job.settings.save_chat, "chat"), (job.settings.save_analysis, "analysis")):
            if wanted:
                value = data.get("files", {}).get(kind)
                if not value or not Path(value).is_file():
                    return False
        return True
    except (OSError, ValueError, TypeError, AttributeError):
        return infer_existing_completion(job)


def infer_existing_completion(job):
    """Migrate older readable results only when the request can be identified."""
    folder = Path(job.settings.output_dir) / safe_name(job.metadata.channel)
    stem = safe_name(f"{job.metadata.date}_{job.metadata.vod_id}")
    try:
        files = list(folder.glob(stem + "*.txt"))
        chats = [p for p in files if re.fullmatch(re.escape(stem) + r"(?: \(\d+\))?\.txt", p.name)]
        reports = [p for p in files if re.fullmatch(re.escape(stem) + r"_analysis(?: \(\d+\))?\.txt", p.name)]
        chats.sort(key=lambda p: p.stat().st_mtime_ns, reverse=True)
        reports.sort(key=lambda p: p.stat().st_mtime_ns, reverse=True)
        if job.settings.save_chat and not chats:
            return False
        paths = [chats[0]] if job.settings.save_chat else []
        if job.settings.save_analysis:
            if not reports:
                return False
            with reports[0].open(encoding="utf-8-sig") as stream:
                lines = []
                for _ in range(160):
                    line = stream.readline(10000)
                    if not line:
                        break
                    lines.append(line.strip())
            if "CHZZK VOD CHAT ANALYZER" not in lines:
                return False
            values = {line: lines[index + 1] for index, line in enumerate(lines[:-1])}
            if values.get("분석 키워드") != job.selection.keyword:
                return False
            expected_end = job.selection.end_ms if job.selection.end_ms is not None else job.metadata.duration_ms
            if expected_end is None:
                return False
            actual = values.get("분석 구간", "")
            match = re.fullmatch(r"(\d{2,}:\d{2}:\d{2})(?::00)? ~ (\d{2,}:\d{2}:\d{2})(?::00)?", actual)
            if not match or (match[1], match[2]) != (hms(job.selection.start_ms), hms(expected_end)):
                return False
            boundary = "자동 영상 끝점 포함" if job.selection.end_ms is None else "종료 제외"
            if values.get("종료 경계") != boundary:
                return False
            paths.append(reports[0])
        else:
            # Collection-only jobs have no active range/keyword and always collect
            # the full VOD. Confirm a known collection marker before migration.
            with chats[0].open(encoding="utf-8-sig") as stream:
                if not any(stream.readline(10000).strip() in ("[채팅 데이터]", "[채팅 데이터 CVC2]") for _ in range(32)):
                    return False
        try:
            record_completion(job, paths)
        except OSError:
            pass
        return True
    except (OSError, ValueError, TypeError):
        return False


def record_completion(job, paths):
    if job.source is not None:
        return
    files = {}
    remaining = iter(paths)
    if job.settings.save_chat:
        files["chat"] = str(next(remaining).resolve())
    if job.settings.save_analysis:
        files["analysis"] = str(next(remaining).resolve())
    data = {"schema_version": 1, "selection": asdict(job.selection), "files": files}
    path = receipt_path(job)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
