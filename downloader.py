from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import yt_dlp


# Tìm đường dẫn ffmpeg khả dụng (hệ thống hoặc thư mục đính kèm)
def _ensure_ffmpeg_executable() -> Optional[str]:
    """Tự động kiểm tra và giải nén/tải xuống ffmpeg.exe nếu hệ thống chưa có."""
    base_dir = Path(__file__).resolve().parent
    bin_dir = base_dir / "bin"
    target_ffmpeg = bin_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")

    if target_ffmpeg.exists() and target_ffmpeg.stat().st_size > 0:
        return str(target_ffmpeg)

    # Thử giải nén từ file zip local nếu sẵn có
    zip_path = base_dir / "ffmpeg-tools-2025-01-01-git-d3aa99a4f4.zip"
    if zip_path.exists():
        try:
            import zipfile
            with zipfile.ZipFile(zip_path, "r") as z:
                for member in z.namelist():
                    if member.endswith("ffmpeg.exe") or member.endswith("ffmpeg"):
                        bin_dir.mkdir(parents=True, exist_ok=True)
                        with z.open(member) as source, open(target_ffmpeg, "wb") as target:
                            shutil.copyfileobj(source, target)
                        if target_ffmpeg.exists() and target_ffmpeg.stat().st_size > 0:
                            return str(target_ffmpeg)
        except Exception:
            pass

    # Tải xuống binary ffmpeg tĩnh đơn vị từ GitHub release chính thức của yt-dlp
    bin_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        url = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        temp_download = bin_dir / "ffmpeg_download.tmp"
        temp_zip = bin_dir / "ffmpeg_download.zip"
        try:
            if not temp_zip.exists():
                urllib.request.urlretrieve(url, temp_download)
                temp_download.rename(temp_zip)
            import zipfile
            try:
                with zipfile.ZipFile(temp_zip, "r") as z:
                    for member in z.namelist():
                        if member.endswith("ffmpeg.exe"):
                            with z.open(member) as source, open(target_ffmpeg, "wb") as target:
                                shutil.copyfileobj(source, target)
                            break
            except zipfile.BadZipFile:
                temp_zip.unlink(missing_ok=True)
                temp_download.unlink(missing_ok=True)
            temp_zip.unlink(missing_ok=True)
            if target_ffmpeg.exists() and target_ffmpeg.stat().st_size > 0:
                return str(target_ffmpeg)
        except Exception:
            temp_download.unlink(missing_ok=True)

    return None


