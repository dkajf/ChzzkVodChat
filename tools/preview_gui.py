"""Launch a local UI preview with offline sample data for layout inspection."""
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cvc.gui import App
from cvc.model import Metadata


def main():
    with tempfile.TemporaryDirectory() as temp, patch("cvc.gui.settings_path", return_value=Path(temp) / "CVC_settings.json"), patch.object(App, "lookup", lambda app, token: None):
        root = tk.Tk()
        app = App(root)
        if "--empty" not in sys.argv:
            app.add_urls("\n".join(f"https://chzzk.naver.com/video/{vod}" for vod in (15944884, 15928266, 15911763)))
        for token, item in app.items.items():
            meta = Metadata(item["vod"], "멀럭킹", "방송 제목 예시 · 기존 채팅 수집 및 분석", 40078000,
                            start="2026-10-30 18:02:05 (KST)", date="2026-10-31")
            app.events.put((token, "metadata", (0, meta, None)))
        samples = Path(__file__).resolve().parent.parent / "멀럭킹"
        for path in sorted(samples.glob("*.txt")):
            if "--empty" not in sys.argv and path.stem[:4].isdigit() and not path.stem.endswith("_analysis"):
                app.add_txt(path)
        if "--txt" in sys.argv:
            app.notebook.select(1)
        elif "--options" in sys.argv:
            app.notebook.select(2)
        root.mainloop()


if __name__ == "__main__":
    main()
