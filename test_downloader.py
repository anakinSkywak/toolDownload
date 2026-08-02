from pathlib import Path

from downloader import (
    _get_ffmpeg_path,
    build_audio_download_options,
    build_video_download_options,
    build_watermark_removal_command,
    detect_platform,
    extract_channel_username,
    extract_url,
    get_candidate_urls,
    normalize_url,
    resolve_douyin_direct,
)


def test_build_watermark_removal_command_uses_ffmpeg() -> None:
    input_path = Path("video.mp4")
    output_path = Path("video_clean.mp4")
    command = build_watermark_removal_command(input_path, output_path, ffmpeg_executable="ffmpeg")

    assert command[0] == "ffmpeg"
    assert command[1] == "-y"
    assert command[2] == "-i"
    assert command[3] == str(input_path)
    assert command[-1] == str(output_path)


def test_build_audio_download_options() -> None:
    options = build_audio_download_options("/tmp/out", title="demo", quality="best", platform="tiktok")

    assert options["format"] == "bestaudio/best"
    assert "/tmp/out" in options["outtmpl"] or r"\tmp\out" in options["outtmpl"]
    if _get_ffmpeg_path():
        assert options["postprocessors"][0]["key"] == "FFmpegExtractAudio"
        assert options["postprocessors"][0]["preferredcodec"] == "mp3"
    else:
        assert options["postprocessors"] == []



def test_build_video_download_options() -> None:
    options = build_video_download_options("/tmp/out", title="demo", quality="best", platform="tiktok")

    assert options["format"] == "best[ext=mp4]/bestvideo+bestaudio/best"
    if _get_ffmpeg_path():
        assert options["postprocessors"][0]["key"] == "FFmpegVideoConvertor"
    else:
        assert options["postprocessors"] == []


def test_get_ffmpeg_path_returns_executable() -> None:
    path = _get_ffmpeg_path()
    if path:
        assert Path(path).exists()


def test_tiktok_options_use_android_headers_and_client() -> None:
    options = build_video_download_options("/tmp/out", title="demo", quality="best", platform="tiktok")

    assert options["http_headers"]["Referer"] == "https://www.tiktok.com/"


def test_douyin_options_use_ios_headers_and_client() -> None:
    options = build_video_download_options("/tmp/out", title="demo", quality="best", platform="douyin")

    assert options["http_headers"]["Referer"] == "https://www.douyin.com/"


def test_detect_platform_supports_short_links() -> None:
    assert detect_platform("https://vt.tiktok.com/ZSjxxxx/") == "tiktok"
    assert detect_platform("https://vm.tiktok.com/ZSjxxxx/") == "tiktok"
    assert detect_platform("https://v.douyin.com/ixxxx/") == "douyin"


def test_normalize_url_converts_photo_to_video() -> None:
    photo_url = "https://www.tiktok.com/@thibith8/photo/7658639611387727111?is_from_webapp=1&sender_device=pc"
    normalized = normalize_url(photo_url)
    assert "/video/" in normalized
    assert "7658639611387727111" in normalized


def test_get_candidate_urls_generates_embed_fallback() -> None:
    photo_url = "https://www.tiktok.com/@thibith8/photo/7658639611387727111?is_from_webapp=1&sender_device=pc"
    candidates = get_candidate_urls(photo_url, "tiktok")
    assert any("embed/v2/7658639611387727111" in c for c in candidates)
    assert any("m.tiktok.com/v/7658639611387727111" in c for c in candidates)


def test_douyin_short_url_resolution() -> None:
    share_text = "7.64 Y@m.da ytr:/ 04/23 :7pm 回村以后 我过上了普通人里最好的生活 https://v.douyin.com/zgKsrar86lc/ 复制此链接"
    extracted = extract_url(share_text)
    assert extracted == "https://v.douyin.com/zgKsrar86lc/"

    title, direct_url = resolve_douyin_direct(extracted)
    assert title != ""
    assert "aweme.snssdk.com" in direct_url or "play" in direct_url


def test_extract_channel_username() -> None:
    assert extract_channel_username("https://www.tiktok.com/@thibith8") == "@thibith8"
    assert extract_channel_username("@thibith8") == "@thibith8"