def _get_ffmpeg_path() -> Optional[str]:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    base_dir = Path(__file__).resolve().parent
    candidates = [
        base_dir / "ffmpeg.exe",
        base_dir / "bin" / "ffmpeg.exe",
        base_dir / "ffmpeg-tools-2025-01-01-git-d3aa99a4f4" / "bin" / "ffmpeg.exe",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.stat().st_size > 0:
            return str(candidate)

    auto_ffmpeg = _ensure_ffmpeg_executable()
    if auto_ffmpeg and Path(auto_ffmpeg).exists():
        return auto_ffmpeg

    return None


# Đảm bảo yt-dlp được cập nhật lên phiên bản mới nhất bằng sys.executable (cache 24h)
def _ensure_latest_ytdlp() -> None:
    cache_file = Path.home() / ".ytdlp_last_update"
    try:
        if cache_file.exists():
            last_check = float(cache_file.read_text().strip() or "0")
            if time.time() - last_check < 86400:  # 24 giờ
                return
    except Exception:
        pass

    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--quiet",
                "yt-dlp",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            cache_file.write_text(str(time.time()))
        except Exception:
            pass
    except Exception:
        pass


def _http_get(url: str, timeout: int = 10, headers: Optional[dict] = None) -> bytes:
    req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# Regex linh hoạt hỗ trợ nhiều định dạng URL TikTok và Douyin (bao gồm m.tiktok, vt.tiktok, vm.tiktok, photo, v.douyin)
TIKTOK_URL_RE = re.compile(r"https?://(?:[a-zA-Z0-9-]+\.)?tiktok\.com/")
DOUYIN_URL_RE = re.compile(r"https?://(?:[a-zA-Z0-9-]+\.)?douyin\.com/|v\.douyin\.com")


def extract_url(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""

    match = re.search(r"https?://[^\s]+", cleaned)
    if match:
        return match.group(0).rstrip(".,;:!?)]}")

    return cleaned


def normalize_url(url: str) -> str:
    cleaned = extract_url(url)
    if not cleaned:
        return ""
    # Chuyển định dạng bài đăng ảnh /photo/ thành /video/ để yt-dlp nhận diện
    if "/photo/" in cleaned:
        cleaned = cleaned.replace("/photo/", "/video/")
    return cleaned


def get_candidate_urls(url: str, platform: str) -> list[str]:
    cleaned = normalize_url(url)
    if not cleaned:
        return []

    candidates = [cleaned]

    if platform == "tiktok":
        match = re.search(r"/(?:video|photo|v)/([0-9]+)", url)
        if not match:
            match = re.search(r"/([0-9]{15,22})", url)

        if match:
            video_id = match.group(1)
            embed_url = f"https://www.tiktok.com/embed/v2/{video_id}"
            mobile_url = f"https://m.tiktok.com/v/{video_id}.html"
            canonical_url = f"https://www.tiktok.com/@user/video/{video_id}"

            for alt in [embed_url, mobile_url, canonical_url]:
                if alt not in candidates:
                    candidates.append(alt)

    return candidates


def extract_channel_username(url: str) -> str:
    """Trích xuất tên tài khoản (@username) từ URL TikTok hoặc Douyin."""
    cleaned = url.strip()
    match = re.search(r"@([a-zA-Z0-9._-]+)", cleaned)
    if match:
        return f"@{match.group(1)}"
    match_douyin = re.search(r"/user/([a-zA-Z0-9._-]+)", cleaned)
    if match_douyin:
        return f"douyin_{match_douyin.group(1)[:12]}"
    return "channel_downloads"


def fetch_channel_video_list(channel_url: str, platform_choice: str = "tiktok") -> tuple[str, list[dict]]:
    """Quét toàn bộ danh sách video trong kênh/tài khoản và sắp xếp theo ngày đăng (tăng dần YYYYMMDD)."""
    cleaned_url = extract_url(channel_url) or channel_url.strip()
    if cleaned_url.startswith("@"):
        cleaned_url = f"https://www.tiktok.com/{cleaned_url}"

    platform = detect_platform(cleaned_url, user_choice=platform_choice)
    username = extract_channel_username(cleaned_url)

    options = _build_base_download_options("/tmp", platform=platform)
    options["extract_flat"] = "in_playlist"

    entries = []
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(cleaned_url, download=False)
            if info:
                uploader = info.get("uploader") or info.get("uploader_id") or info.get("title")
                if uploader and uploader != "TikTok":
                    username = f"@{uploader.lstrip('@')}"

                raw_entries = info.get("entries", [])
                if not raw_entries and info.get("id"):
                    raw_entries = [info]

                for item in raw_entries:
                    if isinstance(item, dict):
                        v_url = item.get("url") or item.get("webpage_url")
                        v_id = item.get("id")
                        if not v_url and v_id:
                            v_url = f"https://www.tiktok.com/{username}/video/{v_id}"

                        if v_url:
                            u_date = str(item.get("upload_date") or "00000000")
                            entries.append({
                                "url": v_url,
                                "title": item.get("title") or f"video_{v_id or 'item'}",
                                "upload_date": u_date,
                                "id": v_id,
                            })
    except Exception as exc:
        raise RuntimeError(f"Không thể quét danh sách video từ tài khoản này: {exc}") from exc

    # Sắp xếp video theo ngày đăng từ cũ đến mới (YYYYMMDD) để khi sắp xếp tên file sẽ đúng thứ tự thời gian
    entries.sort(key=lambda x: x["upload_date"])

    return username, entries


def resolve_douyin_direct(url: str) -> tuple[str, str]:
    """Giải mã trực tiếp liên kết chia sẻ Douyin (bao gồm link v.douyin.com rút gọn) thành URL video không logo."""
    cleaned_url = extract_url(url)
    if not cleaned_url:
        raise ValueError("Liên kết Douyin không hợp lệ.")

    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    }

    req = urllib.request.Request(cleaned_url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as res:
        final_url = res.geturl()
        html = res.read().decode("utf-8", errors="ignore")

    # Trích xuất tiêu đề video
    title_match = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html)
    if not title_match:
        title_match = re.search(r'<title>([^<]+)</title>', html)

    raw_title = title_match.group(1) if title_match else "douyin_video"
    title = raw_title.split("-")[0].split("复制此链接")[0].strip()

    # Trích xuất ID video CDN Douyin từ html hoặc final_url
    vid_match = re.search(r'"video_id=([a-zA-Z0-9_]+)"', html)
    if not vid_match:
        vid_match = re.search(r'"uri"\s*:\s*"([a-zA-Z0-9_]+)"', html)

    if vid_match:
        direct_url = f"https://aweme.snssdk.com/aweme/v1/play/?video_id={vid_match.group(1)}&ratio=1080p&line=0"
    else:
        raw_url_match = re.search(r'https?:\\?/\\?/[^"\'\s]+playwm[^\s"\'<>]*', html)
        if raw_url_match:
            direct_url = raw_url_match.group(0).replace("\\/", "/").replace("playwm", "play")
        else:
            num_id_match = re.search(r"/video/([0-9]{15,22})", final_url)
            if num_id_match:
                direct_url = f"https://www.iesdouyin.com/share/video/{num_id_match.group(1)}/"
            else:
                direct_url = cleaned_url

    return title, direct_url


def detect_platform(url: str, user_choice: str = "tiktok") -> str:
    cleaned = extract_url(url)
    if DOUYIN_URL_RE.search(cleaned):
        return "douyin"
    if TIKTOK_URL_RE.search(cleaned):
        return "tiktok"
    choice = user_choice.lower()
    return choice if choice in {"tiktok", "douyin"} else "tiktok"


def is_supported_tiktok_url(url: str) -> bool:
    return detect_platform(url) in {"tiktok", "douyin"}


def sanitize_filename(value: str) -> str:
    """Giữ nguyên ký tự Unicode (tiếng Việt, tiếng Trung), chỉ loại bỏ các ký tự cấm hệ điều hành."""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', value).strip(" ._")
    if len(cleaned) > 120:
        cleaned = cleaned[:120].rstrip(" ._")
    return cleaned or "media_download"


def download_direct_stream_with_resume(
    direct_url: str,
    target_path: Path,
    headers: Optional[dict] = None,
    timeout: int = 30,
) -> bool:
    """Tải tệp trực tiếp bằng HTTP hỗ trợ tiếp tục (Resume) từ vị trí dở dang (Header Range)."""
    part_path = target_path.with_suffix(target_path.suffix + ".part")
    existing_bytes = part_path.stat().st_size if part_path.exists() else 0

    req_headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    }
    if headers:
        req_headers.update(headers)

    if existing_bytes > 0:
        req_headers["Range"] = f"bytes={existing_bytes}-"

    req = urllib.request.Request(direct_url, headers=req_headers)
    mode = "ab" if existing_bytes > 0 else "wb"

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response, open(part_path, mode) as out_f:
            shutil.copyfileobj(response, out_f)

        if part_path.exists() and part_path.stat().st_size > 0:
            if target_path.exists():
                target_path.unlink()
            part_path.rename(target_path)
            return True
    except urllib.error.HTTPError as err:
        if err.code == 416 and part_path.exists() and part_path.stat().st_size > 0:
            if target_path.exists():
                target_path.unlink()
            part_path.rename(target_path)
            return True
        raise

    return False


