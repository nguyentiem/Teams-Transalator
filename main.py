"""
Teams Meeting Real-Time Translator
Captures system audio, transcribes English, translates to Vietnamese
Shows bilingual transcript and saves to file
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import queue
import time
import datetime
import os
import sys

import soundcard as sc
import numpy as np
import speech_recognition as sr
from googletrans import Translator

# ─────────────────────────── Constants ────────────────────────────
SAMPLE_RATE      = 16000
CHANNELS         = 1
FRAME_MS         = 100    # ms mỗi frame đo RMS (100ms = 1600 samples)
RMS_THRESHOLD    = 0.005  # ngưỡng phân biệt có tiếng / im lặng
SILENCE_TRIGGER  = 0.8    # im lặng bao lâu (giây) thì flush → STT
MIN_SPEECH_SEC   = 0.4    # buffer tối thiểu mới đáng gửi STT
MAX_CHUNK_SEC    = 5.0    # flush bắt buộc dù vẫn còn tiếng


# ─────────────────────────── Audio Capture Thread ──────────────────
class AudioCaptureThread(threading.Thread):
    """
    Captures system audio (loopback) với VAD pure-numpy.
    Flush buffer khi:
      - im lặng >= SILENCE_TRIGGER giây, VÀ buffer >= MIN_SPEECH_SEC
      - hoặc buffer >= MAX_CHUNK_SEC (tránh chunk quá dài)
    """

    def __init__(self, audio_queue: queue.Queue, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.audio_queue = audio_queue
        self.stop_event = stop_event

    def _get_loopback_mic(self):
        try:
            mics = sc.all_microphones(include_loopback=True)
            for m in mics:
                if any(kw in m.name.lower() for kw in ("loopback", "stereo mix", "what u hear", "cable")):
                    return m
            for m in mics:
                if hasattr(m, '_is_loopback') and m._is_loopback:
                    return m
            return sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
        except Exception:
            return None

    def _flush(self, buffer: list) -> None:
        """Ghép buffer → PCM bytes → đẩy vào queue."""
        if not buffer:
            return
        audio = np.concatenate(buffer)
        pcm = (audio * 32767).astype(np.int16).tobytes()
        self.audio_queue.put(("audio", pcm))

    def run(self):
        mic = self._get_loopback_mic()
        if mic is None:
            self.audio_queue.put(("error",
                "Không tìm thấy thiết bị system audio (loopback).\n"
                "Hãy bật 'Stereo Mix' trong Sound Settings của Windows."))
            return

        frames_per_frame = int(SAMPLE_RATE * FRAME_MS / 1000)  # 1600 samples
        silence_frames_needed = int(SILENCE_TRIGGER * 1000 / FRAME_MS)  # 8 frames
        min_speech_frames     = int(MIN_SPEECH_SEC  * 1000 / FRAME_MS)  # 4 frames
        max_buffer_frames     = int(MAX_CHUNK_SEC   * 1000 / FRAME_MS)  # 50 frames

        speech_buffer: list  = []   # tích lũy frames có tiếng
        silence_count: int   = 0    # số frame im lặng liên tiếp

        try:
            with mic.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS) as recorder:
                while not self.stop_event.is_set():
                    frame = recorder.record(numframes=frames_per_frame)
                    if frame.ndim > 1:
                        frame = frame[:, 0]

                    rms = float(np.sqrt(np.mean(frame ** 2)))
                    is_speech = rms > RMS_THRESHOLD

                    if is_speech:
                        speech_buffer.append(frame)
                        silence_count = 0

                        # Flush bắt buộc nếu buffer quá dài
                        if len(speech_buffer) >= max_buffer_frames:
                            self._flush(speech_buffer)
                            speech_buffer = []
                            silence_count = 0
                    else:
                        # Frame im lặng — vẫn append vào buffer nếu đang có speech
                        # (để không cắt giữa chừng do ngập ngừng ngắn)
                        if speech_buffer:
                            silence_count += 1
                            speech_buffer.append(frame)

                            if silence_count >= silence_frames_needed:
                                # Im lặng đủ lâu → flush nếu buffer đủ dài
                                if len(speech_buffer) >= min_speech_frames:
                                    self._flush(speech_buffer)
                                speech_buffer = []
                                silence_count = 0

        except Exception as e:
            self.audio_queue.put(("error", f"Lỗi capture audio: {e}"))


# ─────────────────────────── Recognizer Thread ─────────────────────
class RecognizerThread(threading.Thread):
    """Consumes PCM chunks, runs STT + translation, pushes results."""

    def __init__(self, audio_queue: queue.Queue, result_queue: queue.Queue,
                 stop_event: threading.Event):
        super().__init__(daemon=True)
        self.audio_queue = audio_queue
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.recognizer = sr.Recognizer()
        self.translator = Translator()

    def _translate(self, text: str) -> str:
        try:
            result = self.translator.translate(text, src="en", dest="vi")
            return result.text
        except Exception:
            return "[Lỗi dịch]"

    def run(self):
        while not self.stop_event.is_set():
            try:
                item = self.audio_queue.get(timeout=1)
            except queue.Empty:
                continue

            kind, payload = item
            if kind == "error":
                self.result_queue.put(("error", payload))
                continue

            pcm = payload
            audio_data = sr.AudioData(pcm, SAMPLE_RATE, 2)  # 2 bytes per sample
            try:
                english = self.recognizer.recognize_google(audio_data, language="en-US")
                vietnamese = self._translate(english)
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                self.result_queue.put(("transcript", ts, english, vietnamese))
            except sr.UnknownValueError:
                pass  # silence / unintelligible
            except sr.RequestError as e:
                self.result_queue.put(("error", f"Google STT lỗi: {e}"))
            except Exception as e:
                self.result_queue.put(("error", str(e)))


# ─────────────────────────── Main GUI ──────────────────────────────
class TranslatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Teams Meeting Translator  •  EN → VI")
        self.geometry("900x650")
        self.minsize(700, 500)
        self.configure(bg="#0f1117")
        self._setup_styles()
        self._build_ui()

        self.transcript_entries = []   # list of (ts, en, vi)
        self.audio_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.capture_thread = None
        self.recognizer_thread = None
        self.running = False

        self.after(200, self._poll_results)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Styles ──────────────────────────────────────────────────────
    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#0f1117")
        style.configure("Header.TLabel",
                         background="#0f1117", foreground="#e2e8f0",
                         font=("Segoe UI", 13, "bold"))
        style.configure("Sub.TLabel",
                         background="#0f1117", foreground="#64748b",
                         font=("Segoe UI", 9))
        style.configure("Status.TLabel",
                         background="#0f1117", foreground="#94a3b8",
                         font=("Segoe UI", 9))
        style.configure("Start.TButton",
                         background="#2563eb", foreground="white",
                         font=("Segoe UI", 10, "bold"), padding=(16, 8))
        style.map("Start.TButton",
                  background=[("active", "#1d4ed8")])
        style.configure("Stop.TButton",
                         background="#dc2626", foreground="white",
                         font=("Segoe UI", 10, "bold"), padding=(16, 8))
        style.map("Stop.TButton",
                  background=[("active", "#b91c1c")])
        style.configure("Save.TButton",
                         background="#059669", foreground="white",
                         font=("Segoe UI", 10, "bold"), padding=(16, 8))
        style.map("Save.TButton",
                  background=[("active", "#047857")])

    # ── Build UI ─────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Top bar ──
        top = ttk.Frame(self, style="TFrame")
        top.pack(fill="x", padx=20, pady=(16, 0))

        ttk.Label(top, text="🎙  Teams Translator", style="Header.TLabel").pack(side="left")

        self.status_var = tk.StringVar(value="⏹  Chưa bắt đầu")
        ttk.Label(top, textvariable=self.status_var, style="Status.TLabel").pack(side="right", pady=4)

        # ── Button row ──
        btn_row = ttk.Frame(self, style="TFrame")
        btn_row.pack(fill="x", padx=20, pady=10)

        self.btn_start = ttk.Button(btn_row, text="▶  Bắt đầu dịch",
                                     style="Start.TButton", command=self._start)
        self.btn_start.pack(side="left", padx=(0, 8))

        self.btn_stop = ttk.Button(btn_row, text="■  Dừng",
                                    style="Stop.TButton", command=self._stop,
                                    state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 8))

        self.btn_save = ttk.Button(btn_row, text="💾  Lưu transcript",
                                    style="Save.TButton", command=self._save,
                                    state="disabled")
        self.btn_save.pack(side="left")

        ttk.Button(btn_row, text="🗑  Xoá", command=self._clear).pack(side="left", padx=(8, 0))

        # ── Separator ──
        sep = tk.Frame(self, bg="#1e293b", height=1)
        sep.pack(fill="x", padx=20, pady=(0, 8))

        # ── Column headers ──
        col_frame = ttk.Frame(self, style="TFrame")
        col_frame.pack(fill="x", padx=20)
        ttk.Label(col_frame, text="  Giờ", style="Sub.TLabel", width=8).pack(side="left")
        ttk.Label(col_frame, text="Tiếng Anh (gốc)", style="Sub.TLabel", width=42).pack(side="left")
        ttk.Label(col_frame, text="Tiếng Việt (dịch)", style="Sub.TLabel").pack(side="left")

        # ── Main transcript area ──
        txt_frame = tk.Frame(self, bg="#1e293b", bd=0)
        txt_frame.pack(fill="both", expand=True, padx=20, pady=(4, 12))

        self.transcript_text = scrolledtext.ScrolledText(
            txt_frame,
            wrap="word",
            font=("Cascadia Code", 10),
            bg="#0d1117",
            fg="#e2e8f0",
            insertbackground="#60a5fa",
            selectbackground="#2563eb",
            relief="flat",
            padx=12, pady=10,
            spacing1=4, spacing3=6,
        )
        self.transcript_text.pack(fill="both", expand=True)
        self.transcript_text.config(state="disabled")

        # Text tags
        self.transcript_text.tag_configure("time",    foreground="#475569", font=("Cascadia Code", 9))
        self.transcript_text.tag_configure("english",  foreground="#93c5fd", font=("Cascadia Code", 10))
        self.transcript_text.tag_configure("sep",      foreground="#334155")
        self.transcript_text.tag_configure("vietnamese", foreground="#6ee7b7",
                                            font=("Cascadia Code", 10, "bold"))
        self.transcript_text.tag_configure("error",    foreground="#f87171",
                                            font=("Cascadia Code", 9, "italic"))

        # ── Bottom status bar ──
        bar = ttk.Frame(self, style="TFrame")
        bar.pack(fill="x", padx=20, pady=(0, 12))
        self.count_var = tk.StringVar(value="0 dòng transcript")
        ttk.Label(bar, textvariable=self.count_var, style="Status.TLabel").pack(side="left")
        ttk.Label(bar, text="Google STT  •  googletrans", style="Status.TLabel").pack(side="right")

    # ── Control ──────────────────────────────────────────────────────
    def _start(self):
        if self.running:
            return
        self.running = True
        self.stop_event.clear()

        self.capture_thread = AudioCaptureThread(self.audio_queue, self.stop_event)
        self.recognizer_thread = RecognizerThread(self.audio_queue, self.result_queue, self.stop_event)
        self.capture_thread.start()
        self.recognizer_thread.start()

        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.btn_save.config(state="disabled")
        self.status_var.set("🔴  Đang dịch realtime...")

    def _stop(self):
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.btn_save.config(state="normal" if self.transcript_entries else "disabled")
        self.status_var.set("⏹  Đã dừng")

    def _clear(self):
        self.transcript_text.config(state="normal")
        self.transcript_text.delete("1.0", "end")
        self.transcript_text.config(state="disabled")
        self.transcript_entries.clear()
        self.count_var.set("0 dòng transcript")

    def _save(self):
        if not self.transcript_entries:
            messagebox.showinfo("Thông báo", "Chưa có transcript để lưu.")
            return
        default_name = f"transcript_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")],
            initialfile=default_name,
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write("Teams Meeting Transcript\n")
            f.write(f"Ngày: {datetime.datetime.now().strftime('%d/%m/%Y')}\n")
            f.write("=" * 70 + "\n\n")
            for ts, en, vi in self.transcript_entries:
                f.write(f"[{ts}]\n")
                f.write(f"EN: {en}\n")
                f.write(f"VI: {vi}\n")
                f.write("-" * 50 + "\n")
        messagebox.showinfo("Đã lưu", f"Transcript đã được lưu:\n{path}")

    # ── Poll result queue ─────────────────────────────────────────────
    def _poll_results(self):
        while not self.result_queue.empty():
            item = self.result_queue.get_nowait()
            if item[0] == "transcript":
                _, ts, en, vi = item
                self._append_transcript(ts, en, vi)
            elif item[0] == "error":
                self._append_error(item[1])
        self.after(150, self._poll_results)

    def _append_transcript(self, ts: str, en: str, vi: str):
        self.transcript_entries.append((ts, en, vi))
        box = self.transcript_text
        box.config(state="normal")
        box.insert("end", f"[{ts}]  ", "time")
        box.insert("end", en, "english")
        box.insert("end", "\n          ", "sep")
        box.insert("end", vi, "vietnamese")
        box.insert("end", "\n\n")
        box.see("end")
        box.config(state="disabled")
        self.count_var.set(f"{len(self.transcript_entries)} dòng transcript")

    def _append_error(self, msg: str):
        box = self.transcript_text
        box.config(state="normal")
        box.insert("end", f"⚠  {msg}\n", "error")
        box.see("end")
        box.config(state="disabled")

    # ── Close ─────────────────────────────────────────────────────────
    def _on_close(self):
        self._stop()
        time.sleep(0.3)
        self.destroy()


# ─────────────────────────── Entry point ───────────────────────────
if __name__ == "__main__":
    app = TranslatorApp()
    app.mainloop()