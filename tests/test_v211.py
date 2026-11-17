from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cvc.model import Metadata
from cvc.storage import metadata_lines, chat_lines, save_lines, load_txt
from cvc.settings import Settings, persist_settings, settings_path, load_settings


class V211Tests(unittest.TestCase):
    def test_compact_header_and_url_identity(self):
        meta = Metadata("15944884", "멀럭킹", "제목", 40078000,
                        "2026-10-30 18:02:05 (KST)", "2026-10-31 05:10:03 (KST, 계산값)")
        lines = list(metadata_lines(meta, Settings()))
        self.assertEqual(len([line for line in lines if ': ' in line]), 6)
        self.assertIn("방송 시작: 2026-10-30 18:02:05", lines)
        self.assertNotIn("KST", "\n".join(lines))
        with tempfile.TemporaryDirectory() as tmp:
            path = save_lines(tmp, "compact", chat_lines([], meta, Settings()))
            loaded, _ = load_txt(path)
            self.assertEqual(loaded.vod_id, meta.vod_id)

    def test_output_override_cannot_change_settings_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("cvc.settings.legacy_settings_path", return_value=root / "appdata" / "CVC_settings.json"), patch("cvc.settings.executable_dir", return_value=root / "exe"):
                original = replace(Settings(), output_dir=str(root / "first"), top_count=17)
                old = persist_settings(original)
                updated = replace(original, output_dir=str(root / "second"), repeat=2)
                new = persist_settings(updated)
                self.assertTrue(old.exists())
                self.assertEqual(old, new)
                self.assertEqual(load_settings(new)[0], replace(updated, output_dir=str(root / "exe")))
                self.assertEqual(settings_path(), new)
                self.assertFalse((root / "exe" / "settings_location.json").exists())
                self.assertFalse((root / "appdata").exists())
