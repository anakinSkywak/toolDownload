from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

import yt_dlp

# code xử lý kiểm tra xem URL có phải là video TikTok hoặc Douyin hợp lệ hay không
TIKTOK_URL_RE = re.compile(r"https?://(?:www\.)?tiktok\.com/.*(?:/video/|/v/)")
DOUYIN_URL_RE = re.compile(r"https?://(?:www\.)?v\.douyin\.com/|https?://(?:www\.)?douyin\.com/")


def extract_url(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""

    match = re.search(r"https?://[^\s]+", cleaned)
    if match:
        return match.group(0).rstrip(".,;:!?)]}")

    return cleaned


def detect_platform(url: str) -> str:
    cleaned = extract_url(url)
    if TIKTOK_URL_RE.match(cleaned):
        return "tiktok"
    if DOUYIN_URL_RE.search(cleaned):
        return "douyin"
    return "unknown"


def is_supported_tiktok_url(url: str) -> bool:
    return detect_platform(url) in {"tiktok", "douyin"}

# code xử lý làm sạch tên tệp để tránh các ký tự không hợp lệ
def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned or "tiktok_video"

# code xử lý xây dựng các tùy chọn tải xuống cho yt-dlp
def build_download_options(output_dir: str, title: Optional[str] = None, quality: str = "best", platform: str = "tiktok") -> dict:
    # Tạo thư mục đầu ra nếu chưa tồn tại
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    filename = f"{sanitize_filename(title or 'tiktok_video')}.%(ext)s"

    if quality == "best":
        format_selector = "bestvideo+bestaudio/best[ext=mp4]/best"
    elif quality == "high":
        format_selector = "bestvideo[height<=1080]+bestaudio/best[height<=1080][ext=mp4]/best"
    elif quality == "medium":
        format_selector = "bestvideo[height<=720]+bestaudio/best[height<=720][ext=mp4]/best"
    else:
        format_selector = "bestvideo+bestaudio/best[ext=mp4]/best"

    http_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    options = {
        "format": format_selector,
        "outtmpl": str(output_path / filename),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 4,
        "merge_output_format": "mp4",
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }
        ],
        "http_headers": http_headers,
    }

    if platform == "douyin":
        options["http_headers"].update({
            "Referer": "https://www.douyin.com/",
            "Origin": "https://www.douyin.com",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        })
        options["extractor_args"] = {
            "ytdlp": {
                "http": {
                    "client": "ios"
                }
            }
        }

    return options

# code xử lý tìm kiếm tệp đã tải xuống trong thư mục đầu ra
def locate_downloaded_file(output_dir: str, expected_title: Optional[str] = None) -> Optional[Path]:
    output_path = Path(output_dir).expanduser().resolve()
    if not output_path.exists():
        return None

    candidates = [
        p for p in output_path.iterdir()
        if p.is_file() and p.suffix.lower() in {".mp4", ".m4a", ".webm", ".mp3"}
    ]
    if not candidates:
        return None

    if expected_title:
        expected = sanitize_filename(expected_title).lower()
        for candidate in candidates:
            if expected in candidate.stem.lower():
                return candidate

    return max(candidates, key=lambda item: item.stat().st_mtime)

# code xử lý loại bỏ watermark bằng ffmpeg
def build_watermark_removal_command(input_path: Path, output_path: Path, crop_ratio: float = 0.12) -> list[str]:
    if crop_ratio <= 0 or crop_ratio >= 1:
        raise ValueError("crop_ratio cần nằm giữa 0 và 1.")

    return [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        f"crop=iw:ih*{1 - crop_ratio}:0:0",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        str(output_path),
    ]

# code xử lý loại bỏ watermark bằng ffmpeg
def remove_watermark(input_path: Path, output_dir: str) -> Path:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return input_path

    output_path = Path(output_dir).expanduser().resolve() / f"{input_path.stem}_clean.mp4"
    command = build_watermark_removal_command(input_path, output_path)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Không thể xử lý watermark. Chi tiết: {completed.stderr.strip() or completed.stdout.strip()}")

    return output_path

# code xử lý tải video TikTok và loại bỏ watermark
def download_video(url: str, output_dir: str, progress_hook: Optional[Callable[[dict], None]] = None, quality: str = "best") -> dict:
    cleaned_url = extract_url(url)
    platform = detect_platform(cleaned_url)
    if platform not in {"tiktok", "douyin"}:
        raise ValueError("Đường dẫn không phải video TikTok hoặc Douyin hợp lệ.")

    output_dir = str(Path(output_dir).expanduser().resolve())
    os.makedirs(output_dir, exist_ok=True)

    options = build_download_options(output_dir, quality=quality, platform=platform)
    if progress_hook is not None:
        options["progress_hooks"] = [progress_hook]

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(cleaned_url, download=False)
            title = info.get("title") if isinstance(info, dict) else None
            options = build_download_options(output_dir, title, quality=quality, platform=platform)
            if progress_hook is not None:
                options["progress_hooks"] = [progress_hook]

            with yt_dlp.YoutubeDL(options) as downloader2:
                downloader2.download([cleaned_url])
    except Exception as exc:  # noqa: BLE001
        if platform == "douyin":
            raise RuntimeError(
                "Video Douyin đang bị chặn bởi hệ thống bảo mật và không thể tải trực tiếp bằng công cụ này."
            ) from exc
        raise

    downloaded_file = locate_downloaded_file(output_dir, title)
    if downloaded_file is None:
        raise RuntimeError("Không tìm thấy tệp đã tải. Hãy kiểm tra lại đường dẫn video.")

    if progress_hook is not None:
        progress_hook({"status": "removing_watermark"})

    try:
        cleaned_file = remove_watermark(downloaded_file, output_dir)
    except RuntimeError:
        cleaned_file = downloaded_file

    final_file = cleaned_file if cleaned_file.exists() else downloaded_file

    return {
        "title": title or f"{platform}_video",
        "output_path": str(final_file),
        "file_name": final_file.name,
        "platform": platform,
    }
