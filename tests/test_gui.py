"""Native Tk widget checks; run explicitly with CVC_GUI_TEST=1."""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import tkinter as tk
from cvc.gui import App, Inputs
from cvc.model import Metadata


@unittest.skipUnless(os.environ.get("CVC_GUI_TEST") == "1", "opt-in native GUI checks")
class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.root.withdraw()
        self.paths = patch("cvc.gui.settings_path", return_value=Path(self.temp.name) / "CVC_settings.json")
        self.paths.start()
        self.lookup = patch.object(App, "lookup", lambda app, token: None)
        self.lookup.start()
        self.app = App(self.root)

    def tearDown(self):
        self.app.shutdown.set()
        self.app.pool.shutdown(wait=True, cancel_futures=True)
        self.app.finish_close()
        self.paths.stop()
        self.lookup.stop()
        self.temp.cleanup()

    def ready(self, token, duration=60000):
        self.app.events.put((token, "metadata", (0, Metadata("123", duration_ms=duration), None)))
        self.app.poll()

    def test_independent_inputs_and_late_response(self):
        self.app.add_urls("https://chzzk.naver.com/video/123\nhttps://chzzk.naver.com/video/456")
        a, b = self.app.items
        self.ready(a)
        self.ready(b, 120000)
        ia = self.app.items[a]["inputs"]
        ib = self.app.items[b]["inputs"]
        ia.keyword.set("hello")
        ia.end.set("00:00:30")
        ia.set_duration(180000)
        self.assertEqual(ia.end.get(), "00:00:30")
        self.assertEqual(ib.end.get(), "00:02:00")
        self.assertEqual(ib.snapshot().end_ms, None)
        self.assertIn("00:02:00", ib.hint["text"])
        self.app.remove(a)
        self.app.add_urls("https://chzzk.naver.com/video/123")
        new_token = next(t for t in self.app.items if t != b)
        self.app.events.put((a, "metadata", (0, Metadata("123", title="OLD"), None)))
        self.app.poll()
        self.assertIsNone(self.app.items[new_token]["meta"])
        self.assertEqual(ib.keyword.get(), "ㅋ")

    def test_max_duplicates_outputs(self):
        self.app.add_urls("\n".join(f"https://chzzk.naver.com/video/{i}" for i in range(1, 12)))
        self.assertEqual(len(self.app.items), 10)
        self.assertEqual(str(self.app.url["state"]), "disabled")
        token = next(iter(self.app.items))
        self.ready(token)
        self.app.save_analysis.set(False)
        self.app.refresh()
        inputs = self.app.items[token]["inputs"]
        inputs.keyword.set("saved")
        self.assertEqual(str(inputs.entries[0]["state"]), "disabled")
        self.app.save_chat.set(False)
        self.app.refresh()
        self.assertEqual(str(self.app.run_button["state"]), "disabled")
        self.app.save_analysis.set(True)
        self.app.refresh()
        self.assertEqual(inputs.keyword.get(), "saved")
        self.assertEqual(str(inputs.entries[0]["state"]), "normal")
        self.app.remove(token)
        self.assertEqual(str(self.app.url["state"]), "normal")

    def test_snapshot_and_double_click(self):
        self.app.add_urls("https://chzzk.naver.com/video/123")
        token = next(iter(self.app.items))
        self.ready(token)
        with patch.object(self.app.pool, "submit") as submit:
            self.app.start_urls()
            self.app.start_urls()
            self.assertEqual(submit.call_count, 1)
            jobs = submit.call_args.args[1]
            self.app.items[token]["inputs"].keyword.set("changed")
            self.app.option_vars["top_count"].set("2")
            self.app.apply()
            self.assertEqual(jobs[0].selection.keyword, "ㅋ")
            self.assertEqual(jobs[0].settings.top_count, 10)
        self.app.busy = False

    def test_old_generation_ignored(self):
        self.app.add_urls("https://chzzk.naver.com/video/123")
        token = next(iter(self.app.items))
        self.app.items[token]["generation"] = 2
        self.app.events.put((token, "metadata", (1, Metadata("123", title="OLD"), None)))
        self.app.poll()
        self.assertIsNone(self.app.items[token]["meta"])

    def test_gui_responds_during_worker(self):
        finished = threading.Event()
        release = threading.Event()
        def work():
            release.wait(3)
            finished.set()
        self.app.pool.submit(work)
        self.root.after(10, release.set)
        self.root.after(25, self.root.quit)
        self.root.mainloop()
        self.assertTrue(release.is_set())
        self.assertTrue(finished.wait(1))

    def test_collect_only_ignores_invalid_analysis_inputs(self):
        self.app.add_urls("https://chzzk.naver.com/video/123")
        token = next(iter(self.app.items))
        self.ready(token)
        self.app.save_analysis.set(False)
        self.app.items[token]["inputs"].start.set("invalid")
        self.app.items[token]["inputs"].keyword.set("way too long keyword")
        with patch.object(self.app.pool, "submit") as submit:
            self.app.start_urls()
            self.assertEqual(submit.call_count, 1)
            self.assertFalse(submit.call_args.args[1][0].settings.save_analysis)
        self.app.busy = False

    def test_multiple_txt_independent_inputs_and_deleted_response(self):
        a = Path(self.temp.name) / "a.txt"
        b = Path(self.temp.name) / "b.txt"
        with patch.object(self.app.pool, "submit"):
            self.app.add_txt(a)
            self.app.add_txt(b)
            self.app.add_txt(a)
        self.assertEqual(len(self.app.txt_items), 2)
        one, two = self.app.txt_items
        self.app.events.put((one, "txt", (Metadata(), (), None)))
        self.app.events.put((two, "txt", (Metadata(), (), None)))
        self.app.poll()
        self.app.txt_items[one]["inputs"].keyword.set("hello")
        self.app.txt_items[two]["inputs"].keyword.set("bye")
        self.assertEqual(self.app.txt_items[one]["inputs"].hint["text"], "빈칸=채팅 데이터 끝까지")
        with patch.object(self.app.pool, "submit") as submit:
            self.app.start_txt()
            jobs = submit.call_args.args[1]
            self.assertEqual([job.selection.keyword for job in jobs], ["hello", "bye"])
            self.app.busy = False
            self.app.remove_txt(one)
            self.app.add_txt(a)
        replacement = next(t for t in self.app.txt_items if t != two)
        self.app.events.put((one, "txt", (Metadata(title="OLD"), (), None)))
        self.app.poll()
        self.assertIsNone(self.app.txt_items[replacement]["meta"])
        self.assertEqual(self.app.txt_items[two]["inputs"].keyword.get(), "bye")

    def test_options_apply_persists_and_cancel_discards_edits(self):
        from cvc.settings import load_settings
        self.app.option_vars["top_count"].set("7")
        self.assertTrue(self.app.apply())
        self.assertEqual(load_settings(self.app.path)[0].top_count, 7)
        self.app.option_vars["top_count"].set("99")
        self.app.reset_editor()
        self.assertEqual(self.app.option_vars["top_count"].get(), "7")

    def test_date_placeholder_and_wheel(self):
        self.assertEqual(self.app.url.get(), "")
        self.assertIn("Enter", self.app.url_instruction["text"])
        original_card = self.app.add_row
        self.app.add_urls("\n".join(f"https://chzzk.naver.com/video/{i}" for i in range(1, 10)))
        for token in self.app.items:
            self.app.events.put((token, "metadata", (0, Metadata("1", date="2026-10-31", duration_ms=60000), None)))
        self.app.poll()
        self.root.deiconify()
        self.root.update()
        token = next(iter(self.app.items))
        self.assertEqual(self.app.items[token]["frame"], original_card)
        self.assertNotEqual(self.app.add_row, original_card)
        self.assertIn("2026-10-31", self.app.items[token]["label"]["text"])
        canvas = self.app.collect_list.canvas
        before = canvas.yview()
        self.app.items[token]["inputs"].entries[0].event_generate("<MouseWheel>", delta=-120)
        self.root.update()
        self.assertGreater(canvas.yview()[0], before[0])

    def test_completed_url_skips_until_inputs_change(self):
        from cvc.jobs import Job
        from cvc.completion import record_completion
        from dataclasses import replace
        self.app.add_urls("https://chzzk.naver.com/video/123")
        token = next(iter(self.app.items))
        self.ready(token)
        self.app.settings = replace(self.app.settings, output_dir=self.temp.name)
        item = self.app.items[token]
        job = Job(token, item["meta"], item["inputs"].snapshot(), self.app.settings)
        chat = Path(self.temp.name) / "chat.txt"
        report = Path(self.temp.name) / "analysis.txt"
        chat.touch()
        report.touch()
        record_completion(job, [chat, report])
        with patch.object(self.app.pool, "submit") as submit:
            self.app.start_urls()
            submit.assert_not_called()
            item["inputs"].keyword.set("different")
            self.app.start_urls()
            self.assertEqual(submit.call_count, 1)
        self.app.busy = False

    def test_tooltips_are_source_specific_and_options_have_help(self):
        vod = Inputs(self.root)
        vod.set_duration(60000)
        self.assertIn("HHMMSS / MMSS", vod.tips[0].text)
        self.assertIn("빈칸=영상 종료 시간", vod.tips[1].text)
        self.assertNotIn("TXT", vod.tips[1].text)
        txt = Inputs(self.root)
        txt.set_duration(None, True)
        self.assertIn("빈칸=채팅 데이터 끝까지", txt.tips[1].text)
        self.assertEqual(set(self.app.option_vars), set(self.app.option_help))
        vod.destroy()
        txt.destroy()

    def test_requested_url_defaults_and_scroll_limits(self):
        from types import SimpleNamespace
        self.assertFalse(self.app.add_button.bind("<Enter>"))
        self.assertFalse(self.app.add_button.bind("<FocusIn>"))
        self.app.add_urls("https://chzzk.naver.com/video/123")
        token = next(iter(self.app.items))
        self.ready(token, 120000)
        inputs = self.app.items[token]["inputs"]
        self.assertEqual(inputs.end.get(), "00:02:00")
        self.assertIsNone(inputs.snapshot().end_ms)
        inputs.set_duration(180000)
        self.assertEqual(inputs.end.get(), "00:03:00")
        inputs.end.set("00:00:30")
        inputs.set_duration(240000)
        self.assertEqual(inputs.end.get(), "00:00:30")
        self.assertEqual(inputs.snapshot().end_ms, 30000)
        self.root.deiconify()
        self.app.notebook.select(2)
        self.root.update()
        area = next(widget for widget in self.app.notebook.nametowidget(self.app.notebook.tabs()[2]).winfo_children() if hasattr(widget, "canvas"))
        for _ in range(200):
            area.wheel(SimpleNamespace(delta=-120))
            self.root.update()
        self.root.update()
        self.assertLessEqual(area.canvas.yview()[1], 1.00001)
        self.assertAlmostEqual(area.canvas.yview()[1], 1, places=2, msg=(area.canvas.bbox("all"), area.canvas.winfo_height(), area.canvas["scrollregion"]))
        for _ in range(200):
            area.wheel(SimpleNamespace(delta=120))
            self.root.update()
        self.assertAlmostEqual(area.canvas.yview()[0], 0, places=3)


if __name__ == "__main__":
    unittest.main()
