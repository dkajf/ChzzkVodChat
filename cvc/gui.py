from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
from pathlib import Path
from queue import Queue, Empty
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import uuid
from .api import Api
from .model import hms, video_id, selection, Metadata
from .settings import Settings, load_settings, save_settings, settings_path
from .storage import load_txt
from .jobs import Job, run_jobs
from .completion import completed


class Tip:
    def __init__(self, widget, text):
        self.window = None
        self.widget, self.text = widget, text
        for event in ("<Enter>", "<FocusIn>"):
            widget.bind(event, self.show, add=True)
        for event in ("<Leave>", "<FocusOut>", "<Destroy>"):
            widget.bind(event, self.hide, add=True)

    def show(self, event=None):
        if self.window:
            return
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.geometry(f"+{self.widget.winfo_rootx()}+{self.widget.winfo_rooty() + self.widget.winfo_height() + 3}")
        ttk.Label(self.window, text=self.text, padding=6, wraplength=420, relief="solid").pack()

    def hide(self, event=None):
        if self.window:
            self.window.destroy()
            self.window = None


class ScrollList(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, confine=True, yscrollincrement=1)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas)
        window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        def resize(event):
            self.canvas.itemconfigure(window, width=event.width)
            self.update_region()
        self.canvas.bind("<Configure>", resize)
        self.body.bind("<Configure>", lambda e: self.update_region())

    def update_region(self):
        height = max(self.body.winfo_height(), self.canvas.winfo_height(), 1)
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), height))
        maximum = max(0, 1 - self.canvas.winfo_height() / height)
        self.canvas.yview_moveto(min(maximum, max(0, self.canvas.yview()[0])))

    def wheel(self, event):
        self.update_region()
        if self.body.winfo_height() > self.canvas.winfo_height():
            delta = -1 if getattr(event, "num", None) == 4 else 1
            if getattr(event, "delta", 0):
                delta = -int(event.delta / 120) or (-1 if event.delta > 0 else 1)
            height = self.body.winfo_height()
            maximum = max(0, 1 - self.canvas.winfo_height() / height)
            target = self.canvas.yview()[0] + delta * 40 / height
            self.canvas.yview_moveto(min(maximum, max(0, target)))
        return "break"


class Inputs(ttk.Frame):
    def __init__(self, parent, keyword="ㅋ"):
        super().__init__(parent)
        self.start = tk.StringVar(value="00:00:00")
        self.end = tk.StringVar()
        self.keyword = tk.StringVar(value=keyword)
        self.duration = None
        self._end_edited = False
        self._setting_end = False
        self._autofilled_end = False
        self.end.trace_add("write", self.end_changed)
        self.entries = []
        self.tips = []
        for i, (label, var, tip) in enumerate((
            ("시작 시간", self.start, "HH:MM:SS / HHMMSS / MMSS, 빈칸=00:00:00"),
            ("종료 시간", self.end, "HH:MM:SS / HHMMSS / MMSS, 시작 시간보다 크게 설정, 빈칸=영상 종료 시간"),
            ("키워드", self.keyword, "최대 10자. 빈칸=ㅋ. 공백·특수문자 사용 가능"))):
            ttk.Label(self, text=label).grid(row=0, column=i, sticky="w")
            entry = ttk.Entry(self, textvariable=var, width=18)
            entry.grid(row=1, column=i, sticky="ew", padx=(0, 8))
            self.tips.append(Tip(entry, tip))
            self.entries.append(entry)
            self.columnconfigure(i, weight=1)
        self.hint = ttk.Label(self, text="영상 끝: 미확인")
        self.hint.grid(row=2, column=1, sticky="w")
        ttk.Label(self, text="빈칸=00:00:00").grid(row=2, column=0, sticky="w")
        ttk.Label(self, text="빈칸=ㅋ · 최대 10자").grid(row=2, column=2, sticky="w")
        self.error = ttk.Label(self, foreground="#b3261e", wraplength=680)
        self.error.grid(row=3, column=0, columnspan=4, sticky="w")

    def end_changed(self, *args):
        if not self._setting_end:
            self._end_edited = True

    def set_duration(self, duration, txt=False):
        self.duration = duration
        if not txt and not self._end_edited:
            self._setting_end = True
            try:
                self.end.set(hms(duration) if duration is not None else "")
                self._autofilled_end = duration is not None
            finally:
                self._setting_end = False
        self.hint.configure(text=("빈칸=영상 끝 " + hms(duration)) if duration is not None else ("빈칸=채팅 데이터 끝까지" if txt else "빈칸=영상 끝 (길이 미확인)"))
        self.tips[1].text = "HH:MM:SS / HHMMSS / MMSS, 시작 시간보다 크게 설정, 빈칸=" + ("채팅 데이터 끝까지" if txt and duration is None else "영상 종료 시간")

    def enable(self, enabled):
        for widget in self.entries:
            widget.configure(state="normal" if enabled else "disabled")

    def snapshot(self):
        try:
            automatic = not self.end.get().strip() or (self._autofilled_end and not self._end_edited)
            result = selection(self.start.get(), self.end.get(), self.keyword.get(), automatic, self.duration)
            self.error.configure(text="")
            return result
        except ValueError as e:
            self.error.configure(text=str(e))
            raise


