import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import requests
from dataclasses import replace
from cvc.model import Chat, Metadata, Selection, parse_time, video_id, selection
from cvc.settings import Settings, load_settings, save_settings
from cvc.analysis import analyze, merged
from cvc.storage import chat_lines, load_txt, save_lines, safe_name
from cvc.jobs import Job, run_jobs
from cvc.api import Api, Cancelled


class CoreTests(unittest.TestCase):
    def test_input(self):
        self.assertEqual(parse_time("2222"), 1342000)
        self.assertEqual(parse_time("012345"), 5025000)
        self.assertEqual(parse_time("100:00:00"), 360000000)
        for value in ("123", "-01:00:00", "00:60:00", "00:00:00:00"):
            with self.assertRaises(ValueError):
                parse_time(value)
        self.assertEqual(video_id(" https://chzzk.naver.com/video/123?t=2 "), "123")
        for value in ("https://evil.com/video/123", "https://chzzk.naver.com/live/123"):
            with self.assertRaises(ValueError):
                video_id(value)
        with self.assertRaises(ValueError):
            selection("", "", "", False, 10000)

    def test_boundaries_all_intervals(self):
        for interval in range(1, 11):
            settings = replace(Settings(), interval=interval, moving_minutes=interval * 3)
            width = interval * 60000
            chats = [Chat(width - 1, "ㅋ"), Chat(width, "ㅋㅋ"), Chat(width * 2, "x")]
            result = analyze(chats, Metadata(duration_ms=width * 3), Selection(), settings)
            self.assertEqual([r.chat for r in result.buckets], [1, 1, 1])
            self.assertEqual(result.buckets[1].keyword, 2)
            self.assertEqual(result.buckets[1].rate, 100)
            self.assertIsNone(result.buckets[0].increase)

    def test_partial_range(self):
        chats = [Chat(609999, "ㅋ"), Chat(610000, "ㅋ"), Chat(769999, "ㅋ"), Chat(770000, "ㅋ")]
        selected = Selection(610000, 770000)
        result = analyze(chats, Metadata(), selected, replace(Settings(), interval=5))
        self.assertEqual(len(result.buckets), 1)
        row = result.buckets[0]
        self.assertEqual((row.start, row.included_start, row.included_end, row.chat), (600000, 610000, 770000, 2))
        result = analyze(chats, Metadata(), selected, Settings())
        self.assertEqual([r.start for r in result.buckets], [600000, 660000, 720000])
        self.assertEqual([r.chat for r in result.buckets], [1, 0, 1])

    def test_auto_endpoint_and_unknown(self):
        chats = [Chat(60000, "ㅋ")]
        result = analyze(chats, Metadata(duration_ms=60000), Selection(), Settings())
        self.assertEqual([r.chat for r in result.buckets], [1])
        result = analyze(chats, Metadata(duration_ms=60000), Selection(end_ms=60000), Settings())
        self.assertEqual([r.chat for r in result.buckets], [0])
        result = analyze(chats, Metadata(), Selection(), Settings())
        self.assertEqual(result.end, 120000)
        self.assertTrue(result.data_range)
        with self.assertRaises(ValueError):
            analyze([], Metadata(), Selection(), Settings())
        with self.assertRaises(ValueError):
            analyze([], Metadata(duration_ms=60000), Selection(60000, 60000), Settings())

    def test_statistics(self):
        chats = [Chat(0, "ㅋㅋㅋㅋㅋㅋ"), Chat(1000, "none"), Chat(120000, "ㅋ")]
        result = analyze(chats, Metadata(duration_ms=180000), Selection(), replace(Settings(), moving_minutes=2))
        self.assertEqual(result.cutoff, 1)
        self.assertEqual(result.buckets[0].keyword, 5)
        self.assertEqual(result.buckets[0].rate, 50)
        self.assertEqual(result.buckets[2].average, 1)
        self.assertEqual(result.buckets[2].increase, 0)
        self.assertEqual(result.buckets[1].chat, 0)
        with self.assertRaises(ValueError):
            replace(Settings(), interval=2, moving_minutes=15).validate()

    def test_merge_limits_and_replenishment(self):
        result = analyze([Chat(i * 60000, "ㅋ") for i in range(20)], Metadata(duration_ms=1200000), Selection(), Settings())
        rows = result.buckets
        for limit in (0, 1, 3):
            groups = merged(rows, 4, limit)
            self.assertLessEqual(len(groups), 4)
            self.assertTrue(all(not limit or len(g) <= limit for g in groups))
            self.assertTrue(all(all(b.index == a.index + 1 for a, b in zip(g, g[1:])) for g in groups))
        self.assertEqual(len(merged(rows, 4, 3)), 4)
        self.assertEqual(len(merged(rows, 4, 0)), 1)

    def test_txt_roundtrip_four_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            chats = [Chat(59999, '안녕 😀 [x]: "ㅋ"\n다음 행', '닉] "[', "2026-11-11 00:00:00 KST"), Chat(60000, "ㅋ")]
            meta = Metadata("123", "채널", "제목", 120000)
            expected = analyze(chats, meta, Selection(), Settings())
            for actual in (False, True):
                for premiere in (False, True):
                    settings = replace(Settings(), actual_time=actual, premiere=premiere)
                    path = save_lines(tmp, "chat", chat_lines(chats, meta, settings))
                    loaded_meta, loaded = load_txt(path)
                    self.assertEqual(loaded_meta, meta)
                    expected_chats = [replace(c, ms=c.ms // 1000 * 1000, actual=c.actual if actual else None) for c in chats]
                    self.assertEqual(loaded, expected_chats)
                    result = analyze(loaded, loaded_meta, Selection(), settings)
                    self.assertEqual(result.buckets, expected.buckets)
            legacy = save_lines(tmp, "legacy", ['[00:00:10][닉] "안녕 [00:00:00]: ㅋ"', '[00:01:00][Unknown] "😀"'])
            meta, loaded = load_txt(legacy)
            self.assertIsNone(meta.duration_ms)
            self.assertEqual(len(loaded), 2)

    def test_atomic_save_and_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = save_lines(tmp, "chat", ["original"])
            b = save_lines(tmp, "chat", ["second"])
            self.assertNotEqual(a, b)
            self.assertEqual(a.read_text(encoding="utf-8"), "original\n")
            def stop():
                raise Cancelled()
            with self.assertRaises(Cancelled):
                save_lines(tmp, "cancel", ["x"], stop)
            self.assertFalse(list(Path(tmp).glob("*.partial")))
            self.assertFalse(list(Path(tmp).glob("cancel*")))
        self.assertEqual(safe_name("CON"), "_CON")

    def test_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CVC_settings.json"
            original = replace(Settings(), top_count=7)
            save_settings(path, original)
            self.assertEqual(load_settings(path)[0], original)
            path.write_text(json.dumps({"top_count": 8, "repeat": -5, "detail": "False", "schema_version": 99}), encoding="utf-8")
            settings, notices = load_settings(path)
            self.assertEqual(settings.top_count, 8)
            self.assertEqual(settings.repeat, 5)
            self.assertTrue(settings.detail)
            self.assertTrue(notices)
            path.write_text("broken", encoding="utf-8")
            settings, notices = load_settings(path)
            self.assertEqual(settings, Settings())
            self.assertTrue(list(Path(tmp).glob("*.bak")))

    def test_legacy_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CVC_settings.json"
            legacy = Path(tmp) / "CVC_setting_v1.3.txt"
            legacy.write_text("Version=1.3\nTopCount=8\nSaveDetailLog=False\nDefaultKeyword=hi\nSaveJson=True", encoding="utf-8")
            settings, notices = load_settings(path, tmp)
            self.assertEqual(settings.top_count, 8)
            self.assertFalse(settings.detail)
            self.assertEqual(settings.default_keyword, "hi")
            self.assertTrue(legacy.exists())
            self.assertTrue(any("SaveJson" in n for n in notices))

    def test_collection_overlap_same_time(self):
        def row(ms, text, user="u"):
            return dict(playerMessageTime=ms, content=text, userIdHash=user, profile="invalid")
        class Fake(Api):
            def __init__(self):
                self.calls = 0
            def get(self, path, cancel, params=None):
                self.calls += 1
                cursor = params["playerMessageTime"]
                if cursor == 10000:
                    return {"previousVideoChats": [row(9000, "last"), row(5000, "same"), row(5000, "same"), row(5000, "different")]}
                if cursor == 5000:
                    return {"previousVideoChats": [row(5000, "same"), row(5000, "same"), row(5000, "different"), row(0, "first")]}
                if cursor == 0:
                    return {"previousVideoChats": [row(0, "first")]}
                return {"previousVideoChats": []}
        fake = Fake()
        chats = fake.collect(Metadata("123", duration_ms=10000), threading.Event(), lambda *a: None)
        self.assertEqual(len(chats), 5)
        self.assertEqual([c.ms for c in chats], [0, 5000, 5000, 5000, 9000])
        self.assertTrue(all(c.nickname == "Unknown" for c in chats))

    def test_pipeline_modes_and_partial_failure(self):
        class Fake:
            def collect(self, meta, cancel, progress):
                return [Chat(0, "ㅋ"), Chat(59999, "ㅋㅋ")]
            def close(self):
                pass
        with tempfile.TemporaryDirectory() as tmp:
            meta = Metadata("123", duration_ms=60000)
            for chat, analysis in ((True, False), (False, True), (True, True)):
                folder = Path(tmp) / f"{chat}_{analysis}"
                settings = replace(Settings(), output_dir=str(folder), save_chat=chat, save_analysis=analysis)
                events = []
                run_jobs([Job("x", meta, Selection(), settings)], threading.Event(), lambda *e: events.append(e), Fake)
                self.assertEqual(len(list(folder.rglob("*.txt"))), int(chat) + int(analysis))
                self.assertIn("완료", [e[1] for e in events])
            settings = replace(Settings(), output_dir=str(Path(tmp) / "failure"))
            events = []
            jobs = [Job("bad", meta, Selection(60000, 60000), settings), Job("ok", meta, Selection(), settings)]
            run_jobs(jobs, threading.Event(), lambda *e: events.append(e), Fake)
            self.assertTrue(any(e[0] == "bad" and e[1] == "실패" for e in events))
            self.assertTrue(any(e[0] == "ok" and e[1] == "완료" for e in events))
            self.assertEqual(len(list((Path(tmp) / "failure").rglob("*.txt"))), 3)

    def test_retries_are_bounded(self):
        class Session:
            headers = {}
            calls = 0
            def get(self, *a, **kw):
                self.calls += 1
                raise requests.Timeout("test timeout")
            def close(self):
                pass
        class NoWait:
            def is_set(self):
                return False
            def wait(self, seconds):
                return False
        session = Session()
        api = Api(session)
        with self.assertRaisesRegex(RuntimeError, "timeout"):
            api.get("/test", NoWait())
        self.assertEqual(session.calls, 3)

    def test_saturated_page_is_failure(self):
        class Capped(Api):
            def __init__(self):
                pass
            def get(self, path, cancel, params=None):
                return {"previousVideoChats": [dict(playerMessageTime=1000, content=str(i), userIdHash=str(i)) for i in range(50)]}
        with self.assertRaisesRegex(RuntimeError, "완전성"):
            Capped().collect(Metadata("123", duration_ms=1000), threading.Event(), lambda *a: None)

    def test_server_identity_deduplicates(self):
        class Fake(Api):
            def __init__(self):
                pass
            def get(self, path, cancel, params=None):
                cursor = params["playerMessageTime"]
                if cursor < 0:
                    return {"previousVideoChats": []}
                row = dict(playerMessageTime=0, content="ㅋ", messageId="id", userIdHash="u")
                return {"previousVideoChats": [row, row]}
        chats = Fake().collect(Metadata("123", duration_ms=1000), threading.Event(), lambda *a: None)
        self.assertEqual(len(chats), 1)

    def test_cancel_pipeline_never_starts_collection(self):
        cancel = threading.Event()
        cancel.set()
        events = []
        with patch("cvc.jobs.Api") as factory:
            jobs = [Job(str(i), Metadata(str(i), duration_ms=1000), Selection(), Settings()) for i in range(3)]
            run_jobs(jobs, cancel, lambda *e: events.append(e), factory)
            factory.assert_not_called()
        self.assertEqual(sum(e[1] == "취소" for e in events), 3)

    def test_txt_cached_analysis_does_not_read_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = replace(Settings(), output_dir=tmp, save_chat=False, save_analysis=False)
            source = Path(tmp) / "no-longer-exists.txt"
            job = Job("TXT", Metadata(duration_ms=60000), Selection(), settings, source, (Chat(1000, "ㅋ"),))
            events = []
            with patch("cvc.jobs.load_txt", side_effect=AssertionError("unexpected read")):
                run_jobs([job], threading.Event(), lambda *e: events.append(e))
            self.assertTrue(any(e[1] == "완료" for e in events))
            self.assertEqual(len(list(Path(tmp).rglob("*_analysis.txt"))), 1)

    def test_old_writer_to_new_reader(self):
        import main as legacy
        with tempfile.TemporaryDirectory() as tmp:
            rows = [dict(playerMessageTime=10000, content='문장 ] "x" 😀', profile=json.dumps({"nickname": "닉]네임"})),
                    dict(playerMessageTime=60000, content="ㅋ", profile="bad")]
            with patch.object(legacy, "get_output_base_dir", return_value=Path(tmp)), patch.object(legacy, "get_setting", return_value=False):
                path = legacy.save_chat_files(rows, "채널", "2026-11-10", "123")
            meta, chats = load_txt(path)
            self.assertEqual([c.text for c in chats], [r["content"] for r in rows])
            self.assertEqual(chats[0].nickname, "닉]네임")
            self.assertEqual(chats[1].nickname, "Unknown")

    def test_analysis_cancellation(self):
        def stop():
            raise Cancelled()
        with self.assertRaises(Cancelled):
            analyze([Chat(0, "ㅋ")], Metadata(duration_ms=60000), Selection(), Settings(), stop)

    def test_previous_v2_json_rows_remain_readable(self):
        from dataclasses import asdict
        with tempfile.TemporaryDirectory() as tmp:
            meta = Metadata("123", "channel", "title", 60000)
            chat = Chat(59999, 'hello [x] "ㅋ"', "nick")
            path = save_lines(tmp, "old-v2", ["[방송 정보]", "# CVC2 " + json.dumps(asdict(meta)),
                              "[채팅 데이터 CVC2]", "[00:00:59]" + json.dumps(asdict(chat))])
            self.assertEqual(load_txt(path), (meta, [chat]))

    def test_legacy_multiline_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = save_lines(tmp, "legacy-multiline", ['[00:00:01][nick] "line1', '[방송 정보]', 'line3"', '[00:00:02][nick] "normal"'])
            _, chats = load_txt(path)
            self.assertEqual(len(chats), 2)
            self.assertEqual(chats[0].text, 'line1\n[방송 정보]\nline3')

    def test_metadata_start_and_calculated_end(self):
        class Fake(Api):
            def __init__(self, data):
                self.data = data
            def get(self, *args, **kwargs):
                return self.data
        data = dict(liveOpenDate="2026-10-30 18:02:05", publishDate="2026-10-31 05:22:26", duration=40078)
        meta = Fake(data).metadata("15944884", threading.Event())
        self.assertEqual(meta.start, "2026-10-30 18:02:05 (KST)")
        self.assertEqual(meta.broadcast_date, "2026-10-30")
        self.assertEqual(meta.date, "2026-10-31")
        self.assertIn("2026-10-31 05:10:03", meta.end)
        self.assertIn("계산값", meta.end)
        data.pop("liveOpenDate")
        unknown = Fake(data).metadata("123", threading.Event())
        self.assertIsNone(unknown.start)
        self.assertIsNone(unknown.end)

    def test_completion_skip_persists_and_changes_allow_rerun(self):
        from cvc.completion import completed
        class Fake:
            calls = 0
            def collect(self, meta, cancel, progress):
                Fake.calls += 1
                return [Chat(1000, "ㅋ")]
            def close(self):
                pass
        with tempfile.TemporaryDirectory() as tmp:
            settings = replace(Settings(), output_dir=tmp)
            job = Job("x", Metadata("123", duration_ms=60000), Selection(), settings)
            events = []
            run_jobs([job], threading.Event(), lambda *event: events.append(event), Fake)
            self.assertTrue(completed(job))
            run_jobs([job], threading.Event(), lambda *event: events.append(event), Fake)
            self.assertEqual(Fake.calls, 1)
            self.assertIn("건너뜀", [e[1] for e in events])
            self.assertTrue(completed(replace(job, settings=replace(settings, top_count=3))))
            changed = replace(job, selection=Selection(keyword="hi"))
            self.assertFalse(completed(changed))
            run_jobs([changed], threading.Event(), lambda *event: events.append(event), Fake)
            self.assertEqual(Fake.calls, 2)
            self.assertTrue(completed(changed))
            latest = next(e[2] for e in reversed(events) if e[1] == "완료")
            latest[-1].unlink()
            self.assertFalse(completed(changed))

    def test_report_sections_and_whole_second_chat_output(self):
        from cvc.analysis import analysis_lines
        meta = Metadata("123", duration_ms=60000, start="2026-11-10 12:00:00 (KST)")
        chats = [Chat(59999, "last"), Chat(59999, "same time")]
        lines = list(chat_lines(chats, meta, Settings()))
        self.assertTrue(lines[-2].startswith('[00:00:59]'))
        self.assertTrue(lines[-1].startswith('[00:00:59]'))
        premiere = list(chat_lines(chats, meta, replace(Settings(), premiere=True)))
        self.assertTrue(premiere[-1].startswith('[00:00:59:00]'))
        result = analyze(chats, meta, Selection(), Settings())
        text = "\n".join(analysis_lines(result, Selection(), Settings(), "file", meta))
        headings = [text.index(name) for name in ("CHZZK VOD CHAT ANALYZER", "방송 정보", "분석 정보", "적용 옵션", "채팅량 TOP")]
        self.assertEqual(headings, sorted(headings))

    def test_existing_result_migrates_completion_record(self):
        from cvc.completion import completed, receipt_path
        from cvc.analysis import analysis_lines
        with tempfile.TemporaryDirectory() as tmp:
            meta = Metadata("123", "channel", duration_ms=60000, date="2026-11-10")
            settings = replace(Settings(), output_dir=tmp)
            job = Job("x", meta, Selection(), settings)
            folder = Path(tmp) / "channel"
            chats = [Chat(1000, "ㅋ")]
            save_lines(folder, "2026-11-10_123", chat_lines(chats, meta, settings))
            result = analyze(chats, meta, Selection(), settings)
            save_lines(folder, "2026-11-10_123_analysis", analysis_lines(result, Selection(), settings, "file", meta))
            self.assertFalse(receipt_path(job).exists())
            self.assertTrue(completed(job))
            self.assertTrue(receipt_path(job).exists())
            self.assertFalse(completed(replace(job, selection=Selection(keyword="different"))))


if __name__ == "__main__":
    unittest.main()
