#!/usr/bin/env python3
"""
Sơ chế clip cho OpenReel Video:
- Đọc kế hoạch cắt dựng JSON (edit_plan.json).
- Cắt chính xác từng đoạn từ 02_video_tho bằng FFmpeg.
- Tự động crop/scale về chuẩn khung dọc TikTok 1080x1920 (9:16), 30fps, H.264.
- Xuất tuần tự clip_01.mp4, clip_02.mp4... vào 04_workspace/ready_for_openreel/01_clips/.
- Tùy chọn nối sẵn 1 video nháp không tiếng 00_video_nhap_da_ghep.mp4.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from project_manager import get_project_root

PROJECT_ROOT = get_project_root()


def configure_windows_ffmpeg_path() -> None:
    if os.name != "nt":
        return
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        return
    winget_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if not winget_dir.exists():
        return
    current_path = os.environ.get("PATH", "")
    for pkg in winget_dir.glob("Gyan.FFmpeg*"):
        for exe in pkg.rglob("ffmpeg.exe"):
            bin_dir = str(exe.parent)
            if bin_dir not in current_path:
                os.environ["PATH"] = bin_dir + os.pathsep + current_path
            break


def find_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(
        f"Không tìm thấy '{name}'. Vui lòng cài đặt FFmpeg và thêm vào PATH."
    )


def parse_timestamp(value: Any) -> float:
    """Chuyển đổi giây (float/int) hoặc chuỗi HH:MM:SS.mmm / MM:SS.mmm sang giây."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        raise ValueError("Mốc thời gian rỗng.")
    parts = text.split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        return int(parts[0]) * 60.0 + float(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600.0 + int(parts[1]) * 60.0 + float(parts[2])
    raise ValueError(f"Định dạng thời gian không hợp lệ: {value}")


def resolve_source_video(source_value: str, raw_dir: Path) -> Path:
    """Tìm file video nguồn theo đường dẫn tương đối, tuyệt đối hoặc tên file trong 02_video_tho."""
    candidate = Path(source_value)
    if candidate.is_absolute() and candidate.exists():
        return candidate

    rel_root = (PROJECT_ROOT / candidate).resolve()
    if rel_root.exists():
        return rel_root

    in_raw = (raw_dir / candidate).resolve()
    if in_raw.exists():
        return in_raw

    in_raw_name = (raw_dir / candidate.name).resolve()
    if in_raw_name.exists():
        return in_raw_name

    raise FileNotFoundError(
        f"Không tìm thấy video nguồn '{source_value}' trong dự án hoặc '{raw_dir}'."
    )


def probe_duration(ffprobe_bin: str, media_path: Path) -> float:
    cmd = [
        ffprobe_bin,
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
    try:
        return round(float(res.stdout.strip()), 3)
    except ValueError:
        return 0.0


def build_video_filter(
    width: int,
    height: int,
    fps: int,
    speed: float,
    crop_mode: str,
) -> str:
    """Tạo filter FFmpeg chuẩn hóa về khung dọc 9:16 (1080x1920), fps đồng nhất."""
    filters: list[str] = []
    if speed != 1.0:
        filters.append(f"setpts=PTS/{speed:.4f}")

    if crop_mode == "blur_bg":
        # Giữ toàn bộ khung hình ngang trên nền mờ 9:16 + làm nét & cân màu nhẹ sản phẩm
        return (
            f"{','.join(filters) + ',' if filters else ''}"
            f"split=2[bg][fg];"
            f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=20:5[bg_blur];"
            f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"unsharp=3:3:0.55:3:3:0.0,eq=contrast=1.03:saturation=1.05[fg_scaled];"
            f"[bg_blur][fg_scaled]overlay=(W-w)/2:(H-h)/2,fps={fps},setsar=1"
        )

    # Mặc định ("center"): crop tỉ lệ 9:16 lấy trung tâm, scale lên 1080x1920 + làm nét nhẹ bao bì
    filters.append("crop='min(iw,ih*9/16)':'min(ih,iw*16/9)'")
    filters.append(f"scale={width}:{height}:flags=lanczos")
    filters.append("unsharp=3:3:0.55:3:3:0.0")
    filters.append("eq=contrast=1.03:saturation=1.05")
    filters.append("setsar=1")
    filters.append(f"fps={fps}")
    return ",".join(filters)


def cut_and_normalize_clip(
    ffmpeg_bin: str,
    src_path: Path,
    dst_path: Path,
    start_sec: float,
    end_sec: float,
    width: int,
    height: int,
    fps: int,
    speed: float,
    crop_mode: str,
    keep_audio: bool,
) -> None:
    if end_sec <= start_sec:
        raise ValueError(
            f"Thời gian kết thúc ({end_sec}s) phải lớn hơn bắt đầu ({start_sec}s) cho {src_path.name}."
        )

    duration = end_sec - start_sec
    vf = build_video_filter(width, height, fps, speed, crop_mode)

    cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_sec:.3f}",
        "-i",
        str(src_path),
        "-t",
        f"{duration:.3f}",
    ]

    if crop_mode == "blur_bg":
        cmd.extend(["-filter_complex", f"[0:v]{vf}[vout]", "-map", "[vout]"])
    else:
        cmd.extend(["-vf", vf])

    if keep_audio:
        if speed != 1.0 and 0.5 <= speed <= 2.0:
            cmd.extend(["-af", f"atempo={speed:.4f}"])
        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"])
    else:
        cmd.append("-an")

    vcodec, vcodec_args = _get_h264_encoder(ffmpeg_bin)
    cmd.extend(
        [
            "-c:v",
            vcodec,
            *vcodec_args,
            "-pix_fmt",
            "yuv420p",
            "-map_metadata",
            "-1",
            "-movflags",
            "+faststart",
            str(dst_path),
        ]
    )
    subprocess.run(cmd, check=True)


