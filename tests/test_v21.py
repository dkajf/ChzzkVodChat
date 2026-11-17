import json
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from cvc.api import Api, donation_fields
from cvc.model import Chat, Metadata, Selection
from cvc.analysis import analyze
from cvc.settings import Settings, persist_settings, settings_path, load_settings
from cvc.storage import chat_lines, save_lines, load_txt


class V21Tests(unittest.TestCase):
    def test_donation_parsing_and_txt_analysis(self):
        rows = [
            {"messageTypeCode": 1, "extras": "{}"},
            {"messageTypeCode": 10, "extras": json.dumps({"payAmount": 10000})},
            {"messageTypeCode": 10, "extras": "{}"},
            {"messageTypeCode": 10, "extras": "broken"},
            {"messageTypeCode": 10, "extras": {"payAmount": 0}},
        ]
        fields = [donation_fields(row) for row in rows]
        self.assertEqual(fields, [(False, None), (True, 10000), (True, None), (True, None), (True, None)])
        chats = [Chat(i * 1000, 'ㅋ "hello"', '닉]네임', donation=d, amount=a) for i, (d, a) in enumerate(fields)]
        chats.append(Chat(5000, '[후원] "본문"'))
        meta = Metadata("123", duration_ms=60000)
        with tempfile.TemporaryDirectory() as tmp:
            lines = list(chat_lines(chats, meta, Settings()))
            self.assertIn('[00:00:01] [닉\\u005d네임] [후원 10,000원]', lines[-5])
            path = save_lines(tmp, "new", lines)
            loaded_meta, loaded = load_txt(path)
            self.assertEqual(loaded, chats)
            self.assertEqual(analyze(loaded, loaded_meta, Selection(keyword="10,000"), Settings()).buckets[0].keyword, 0)

    def test_settings_locator_and_previous_settings_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "appdata" / "CVC_settings.json"
            local = root / "exe"
            local.mkdir()
            with patch("cvc.settings.legacy_settings_path", return_value=legacy), patch("cvc.settings.executable_dir", return_value=local):
                self.assertEqual(settings_path(), local / "CVC_settings.json")
                settings = replace(Settings(), output_dir=str(root / "output"), top_count=7)
                target = persist_settings(settings)
                self.assertEqual(target.parent, local)
                self.assertEqual(settings_path(), target)
                self.assertEqual(load_settings(target)[0], replace(settings, output_dir=str(local)))
                self.assertFalse((root / "output").exists())

    def test_live_open_date_timezones_and_invalid(self):
        class Fake(Api):
            def __init__(self, value):
                self.value = value
            def get(self, *args, **kwargs):
                return dict(liveOpenDate=self.value, duration=3600)
        meta = Fake("2026-11-10T18:30:00+00:00").metadata("123", threading.Event())
        self.assertEqual(meta.start, "2026-11-11 03:30:00 (KST)")
        self.assertIsNone(Fake("bad").metadata("123", threading.Event()).start)
