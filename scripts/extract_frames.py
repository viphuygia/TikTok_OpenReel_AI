#!/usr/bin/env python3
"""
Trích xuất khung hình (1 ảnh/giây mặc định) và lời thoại gốc từ video mẫu / video thô.
Hỗ trợ chạy trên Windows, macOS và Linux; tự động dò GPU/CPU cho Faster-Whisper.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".ts", ".flv"}
from project_manager import get_project_root

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = get_project_root()


def configure_windows_tool_paths() -> None:
    """Bổ sung đường dẫn FFmpeg (WinGet) và CUDA DLL (trong venv) trên Windows."""
    if os.name != "nt":
        return

    extra_dirs: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_dir.exists():
            for pkg in winget_dir.glob("Gyan.FFmpeg*"):
                for exe in pkg.rglob("ffmpeg.exe"):
                    extra_dirs.append(exe.parent)
                    break

    # Thêm các thư mục DLL của PyTorch / NVIDIA trong venv để ctranslate2 tìm thấy CUDA/cuDNN
    site_pkgs = Path(sys.executable).resolve().parent.parent / "Lib" / "site-packages"
    for rel in [Path("torch/lib"), Path("ctranslate2")]:
        p = site_pkgs / rel
        if p.exists():
            extra_dirs.append(p)
    nvidia_dir = site_pkgs / "nvidia"
    if nvidia_dir.exists():
        for bin_dir in nvidia_dir.glob("*/bin"):
            if bin_dir.is_dir():
                extra_dirs.append(bin_dir)

    current_path = os.environ.get("PATH", "")
    for d in extra_dirs:
        s = str(d)
        if s not in current_path:
            current_path = s + os.pathsep + current_path
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(s)
            except OSError:
                pass
    os.environ["PATH"] = current_path


configure_windows_tool_paths()


def find_binary(name: str) -> str:
    """Tìm binary ffmpeg hoặc ffprobe."""
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(
        f"Không tìm thấy '{name}'. Hãy chắc chắn đã cài đặt FFmpeg và thêm vào PATH."
    )


def natural_sort_key(path: Path) -> list[Any]:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path.name)]


def probe_video(ffprobe_bin: str, video_path: Path) -> dict[str, Any]:
    """Lấy thông tin độ phân giải, thời lượng, fps và luồng âm thanh bằng ffprobe."""
    cmd = [
        ffprobe_bin,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
    info = json.loads(res.stdout)

    video_stream = next(
        (s for s in info.get("streams", []) if s.get("codec_type") == "video"), None
    )
    audio_stream = next(
        (s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None
    )
    duration = float(info.get("format", {}).get("duration") or 0.0)
    if duration == 0.0 and video_stream and video_stream.get("duration"):
        duration = float(video_stream["duration"])

    width = int(video_stream.get("width", 0)) if video_stream else 0
    height = int(video_stream.get("height", 0)) if video_stream else 0

    fps = 0.0
    if video_stream and video_stream.get("r_frame_rate"):
        num, _, den = video_stream["r_frame_rate"].partition("/")
        try:
            fps = round(float(num) / float(den or 1), 2)
        except ZeroDivisionError:
            fps = 0.0

    return {
        "file": str(video_path.relative_to(PROJECT_ROOT))
        if video_path.is_relative_to(PROJECT_ROOT)
        else str(video_path),
        "filename": video_path.name,
        "duration_sec": round(duration, 3),
        "width": width,
        "height": height,
        "fps": fps,
        "has_audio": audio_stream is not None,
    }


def extract_frames_for_video(
    ffmpeg_bin: str,
    video_path: Path,
    out_dir: Path,
    fps: float,
    max_width: int,
) -> list[str]:
    """Trích xuất ảnh JPG theo fps và max_width, trả về danh sách file đã tạo."""
    if out_dir.exists():
        for old_img in out_dir.glob("frame_*.jpg"):
            old_img.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)

    vf = f"fps={fps},scale='min({max_width},iw)':-2"
    pattern = str(out_dir / "frame_%04d.jpg")
    cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        vf,
        "-q:v",
        "4",
        pattern,
    ]
    subprocess.run(cmd, check=True)
    frames = sorted(out_dir.glob("frame_*.jpg"), key=natural_sort_key)
    return [f.name for f in frames]


def format_srt_timestamp(seconds: float) -> str:
    ms_total = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(ms_total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def format_short_time(seconds: float) -> str:
    mins, secs = divmod(max(0.0, seconds), 60.0)
    return f"{int(mins):02d}:{secs:05.2f}"


def patch_av_open() -> None:
    """Đảm bảo av.open tương thích giữa faster-whisper và PyAV >= 17 (bỏ metadata_errors)."""
    import av

    if getattr(av.open, "_tiktok_patched", False):
        return
    orig_open = av.open

    def compat_open(*args: Any, **kwargs: Any):
        try:
            return orig_open(*args, **kwargs)
        except TypeError:
            kwargs.pop("metadata_errors", None)
            return orig_open(*args, **kwargs)

    compat_open._tiktok_patched = True  # type: ignore[attr-defined]
    av.open = compat_open


def _preload_cuda_dlls() -> bool:
    """Nạp sẵn CUDA/cuBLAS DLL trên Windows; trả về False nếu thiếu cublas64_12.dll."""
    if os.name != "nt":
        return True
    import ctypes

    configure_windows_tool_paths()
    site_pkgs = Path(sys.executable).resolve().parent.parent / "Lib" / "site-packages"
    search_dirs = [site_pkgs / "torch" / "lib", site_pkgs / "ctranslate2"]
    nvidia_dir = site_pkgs / "nvidia"
    if nvidia_dir.exists():
        search_dirs.extend(p for p in nvidia_dir.glob("*/bin") if p.is_dir())

    for d in search_dirs:
        if not d.exists():
            continue
        for pat in ("cudart64_*.dll", "cublasLt64_12.dll", "cublas64_12.dll", "cudnn64_*.dll"):
            for dll_p in d.glob(pat):
                try:
                    ctypes.WinDLL(str(dll_p))
                except OSError:
                    pass

    for candidate in [*(d / "cublas64_12.dll" for d in search_dirs if d.exists()), Path("cublas64_12.dll")]:
        try:
            ctypes.WinDLL(str(candidate))
            return True
        except OSError:
            continue
    return False


def load_whisper_model(model_size: str):
    """Khởi tạo Faster-Whisper, tự động ưu tiên CUDA nếu khả dụng, fallback sang CPU."""
    patch_av_open()
    from faster_whisper import WhisperModel

    use_cuda = False
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0 and _preload_cuda_dlls():
            use_cuda = True
    except Exception:
        use_cuda = False

    if use_cuda:
        for compute_type in ("float16", "int8_float16", "int8"):
            try:
                model = WhisperModel(model_size, device="cuda", compute_type=compute_type)
                print(f"  [Whisper] Đã nạp model '{model_size}' trên GPU CUDA ({compute_type}).")
                return model
            except Exception as exc:
                print(f"  [Whisper] Thử CUDA {compute_type} thất bại ({exc}), chuyển cấu hình...")

    print(f"  [Whisper] Đang nạp model '{model_size}' trên CPU (int8)...")
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe_video(
    ffmpeg_bin: str,
    whisper_model: Any,
    video_path: Path,
    out_dir: Path,
    language: str,
    model_size: str = "small",
) -> dict[str, Any]:
    """Tách âm thanh tạm và bóc lời thoại bằng Faster-Whisper."""
    from faster_whisper import WhisperModel

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = Path(tmp.name)

    try:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(tmp_wav),
        ]
        subprocess.run(cmd, check=True)

        def _run_transcribe(mdl: Any) -> tuple[list[dict[str, Any]], Any]:
            segments_iter, tr_info = mdl.transcribe(
                str(tmp_wav),
                language=language if language != "auto" else None,
                beam_size=5,
                vad_filter=True,
                word_timestamps=True,
            )
            out_segs: list[dict[str, Any]] = []
            for seg in segments_iter:
                text = seg.text.strip()
                if not text:
                    continue
                out_segs.append(
                    {
                        "start": round(float(seg.start), 3),
                        "end": round(float(seg.end), 3),
                        "text": text,
                    }
                )
            return out_segs, tr_info

        try:
            segments, info = _run_transcribe(whisper_model)
        except Exception as exc:
            print(f"  [Whisper WARN] Lỗi GPU ({exc}) -> Tự động chuyển sang CPU (int8)...")
            cpu_model = WhisperModel(model_size, device="cpu", compute_type="int8")
            segments, info = _run_transcribe(cpu_model)
    finally:
        if tmp_wav.exists():
            tmp_wav.unlink()

    txt_lines = [
        f"[{format_short_time(s['start'])} -> {format_short_time(s['end'])}] {s['text']}"
        for s in segments
    ]
    full_text = " ".join(s["text"] for s in segments)

    srt_lines = []
    for idx, s in enumerate(segments, start=1):
        srt_lines.append(
            f"{idx}\n"
            f"{format_srt_timestamp(s['start'])} --> {format_srt_timestamp(s['end'])}\n"
            f"{s['text']}\n"
        )

    (out_dir / "transcript.txt").write_text(
        "\n".join(txt_lines) + ("\n" if txt_lines else ""), encoding="utf-8"
    )
    (out_dir / "transcript.srt").write_text("\n".join(srt_lines), encoding="utf-8")
    (out_dir / "transcript.json").write_text(
        json.dumps(
            {
                "language": getattr(info, "language", language),
                "full_text": full_text,
                "segments": segments,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "language": getattr(info, "language", language),
        "full_text": full_text,
        "segments": segments,
    }


def collect_videos(source_path: Path) -> list[Path]:
    if source_path.is_file():
        return [source_path] if source_path.suffix.lower() in VIDEO_EXTENSIONS else []
    if not source_path.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục/tệp nguồn: {source_path}")
    videos = [
        p
        for p in source_path.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    ]
    return sorted(videos, key=natural_sort_key)


def sanitize_stem(name: str) -> str:
    cleaned = re.sub(r"[^\w\-.]+", "_", name, flags=re.UNICODE).strip("._")
    return cleaned or "video"


def main() -> int:
    configure_windows_tool_paths()

    parser = argparse.ArgumentParser(
        description="Trích xuất khung hình (1fps) và lời thoại gốc từ video TikTok."
    )
    parser.add_argument(
        "--source",
        default="01_video_mau",
        help="Thư mục hoặc file video nguồn (mặc định: 01_video_mau; hoặc truyền 02_video_tho).",
    )
    parser.add_argument(
        "--output-dir",
        default="04_workspace/frames",
        help="Thư mục gốc lưu khung hình (mặc định: 04_workspace/frames).",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=1.0,
        help="Số khung hình trích xuất mỗi giây (mặc định: 1.0).",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=540,
        help="Chiều rộng tối đa của ảnh trích xuất để tiết kiệm token (mặc định: 540px).",
    )
    parser.add_argument(
        "--transcribe",
        choices=["auto", "always", "never"],
        default="auto",
        help="Chế độ bóc lời thoại: auto (tự bật với 01_video_mau), always, hoặc never.",
    )
    parser.add_argument(
        "--whisper-model",
        default="small",
        help="Kích thước model Faster-Whisper (tiny, base, small, medium, large-v3-turbo). Mặc định: small.",
    )
    parser.add_argument(
        "--language",
        default="vi",
        help="Ngôn ngữ lời thoại (mặc định: vi; dùng 'auto' để tự nhận diện).",
    )
    args = parser.parse_args()

    norm_src = str(args.source or "").replace("\\", "/").strip("/")
    base_root = REPO_ROOT if norm_src == "01_video_mau" else PROJECT_ROOT

    source_path = Path(args.source)
    if not source_path.is_absolute():
        source_path = (base_root / source_path).resolve()

    out_root = Path(args.output_dir)
    if not out_root.is_absolute():
        out_root = (base_root / out_root).resolve()

    ffmpeg_bin = find_binary("ffmpeg")
    ffprobe_bin = find_binary("ffprobe")

    videos = collect_videos(source_path)
    if not videos:
        print(f"[THÔNG BÁO] Không tìm thấy file video nào trong: {source_path}")
        return 1

    source_bucket = source_path.parent.name if source_path.is_file() else source_path.name
    bucket_dir = out_root / source_bucket
    bucket_dir.mkdir(parents=True, exist_ok=True)

    should_transcribe = args.transcribe == "always" or (
        args.transcribe == "auto" and "01_video_mau" in str(source_path)
    )

    whisper_model = None
    if should_transcribe:
        whisper_model = load_whisper_model(args.whisper_model)

    manifest_items: list[dict[str, Any]] = []
    transcript_md_lines = [
        f"# Tổng hợp khung hình & lời thoại gốc ({source_bucket})",
        "",
    ]

    for idx, video_path in enumerate(videos, start=1):
        stem = sanitize_stem(video_path.stem)
        video_out_dir = bucket_dir / stem
        print(f"[{idx}/{len(videos)}] Đang xử lý: {video_path.name}")

        meta = probe_video(ffprobe_bin, video_path)
        frames = extract_frames_for_video(
            ffmpeg_bin=ffmpeg_bin,
            video_path=video_path,
            out_dir=video_out_dir,
            fps=args.fps,
            max_width=args.max_width,
        )
        meta["frames_dir"] = str(video_out_dir.relative_to(PROJECT_ROOT)) if video_out_dir.is_relative_to(PROJECT_ROOT) else str(video_out_dir)
        meta["frame_count"] = len(frames)
        meta["fps_extracted"] = args.fps
        meta["frames"] = frames

        # Lưu metadata ngay sau khi trích xuất frames để không bị mất thông số nếu bước âm thanh lỗi
        (video_out_dir / "metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        transcript_data = None
        if should_transcribe and meta["has_audio"] and whisper_model is not None:
            print(f"  -> Đang bóc lời thoại gốc ({video_path.name})...")
            try:
                transcript_data = transcribe_video(
                    ffmpeg_bin=ffmpeg_bin,
                    whisper_model=whisper_model,
                    video_path=video_path,
                    out_dir=video_out_dir,
                    language=args.language,
                    model_size=args.whisper_model,
                )
                meta["transcript"] = transcript_data
            except Exception as exc:
                print(f"  [WARN] Bóc thoại thất bại cho {video_path.name}: {exc}")

        (video_out_dir / "metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest_items.append(meta)

        transcript_md_lines.append(f"## {idx}. {video_path.name}")
        transcript_md_lines.append(
            f"- Thời lượng: **{meta['duration_sec']}s** | Độ phân giải: `{meta['width']}x{meta['height']}` | FPS gốc: `{meta['fps']}`"
        )
        transcript_md_lines.append(
            f"- Thư mục khung hình (`{len(frames)}` ảnh @ {args.fps} fps): `{meta['frames_dir']}`"
        )
        if transcript_data:
            transcript_md_lines.append("- Lời thoại theo mốc thời gian:")
            if transcript_data["segments"]:
                for seg in transcript_data["segments"]:
                    transcript_md_lines.append(
                        f"  - `[{format_short_time(seg['start'])} -> {format_short_time(seg['end'])}]` {seg['text']}"
                    )
            else:
                transcript_md_lines.append("  - *(Không phát hiện lời thoại)*")
        transcript_md_lines.append("")

        print(f"  -> Đã xuất {len(frames)} khung hình vào {meta['frames_dir']}")

    manifest_path = bucket_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_items, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary_filename = "loi_thoai_goc.md" if should_transcribe else "tom_tat_khung_hinh.md"
    summary_path = bucket_dir / summary_filename
    summary_path.write_text("\n".join(transcript_md_lines), encoding="utf-8")

    print(f"\n[HOÀN TẤT] Đã tổng hợp thông tin tại: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