_HW_ENC_CACHE: tuple[str, list[str]] | None = None


def _get_h264_encoder(ffmpeg_bin: str) -> tuple[str, list[str]]:
    global _HW_ENC_CACHE
    if _HW_ENC_CACHE is not None:
        return _HW_ENC_CACHE
    for enc, extra in (
        ("h264_qsv", ["-global_quality", "18"]),
        ("h264_nvenc", ["-cq", "18"]),
    ):
        try:
            r = subprocess.run(
                [ffmpeg_bin, "-hide_banner", "-f", "lavfi", "-i", "color=c=black:s=640x480:d=0.1,format=yuv420p", "-c:v", enc, "-f", "null", "-"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0:
                _HW_ENC_CACHE = (enc, extra)
                return _HW_ENC_CACHE
        except Exception:
            pass
    _HW_ENC_CACHE = ("libx264", ["-preset", "medium", "-crf", "18"])
    return _HW_ENC_CACHE


def concat_clips_to_draft(
    ffmpeg_bin: str,
    clip_paths: list[Path],
    output_path: Path,
) -> None:
    """Nối các clip đã chuẩn hóa thành 1 video nháp không tiếng để kéo nhanh vào OpenReel."""
    list_file = output_path.parent / "_concat_list.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in clip_paths]
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-an",
            "-c:v",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        subprocess.run(cmd, check=True)
    finally:
        if list_file.exists():
            list_file.unlink()


def main() -> int:
    configure_windows_ffmpeg_path()

    parser = argparse.ArgumentParser(
        description="Cắt và chuẩn hóa clip dọc TikTok (1080x1920) từ JSON cho OpenReel Video."
    )
    parser.add_argument(
        "--config",
        default="04_workspace/edit_plan.json",
        help="Đường dẫn file JSON cấu trúc dựng (mặc định: 04_workspace/edit_plan.json).",
    )
    parser.add_argument(
        "--raw-dir",
        default="02_video_tho",
        help="Thư mục chứa video thô gốc (mặc định: 02_video_tho).",
    )
    parser.add_argument(
        "--output-dir",
        default="04_workspace/ready_for_openreel/01_clips",
        help="Thư mục xuất clip_01.mp4, clip_02.mp4... (mặc định: 04_workspace/ready_for_openreel/01_clips).",
    )
    parser.add_argument(
        "--concat",
        dest="concat",
        action="store_true",
        default=None,
        help="Nối sẵn thành 00_video_nhap_da_ghep.mp4 (không tiếng).",
    )
    parser.add_argument(
        "--no-concat",
        dest="concat",
        action="store_false",
        help="Không tạo file video nháp đã ghép.",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (PROJECT_ROOT / config_path).resolve()
    if not config_path.exists():
        print(f"[LỖI] Không tìm thấy file cấu trúc dựng JSON: {config_path}", file=sys.stderr)
        return 1

    raw_dir = Path(args.raw_dir)
    if not raw_dir.is_absolute():
        raw_dir = (PROJECT_ROOT / raw_dir).resolve()

    clips_out_dir = Path(args.output_dir)
    if not clips_out_dir.is_absolute():
        clips_out_dir = (PROJECT_ROOT / clips_out_dir).resolve()
    clips_out_dir.mkdir(parents=True, exist_ok=True)

    # Xóa clip cũ của lần dựng trước để tránh nhầm lẫn
    for old_clip in clips_out_dir.glob("clip_*.mp4"):
        old_clip.unlink()

    plan = json.loads(config_path.read_text(encoding="utf-8-sig"))
    clips = plan.get("clips", [])
    if not clips:
        print("[LỖI] Danh sách 'clips' trong JSON đang trống.", file=sys.stderr)
        return 1

    res = plan.get("target_resolution", [1080, 1920])
    target_w, target_h = int(res[0]), int(res[1])
    target_fps = int(plan.get("target_fps", 30))
    default_keep_audio = bool(plan.get("keep_clip_audio", False))
    should_concat = args.concat if args.concat is not None else bool(plan.get("concat_draft", True))

    ffmpeg_bin = find_binary("ffmpeg")
    ffprobe_bin = find_binary("ffprobe")

    cache_dir = clips_out_dir.parent / ".clip_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    prepared_jobs: list[dict[str, Any]] = []
    for idx, item in enumerate(clips, start=1):
        src_path = resolve_source_video(item["source"], raw_dir)
        start_sec = parse_timestamp(item["start"])
        if "end" in item and item["end"] is not None:
            end_sec = parse_timestamp(item["end"])
        elif "duration" in item and item["duration"] is not None:
            end_sec = start_sec + float(item["duration"])
        else:
            raise ValueError(f"Clip #{idx} thiếu 'end' hoặc 'duration'.")

        speed = float(item.get("speed", 1.0))
        crop_mode = str(item.get("crop_mode", "center"))
        if "mute" in item:
            keep_audio = not bool(item["mute"])
        else:
            keep_audio = default_keep_audio

        out_name = f"clip_{idx:02d}.mp4"
        out_path = clips_out_dir / out_name
        src_mtime = round(src_path.stat().st_mtime, 2)
        key_payload = json.dumps(
            [
                str(src_path.resolve()),
                src_mtime,
                round(start_sec, 3),
                round(end_sec, 3),
                round(speed, 3),
                crop_mode,
                target_w,
                target_h,
                target_fps,
                keep_audio,
                "polish_v2",
            ],
            ensure_ascii=False,
        )
        cache_key = hashlib.sha1(key_payload.encode("utf-8")).hexdigest()[:16]
        cached_path = cache_dir / f"{cache_key}.mp4"

        prepared_jobs.append(
            {
                "idx": idx,
                "item": item,
                "src_path": src_path,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "speed": speed,
                "crop_mode": crop_mode,
                "keep_audio": keep_audio,
                "out_name": out_name,
                "out_path": out_path,
                "cached_path": cached_path,
            }
        )

    def _process_clip_job(job: dict[str, Any]) -> tuple[dict[str, Any], float, bool]:
        out_p: Path = job["out_path"]
        cached_p: Path = job["cached_path"]
        hit = cached_p.exists() and cached_p.stat().st_size > 1024
        if hit:
            shutil.copy2(cached_p, out_p)
        else:
            cut_and_normalize_clip(
                ffmpeg_bin=ffmpeg_bin,
                src_path=job["src_path"],
                dst_path=out_p,
                start_sec=job["start_sec"],
                end_sec=job["end_sec"],
                width=target_w,
                height=target_h,
                fps=target_fps,
                speed=job["speed"],
                crop_mode=job["crop_mode"],
                keep_audio=job["keep_audio"],
            )
            tmp_cache = cached_p.with_suffix(".tmp.mp4")
            shutil.copy2(out_p, tmp_cache)
            os.replace(tmp_cache, cached_p)
        dur_val = probe_duration(ffprobe_bin, out_p)
        return job, dur_val, hit

    results_by_idx: dict[int, tuple[dict[str, Any], float, bool]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, max(1, len(prepared_jobs)))) as pool:
        futures = [pool.submit(_process_clip_job, j) for j in prepared_jobs]
        for fut in concurrent.futures.as_completed(futures):
            j_res, actual_dur, cache_hit = fut.result()
            results_by_idx[j_res["idx"]] = (j_res, actual_dur, cache_hit)

    generated_clips: list[Path] = []
    report_items: list[dict[str, Any]] = []
    total_duration = 0.0
    cache_hits = 0

    for idx in sorted(results_by_idx.keys()):
        job, actual_dur, cache_hit = results_by_idx[idx]
        item = job["item"]
        src_path = job["src_path"]
        start_sec = job["start_sec"]
        end_sec = job["end_sec"]
        speed = job["speed"]
        out_name = job["out_name"]
        out_path = job["out_path"]
        if cache_hit:
            cache_hits += 1
        tag = "[CACHE HIT]" if cache_hit else "[CUT+POLISH]"
        print(
            f"[{idx}/{len(clips)}] {tag} {src_path.name} ({start_sec:.2f}s -> {end_sec:.2f}s, x{speed}) => {out_name} ({actual_dur:.2f}s)"
        )
        total_duration += actual_dur
        generated_clips.append(out_path)
        report_items.append(
            {
                "clip": out_name,
                "source": src_path.name,
                "start": start_sec,
                "end": end_sec,
                "speed": speed,
                "actual_duration_sec": actual_dur,
                "beat_index": item.get("beat_index"),
                "spoken_text": item.get("spoken_text", ""),
                "callout_text": item.get("callout_text", ""),
                "zoom_mode": item.get("zoom_mode"),
                "zoom_from": item.get("zoom_from") if item.get("zoom_from") is not None else 1.0,
                "zoom_to": item.get("zoom_to"),
                "pan_x": item.get("pan_x", 0),
                "pan_y": item.get("pan_y", 0),
                "transition_type": item.get("transition_type"),
                "feature_pill": item.get("feature_pill", ""),
                "note": item.get("note", ""),
                "cache_hit": cache_hit,
            }
        )

    draft_path = clips_out_dir.parent / "00_video_nhap_da_ghep.mp4"
    if should_concat and generated_clips:
        print(f"Đang nối {len(generated_clips)} clip thành video nháp không tiếng...")
        concat_clips_to_draft(ffmpeg_bin, generated_clips, draft_path)
        print(f"  -> Đã tạo: {draft_path}")
    elif draft_path.exists():
        draft_path.unlink()

    report_path = clips_out_dir.parent / "clips_manifest.json"
    report_path.write_text(
        json.dumps(
            {
                "resolution": f"{target_w}x{target_h}",
                "fps": target_fps,
                "total_duration_sec": round(total_duration, 3),
                "clip_count": len(generated_clips),
                "cache_hits": cache_hits,
                "draft_video": str(draft_path.relative_to(PROJECT_ROOT))
                if should_concat and draft_path.exists()
                else None,
                "clips": report_items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"\n[HOÀN TẤT] Đã xuất {len(generated_clips)} clip ({target_w}x{target_h}, cache_hits={cache_hits}/{len(generated_clips)}), tổng thời lượng: {total_duration:.2f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
