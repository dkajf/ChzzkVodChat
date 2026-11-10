"""Integration checks against the user's local v1.3 examples, when present."""
from pathlib import Path
from dataclasses import replace
import unittest
import re
from cvc.storage import load_txt, save_lines, metadata_lines, chat_lines
from cvc.analysis import analyze, analysis_lines
from cvc.model import Selection
from cvc.settings import Settings


SAMPLES = Path(__file__).resolve().parent.parent / "멀럭킹"


@unittest.skipUnless(SAMPLES.is_dir(), "local v1.3 samples are not present")
class SampleTests(unittest.TestCase):
    def test_supplied_legacy_files(self):
        import tempfile
        for source in sorted(SAMPLES.glob("*.txt")):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d+", source.stem):
                continue
            with self.subTest(file=source.name), tempfile.TemporaryDirectory() as tmp:
                meta, chats = load_txt(source)
                expected = sum(line.startswith("[") for line in source.read_text(encoding="utf-8-sig").splitlines())
                self.assertEqual(len(chats), expected)
                settings = replace(Settings(), top_count=15, merge_limit=5)
                result = analyze(chats, meta, Selection(), settings)
                self.assertEqual(sum(row.chat for row in result.buckets), len(chats))
                saved = save_lines(tmp, "roundtrip", chat_lines(chats, meta, settings))
                loaded_meta, loaded = load_txt(saved)
                self.assertEqual(loaded, chats)
                self.assertEqual(loaded_meta, meta)
                lines = list(metadata_lines(meta, settings)) + list(analysis_lines(result, Selection(), settings))
                text = "\n".join(lines)
                self.assertIn("CHZZK VOD CHAT ANALYZER", text)
                self.assertIn("채팅량 TOP15", text)
                self.assertNotIn('"ms":', text)
                print(f"Sample {source.name}: {len(chats):,} chats, {len(result.buckets)} buckets")


if __name__ == "__main__":
    unittest.main()