class App:
    def __init__(self, root):
        self.root = root
        self.events = Queue()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cvc")
        self.cancel = threading.Event()
        self.shutdown = threading.Event()
        self.busy = False
        self.closing = False
        self.items = {}
        self.files = []
        self.txt_items = {}
        self.path = settings_path()
        self.settings, notices = load_settings(self.path, Path(__file__).resolve().parent.parent)
        root.title("ChzzkVodChat v2.0")
        root.geometry("980x820")
        root.minsize(780, 640)
        icon = Path(__file__).resolve().parent.parent / "chzzk_blue_icon.ico"
        try:
            root.iconbitmap(str(icon))
        except tk.TclError:
            pass
        notebook = ttk.Notebook(root)
        self.notebook = notebook
        notebook.pack(fill="both", expand=True, padx=12, pady=12)
        collect, txt, options = (ttk.Frame(notebook, padding=10) for _ in range(3))
        for frame, name in ((collect, "수집·분석"), (txt, "채팅 분석"), (options, "옵션")):
            notebook.add(frame, text=name)
        self.build_collect(collect)
        self.build_txt(txt)
        self.build_options(options)
        progress = ttk.Frame(root, padding=(12, 0, 12, 12))
        progress.pack(fill="x")
        self.status = tk.StringVar(value="대기")
        ttk.Label(progress, textvariable=self.status, wraplength=900).pack(anchor="w")
        self.bar = ttk.Progressbar(progress, mode="indeterminate")
        self.bar.pack(fill="x", pady=4)
        self.log = tk.Text(progress, height=6, state="disabled", wrap="word")
        self.log.pack(fill="x")
        self.root.bind("<MouseWheel>", self.on_wheel, add=True)
        self.root.bind("<Button-4>", self.on_wheel, add=True)
        self.root.bind("<Button-5>", self.on_wheel, add=True)
        self.refresh()
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.poll_id = root.after(80, self.poll)
        for notice in notices:
            self.log_line(notice)

    def build_collect(self, parent):
        self.count = ttk.Label(parent, text="0/10")
        self.count.pack(anchor="e")
        area = ScrollList(parent)
        area.pack(fill="both", expand=True)
        self.collect_list = area
        self.rows = area.body
        self.build_url_card()
        self.notice = ttk.Label(parent, foreground="#b3261e", wraplength=860)
        self.notice.pack(fill="x")
        bottom = ttk.Frame(parent)
        bottom.pack(fill="x", pady=(8, 0))
        self.save_chat = tk.BooleanVar(value=self.settings.save_chat)
        self.save_analysis = tk.BooleanVar(value=self.settings.save_analysis)
        ttk.Checkbutton(bottom, text="채팅 수집 TXT 저장", variable=self.save_chat, command=self.refresh).pack(side="left")
        ttk.Checkbutton(bottom, text="채팅 분석 TXT 저장", variable=self.save_analysis, command=self.refresh).pack(side="left", padx=8)
        self.run_button = ttk.Button(bottom, text="실행", command=self.start_urls)
        self.run_button.pack(side="right")
        ttk.Button(bottom, text="저장 폴더 열기", command=self.open_folder).pack(side="right", padx=8)

    def build_url_card(self):
        self.add_row = ttk.Frame(self.rows, padding=12, relief="solid", borderwidth=1)
        self.add_row.pack(fill="x", pady=(0, 10), padx=2)
        self.url_instruction = ttk.Label(self.add_row, text="URL 입력 후 Enter로 등록")
        self.url_instruction.pack(anchor="w", pady=(0, 6))
        controls = ttk.Frame(self.add_row)
        controls.pack(fill="x")
        self.url = ttk.Entry(controls)
        self.url.pack(side="left", fill="x", expand=True)
        self.url.bind("<Return>", lambda e: self.add_urls())
        self.url.bind("<<Paste>>", self.paste_urls)
        self.add_button = ttk.Button(controls, text="+", width=4, command=self.add_urls)
        self.add_button.pack(side="left", padx=(6, 0))

    def on_wheel(self, event):
        widget = event.widget
        while widget:
            if isinstance(widget, ScrollList):
                return widget.wheel(event)
            widget = getattr(widget, "master", None)

    def paste_urls(self, event):
        try:
            value = self.root.clipboard_get()
        except tk.TclError:
            return
        if "\n" in value or "\r" in value:
            self.add_urls(value)
            return "break"

    def add_urls(self, value=None):
        value = self.url.get() if value is None else value
        errors = []
        for url in value.splitlines():
            if not url.strip():
                continue
            try:
                vod = video_id(url)
                if any(item["vod"] == vod for item in self.items.values()):
                    raise ValueError(f"중복 VOD: {vod}")
                if len(self.items) >= 10:
                    raise ValueError("최대 10개입니다")
                self.add_item(vod)
            except ValueError as e:
                errors.append(str(e))
        if not value.strip():
            errors.append("URL을 입력하세요")
        self.url.delete(0, "end")
        self.notice.configure(text=" / ".join(errors))
        self.refresh(preserve_notice=True)

    def add_item(self, vod):
        token = uuid.uuid4().hex
        frame = self.add_row
        for widget in frame.winfo_children():
            widget.destroy()
        first = ttk.Frame(frame)
        first.pack(fill="x")
        ttk.Button(first, text="−", width=3, command=lambda: self.remove(token)).pack(side="left")
        ttk.Label(first, text=f"https://chzzk.naver.com/video/{vod}").pack(side="left", padx=6)
        retry = ttk.Button(first, text="재조회", command=lambda: self.lookup(token))
        retry.pack(side="right")
        label = ttk.Label(frame, text="정보 불러오는 중…", wraplength=820)
        label.pack(anchor="w", pady=4)
        state_label = ttk.Label(frame, text="정보 조회")
        state_label.pack(anchor="w")
        inputs = Inputs(frame, self.settings.default_keyword)
        self.items[token] = dict(vod=vod, frame=frame, label=label, status=state_label, inputs=inputs, meta=None, generation=0, state="정보 조회")
        self.build_url_card()
        self.lookup(token)

    def remove(self, token):
        item = self.items.pop(token, None)
        if item:
            item["frame"].destroy()
        self.refresh()

    def lookup(self, token):
        item = self.items.get(token)
        if not item:
            return
        item["generation"] += 1
        generation, vod = item["generation"], item["vod"]
        item["state"] = "정보 조회"
        item["label"].configure(text="정보 불러오는 중…")
        def worker():
            api = Api()
            try:
                result = api.metadata(vod, self.shutdown)
                self.events.put((token, "metadata", (generation, result, None)))
            except Exception as e:
                self.events.put((token, "metadata", (generation, None, str(e))))
            finally:
                api.close()
        self.pool.submit(worker)
        self.refresh()

    def build_txt(self, parent):
        header = ttk.Frame(parent)
        header.pack(fill="x", pady=(0, 10))
        ttk.Button(header, text="TXT 파일 추가", command=self.choose_txt).pack(side="left")
        self.txt_count = ttk.Label(header, text="0개")
        self.txt_count.pack(side="right")
        self.txt_list = ScrollList(parent)
        self.txt_list.pack(fill="both", expand=True)
        self.txt_notice = ttk.Label(parent, foreground="#b3261e", wraplength=850)
        self.txt_notice.pack(fill="x", pady=6)
        bottom = ttk.Frame(parent)
        bottom.pack(fill="x")
        self.txt_button = ttk.Button(bottom, text="분석 TXT 저장", command=self.start_txt, state="disabled")
        self.txt_button.pack(side="right")
        ttk.Button(bottom, text="저장 폴더 열기", command=self.open_folder).pack(side="right", padx=8)

    def choose_txt(self):
        paths = filedialog.askopenfilenames(filetypes=[("채팅 TXT", "*.txt")])
        for path in paths:
            self.add_txt(Path(path))

    def add_txt(self, path):
        path = Path(path).resolve()
        if any(item["path"] == path for item in self.txt_items.values()):
            self.txt_notice.configure(text=f"이미 등록된 파일: {path.name}")
            return
        token = uuid.uuid4().hex
        frame = ttk.Frame(self.txt_list.body, padding=12, relief="solid", borderwidth=1)
        frame.pack(fill="x", pady=(0, 10), padx=2)
        header = ttk.Frame(frame)
        header.pack(fill="x")
        ttk.Button(header, text="−", width=3, command=lambda: self.remove_txt(token)).pack(side="left")
        ttk.Label(header, text=path.name, wraplength=690).pack(side="left", padx=8)
        Tip(header, str(path))
        label = ttk.Label(frame, text="TXT 불러오는 중…", wraplength=800)
        label.pack(anchor="w", pady=6)
        inputs = Inputs(frame, self.settings.default_keyword)
        inputs.set_duration(None, True)
        status = ttk.Label(frame, text="TXT 읽기")
        status.pack(anchor="w")
        self.txt_items[token] = dict(path=path, frame=frame, label=label, inputs=inputs,
                                     status=status, state="TXT 읽기", meta=None, data=None)
        def worker():
            try:
                meta, chats = load_txt(path)
                self.events.put((token, "txt", (meta, tuple(chats), None)))
            except Exception as e:
                self.events.put((token, "txt", (None, (), str(e))))
        self.pool.submit(worker)
        self.refresh()

    def remove_txt(self, token):
        item = self.txt_items.pop(token, None)
        if item:
            item["frame"].destroy()
        self.refresh()

    def build_options(self, parent):
        outer = parent
        area = ScrollList(outer)
        area.pack(fill="both", expand=True)
        parent = area.body
        self.option_help = {}
        explanations = {
            "output_dir": "수집·분석 TXT를 저장할 폴더입니다. 이 폴더 안에 채널별 하위 폴더를 만들며, 기존 파일은 새 이름으로 보존합니다.",
            "default_keyword": "새 URL 또는 TXT를 등록할 때 채울 키워드입니다 (1~10자). 이미 등록한 항목의 키워드는 바뀌지 않습니다.",
            "interval": "VOD 시작 00:00:00을 기준으로 1~10분씩 집계합니다. 예: 5분은 00~05, 05~10분. 부분 구간도 한 구간으로 계산합니다.",
            "top_count": "채팅량·증가율·키워드 개수·키워드 포함 채팅 비율의 TOP 목록마다 표시할 최대 순위 수입니다. 대상이 부족하면 있는 결과만 표시합니다.",
            "moving_minutes": "현재 구간을 제외한 이전 N분의 평균 채팅량과 비교합니다. 분석 단위의 배수로 입력하세요 (5분 단위라면 5·10·15분). 평균이 0이면 증가율은 N/A입니다.",
            "minimum": "TOP 후보에 포함할 구간의 최소 채팅 수입니다. 0이면 분석 범위의 구간당 평균을 사용하며, 채팅 0개 구간과 부분 구간도 평균에 포함합니다.",
            "repeat": "한 채팅에서 같은 키워드를 최대 몇 번 셀지 정합니다. 예: 5이면 ㅋㅋㅋㅋㅋㅋ도 최대 5회. 0은 무제한이며, 포함 채팅 비율은 메시지당 한 번만 셉니다.",
            "merge_limit": "연속 TOP 구간을 최대 몇 개까지 묶을지 정합니다. 0은 무제한, 1은 병합 안 함. 예: 5분 단위에서 3개를 병합하면 최대 15분입니다.",
            "detail": "켜면 TOP 결과 아래에 분석 범위의 모든 구간을 시간순으로 기록합니다. 끄면 방송·분석 정보와 TOP 결과만 저장합니다.",
            "premiere": "출력 경과 시간 HH:MM:SS 뒤에 :00을 붙입니다. 실제 프레임·FPS 계산이 아니며, 통계나 입력 형식은 바뀌지 않습니다.",
            "actual_time": "수집 TXT에 채팅의 실제 날짜·시각을 함께 표시합니다. 원본에 실제 시각 근거가 없으면 미확인으로 표시합니다.",
        }
        self.option_vars = {}
        labels = dict(output_dir="저장 위치", default_keyword="새 영상 기본 키워드 (1~10자)", interval="분석 단위 (1~10분)",
                      top_count="TOP 개수", moving_minutes="이동평균 이전 N분 (분석 단위의 배수)", minimum="최소 채팅 수 (0=구간 평균)",
                      repeat="키워드 반복 제한 (0=무제한)", merge_limit="최대 병합 구간 수 (0=무제한)",
                      detail="상세 로그 저장", premiere="프리미어 입력용 시간 표시 (:00 추가)", actual_time="수집 TXT 실제 시각 표시")
        for index, (key, label) in enumerate(labels.items()):
            row = index * 2
            value = getattr(self.settings, key)
            var = tk.BooleanVar(value=value) if type(value) is bool else tk.StringVar(value=str(value))
            self.option_vars[key] = var
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
            if type(value) is bool:
                control = ttk.Checkbutton(parent, variable=var)
            elif key == "interval":
                control = ttk.Spinbox(parent, from_=1, to=10, textvariable=var, width=12)
            else:
                control = ttk.Entry(parent, textvariable=var, width=45)
            control.grid(row=row, column=1, sticky="ew", padx=12)
            if key == "output_dir":
                ttk.Button(parent, text="찾아보기", command=self.choose_folder).grid(row=row, column=2)
            explanation = ttk.Label(parent, text=explanations[key], foreground="#555555", wraplength=820)
            explanation.grid(row=row + 1, column=0, columnspan=3, sticky="w", padx=(0, 8), pady=(0, 10))
            self.option_help[key] = explanation
            Tip(control, explanations[key])
        parent.bind("<Configure>", lambda e: [label.configure(wraplength=max(240, e.width - 24)) for label in self.option_help.values()])
        parent.columnconfigure(1, weight=1)
        self.option_error = ttk.Label(outer, foreground="#b3261e", wraplength=750)
        self.option_error.pack(fill="x", pady=8)
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        for label, command in (("적용", self.apply), ("취소", self.reset_editor), ("기본값 복원", self.restore)):
            ttk.Button(buttons, text=label, command=command).pack(side="left", padx=(0, 8))
        ttk.Label(outer, text=str(self.path), wraplength=750).pack(anchor="w", pady=8)

    def choose_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.option_vars["output_dir"].set(path)

    def apply(self):
        try:
            values = {}
            for key, var in self.option_vars.items():
                old = getattr(self.settings, key)
                values[key] = int(var.get()) if type(old) is int else var.get()
            settings = replace(self.settings, **values)
            settings.validate()
            settings = replace(settings, save_chat=self.save_chat.get(), save_analysis=self.save_analysis.get())
            save_settings(self.path, settings)
            self.settings = settings
            self.option_error.configure(text=f"적용·저장 완료 · 병합 최대 {settings.merge_limit * settings.interval}분 (0=무제한)")
            return True
        except (ValueError, tk.TclError, OSError) as e:
            self.option_error.configure(text=str(e))
            return False

    def reset_editor(self):
        for key, var in self.option_vars.items():
            var.set(getattr(self.settings, key))
        self.option_error.configure(text="")

    def restore(self):
        if messagebox.askyesno("기본값 복원", "공통 설정을 기본값으로 복원하고 적용할까요?"):
            try:
                defaults = Settings()
                save_settings(self.path, defaults)
                self.settings = defaults
                self.save_chat.set(True)
                self.save_analysis.set(True)
                self.reset_editor()
                self.refresh()
            except OSError as e:
                self.option_error.configure(text=f"설정 저장 실패: {e}")

    def refresh(self, preserve_notice=False):
        analysis = self.save_analysis.get()
        ready = 0
        for item in self.items.values():
            item["inputs"].enable(analysis)
            ready += item["state"] == "대기"
        count = len(self.items)
        self.count.configure(text=f"{count}/10")
        state = "disabled" if count >= 10 else "normal"
        self.url.configure(state=state)
        self.add_button.configure(state=state)
        enabled = (analysis or self.save_chat.get()) and ready and not self.busy
        self.run_button.configure(state="normal" if enabled else "disabled")
        txt_ready = sum(item["state"] == "대기" for item in self.txt_items.values())
        self.txt_count.configure(text=f"{len(self.txt_items)}개")
        self.txt_button.configure(state="normal" if txt_ready and not self.busy else "disabled")
        if not preserve_notice:
            hint = ""
            if not analysis and not self.save_chat.get():
                hint = "저장할 TXT를 하나 이상 선택하세요"
            elif analysis and not self.save_chat.get():
                hint = "채팅 수집 후 분석 결과만 저장합니다"
            if count - ready:
                hint += f" · 조회 중/실패 {count - ready}개는 실행 대상에서 제외됩니다"
            self.notice.configure(text=hint)

    def start_urls(self):
        if self.busy or not (self.save_chat.get() or self.save_analysis.get()):
            return
        settings = replace(self.settings, save_chat=self.save_chat.get(), save_analysis=self.save_analysis.get())
        try:
            settings.validate(analysis=settings.save_analysis)
            jobs = []
            invalid = False
            skipped = 0
            for token, item in self.items.items():
                if item["state"] != "대기":
                    continue
                try:
                    selected = item["inputs"].snapshot() if settings.save_analysis else selection("", "", "", True, None)
                    job = Job(token, item["meta"], selected, settings)
                    if completed(job):
                        skipped += 1
                        item["status"].configure(text="완료 · 같은 시간·키워드의 결과가 있어 건너뜁니다")
                    else:
                        jobs.append(job)
                except ValueError:
                    invalid = True
            if invalid:
                return
            if not jobs:
                if skipped:
                    self.notice.configure(text=f"완료된 {skipped}개를 건너뛰었습니다. 시간 또는 키워드를 변경하면 다시 실행합니다.")
                    return
                raise ValueError("준비 완료된 영상이 없습니다")
            if skipped:
                self.log_line(f"같은 시간·키워드로 완료된 {skipped}개는 건너뜁니다")
            self.start(jobs)
        except ValueError as e:
            self.notice.configure(text=str(e))

    def start_txt(self):
        if self.busy:
            return
        try:
            self.settings.validate()
            jobs = []
            invalid = False
            for token, item in self.txt_items.items():
                if item["state"] != "대기":
                    continue
                try:
                    selected = item["inputs"].snapshot()
                    jobs.append(Job(token, item["meta"], selected, self.settings, item["path"], item["data"]))
                except ValueError:
                    invalid = True
            if invalid:
                return
            if not jobs:
                raise ValueError("준비 완료된 TXT가 없습니다")
            skipped = len(self.txt_items) - len(jobs)
            self.txt_notice.configure(text=f"읽기 중/실패 {skipped}개는 제외됩니다" if skipped else "")
            self.start(jobs)
        except ValueError as e:
            self.txt_notice.configure(text=str(e))

    def start(self, jobs):
        self.busy = True
        self.cancel.clear()
        self.bar.configure(mode="indeterminate")
        self.bar.start(12)
        for job in jobs:
            end = hms(job.selection.end_ms) if job.selection.end_ms is not None else "자동 끝"
            if job.source or job.settings.save_analysis:
                self.log_line(f"{job.metadata.vod_id or 'TXT'} 적용: {hms(job.selection.start_ms)} ~ {end}, 키워드={job.selection.keyword}")
        self.pool.submit(run_jobs, tuple(jobs), self.cancel, lambda *event: self.events.put(event))
        self.refresh()

    def log_line(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", str(text) + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 250:
            self.log.delete("1.0", "50.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def poll(self):
        try:
            for _ in range(100):
                token, kind, payload = self.events.get_nowait()
                if kind == "metadata":
                    item = self.items.get(token)
                    generation, meta, error = payload
                    if not item or generation != item["generation"]:
                        continue
                    item["state"] = "실패" if error else "대기"
                    item["status"].configure(text=item["state"])
                    if error:
                        item["label"].configure(text="정보 조회 실패: " + error)
                    else:
                        item["meta"] = meta
                        length = hms(meta.duration_ms) if meta.duration_ms is not None else "미확인"
                        item["label"].configure(text=f"{meta.channel} · {meta.title}\n방송 날짜: {meta.broadcast_date} · 게시 날짜: {meta.date} · 영상 길이: {length}")
                        item["inputs"].set_duration(meta.duration_ms)
                        item["inputs"].pack(fill="x")
                    self.refresh()
                elif kind == "txt":
                    item = self.txt_items.get(token)
                    if not item:
                        continue
                    meta, chats, error = payload
                    item["state"] = "실패" if error else "대기"
                    item["status"].configure(text=item["state"])
                    if error:
                        item["label"].configure(text="TXT 읽기 실패: " + error)
                    else:
                        item["meta"], item["data"] = meta, chats
                        item["label"].configure(text=f"{meta.channel} · {meta.title}\n방송 날짜: {meta.broadcast_date} · 게시 날짜: {meta.date} · 채팅 {len(chats):,}개")
                        item["inputs"].set_duration(meta.duration_ms, True)
                        item["inputs"].pack(fill="x")
                    self.refresh()
                elif kind == "종료":
                    self.busy = False
                    self.bar.stop()
                    self.bar.configure(value=0)
                    self.refresh()
                    if self.closing:
                        self.finish_close()
                        return
                elif kind == "파일":
                    self.files.append(payload)
                    self.log_line(f"저장: {payload}")
                elif kind == "결과":
                    self.log_line(f"분석 범위 {hms(payload.start)} ~ {hms(payload.end)}, 채팅 {sum(r.chat for r in payload.buckets):,}개")
                else:
                    name = self.items[token]["vod"] if token in self.items else (self.txt_items[token]["path"].name if token in self.txt_items else token)
                    text = f"{name}: {kind}"
                    if kind == "수집" and payload:
                        count, cursor, duration = payload
                        text += f" · {count:,}개 · 위치 {hms(cursor)} · VOD 시간 기준 {(duration - cursor) / duration * 100:.1f}%"
                    elif kind in ("실패", "건너뜀", "안내"):
                        text += " · " + str(payload)
                    self.status.set(text)
                    if token in self.items:
                        self.items[token]["status"].configure(text=text, wraplength=820)
                    elif token in self.txt_items:
                        self.txt_items[token]["status"].configure(text=text, wraplength=820)
                    if not (kind == "수집" and payload):
                        self.log_line(text)
        except Empty:
            pass
        if self.poll_id is not None:
            self.root.after_cancel(self.poll_id)
        self.poll_id = self.root.after(80, self.poll)

    def open_path(self, path):
        try:
            os.startfile(str(path))
        except OSError as e:
            messagebox.showerror("열기 실패", str(e))

    def open_folder(self):
        path = Path(self.settings.output_dir)
        try:
            path.mkdir(parents=True, exist_ok=True)
            self.open_path(path)
        except OSError as e:
            messagebox.showerror("폴더 열기 실패", str(e))

    def close(self):
        if self.busy:
            if not messagebox.askyesno("작업 중", "작업을 취소하고 종료할까요? 완료한 파일은 유지됩니다."):
                return
            self.closing = True
            self.cancel.set()
            self.status.set("작업 취소를 기다리는 중…")
        else:
            self.finish_close()

    def finish_close(self):
        self.shutdown.set()
        self.bar.stop()
        if self.poll_id is not None:
            self.root.after_cancel(self.poll_id)
            self.poll_id = None
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
