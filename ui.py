from __future__ import annotations

import io
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk
from PIL import Image

from downloader import (
    download_audio,
    download_video,
    extract_url,
    fetch_channel_video_list,
    fetch_video_preview,
    sanitize_filename,
)

# Thiết lập theme tối hiện đại
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def open_file_in_explorer(filepath: str) -> None:
    """Mở thư mục chứa file và tự động chọn (select/highlight) tệp vừa tải trên Windows Explorer/macOS Finder."""
    try:
        path = Path(filepath).resolve()
        if os.name == "nt":
            if path.exists():
                subprocess.run(["explorer", "/select,", str(path)], check=False)
            else:
                subprocess.run(["explorer", str(path.parent)], check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path.parent)], check=False)
    except Exception:
        pass


class TikTokDownloaderApp:
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.root.title("TikTok & Douyin Downloader Pro by Delwynaa ver 1.0")
        self.root.geometry("920x760")
        self.root.minsize(760, 560)
        self.root.configure(fg_color="#0f172a")

        self.config_path = Path.home() / ".tiktok_downloader_config.json"
        self.default_output_dir = str(Path.home() / "Downloads" / "TikTok")

        self.output_var = tk.StringVar(value=self._load_saved_output_dir())
        self.community_url_var = tk.StringVar(value=self._load_saved_community_url())
        self.url_var = tk.StringVar()
        self.platform_var = tk.StringVar(value="TikTok")
        self.quality_var = tk.StringVar(value="best")
        self.download_mode_var = tk.StringVar(value="video")
        self.remove_watermark_var = tk.BooleanVar(value=True)
        self.auto_clipboard_var = tk.BooleanVar(value=False)
        self.batch_mode_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="⚡ Sẵn sàng tải video hoặc âm thanh")

        self.last_clipboard = ""
        self.preview_image = None

        self.msg_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_ui()
        self.root.after(100, self._process_queue)
        self.root.after(1000, self._check_clipboard)

    def build_ui(self) -> None:
        # Khung cuộn chính mượt mà - tối ưu hóa hiệu năng kéo chỉnh kích thước cửa sổ
        main_container = ctk.CTkScrollableFrame(
            self.root,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color="#334155",
            scrollbar_button_hover_color="#475569",
        )
        main_container.pack(fill="both", expand=True, padx=16, pady=12)

        # ---------------- HERO HEADER ----------------
        header_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))

        title_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_row.pack(fill="x")

        title_left = ctk.CTkFrame(title_row, fg_color="transparent")
        title_left.pack(side="left")

        title_label = ctk.CTkLabel(
            title_left,
            text="⚡ TikTok & Douyin Downloader",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color="#f8fafc",
        )
        title_label.pack(side="left")

        badge = ctk.CTkLabel(
            title_left,
            text=" PRO ver 1.0 by Delwynaa ",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#ff0050",
            text_color="#ffffff",
            corner_radius=8,
        )
        badge.pack(side="left", padx=10)

        # NÚT CỘNG ĐỒNG CỦA DELWYNAA
        btn_community = ctk.CTkButton(
            title_row,
            text="💬 Tham Gia Cộng Đồng",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            height=34,
            corner_radius=10,
            fg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            command=self.open_community_link,
        )
        btn_community.pack(side="right")

        subtitle_label = ctk.CTkLabel(
            header_frame,
            text="Tải nhanh video đơn/kênh tác giả • Hỗ trợ khôi phục tải gián đoạn • Nhúng Cover Art MP3",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#94a3b8",
        )
        subtitle_label.pack(anchor="w", pady=(2, 0))

        # ---------------- MODE SWITCH TABS ----------------
        mode_select_row = ctk.CTkFrame(main_container, fg_color="transparent")
        mode_select_row.pack(fill="x", pady=(0, 10))

        self.seg_input_mode = ctk.CTkSegmentedButton(
            mode_select_row,
            values=["🔗 Tải Đơn Link", "📚 Tải Kênh / Hàng Loạt"],
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            selected_color="#ff0050",
            selected_hover_color="#e11d48",
            unselected_color="#1e293b",
            unselected_hover_color="#334155",
            height=38,
            corner_radius=10,
            command=self._on_input_mode_change,
        )
        self.seg_input_mode.set("🔗 Tải Đơn Link")
        self.seg_input_mode.pack(side="left")

        # Công tắc Auto-Clipboard
        self.switch_clip = ctk.CTkSwitch(
            mode_select_row,
            text="📋 Tự động dán Clipboard",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#cbd5e1",
            progress_color="#00f2fe",
            variable=self.auto_clipboard_var,
        )
        self.switch_clip.pack(side="right", padx=10)

        # ---------------- CARD 1: INPUT LINK / BATCH & DESTINATION ----------------
        self.card_input = ctk.CTkFrame(main_container, corner_radius=16, fg_color="#1e293b", border_width=1, border_color="#334155")
        self.card_input.pack(fill="x", pady=(0, 10), ipadx=10, ipady=8)

        # Khung tải đơn
        self.frame_single = ctk.CTkFrame(self.card_input, fg_color="transparent")
        self.frame_single.pack(fill="x", padx=12, pady=6)

        lbl_url = ctk.CTkLabel(
            self.frame_single,
            text="🔗 LIÊN KẾT VIDEO TIKTOK / DOUYIN",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38bdf8",
        )
        lbl_url.pack(anchor="w", pady=(0, 4))

        url_input_row = ctk.CTkFrame(self.frame_single, fg_color="transparent")
        url_input_row.pack(fill="x")

        self.url_entry = ctk.CTkEntry(
            url_input_row,
            textvariable=self.url_var,
            placeholder_text="Dán liên kết TikTok hoặc Douyin tại đây...",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            height=42,
            corner_radius=10,
            fg_color="#0f172a",
            border_color="#334155",
            border_width=1,
            text_color="#f8fafc",
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_preview = ctk.CTkButton(
            url_input_row,
            text="🔍 Xem Trước",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            height=42,
            width=110,
            corner_radius=10,
            fg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            command=self.load_preview,
        )
        self.btn_preview.pack(side="right")

        # Khung tải hàng loạt / Tải kênh (Ẩn mặc định)
        self.frame_batch = ctk.CTkFrame(self.card_input, fg_color="transparent")

        lbl_batch = ctk.CTkLabel(
            self.frame_batch,
            text="👤 LINK TÀI KHOẢN TIKTOK (VD: @username HOẶC LINK KÊNH) HOẶC DANH SÁCH LINK VIDEO",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38bdf8",
        )
        lbl_batch.pack(anchor="w", pady=(0, 4))

        self.batch_textbox = ctk.CTkTextbox(
            self.frame_batch,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            height=100,
            corner_radius=10,
            fg_color="#0f172a",
            border_color="#334155",
            border_width=1,
            text_color="#f8fafc",
        )
        self.batch_textbox.pack(fill="x", pady=(0, 6))

        batch_btn_row = ctk.CTkFrame(self.frame_batch, fg_color="transparent")
        batch_btn_row.pack(fill="x")

        btn_load_txt = ctk.CTkButton(
            batch_btn_row,
            text="📂 Nạp Từ File .txt",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            height=32,
            corner_radius=8,
            fg_color="#334155",
            hover_color="#475569",
            text_color="#f8fafc",
            command=self.load_txt_file,
        )
        btn_load_txt.pack(side="left")

        # THƯ MỤC LƯU FILE
        lbl_folder = ctk.CTkLabel(
            self.card_input,
            text="📁 THƯ MỤC LƯU FILE",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38bdf8",
        )
        lbl_folder.pack(anchor="w", padx=12, pady=(6, 4))

        folder_row = ctk.CTkFrame(self.card_input, fg_color="transparent")
        folder_row.pack(fill="x", padx=12, pady=(0, 6))

        folder_entry = ctk.CTkEntry(
            folder_row,
            textvariable=self.output_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            height=38,
            corner_radius=10,
            fg_color="#0f172a",
            border_color="#334155",
            border_width=1,
            text_color="#cbd5e1",
        )
        folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_browse = ctk.CTkButton(
            folder_row,
            text="📁 Chọn Thư Mục",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            height=38,
            corner_radius=10,
            fg_color="#334155",
            hover_color="#475569",
            text_color="#f8fafc",
            command=self.choose_output_dir,
        )
        btn_browse.pack(side="right")

        # ---------------- SMART PREVIEW CARD (Ẩn mặc định) ----------------
        self.card_preview = ctk.CTkFrame(main_container, corner_radius=14, fg_color="#1e293b", border_width=1, border_color="#0284c7")

        self.img_label = ctk.CTkLabel(self.card_preview, text="")
        self.img_label.pack(side="left", padx=12, pady=10)

        preview_info = ctk.CTkFrame(self.card_preview, fg_color="transparent")
        preview_info.pack(side="left", fill="both", expand=True, padx=(0, 12), pady=10)

        self.lbl_prev_title = ctk.CTkLabel(
            preview_info,
            text="Tiêu đề video...",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#f8fafc",
            anchor="w",
            justify="left",
            wraplength=480,
        )
        self.lbl_prev_title.pack(anchor="w", fill="x")

        self.lbl_prev_author = ctk.CTkLabel(
            preview_info,
            text="👤 Tác giả: --",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94a3b8",
            anchor="w",
        )
        self.lbl_prev_author.pack(anchor="w", pady=(2, 0))

        # ---------------- CARD 2: OPTIONS & CONFIGURATION ----------------
        card_opts = ctk.CTkFrame(main_container, corner_radius=16, fg_color="#1e293b", border_width=1, border_color="#334155")
        card_opts.pack(fill="x", pady=(0, 10), ipadx=10, ipady=6)

        opts_grid = ctk.CTkFrame(card_opts, fg_color="transparent")
        opts_grid.pack(fill="x", padx=12, pady=8)

        # Cột 1: Nền tảng
        col1 = ctk.CTkFrame(opts_grid, fg_color="transparent")
        col1.pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkLabel(
            col1,
            text="Nguồn Nền Tảng",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#cbd5e1",
        ).pack(anchor="w", pady=(0, 4))

        self.seg_platform = ctk.CTkSegmentedButton(
            col1,
            values=["TikTok", "Douyin"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            selected_color="#ff0050",
            selected_hover_color="#e11d48",
            unselected_color="#0f172a",
            unselected_hover_color="#334155",
            height=36,
            corner_radius=8,
            command=self._on_platform_change,
        )
        self.seg_platform.set(self.platform_var.get())
        self.seg_platform.pack(fill="x")

        # Cột 2: Loại nội dung
        col2 = ctk.CTkFrame(opts_grid, fg_color="transparent")
        col2.pack(side="left", fill="x", expand=True, padx=6)

        ctk.CTkLabel(
            col2,
            text="Loại Nội Dung Tải",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#cbd5e1",
        ).pack(anchor="w", pady=(0, 4))

        self.seg_mode = ctk.CTkSegmentedButton(
            col2,
            values=["🎬 Video", "🎵 Audio MP3"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            selected_color="#0284c7",
            selected_hover_color="#0369a1",
            unselected_color="#0f172a",
            unselected_hover_color="#334155",
            height=36,
            corner_radius=8,
            command=self._on_mode_change,
        )
        self.seg_mode.set("🎬 Video" if self.download_mode_var.get() == "video" else "🎵 Audio MP3")
        self.seg_mode.pack(fill="x")

        # Cột 3: Chất lượng
        col3 = ctk.CTkFrame(opts_grid, fg_color="transparent")
        col3.pack(side="left", fill="x", expand=True, padx=(6, 0))

        ctk.CTkLabel(
            col3,
            text="Chất Lượng Tải",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#cbd5e1",
        ).pack(anchor="w", pady=(0, 4))

        self.opt_quality = ctk.CTkOptionMenu(
            col3,
            values=["best (Gốc cao nhất)", "high (1080p)", "medium (720p)"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#0f172a",
            button_color="#334155",
            button_hover_color="#475569",
            height=36,
            corner_radius=8,
            command=self._on_quality_change,
        )
        self.opt_quality.set("best (Gốc cao nhất)")
        self.opt_quality.pack(fill="x")

        # Toggle Watermark
        watermark_row = ctk.CTkFrame(card_opts, fg_color="transparent")
        watermark_row.pack(fill="x", padx=12, pady=(2, 6))

        self.switch_watermark = ctk.CTkSwitch(
            watermark_row,
            text="Tự động giảm / xóa viền Watermark (sử dụng FFmpeg)",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#cbd5e1",
            progress_color="#ff0050",
            variable=self.remove_watermark_var,
        )
        self.switch_watermark.pack(anchor="w")

        # ---------------- ACTION BUTTONS ----------------
        btn_row = ctk.CTkFrame(main_container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 10))

        self.btn_download = ctk.CTkButton(
            btn_row,
            text="⚡ TẢI NGAY",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            height=48,
            corner_radius=12,
            fg_color="#ff0050",
            hover_color="#e11d48",
            text_color="#ffffff",
            command=self.start_download,
        )
        self.btn_download.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_clear = ctk.CTkButton(
            btn_row,
            text="🗑️ Xóa",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            height=48,
            width=120,
            corner_radius=12,
            fg_color="#334155",
            hover_color="#475569",
            text_color="#f8fafc",
            command=self.clear_fields,
        )
        btn_clear.pack(side="right")

        # ---------------- CARD 3: PROGRESS & LIVE STATUS ----------------
        card_status = ctk.CTkFrame(main_container, corner_radius=16, fg_color="#1e293b", border_width=1, border_color="#334155")
        card_status.pack(fill="x", ipadx=10, ipady=8)

        lbl_status_title = ctk.CTkLabel(
            card_status,
            text="PROGRESS & STATUS",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#64748b",
        )
        lbl_status_title.pack(anchor="w", padx=12, pady=(8, 4))

        self.progress_bar = ctk.CTkProgressBar(
            card_status,
            height=10,
            corner_radius=5,
            progress_color="#00f2fe",
            fg_color="#0f172a",
        )
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 10))

        self.lbl_status = ctk.CTkLabel(
            card_status,
            textvariable=self.status_var,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#38bdf8",
            anchor="center",
        )
        self.lbl_status.pack(fill="x", padx=12, pady=6)

        self.root.bind("<Return>", self._on_return_key)

    def _on_return_key(self, event: tk.Event) -> None:
        focused = self.root.focus_get()
        if focused and isinstance(focused, (ctk.CTkTextbox, tk.Text)):
            return
        self.start_download()

    def open_community_link(self) -> None:
        """Mở trang/nhóm Cộng Đồng trên trình duyệt web mặc định của hệ thống."""
        url = self.community_url_var.get().strip() or "https://zalo.me"
        try:
            webbrowser.open(url)
            self.status_var.set("🌐 Đã mở liên kết Cộng Đồng trên trình duyệt!")
        except Exception as exc:
            messagebox.showerror("Lỗi mở liên kết", str(exc))

    def _on_input_mode_change(self, value: str) -> None:
        if "Kênh" in value or "Batch" in value:
            self.batch_mode_var.set(True)
            self.frame_single.pack_forget()
            self.frame_batch.pack(fill="x", padx=12, pady=6)
        else:
            self.batch_mode_var.set(False)
            self.frame_batch.pack_forget()
            self.frame_single.pack(fill="x", padx=12, pady=6)

    def _on_platform_change(self, value: str) -> None:
        self.platform_var.set(value)

    def _on_mode_change(self, value: str) -> None:
        if "Audio" in value:
            self.download_mode_var.set("audio")
        else:
            self.download_mode_var.set("video")

    def _on_quality_change(self, value: str) -> None:
        if "1080p" in value:
            self.quality_var.set("high")
        elif "720p" in value:
            self.quality_var.set("medium")
        else:
            self.quality_var.set("best")

    def _check_clipboard(self) -> None:
        """Tự động kiểm tra Clipboard và nhận diện link mới nếu bật công tắc Auto-Clipboard."""
        if self.auto_clipboard_var.get():
            try:
                clip_text = self.root.clipboard_get()
                if clip_text and clip_text != self.last_clipboard:
                    extracted = extract_url(clip_text) or clip_text.strip()
                    if extracted and ("tiktok.com" in extracted or "douyin.com" in extracted or extracted.startswith("@")):
                        self.last_clipboard = clip_text
                        self.url_var.set(extracted)
                        self.status_var.set("📋 Đã tự động nhận diện liên kết mới từ Clipboard!")
            except Exception:
                pass

        self.root.after(1000, self._check_clipboard)

    def load_txt_file(self) -> None:
        filepath = filedialog.askopenfilename(
            title="Chọn file chứa danh sách link (.txt)",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                self.batch_textbox.delete("1.0", "end")
                self.batch_textbox.insert("1.0", content)
                self.status_var.set(f"📂 Đã nạp thành công danh sách từ tệp: {Path(filepath).name}")
            except Exception as exc:
                messagebox.showerror("Lỗi Nạp File", str(exc))

    def load_preview(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng dán liên kết video TikTok/Douyin trước.")
            return

        self.btn_preview.configure(state="disabled", text="⏳ Đang Xem...")
        self.status_var.set("🔍 Đang tải thông tin xem trước...")
        thread = threading.Thread(target=self._preview_worker, args=(url,), daemon=True)
        thread.start()

    def _preview_worker(self, url: str) -> None:
        try:
            preview_data = fetch_video_preview(url, platform_choice=self.platform_var.get())
            raw_img = None
            if preview_data.get("thumbnail_url"):
                try:
                    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                    req = urllib.request.Request(preview_data["thumbnail_url"], headers=headers)
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        raw_img = Image.open(io.BytesIO(resp.read()))
                except Exception:
                    pass
            preview_data["pil_image"] = raw_img
            self.msg_queue.put(("preview", preview_data))
        except Exception as exc:
            self.msg_queue.put(("preview_error", str(exc)))

    def _process_queue(self) -> None:
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "status":
                    self.status_var.set(str(data))
                elif msg_type == "progress":
                    val = max(0.0, min(1.0, float(data) / 100.0))
                    self.progress_bar.set(val)
                elif msg_type == "preview_error":
                    self.btn_preview.configure(state="normal", text="🔍 Xem Trước")
                    self.status_var.set(f"⚠️ Không thể xem trước: {data}")
                elif msg_type == "preview":
                    self.btn_preview.configure(state="normal", text="🔍 Xem Trước")
                    info = data
                    self.lbl_prev_title.configure(text=info.get("title", "Video TikTok"))
                    self.lbl_prev_author.configure(text=f"👤 Tác giả: {info.get('author', 'Creator')}")
                    self.card_preview.pack(fill="x", pady=(0, 10), ipadx=6, ipady=4)

                    raw_img = info.get("pil_image")
                    if raw_img:
                        try:
                            orig_w, orig_h = raw_img.size
                            if orig_w > 0 and orig_h > 0:
                                max_w, max_h = 130, 150
                                ratio = min(max_w / orig_w, max_h / orig_h)
                                new_w = max(1, int(orig_w * ratio))
                                new_h = max(1, int(orig_h * ratio))
                            else:
                                new_w, new_h = 110, 140

                            ctk_img = ctk.CTkImage(light_image=raw_img, dark_image=raw_img, size=(new_w, new_h))
                            self.img_label.configure(image=ctk_img, text="", width=new_w, height=new_h)
                        except Exception:
                            pass
                    self.status_var.set("✅ Đã trích xuất thông tin xem trước!")

                elif msg_type == "success":
                    result, media_label = data
                    self.progress_bar.set(1.0)
                    msg_txt = f"✅ Hoàn tất: {result['file_name']}"
                    if result.get("already_existed"):
                        msg_txt = f"⏩ Đã tồn tại: {result['file_name']}"

                    self.status_var.set(msg_txt)
                    self.btn_download.configure(state="normal", text="⚡ TẢI NGAY")

                    ans = messagebox.askyesno(
                        "Tải Thành Công!",
                        f"{media_label.capitalize()} {self.platform_var.get()} đã sẵn sàng tại:\n\n{result['output_path']}\n\nBạn có muốn mở thư mục chứa tệp ngay không?",
                    )
                    if ans:
                        open_file_in_explorer(result["output_path"])

                elif msg_type == "batch_success":
                    success_count, total_count = data
                    self.progress_bar.set(1.0)
                    self.status_var.set(f"🎉 Hoàn tất tải hàng loạt: {success_count}/{total_count} tệp!")
                    self.btn_download.configure(state="normal", text="⚡ TẢI NGAY")
                    messagebox.showinfo("Thành Công", f"Đã hoàn tất tải {success_count}/{total_count} liên kết trong danh sách!")

                elif msg_type == "batch_channel_success":
                    success_count, total_count, username, channel_dir_path = data
                    self.progress_bar.set(1.0)
                    self.status_var.set(f"🎉 Hoàn tất kênh {username}: {success_count}/{total_count} video!")
                    self.btn_download.configure(state="normal", text="⚡ TẢI NGAY")

                    ans = messagebox.askyesno(
                        "Tải Kênh Thành Công!",
                        f"Đã hoàn tất {success_count}/{total_count} video từ kênh {username}!\n\nTất cả video đã được tự động nối tải dở dang và sắp xếp theo ngày đăng tại:\n{channel_dir_path}\n\nBạn có muốn mở thư mục {username} ngay không?",
                    )
                    if ans:
                        open_file_in_explorer(channel_dir_path)

                elif msg_type == "error":
                    self.progress_bar.set(0.0)
                    self.status_var.set(f"❌ Tải thất bại: {data}")
                    self.btn_download.configure(state="normal", text="⚡ TẢI NGAY")
                    messagebox.showerror("Lỗi Tải Video", str(data))
        except queue.Empty:
            pass

        self.root.after(100, self._process_queue)

    def _load_saved_output_dir(self) -> str:
        if not self.config_path.exists():
            return self.default_output_dir
        try:
            with self.config_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, dict) and data.get("output_dir"):
                return str(data["output_dir"])
        except (json.JSONDecodeError, OSError):
            return self.default_output_dir
        return self.default_output_dir

    def _load_saved_community_url(self) -> str:
        default_url = "https://zalo.me"
        if not self.config_path.exists():
            return default_url
        try:
            with self.config_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, dict) and data.get("community_url"):
                return str(data["community_url"])
        except (json.JSONDecodeError, OSError):
            return default_url
        return default_url

    def _save_config(self) -> None:
        try:
            with self.config_path.open("w", encoding="utf-8") as file:
                json.dump(
                    {
                        "output_dir": self.output_var.get().strip() or self.default_output_dir,
                        "community_url": self.community_url_var.get().strip() or "https://zalo.me",
                    },
                    file,
                    ensure_ascii=False,
                    indent=2,
                )
        except OSError:
            pass

    def choose_output_dir(self) -> None:
        directory = filedialog.askdirectory(title="Chọn thư mục lưu video")
        if directory:
            self.output_var.set(directory)
            self._save_config()

    def clear_fields(self) -> None:
        self.url_var.set("")
        self.batch_textbox.delete("1.0", "end")
        self.output_var.set(str(Path.home() / "Downloads" / "TikTok"))
        self.download_mode_var.set("video")
        self.seg_mode.set("🎬 Video")
        self.quality_var.set("best")
        self.opt_quality.set("best (Gốc cao nhất)")
        self.progress_bar.set(0.0)
        self.card_preview.pack_forget()
        self.status_var.set("⚡ Sẵn sàng tải video hoặc âm thanh")

    def on_close(self) -> None:
        self._save_config()
        self.root.destroy()

    def start_download(self) -> None:
        output_dir = self.output_var.get().strip() or self.default_output_dir

        if self.batch_mode_var.get():
            raw_lines = self.batch_textbox.get("1.0", "end").splitlines()
            urls = [line.strip() for line in raw_lines if line.strip()]
            if not urls:
                messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập link tài khoản hoặc danh sách liên kết.")
                return

            self.btn_download.configure(state="disabled", text="⏳ ĐANG TẢI KÊNH / HÀNG LOẠT...")
            self.progress_bar.set(0.0)
            thread = threading.Thread(target=self._batch_worker, args=(urls, output_dir), daemon=True)
            thread.start()
        else:
            url = self.url_var.get().strip()
            if not url:
                messagebox.showwarning("Thiếu thông tin", "Vui lòng dán liên kết video TikTok hoặc Douyin trước.")
                return

            self.btn_download.configure(state="disabled", text="⏳ ĐANG TẢI...")
            self.progress_bar.set(0.0)
            self.status_var.set("⏳ Đang chuẩn bị và kết nối...")

            thread = threading.Thread(target=self._download_worker, args=(url, output_dir), daemon=True)
            thread.start()

    def _batch_worker(self, urls: list[str], output_dir: str) -> None:
        download_audio_only = self.download_mode_var.get() == "audio"
        platform_choice = self.platform_var.get()
        base_output_dir = Path(output_dir).expanduser().resolve()

        # Kiểm tra xem có phải tải theo Kênh/Tài khoản hay không
        first_input = urls[0] if urls else ""
        is_channel_input = ("@" in first_input or "/user/" in first_input or "tiktok.com" in first_input or "douyin.com" in first_input) and ("/video/" not in first_input and "/photo/" not in first_input)

        if is_channel_input and len(urls) == 1:
            try:
                self.msg_queue.put(("status", "⏳ Đang quét danh sách toàn bộ video từ tài khoản kênh..."))
                self.msg_queue.put(("progress", 5.0))

                username, video_list = fetch_channel_video_list(first_input, platform_choice=platform_choice)
                if not video_list:
                    raise RuntimeError("Không tìm thấy video nào trong tài khoản này.")

                # Tạo thư mục riêng đặt tên theo tên tài khoản TikTok / Douyin
                channel_folder_name = sanitize_filename(username)
                target_channel_dir = base_output_dir / channel_folder_name
                target_channel_dir.mkdir(parents=True, exist_ok=True)

                total = len(video_list)
                success_count = 0

                for idx, item in enumerate(video_list, start=1):
                    item_url = item["url"]
                    item_date = item.get("upload_date")
                    formatted_date = f"{item_date[:4]}-{item_date[4:6]}-{item_date[6:]}" if item_date and len(item_date) == 8 else "0000-00-00"

                    self.msg_queue.put(("status", f"⚡ [{idx}/{total}] Đang tải ({formatted_date}): {item.get('title', '')[:30]}..."))
                    self.msg_queue.put(("progress", (idx - 1) / total * 100.0))

                    try:
                        if download_audio_only:
                            res = download_audio(
                                item_url,
                                str(target_channel_dir),
                                quality=self.quality_var.get(),
                                platform_choice=platform_choice,
                                upload_date=item_date,
                            )
                        else:
                            res = download_video(
                                item_url,
                                str(target_channel_dir),
                                quality=self.quality_var.get(),
                                platform_choice=platform_choice,
                                remove_watermark_flag=self.remove_watermark_var.get(),
                                upload_date=item_date,
                            )

                        if res and res.get("already_existed"):
                            self.msg_queue.put(("status", f"⏩ Đã tồn tại: [{idx}/{total}] {item.get('title', '')[:25]}"))

                        success_count += 1
                    except Exception:
                        continue

                    self.msg_queue.put(("progress", idx / total * 100.0))

                self.msg_queue.put(("batch_channel_success", (success_count, total, username, str(target_channel_dir))))
                return
            except Exception as exc:
                self.msg_queue.put(("error", f"Lỗi kênh: {exc}"))
                return

        # Tải theo danh sách nhiều link video lẻ
        total = len(urls)
        success_count = 0

        for idx, url in enumerate(urls, start=1):
            try:
                self.msg_queue.put(("status", f"⚡ Đang tải ({idx}/{total}): {url[:40]}..."))
                self.msg_queue.put(("progress", (idx - 1) / total * 100.0))

                if download_audio_only:
                    download_audio(
                        url,
                        output_dir,
                        quality=self.quality_var.get(),
                        platform_choice=platform_choice,
                    )
                else:
                    download_video(
                        url,
                        output_dir,
                        quality=self.quality_var.get(),
                        platform_choice=platform_choice,
                        remove_watermark_flag=self.remove_watermark_var.get(),
                    )

                success_count += 1
                self.msg_queue.put(("progress", idx / total * 100.0))
            except Exception:
                continue

        self.msg_queue.put(("batch_success", (success_count, total)))

    def _download_worker(self, url: str, output_dir: str) -> None:
        try:
            download_audio_only = self.download_mode_var.get() == "audio"
            platform_choice = self.platform_var.get()
            media_label = "âm thanh" if download_audio_only else "video"

            self.msg_queue.put(("status", f"⏳ Đang kết nối và tải {media_label}..."))
            self.msg_queue.put(("progress", 10.0))

            def progress_hook(info: dict) -> None:
                if not download_audio_only and info.get("status") == "removing_watermark":
                    self.msg_queue.put(("status", "✂️ Đang xử lý và giảm watermark..."))
                    return

                if info.get("_percent") is not None:
                    percent = max(0.0, min(100.0, float(info["_percent"] * 100)))
                    self.msg_queue.put(("progress", percent))
                    self.msg_queue.put(("status", f"⚡ Đang tải {media_label} ({percent:.1f}%)..."))

            if download_audio_only:
                result = download_audio(
                    url,
                    output_dir,
                    progress_hook,
                    quality=self.quality_var.get(),
                    platform_choice=platform_choice,
                )
            else:
                result = download_video(
                    url,
                    output_dir,
                    progress_hook,
                    quality=self.quality_var.get(),
                    platform_choice=platform_choice,
                    remove_watermark_flag=self.remove_watermark_var.get(),
                )

            self.msg_queue.put(("success", (result, media_label)))
        except Exception as exc:  # noqa: BLE001
            self.msg_queue.put(("error", str(exc)))


def run() -> None:
    root = ctk.CTk()
    TikTokDownloaderApp(root)
    root.mainloop()
