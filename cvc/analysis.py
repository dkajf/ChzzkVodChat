from dataclasses import dataclass
from .model import hms


@dataclass(slots=True)
class Bucket:
    index: int
    start: int
    end: int
    included_start: int
    included_end: int
    chat: int = 0
    keyword: int = 0
    matching: int = 0
    average: float = 0
    increase: float | None = None

    @property
    def rate(self):
        return self.matching / self.chat * 100 if self.chat else 0


@dataclass
class Analysis:
    buckets: list
    start: int
    end: int
    data_range: bool
    cutoff: float
    tops: dict


def merged(rows, count, limit):
    def segments(selected):
        out = []
        for rank, row in sorted(selected, key=lambda x: x[1].index):
            if out and row.index == out[-1][-1][1].index + 1 and (not limit or len(out[-1]) < limit):
                out[-1].append((rank, row))
            else:
                out.append([(rank, row)])
        return sorted(out, key=lambda group: min(rank for rank, _ in group))
    candidates = list(enumerate(rows[:count * 3]))
    selected = candidates[:count]
    groups = segments(selected)
    for candidate in candidates[count:]:
        if len(groups) >= count:
            break
        selected.append(candidate)
        groups = segments(selected)
    return [[row for _, row in group] for group in groups[:count]]


def analyze(chats, metadata, selected, settings, check=lambda: None):
    settings.validate()
    width = settings.interval * 60000
    start = selected.start_ms
    automatic = selected.end_ms is None
    end = metadata.duration_ms if automatic else selected.end_ms
    data_range = end is None
    if end is None:
        if not chats:
            raise ValueError("채팅과 영상 길이가 없어 분석 범위를 산출할 수 없습니다")
        end = (max(c.ms for c in chats) // width + 1) * width
    if start < 0 or start >= end or (metadata.duration_ms is not None and end > metadata.duration_ms):
        raise ValueError("분석 범위가 잘못되었거나 영상 길이를 초과합니다")
    first, last = start // width, (end - 1) // width
    rows = []
    for i in range(first, last + 1):
        check()
        rows.append(Bucket(i, i * width, (i + 1) * width, max(start, i * width), min(end, (i + 1) * width)))
    for n, chat in enumerate(chats):
        if n % 1024 == 0:
            check()
        endpoint = automatic and metadata.duration_ms is not None and chat.ms == end
        if chat.ms < start or (chat.ms >= end and not endpoint):
            continue
        row = rows[min(chat.ms // width, last) - first]
        row.chat += 1
        hits = chat.text.count(selected.keyword)
        if settings.repeat:
            hits = min(hits, settings.repeat)
        row.keyword += hits
        row.matching += bool(hits)
    total = sum(r.chat for r in rows)
    cutoff = settings.minimum or total / len(rows)
    window = settings.moving_minutes // settings.interval
    rolling = 0
    for i, row in enumerate(rows):
        check()
        row.average = rolling / min(i, window) if i else 0
        row.increase = (row.chat - row.average) / row.average * 100 if row.average else None
        rolling += row.chat
        if i >= window:
            rolling -= rows[i - window].chat
    eligible = [r for r in rows if r.chat >= cutoff and r.chat > 0]
    rankings = {
        "채팅량 TOP": sorted(eligible, key=lambda r: (-r.chat, r.index)),
        "이동평균 대비 증가율 TOP": sorted((r for r in eligible if r.increase is not None), key=lambda r: (-r.increase, r.index)),
        "키워드 개수 TOP": sorted((r for r in eligible if r.keyword), key=lambda r: (-r.keyword, r.index)),
        "키워드 포함 채팅 비율 TOP": sorted((r for r in eligible if r.keyword), key=lambda r: (-r.rate, -r.keyword, r.index)),
    }
    tops = {}
    for name, ranked in rankings.items():
        check()
        tops[name] = merged(ranked, settings.top_count, settings.merge_limit)
    return Analysis(rows, start, end, data_range, cutoff, tops)


def analysis_lines(result, selected, settings, filename=None, metadata=None):
    fmt = lambda ms: hms(ms, settings.premiere)
    divider = "=" * 36
    total = sum(row.chat for row in result.buckets)
    yield divider
    yield "CHZZK VOD CHAT ANALYZER"
    yield divider
    yield ""
    def section(name, pairs):
        yield divider
        yield name
        yield divider
        yield ""
        for label, value in pairs:
            yield label
            yield str(value).replace("\r", " ").replace("\n", " ")
            yield ""

    if metadata is not None:
        from .storage import broadcast_fields
        yield from section("방송 정보", broadcast_fields(metadata))
    summary = []
    if filename:
        summary.append(("파일명", filename))
    summary.extend((
        ("총 채팅", f"{total:,}"),
        (f"전체 평균 채팅 ({settings.interval}분당)", f"{total / len(result.buckets):,.2f}"),
        ("분석 키워드", selected.keyword),
        ("분석 구간", f"{fmt(result.start)} ~ {fmt(result.end)}"),
        ("범위 근거", "채팅 데이터 기준 범위" if result.data_range else "영상 길이 / 지정 범위"),
        ("종료 경계", "자동 영상 끝점 포함" if selected.end_ms is None and not result.data_range else "종료 제외"),
    ))
    yield from section("분석 정보", summary)
    yield from section("적용 옵션", (
        ("분석 구간 단위", f"{settings.interval}분"),
        ("이동평균 기준", f"이전 {settings.moving_minutes}분 ({settings.moving_minutes // settings.interval}구간, 현재 제외)"),
        ("TOP 개수", settings.top_count),
        ("최소 채팅 컷", f"{result.cutoff:,.4f}"),
        ("키워드 반복 제한", str(settings.repeat) if settings.repeat else "무제한"),
        ("최대 병합", f"{settings.merge_limit}구간 ({settings.merge_limit * settings.interval}분)" if settings.merge_limit else "무제한"),
        ("상세 로그", "저장" if settings.detail else "저장 안 함"),
        ("시간 표시", "HH:MM:SS:00" if settings.premiere else "HH:MM:SS"),
    ))

    def marker(value, thresholds):
        return "▲" * sum(value >= threshold for threshold in thresholds) or "-"

    def detail(row):
        increase = "N/A" if row.increase is None else f"{row.increase:+.0f}%"
        arrows = "-" if row.increase is None else marker(row.increase, (30, 60, 100))
        return (f"채팅 {row.chat:>5,} | 키워드 {row.keyword:>5,} | 비율 {row.rate:>5.1f}% {marker(row.rate, (10, 20, 30)):<3}"
                f" | 증가 {increase:>6} {arrows:<3}")

    def row_lines(row, indent=""):
        yield f"{indent}[{fmt(row.start)}]"
        if row.start != row.included_start or row.end != row.included_end:
            yield f"   부분 구간: {fmt(row.included_start)} ~ {fmt(row.included_end)}"
        yield detail(row)

    for name, groups in result.tops.items():
        yield divider
        yield name.replace(" TOP", f" TOP{settings.top_count}")
        yield divider
        yield ""
        if not groups:
            yield "대상 없음"
            yield ""
        for rank, group in enumerate(groups, 1):
            if len(group) == 1:
                row = group[0]
                partial = row.start != row.included_start or row.end != row.included_end
                label = f"{fmt(row.included_start)} ~ {fmt(row.included_end)}" if partial else fmt(row.start)
                yield f"{rank}. [{label}]" + (" (부분 구간)" if partial else "")
                yield detail(row)
                yield ""
            else:
                yield f"{rank}. [{fmt(group[0].included_start)} ~ {fmt(group[-1].included_end)}]"
                yield ""
                for row in group:
                    yield from row_lines(row, "   ")
                    yield ""
    if settings.detail:
        yield divider
        yield "상세 로그"
        yield divider
        yield ""
        for row in result.buckets:
            yield from row_lines(row)
            yield ""
