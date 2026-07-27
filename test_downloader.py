from pathlib import Path

from downloader import build_watermark_removal_command

# code kiểm tra xem lệnh loại bỏ watermark được xây dựng đúng cách
def test_build_watermark_removal_command_uses_ffmpeg() -> None:
    input_path = Path("video.mp4")
    output_path = Path("video_clean.mp4")
    command = build_watermark_removal_command(input_path, output_path)

    assert command[0] == "ffmpeg"
    assert command[1] == "-y"
    assert command[2] == "-i"
    assert command[3] == str(input_path)
    assert command[-1] == str(output_path)