def embed_mp3_metadata(mp3_path: str, title: str, artist: str, image_url: Optional[str] = None) -> None:
    """Nhúng ID3 Tag (Title, Artist, Cover Art image) vào file MP3 bằng mutagen."""
    try:
        from mutagen.id3 import APIC, ID3, TIT2, TPE1, error
        from mutagen.mp3 import MP3

        audio = MP3(mp3_path, ID3=ID3)
        try:
            audio.add_tags()
        except error:
            pass

        audio.tags.add(TIT2(encoding=3, text=title))
        audio.tags.add(TPE1(encoding=3, text=artist))

        if image_url:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                req = urllib.request.Request(image_url, headers=headers)
                with urllib.request.urlopen(req, timeout=4) as resp:
                    img_data = resp.read()
                    audio.tags.add(
                        APIC(
                            encoding=3,
                            mime="image/jpeg",
                            type=3,
                            desc="Cover",
                            data=img_data,
                        )
                    )
            except Exception:
                pass

        audio.save()
    except Exception:
        pass


def fetch_video_preview(url: str, platform_choice: str = "tiktok") -> dict:
    """Lấy thông tin xem trước Thumbnail, tiêu đề và tác giả từ liên kết siêu nhanh & chính xác."""
    cleaned = extract_url(url)
    if not cleaned:
        raise ValueError("Liên kết không hợp lệ.")

    platform = detect_platform(cleaned, user_choice=platform_choice)

    # Dành cho Douyin: Trích xuất bằng resolve_douyin_direct kết hợp cover regex
    if platform == "douyin":
        try:
            title, direct_url = resolve_douyin_direct(cleaned)
            thumb_url = None
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
                }
                req = urllib.request.Request(cleaned, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as res:
                    html = res.read().decode("utf-8", errors="ignore")
                thumb_m = re.search(r'https?://[^\s"\'<>]+(?:cover|poster|jpeg|jpg|png|webp|template_cover)[^\s"\'<>]*', html)
                if thumb_m:
                    thumb_url = thumb_m.group(0).replace("\\/", "/")
            except Exception:
                pass

            return {
                "title": title or "Douyin Video",
                "author": "Douyin Creator",
                "thumbnail_url": thumb_url,
                "platform": "douyin",
            }
        except Exception:
            pass

    # Dành cho TikTok: Sử dụng official TikTok oEmbed API (nhanh < 0.5s & 100% chuẩn xác)
    normalized = normalize_url(cleaned)
    oembed_url = f"https://www.tiktok.com/oembed?url={normalized}"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        req = urllib.request.Request(oembed_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "title": data.get("title") or "TikTok Video",
                "author": data.get("author_name") or "TikTok Creator",
                "thumbnail_url": data.get("thumbnail_url"),
                "platform": "tiktok",
            }
    except Exception:
        pass

    # Fallback dự phòng bằng yt-dlp nếu oEmbed bị giới hạn
    candidates = get_candidate_urls(url, platform)
    options = _build_base_download_options("/tmp", platform=platform)

    for candidate_url in candidates:
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(candidate_url, download=False)
                if info:
                    return {
                        "title": info.get("title") or "TikTok Media",
                        "author": info.get("uploader") or info.get("uploader_id") or "TikTok Creator",
                        "thumbnail_url": info.get("thumbnail"),
                        "platform": platform,
                        "duration": info.get("duration"),
                    }
        except Exception:
            continue

    raise RuntimeError("Không thể trích xuất thông tin xem trước cho liên kết này.")


def _build_base_download_options(
    output_dir: str,
    title: Optional[str] = None,
    quality: str = "best",
    platform: str = "tiktok",
) -> dict:
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    if title:
        filename = f"{sanitize_filename(title)}.%(ext)s"
    else:
        filename = "%(title).100s_%(id)s.%(ext)s"

    http_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    options = {
        "format": "best",
        "outtmpl": str(output_path / filename),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 4,
        "continuedl": True,
        "part": True,
        "updatetime": False,
        "merge_output_format": "mp4",
        "postprocessors": [],
        "http_headers": http_headers,
        "extractor_retries": 5,
        "extract_flat": False,
        "skip_download": False,
    }

    ffmpeg_path = _get_ffmpeg_path()
    if ffmpeg_path:
        options["ffmpeg_location"] = ffmpeg_path

    if platform == "douyin":
        options["http_headers"].update({
            "Referer": "https://www.douyin.com/",
            "Origin": "https://www.douyin.com",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        })
    else:
        options["http_headers"].update({
            "Referer": "https://www.tiktok.com/",
            "Origin": "https://www.tiktok.com",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        })

    return options


def build_video_download_options(
    output_dir: str,
    title: Optional[str] = None,
    quality: str = "best",
    platform: str = "tiktok",
) -> dict:
    options = _build_base_download_options(output_dir, title, quality, platform)
    if quality == "best":
        options["format"] = "best[ext=mp4]/bestvideo+bestaudio/best"
    elif quality == "high":
        options["format"] = "best[ext=mp4][height<=1080]/bestvideo[height<=1080]+bestaudio/best"
    elif quality == "medium":
        options["format"] = "best[ext=mp4][height<=720]/bestvideo[height<=720]+bestaudio/best"
    else:
        options["format"] = "best[ext=mp4]/bestvideo+bestaudio/best"

    ffmpeg_path = _get_ffmpeg_path()
    if ffmpeg_path:
        options["postprocessors"] = [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }
        ]
    else:
        options["postprocessors"] = []

    return options


