from dataclasses import dataclass
from pathlib import Path
from .api import Api, Cancelled
from .analysis import analyze, analysis_lines
from .storage import chat_lines, save_lines, safe_name, load_txt
from .model import Metadata, Selection
from .settings import Settings
from .completion import completed, record_completion


@dataclass(frozen=True)
class Job:
    token: str
    metadata: Metadata
    selection: Selection
    settings: Settings
    source: Path | None = None
    data: tuple | None = None


def run_jobs(jobs, cancel, emit, api_factory=Api):
    def check():
        if cancel.is_set():
            raise Cancelled()
    for job in jobs:
        paths = []
        stage = "대기"
        try:
            check()
            if completed(job):
                emit(job.token, "건너뜀", "같은 시간·키워드의 결과 파일이 이미 완료되어 있습니다")
                continue
            settings, meta = job.settings, job.metadata
            if job.source:
                stage = "TXT 읽기"
                emit(job.token, stage, None)
                if job.data is not None:
                    chats = job.data
                else:
                    meta, chats = load_txt(job.source, check)
            else:
                stage = "수집"
                emit(job.token, stage, None)
                api = api_factory()
                try:
                    chats = api.collect(meta, cancel, lambda count, cursor, duration: emit(job.token, "수집", (count, cursor, duration)))
                finally:
                    api.close()
            check()
            folder = Path(settings.output_dir) / safe_name(meta.channel)
            stem = f"{safe_name(meta.date)}_{safe_name(meta.vod_id or (job.source.stem if job.source else 'Unknown'))}"
            if not job.source and settings.save_chat:
                stage = "수집 TXT 저장"
                emit(job.token, stage, None)
                paths.append(save_lines(folder, stem, chat_lines(chats, meta, settings), check))
                emit(job.token, "파일", paths[-1])
            if job.source or settings.save_analysis:
                stage = "분석"
                emit(job.token, stage, None)
                result = analyze(chats, meta, job.selection, settings, check)
                stage = "분석 TXT 저장"
                emit(job.token, stage, None)
                def lines():
                    yield from analysis_lines(result, job.selection, settings, stem, meta)
                paths.append(save_lines(folder, stem + "_analysis", lines(), check))
                emit(job.token, "파일", paths[-1])
                emit(job.token, "결과", result)
            try:
                record_completion(job, paths)
            except OSError as e:
                emit(job.token, "안내", f"결과는 저장했지만 완료 기록 저장에 실패했습니다: {e}")
            emit(job.token, "완료", paths)
        except Cancelled:
            emit(job.token, "취소", paths)
        except Exception as e:
            emit(job.token, "실패", f"{stage}: {e}" + (" (완료한 수집 TXT 유지)" if paths else ""))
    emit("", "종료", None)
