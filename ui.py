from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from downloader import download_video


class TikTokDownloaderApp:
    # code xử lý giao diện người dùng cho ứng dụng tải video TikTok
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("TikTok Video Downloader")
        self.root.geometry("760x520")
        self.root.minsize(720, 480)
        self.root.configure(bg="#0f172a")

        self.config_path = Path.home() / ".tiktok_downloader_config.json"
        self.default_output_dir = str(Path.home() / "Downloads" / "TikTok")
        self.output_var = tk.StringVar(value=self._load_saved_output_dir())
        self.url_var = tk.StringVar()
        self.platform_var = tk.StringVar(value="TikTok")
        self.icon_img = self._load_app_icon()
        self.quality_var = tk.StringVar(value="best")
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self.progress_var = tk.DoubleVar(value=0.0)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_ui()

    def build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        title_kwargs = {
            "text": "TikTok Video Downloader",
            "font": ("Segoe UI", 22, "bold"),
            "foreground": "#38bdf8",
        }
        if self.icon_img is not None:
            # kích thước ảnh logo được đặt là 32x32 pixel, và được căn trái của tiêu đề
            self.icon_img = self.icon_img.subsample(max(1, self.icon_img.width() // 32), max(1, self.icon_img.height() // 32))
            title_kwargs.update({"image": self.icon_img, "compound": "left"})

        title = ttk.Label(container, **title_kwargs)
        title.pack(anchor="w", pady=(0, 12))

        subtitle = ttk.Label(
            container,
            text="Dán liên kết video TikTok để tải nhanh về máy của bạn.",
            font=("Segoe UI", 11),
            foreground="#cbd5e1",
        )
        subtitle.pack(anchor="w", pady=(0, 20))

        url_frame = ttk.LabelFrame(container, text="Liên kết video", padding=12)
        url_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Entry(url_frame, textvariable=self.url_var, font=("Segoe UI", 11)).pack(fill=tk.X)

        output_frame = ttk.LabelFrame(container, text="Thư mục lưu", padding=12)
        output_frame.pack(fill=tk.X, pady=(0, 12))

        output_row = ttk.Frame(output_frame)
        output_row.pack(fill=tk.X)
        ttk.Entry(output_row, textvariable=self.output_var, font=("Segoe UI", 10)).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(output_row, text="Chọn thư mục", command=self.choose_output_dir).pack(side=tk.LEFT, padx=(8, 0))

        platform_frame = ttk.LabelFrame(container, text="Nguồn video", padding=12)
        platform_frame.pack(fill=tk.X, pady=(0, 12))
        ttk.Combobox(
            platform_frame,
            textvariable=self.platform_var,
            values=["TikTok", "Douyin"],
            state="readonly",
            width=20,
        ).pack(anchor="w")
        ttk.Label(
            platform_frame,
            text="Chọn nền tảng để tải phù hợp với link của bạn",
            foreground="#cbd5e1",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(6, 0))

        quality_frame = ttk.LabelFrame(container, text="Chất lượng video", padding=12)
        quality_frame.pack(fill=tk.X, pady=(0, 12))
        ttk.Combobox(
            quality_frame,
            textvariable=self.quality_var,
            values=["best", "high", "medium"],
            state="readonly",
            width=20,
        ).pack(anchor="w")
        ttk.Label(
            quality_frame,
            text="best = giữ chất lượng gốc tốt nhất, high = tối đa 1080p, medium = tối đa 720p",
            foreground="#cbd5e1",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(6, 0))

        button_row = ttk.Frame(container)
        button_row.pack(fill=tk.X, pady=(8, 12))
        ttk.Button(button_row, text="Tải ngay", command=self.start_download).pack(side=tk.LEFT)
        ttk.Button(button_row, text="Xóa", command=self.clear_fields).pack(side=tk.LEFT, padx=(8, 0))

        progress_frame = ttk.LabelFrame(container, text="Tiến trình", padding=12)
        progress_frame.pack(fill=tk.X, pady=(0, 12))
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X)

        status_frame = ttk.LabelFrame(container, text="Trạng thái", padding=12, height=60)
        status_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(status_frame, textvariable=self.status_var, font=("Segoe UI", 10), foreground="#0f766e").pack(anchor="w")

        self.root.bind("<Return>", lambda event: self.start_download())


    # code xử lý tải video trong một luồng riêng biệt để không làm treo giao diện người dùng
    def _load_app_icon(self):
        base_dir = Path(__file__).resolve().parent
        candidates = [
            base_dir / "assets" / "images" / "logoTikTok.png",
            base_dir / "assets" / "images" / "logoTiktok.png",
            base_dir / "assets" / "images" / "logo.png",
        ]
        # Tìm kiếm file ảnh logo trong thư mục assets/images và trả về tk.PhotoImage nếu tìm thấy
        for candidate in candidates:
            if candidate.exists():
                try:
                    return tk.PhotoImage(file=str(candidate))
                except Exception:
                    continue
        return None


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

    def _save_output_dir(self) -> None:
        try:
            with self.config_path.open("w", encoding="utf-8") as file:
                json.dump({"output_dir": self.output_var.get().strip() or self.default_output_dir}, file, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def choose_output_dir(self) -> None:
        directory = filedialog.askdirectory(title="Chọn thư mục lưu video")
        if directory:
            self.output_var.set(directory)
            self._save_output_dir()

    def clear_fields(self) -> None:
        self.url_var.set("")
        # Đặt lại thư mục lưu về mặc định (thư mục Downloads/TikTok)
        self.output_var.set(str(Path.home() / "Downloads" / "TikTok"))
        self.progress_var.set(0.0)
        self.status_var.set("Sẵn sàng")

    def on_close(self) -> None:
        self._save_output_dir()
        self.root.destroy()

    def start_download(self) -> None:
        url = self.url_var.get().strip()
        output_dir = self.output_var.get().strip() or self.default_output_dir

        if not url:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng dán liên kết video TikTok hoặc Douyin trước.")
            return

        self.progress_var.set(0.0)
        self.status_var.set("Đang chuẩn bị...")
        self.root.update_idletasks()

        thread = threading.Thread(target=self._download_worker, args=(url, output_dir), daemon=True)
        thread.start()

    def _download_worker(self, url: str, output_dir: str) -> None:
        try:
            self.status_var.set("Đang kết nối và tải video...")
            self.progress_var.set(10.0)
            self.root.update_idletasks()

            def progress_hook(info: dict) -> None:
                if info.get("status") == "removing_watermark":
                    self.status_var.set("Đang xử lý và giảm watermark...")
                    self.root.update_idletasks()
                    return

                if info.get("_percent") is not None:
                    percent = max(0.0, min(100.0, float(info["_percent"] * 100)))
                    self.progress_var.set(percent)
                    self.status_var.set("Đang tải video...")
                    self.root.update_idletasks()

            result = download_video(url, output_dir, progress_hook, quality=self.quality_var.get())
            self.progress_var.set(100.0)
            self.status_var.set(f"Hoàn tất: {result['file_name']}")
            messagebox.showinfo("Thành công", f"Video {self.platform_var.get()} đã được lưu tại:\n{result['output_path']}")
        except Exception as exc:  # noqa: BLE001
            self.progress_var.set(0.0)
            self.status_var.set("Tải thất bại")
            messagebox.showerror("Lỗi", str(exc))


def run() -> None:
    root = tk.Tk()
    TikTokDownloaderApp(root)
    root.mainloop()