def build_audio_download_options(
    output_dir: str,
    title: Optional[str] = None,
    quality: str = "best",
    platform: str = "tiktok",
) -> dict:
    options = _build_base_download_options(output_dir, title, quality, platform)
    options["format"] = "bestaudio/best"

    ffmpeg_path = _get_ffmpeg_path()
    if ffmpeg_path:
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        options["postprocessors"] = []

    return options


def convert_video_to_mp3(input_video: Path, output_mp3: Path) -> bool:
    """Chuyển đổi video sang tệp MP3 chuẩn bằng FFmpeg."""
    ffmpeg_path = _get_ffmpeg_path()
    if not ffmpeg_path:
        return False
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(input_video),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ab",
        "192k",
        str(output_mp3),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return completed.returncode == 0 and output_mp3.exists() and output_mp3.stat().st_size > 0


def download_audio(
    url: str,
    output_dir: str,
    progress_hook: Optional[Callable[[dict], None]] = None,
    quality: str = "best",
    platform_choice: str = "tiktok",
    upload_date: Optional[str] = None,
) -> dict:
    cleaned_url = extract_url(url)
    if not cleaned_url:
        raise ValueError("Liên kết không hợp lệ.")

    platform = detect_platform(cleaned_url, user_choice=platform_choice)
    output_dir_path = Path(output_dir).expanduser().resolve()
    output_dir_path.mkdir(parents=True, exist_ok=True)

    _ensure_latest_ytdlp()

    # Giải mã trực tiếp nếu là Douyin (hỗ trợ chuyển đổi sang MP3 + nhúng ID3 Tag)
    if platform == "douyin":
        try:
            title, direct_url = resolve_douyin_direct(cleaned_url)
            clean_title = sanitize_filename(title)
            date_prefix = f"[{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}]_" if upload_date and len(upload_date) == 8 else ""
            
            ffmpeg_path = _get_ffmpeg_path()
            target_path = output_dir_path / f"{date_prefix}{clean_title}.mp3"

            if target_path.exists() and target_path.stat().st_size > 0:
                return {
                    "title": title or "douyin_audio",
                    "output_path": str(target_path),
                    "file_name": target_path.name,
                    "platform": "douyin",
                    "already_existed": True,
                }

            temp_video = output_dir_path / f".tmp_douyin_{clean_title}.mp4"
            try:
                download_direct_stream_with_resume(direct_url, temp_video)

                if temp_video.exists() and temp_video.stat().st_size > 0:
                    if ffmpeg_path and convert_video_to_mp3(temp_video, target_path):
                        embed_mp3_metadata(str(target_path), title, "Douyin Creator", None)
                    else:
                        raise RuntimeError("Cần FFmpeg để trích xuất âm thanh MP3 từ Douyin.")
            finally:
                if temp_video.exists():
                    try:
                        temp_video.unlink()
                    except Exception:
                        pass

            if target_path.exists() and target_path.stat().st_size > 0:
                return {
                    "title": title or "douyin_audio",
                    "output_path": str(target_path),
                    "file_name": target_path.name,
                    "platform": "douyin",
                }
        except Exception:
            pass

    options = build_audio_download_options(str(output_dir_path), quality=quality, platform=platform)
    if progress_hook is not None:
        options["progress_hooks"] = [progress_hook]

    candidates = get_candidate_urls(url, platform)
    info = None
    downloaded_file = None
    last_error = None
    thumbnail_url = None
    author_name = "TikTok Creator"

    for candidate_url in candidates:
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(candidate_url, download=True)
                if info:
                    prepared_filename = downloader.prepare_filename(info)
                    downloaded_file = Path(prepared_filename)
                    thumbnail_url = info.get("thumbnail")
                    author_name = info.get("uploader") or info.get("uploader_id") or "TikTok Creator"

                    if not downloaded_file.exists():
                        for ext in [".mp3", ".m4a", ".aac", ".wav", ".mp4"]:
                            variant = downloaded_file.with_suffix(ext)
                            if variant.exists():
                                downloaded_file = variant
                                break

                    if not downloaded_file or not downloaded_file.exists():
                        found = locate_downloaded_file(str(output_dir_path), info.get("title"))
                        if found:
                            downloaded_file = found
                    break
        except Exception as exc:
            last_error = exc
            continue

    if not info or not downloaded_file or not downloaded_file.exists():
        raise RuntimeError(f"Không thể tải âm thanh lúc này: {last_error or 'Lỗi trích xuất audio'}") from last_error

    ffmpeg_path = _get_ffmpeg_path()
    title = info.get("title") or downloaded_file.stem
    clean_title = sanitize_filename(title)
    
    real_u_date = upload_date or str(info.get("upload_date") or "")
    date_prefix = f"[{real_u_date[:4]}-{real_u_date[4:6]}-{real_u_date[6:]}]_" if real_u_date and len(real_u_date) == 8 else ""

    target_mp3 = output_dir_path / f"{date_prefix}{clean_title}.mp3"

    if downloaded_file.suffix.lower() == ".mp3":
        if downloaded_file != target_mp3:
            try:
                if target_mp3.exists():
                    target_mp3.unlink()
                downloaded_file.rename(target_mp3)
            except Exception:
                pass
        final_path = target_mp3 if target_mp3.exists() else downloaded_file
    elif ffmpeg_path and convert_video_to_mp3(downloaded_file, target_mp3):
        try:
            if downloaded_file != target_mp3 and downloaded_file.exists():
                downloaded_file.unlink()
        except Exception:
            pass
        final_path = target_mp3
    else:
        raise RuntimeError("Cần FFmpeg để trích xuất tệp âm thanh MP3 chuẩn. Vui lòng kiểm tra cài đặt FFmpeg.")

    embed_mp3_metadata(str(final_path), title, author_name, thumbnail_url)

    return {
        "title": title or f"{platform}_audio",
        "output_path": str(final_path),
        "file_name": final_path.name,
        "platform": platform,
    }


