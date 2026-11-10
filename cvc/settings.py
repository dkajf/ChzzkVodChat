from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
import tempfile
import uuid


@dataclass(frozen=True)
class Settings:
    schema_version: int = 2
    output_dir: str = str(Path.home() / "Documents" / "ChzzkVodChat")
    save_chat: bool = True
    save_analysis: bool = True
    actual_time: bool = False
    premiere: bool = False
    default_keyword: str = "ㅋ"
    interval: int = 1
    top_count: int = 10
    moving_minutes: int = 15
    minimum: int = 0
    repeat: int = 5
    merge_limit: int = 3
    detail: bool = True

    def validate(self, analysis=True):
        if not isinstance(self.output_dir, str) or not self.output_dir.strip():
            raise ValueError("저장 위치를 입력하세요")
        if not analysis:
            return
        for key, low, high in (("interval", 1, 10), ("top_count", 1, None),
                               ("moving_minutes", 1, None), ("minimum", 0, None),
                               ("repeat", 0, None), ("merge_limit", 0, None)):
            n = getattr(self, key)
            if type(n) is not int or n < low or (high is not None and n > high):
                raise ValueError(f"{key}: {low} 이상" + (f" {high} 이하 정수" if high else " 정수"))
        if self.moving_minutes % self.interval:
            raise ValueError(f"이동평균은 분석 단위의 배수여야 합니다 (예: {self.interval}, {self.interval * 2}분)")
        if not 1 <= len(self.default_keyword) <= 10:
            raise ValueError("기본 키워드는 1~10자입니다")


def settings_path():
    return Path(os.environ.get("APPDATA", str(Path.home() / ".config"))) / "ChzzkVodChat" / "CVC_settings.json"


def save_settings(path, settings):
    settings.validate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def load_settings(path, legacy_dir=None):
    path = Path(path)
    notices = []
    raw = {}
    recovered = False
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(raw, dict):
                raise ValueError("설정은 객체여야 합니다")
        except (ValueError, OSError) as e:
            backup = path.with_name(path.name + "." + uuid.uuid4().hex + ".bak")
            try:
                backup.write_bytes(path.read_bytes())
            except OSError as backup_error:
                return Settings(), [f"설정 읽기/백업 실패: {e}; {backup_error}"]
            notices.append(f"설정 손상 복구, 원본 백업: {backup}")
            recovered = True
    elif legacy_dir:
        candidates = sorted(Path(legacy_dir).glob("CVC_setting_v*.txt"))
        if candidates:
            mapping = dict(OutputFolder="output_dir", DefaultKeyword="default_keyword", MaxKeywordRepeat="repeat",
                           TopMinimumChatCount="minimum", MovingAverageMinutes="moving_minutes", TopCount="top_count",
                           TopMergeLimit="merge_limit", SaveDetailLog="detail")
            for line in candidates[-1].read_text(encoding="utf-8-sig").splitlines():
                if "=" not in line or line.lstrip().startswith(("#", ";")):
                    continue
                key, value = (s.strip() for s in line.split("=", 1))
                if key not in mapping:
                    notices.append(f"이관하지 않은 구버전 항목: {key}")
                    continue
                target = mapping[key]
                if target == "detail":
                    value = value.lower() in ("true", "1")
                elif target not in ("output_dir", "default_keyword"):
                    try:
                        value = int(value)
                    except ValueError:
                        pass
                elif target == "output_dir":
                    value = str((Path(legacy_dir) / value).resolve())
                raw[target] = value
            notices.append(f"구버전 설정 이관, 원본 보존: {candidates[-1]}")
    defaults = asdict(Settings())
    values = defaults.copy()
    for field in fields(Settings):
        key = field.name
        if key == "schema_version" or key not in raw:
            continue
        value = raw[key]
        if type(value) is not type(defaults[key]):
            notices.append(f"{key}: 잘못된 자료형, 기본값 복원")
            continue
        trial = values | {key: value}
        # Cross-field divisibility is checked after individual values are restored.
        try:
            check = trial | {"moving_minutes": trial["interval"]}
            if key == "moving_minutes":
                check = trial | {"interval": 1}
            Settings(**check).validate()
            values[key] = value
        except ValueError as e:
            notices.append(f"{key}: {e}, 기본값 복원")
    result = Settings(**values)
    try:
        result.validate()
    except ValueError as e:
        notices.append(str(e) + "; 옵션에서 수정 후 적용하세요")
    if not path.exists() or recovered:
        try:
            save_settings(path, result)
        except (OSError, ValueError) as e:
            notices.append(f"설정 저장 실패: {e}")
    return result, notices
