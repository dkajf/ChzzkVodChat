from dataclasses import replace
from pathlib import Path
import shutil
import json
import tempfile
import threading
import unittest
from unittest.mock import patch

from cvc.settings import Settings, save_settings, load_settings, settings_path, persist_settings
from cvc.jobs import Job, run_jobs
from cvc.model import Metadata, Selection, Chat


class PortableTests(unittest.TestCase):
    def test_moved_distribution_ignores_existing_old_folder_and_locator(self):
        for keep_old in (True, False):
            with self.subTest(keep_old=keep_old), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                old, new = root / "old", root / "new"
                old.mkdir()
                save_settings(old / "CVC_settings.json", replace(Settings(), output_dir=str(old), top_count=17))
                raw = json.loads((old / "CVC_settings.json").read_text(encoding="utf-8"))
                raw["output_dir"] = str(old)
                (old / "CVC_settings.json").write_text(json.dumps(raw), encoding="utf-8")
                (old / "settings_location.json").write_text('{"path": "' + str(old / "CVC_settings.json").replace('\\', '\\\\') + '"}', encoding="utf-8")
                shutil.copytree(old, new)
                if not keep_old:
                    shutil.rmtree(old)
                with patch("cvc.settings.executable_dir", return_value=new):
                    self.assertEqual(settings_path(), new / "CVC_settings.json")
                    settings, _ = load_settings(settings_path())
                    self.assertEqual(settings.top_count, 17)
                    self.assertEqual(Path(settings.output_dir), new)
                    target = persist_settings(settings)
                    self.assertEqual(target, new / "CVC_settings.json")
                    class Fake:
                        def collect(self, *args):
                            return [Chat(0, "ㅋ")]
                        def close(self):
                            pass
                    events = []
                    run_jobs([Job("x", Metadata("123", "channel", duration_ms=60000), Selection(), settings)], threading.Event(), lambda *e: events.append(e), Fake)
                    self.assertTrue(any(e[1] == "완료" for e in events))
                    self.assertEqual(len(list((new / "channel").glob("*.txt"))), 2)
                    self.assertTrue((new / ".cvc_completed").is_dir())
                    self.assertFalse((old / "channel").exists())