def locate_downloaded_file(output_dir: str, expected_title: Optional[str] = None) -> Optional[Path]:
    output_path = Path(output_dir).expanduser().resolve()
    if not output_path.exists():
        return None

    candidates = [
        p for p in output_path.iterdir()
        if p.is_file() and not p.name.endswith(".part") and p.suffix.lower() in {".mp4", ".m4a", ".webm", ".mp3", ".aac", ".unknown_video", ".mpv"}
    ]
    if not candidates:
        candidates = [
            p for p in output_path.iterdir()
            if p.is_file() and not p.name.endswith(".part")
        ]

    if not candidates:
        return None

    if expected_title:
        expected = sanitize_filename(expected_title).lower()
        if expected.strip("_"):
            for candidate in candidates:
                if expected in candidate.stem.lower():
                    return candidate

    return max(candidates, key=lambda item: item.stat().st_mtime)


def build_watermark_removal_command(
    input_path: Path,
    output_path: Path,
    crop_ratio: float = 0.12,
    ffmpeg_executable: Optional[str] = None,
) -> list[str]:
    if crop_ratio <= 0 or crop_ratio >= 1:
        raise ValueError("crop_ratio cần nằm giữa 0 và 1.")

    exe = ffmpeg_executable or _get_ffmpeg_path() or "ffmpeg"
    return [
        exe,
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


def remove_watermark(input_path: Path, output_dir: str) -> Path:
    ffmpeg_path = _get_ffmpeg_path()
    if not ffmpeg_path:
        return input_path

    output_path = Path(output_dir).expanduser().resolve() / f"{input_path.stem}_clean.mp4"
    command = build_watermark_removal_command(input_path, output_path, ffmpeg_executable=ffmpeg_path)
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Không thể xử lý watermark. Chi tiết: {completed.stderr.strip() or completed.stdout.strip()}")

    return output_path


def download_video(
    url: str,
    output_dir: str,
    progress_hook: Optional[Callable[[dict], None]] = None,
    quality: str = "best",
    platform_choice: str = "tiktok",
    remove_watermark_flag: bool = True,
    upload_date: Optional[str] = None,
) -> dict:
    cleaned_url = extract_url(url)
    if not cleaned_url:
        raise ValueError("Liên kết không hợp lệ.")

    platform = detect_platform(cleaned_url, user_choice=platform_choice)
    output_dir_path = Path(output_dir).expanduser().resolve()
    output_dir_path.mkdir(parents=True, exist_ok=True)

    _ensure_latest_ytdlp()

    # Xử lý ưu tiên tải Douyin bằng giải mã luồng CDN không logo trực tiếp (hỗ trợ Resume)
    if platform == "douyin":
        try:
            title, direct_url = resolve_douyin_direct(cleaned_url)
            clean_title = sanitize_filename(title)
            date_prefix = f"[{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}]_" if upload_date and len(upload_date) == 8 else ""
            output_file = output_dir_path / f"{date_prefix}{clean_title}.mp4"

            if output_file.exists() and output_file.stat().st_size > 0:
                return {
                    "title": title or "douyin_video",
                    "output_path": str(output_file),
                    "file_name": output_file.name,
                    "platform": "douyin",
                    "already_existed": True,
                }

            download_direct_stream_with_resume(direct_url, output_file)

            if output_file.exists() and output_file.stat().st_size > 0:
                return {
                    "title": title or "douyin_video",
                    "output_path": str(output_file),
                    "file_name": output_file.name,
                    "platform": "douyin",
                }
        except Exception:
            pass

    options = build_video_download_options(str(output_dir_path), quality=quality, platform=platform)
    if progress_hook is not None:
        options["progress_hooks"] = [progress_hook]

    candidates = get_candidate_urls(url, platform)
    info = None
    downloaded_file = None
    last_error = None

    for candidate_url in candidates:
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(candidate_url, download=True)
                if info:
                    prepared_filename = downloader.prepare_filename(info)
                    downloaded_file = Path(prepared_filename)
                    if not downloaded_file.exists():
                        mp4_variant = downloaded_file.with_suffix(".mp4")
                        if mp4_variant.exists():
                            downloaded_file = mp4_variant
                        else:
                            found = locate_downloaded_file(str(output_dir_path), info.get("title"))
                            if found:
                                downloaded_file = found
                    break
        except Exception as exc:
            last_error = exc
            continue

    if not info or not downloaded_file:
        raise RuntimeError(f"Không thể tải video lúc này: {last_error or 'Lỗi trích xuất video'}") from last_error

    title = info.get("title") or downloaded_file.stem
    real_u_date = upload_date or str(info.get("upload_date") or "")
    
    if real_u_date and len(real_u_date) == 8:
        date_prefix = f"[{real_u_date[:4]}-{real_u_date[4:6]}-{real_u_date[6:]}]_"
        clean_title = sanitize_filename(title)
        dated_path = output_dir_path / f"{date_prefix}{clean_title}{downloaded_file.suffix}"
        try:
            if downloaded_file.exists() and downloaded_file != dated_path:
                downloaded_file.rename(dated_path)
                downloaded_file = dated_path
        except Exception:
            pass

    final_file = downloaded_file

    if remove_watermark_flag and downloaded_file and downloaded_file.exists():
        if progress_hook is not None:
            progress_hook({"status": "removing_watermark"})
        try:
            cleaned_file = remove_watermark(downloaded_file, str(output_dir_path))
            if cleaned_file and cleaned_file.exists():
                try:
                    if downloaded_file != cleaned_file and downloaded_file.exists():
                        downloaded_file.unlink()
                except Exception:
                    pass
                final_file = cleaned_file
        except Exception:
            final_file = downloaded_file

    return {
        "title": title or f"{platform}_video",
        "output_path": str(final_file),
        "file_name": final_file.name,
        "platform": platform,
    }
