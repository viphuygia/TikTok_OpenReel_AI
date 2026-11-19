#!/usr/bin/env python3
"""Long-Form Vlog Timeline Engine (> 90s, up to 20 minutes) with chronological clip ordering & unified style."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import style_dna as _sd
from prepare_clips import find_binary, probe_duration

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEDIA_VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")


def _natural_sort_key(name: str) -> list[Any]:
    return [int(tok) if tok.isdigit() else tok.lower() for tok in re.split(r"(\d+)", name)]


def collect_ordered_raw_clips(
    raw_dir: Path,
    ordered_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Collect raw video files in strict chronological / user-specified order."""
    if not raw_dir.exists():
        return []
    ffprobe_bin = find_binary("ffprobe")
    all_files: dict[str, Path] = {}
    for p in sorted(raw_dir.rglob("*"), key=lambda x: _natural_sort_key(x.relative_to(raw_dir).as_posix())):
        if p.is_file() and p.suffix.lower() in MEDIA_VIDEO_EXTS:
            rel = p.relative_to(raw_dir).as_posix()
            all_files[rel] = p

    ordered_rels: list[str] = []
    if ordered_names:
        for nm in ordered_names:
            clean_nm = str(nm or "").strip().replace("\\", "/")
            if clean_nm in all_files and clean_nm not in ordered_rels:
                ordered_rels.append(clean_nm)
    for rel in all_files:
        if rel not in ordered_rels:
            ordered_rels.append(rel)

    out: list[dict[str, Any]] = []
    for idx, rel in enumerate(ordered_rels, start=1):
        p = all_files[rel]
        try:
            dur = round(float(probe_duration(ffprobe_bin, p)), 2)
        except Exception:
            dur = 5.0
        out.append(
            {
                "order": idx,
                "rel_path": rel,
                "abs_path": str(p),
                "name": p.name,
                "duration_sec": max(0.5, dur),
                "mtime": int(p.stat().st_mtime),
            }
        )
    return out


def build_longform_timeline_plan(
    ordered_clips: list[dict[str, Any]],
    target_duration_sec: float = 600.0,
    auto_fit_duration: bool = False,
    aspect_ratio: str = "16:9",
) -> dict[str, Any]:
    """Build a strict chronological timeline plan for videos > 90s (up to 1200s)."""
    if not ordered_clips:
        raise RuntimeError("Chưa có video thô nào trong 02_video_tho/ để dựng Timeline dài.")

    total_raw = sum(float(c.get("duration_sec") or 0.0) for c in ordered_clips)
    if auto_fit_duration or target_duration_sec <= 0:
        eff_target = max(95.0, min(1200.0, total_raw))
    else:
        eff_target = max(95.0, min(1200.0, float(target_duration_sec)))

    target_w, target_h = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
    segments: list[dict[str, Any]] = []

    if total_raw >= eff_target:
        # Allocate proportionally across clips in chronological order without ever reordering
        ratio = eff_target / max(1.0, total_raw)
        for idx, c in enumerate(ordered_clips, start=1):
            c_dur = float(c["duration_sec"])
            seg_dur = max(2.0, min(c_dur, round(c_dur * ratio, 2)))
            # Take centered or front slice cleanly
            start_sec = round(max(0.0, (c_dur - seg_dur) * 0.35), 2)
            end_sec = round(min(c_dur, start_sec + seg_dur), 2)
            segments.append(
                {
                    "index": idx,
                    "source": c["rel_path"],
                    "abs_path": c["abs_path"],
                    "start": start_sec,
                    "end": end_sec,
                    "duration": round(end_sec - start_sec, 2),
                    "speed": 1.0,
                }
            )
    else:
        # Gently slow down slightly if raw footage is slightly shorter, or loop timeline cleanly in chapter blocks
        needed = eff_target
        pass_idx = 0
        while needed > 1.0 and pass_idx < 6:
            pass_idx += 1
            for c in ordered_clips:
                if needed <= 0.5:
                    break
                c_dur = float(c["duration_sec"])
                use_dur = min(c_dur, needed)
                if use_dur < 1.5 and segments:
                    break
                segments.append(
                    {
                        "index": len(segments) + 1,
                        "source": c["rel_path"],
                        "abs_path": c["abs_path"],
                        "start": 0.0,
                        "end": round(use_dur, 2),
                        "duration": round(use_dur, 2),
                        "speed": 1.0,
                    }
                )
                needed -= use_dur

    actual_total = round(sum(s["duration"] for s in segments), 2)
    return {
        "mode": "long_vlog",
        "aspect_ratio": aspect_ratio,
        "target_resolution": [target_w, target_h],
        "target_duration_sec": actual_total,
        "raw_total_duration_sec": round(total_raw, 2),
        "segments": segments,
    }


def _extract_clip_preview_frame_b64(clip_abs_path: str, duration_sec: float) -> str:
    """Grab 1 lightweight 360px JPEG frame at 35% of the clip duration as base64 for AI vision."""
    import base64

    ffmpeg_bin = find_binary("ffmpeg")
    seek_t = round(max(0.0, float(duration_sec or 1.0) * 0.35), 2)
    try:
        proc = subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{seek_t:.2f}",
                "-i",
                str(clip_abs_path),
                "-frames:v",
                "1",
                "-vf",
                "scale=360:-1",
                "-f",
                "image2",
                "-c:v",
                "mjpeg",
                "pipe:1",
            ],
            capture_output=True,
            timeout=12,
        )
        if proc.returncode == 0 and proc.stdout:
            return base64.b64encode(proc.stdout).decode("ascii")
    except Exception:
        pass
    return ""


def _extract_clip_preview_frame_jpg(clip_abs_path: str, duration_sec: float, out_jpg: Path) -> bool:
    """Save 1 lightweight 480px JPEG frame at 35% of clip duration to disk for agy CLI vision."""
    ffmpeg_bin = find_binary("ffmpeg")
    seek_t = round(max(0.0, float(duration_sec or 1.0) * 0.35), 2)
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{seek_t:.2f}",
                "-i",
                str(clip_abs_path),
                "-frames:v",
                "1",
                "-vf",
                "scale=480:-1",
                str(out_jpg),
            ],
            capture_output=True,
            timeout=12,
        )
        return proc.returncode == 0 and out_jpg.exists() and out_jpg.stat().st_size > 200
    except Exception:
        return False


def generate_longform_vlog_script(
    ordered_clips: list[dict[str, Any]],
    target_duration_sec: float,
    topic_note: str = "",
    content_vibe: str = "outdoor_picnic",
    gemini_api_key: str = "",
    agy_caller: Any = None,
    preview_dir: Path | None = None,
) -> tuple[str, str]:
    """Generate a cohesive chapter-based narration script for 2-20 min vlog (no shopping CTAs)."""
    vibe_meta = _sd.get_content_vibe_meta(content_vibe if content_vibe != "learned_dna" else "outdoor_picnic")
    topic = (topic_note or "").strip() or "chuyến đi trải nghiệm đáng nhớ hôm nay"
    # Vlog narration pace is calmer (~2.4-2.8 words/sec with natural pauses)
    target_words = max(180, min(2800, int(round(target_duration_sec * 2.4))))
    clip_summary = ", ".join(f"Cảnh {c['order']}: {Path(c['name']).stem} ({c['duration_sec']:.0f}s)" for c in ordered_clips[:24])

    sample_clips = ordered_clips[:8]
    if len(ordered_clips) > 8:
        step = len(ordered_clips) / 8.0
        sample_clips = [ordered_clips[int(i * step)] for i in range(8)]

    base_prompt = (
        f"Hãy viết một bài lời bình Vlog tiếng Việt liền mạch, tự nhiên, chia theo trình tự thời gian từ đầu đến cuối "
        f"cho video dài khoảng {target_duration_sec:.0f} giây (~{target_words} từ).\n"
        f"Chủ đề / Ghi chú: {topic}\n"
        f"Phong cách: {vibe_meta.get('prompt_hint') or vibe_meta.get('label')}\n"
        f"Thứ tự các cảnh quay thực tế: {clip_summary}\n"
        "Yêu cầu bắt buộc:\n"
        "- Quan sát các khung hình tương ứng theo đúng trình tự từ đầu đến cuối và viết thành các đoạn văn liền mạch mô tả sát bối cảnh thực tế (Mở đầu -> Diễn biến từng cảnh -> Cảm nhận & Kết).\n"
        "- Chỉ trả về văn bản lời đọc thuần túy (không tiêu đề markdown, không số thứ tự, không ngoặc chú thích).\n"
        "- TUYỆT ĐỐI KHÔNG nhắc giỏ hàng, chốt đơn, freeship hay bán hàng.\n"
        f"- Câu kết nhẹ nhàng tự nhiên: {vibe_meta.get('cta_default')}"
    )

    display_text = ""
    api_key = str(gemini_api_key or "").strip()
    if api_key:
        try:
            import urllib.request

            content_parts: list[dict[str, Any]] = [{"text": base_prompt}]
            for sc in sample_clips:
                b64 = _extract_clip_preview_frame_b64(str(sc.get("abs_path") or ""), float(sc.get("duration_sec") or 2.0))
                if b64:
                    content_parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            req = urllib.request.Request(
                url,
                data=json.dumps({"contents": [{"parts": content_parts}]}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                cands = data.get("candidates") or []
                if cands:
                    parts = ((cands[0].get("content") or {}).get("parts") or [])
                    display_text = " ".join(str(p.get("text") or "") for p in parts).strip()
        except Exception as exc:
            print(f"[LongForm] Gemini fallback ({exc})")

    if (not display_text or len(display_text.split()) < 60) and agy_caller is not None:
        try:
            frame_lines: list[str] = []
            if preview_dir is not None:
                shutil.rmtree(preview_dir, ignore_errors=True)
                preview_dir.mkdir(parents=True, exist_ok=True)
                for idx, sc in enumerate(sample_clips, start=1):
                    out_jpg = preview_dir / f"scene_{idx:02d}.jpg"
                    if _extract_clip_preview_frame_jpg(str(sc.get("abs_path") or ""), float(sc.get("duration_sec") or 2.0), out_jpg):
                        frame_lines.append(f"- Cảnh {sc.get('order')}: {out_jpg}")
            agy_prompt = base_prompt
            if frame_lines:
                agy_prompt += "\n\nHãy xem các ảnh khung hình đại diện theo đúng thứ tự dưới đây trước khi viết:\n" + "\n".join(frame_lines)
            agy_raw = str(agy_caller(agy_prompt) or "").strip()
            # Clean any accidental markdown headings/fences
            agy_raw = re.sub(r"```[a-zA-Z]*\s*", "", agy_raw).replace("```", "")
            agy_raw = re.sub(r"^#+\s+.*$", "", agy_raw, flags=re.M).strip()
            if len(agy_raw.split()) >= 60:
                display_text = agy_raw
        except Exception as exc:
            print(f"[LongForm] agy CLI fallback ({exc})")

    if not display_text or len(display_text.split()) < 60:
        intro = (
            f"Xin chào mọi người, hôm nay tụi mình cùng nhau bắt đầu {topic}. "
            "Từ những bước chuẩn bị đầu tiên, không khí đã mang lại cảm giác rất hào hứng và thư thái."
        )
        chapter_templates = [
            "Ở chặng tiếp theo, khung cảnh mở ra trước mắt thật sự bình yên, ánh sáng tự nhiên làm mọi chi tiết trở nên sống động hơn hẳn.",
            "Đi qua từng góc quay, mình tranh thủ ghi lại những khoảnh khắc chân thật nhất để giữ làm kỷ niệm cho cả nhóm.",
            "Có những lúc chỉ cần dừng lại vài phút, hít thở thật sâu và lắng nghe âm thanh xung quanh là thấy bao mệt mỏi tan biến hết.",
            "Mỗi khung hình nối tiếp nhau như một cuốn nhật ký nhỏ, ghi lại trọn vẹn nhịp điệu chậm rãi và dễ chịu của chuyến đi.",
            "Khoảng thời gian thư giãn bên nhau như thế này luôn mang lại nguồn năng lượng tích cực rất khó tả.",
            "Càng về sau, ánh nắng dịu dần tạo nên tông màu ấm áp, giúp từng thước phim quay bằng điện thoại cũng có chiều sâu riêng.",
        ]
        outro = f"Một hành trình thật trọn vẹn và nhiều tiếng cười. {vibe_meta.get('cta_default') or 'Cảm ơn mọi người đã xem hết video nha.'}"

        sentences = [intro]
        total_clip_dur = max(1.0, sum(float(c.get("duration_sec") or 1.0) for c in ordered_clips))
        approx_sentences = max(4, min(65, int(round(target_words / 24))))
        sent_idx = 0
        for ci, cl in enumerate(ordered_clips):
            share = max(1, int(round((float(cl.get("duration_sec") or 1.0) / total_clip_dur) * approx_sentences)))
            for _ in range(share):
                if len(sentences) - 1 >= approx_sentences:
                    break
                sentences.append(chapter_templates[sent_idx % len(chapter_templates)])
                sent_idx += 1
        while len(sentences) - 1 < approx_sentences:
            sentences.append(chapter_templates[sent_idx % len(chapter_templates)])
            sent_idx += 1
        sentences.append(outro)
        display_text = " ".join(sentences)

    display_text = re.sub(r"\s+", " ", display_text).strip()
    tts_text = _sd.convert_display_to_tts_script(display_text)
    return display_text, tts_text


def _sec_to_ass_time(sec: float) -> str:
    s = max(0.0, float(sec))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    rem = s % 60.0
    return f"{h}:{m:02d}:{rem:05.2f}"


def srt_to_ass_file(
    srt_path: Path,
    ass_path: Path,
    width: int = 1920,
    height: int = 1080,
    font_name: str = "Baloo 2",
) -> Path:
    """Convert SRT subtitles into clean, crisp ASS subtitles scaled for 16:9 or 9:16."""
    is_landscape = width > height
    font_size = 54 if is_landscape else 64
    margin_v = 56 if is_landscape else 310
    margin_lr = 120 if is_landscape else 70

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H88000000,"
        f"-1,0,0,0,100,100,0,0,1,4,2,2,{margin_lr},{margin_lr},{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events: list[str] = []
    if srt_path.exists():
        raw = srt_path.read_text(encoding="utf-8-sig")
        blocks = re.split(r"\r?\n\r?\n+", raw.strip())
        for blk in blocks:
            lines = [ln.strip() for ln in blk.splitlines() if ln.strip()]
            if len(lines) < 2:
                continue
            ts_line = lines[1] if "-->" in lines[1] else (lines[0] if "-->" in lines[0] else "")
            if "-->" not in ts_line:
                continue
            parts = [p.strip() for p in ts_line.split("-->")]
            st = _sd._srt_ts_to_sec(parts[0])
            en = _sd._srt_ts_to_sec(parts[1])
            text_lines = lines[2:] if "-->" in lines[1] else lines[1:]
            txt = " ".join(text_lines).replace("\n", " ").strip()
            txt = re.sub(r"\s+", " ", txt)
            if not txt or en <= st:
                continue
            events.append(f"Dialogue: 0,{_sec_to_ass_time(st)},{_sec_to_ass_time(en)},Default,,0,0,0,,{txt}")

    ass_path.parent.mkdir(parents=True, exist_ok=True)
    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return ass_path


def _detect_h264_encoder(ffmpeg_bin: str) -> tuple[str, list[str]]:
    try:
        probe = subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=256x256:d=0.1",
                "-c:v",
                "h264_nvenc",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            timeout=10,
        )
        if probe.returncode == 0:
            return "h264_nvenc", ["-preset", "p4", "-cq", "21", "-b:v", "0"]
    except Exception:
        pass
    return "libx264", ["-preset", "veryfast", "-crf", "20"]


def _has_audio_stream(ffprobe_bin: str, media_path: Path) -> bool:
    try:
        res = subprocess.run(
            [
                ffprobe_bin,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(media_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return bool((res.stdout or "").strip())
    except Exception:
        return False


def render_longform_ffmpeg_vlog(
    plan: dict[str, Any],
    voice_wav: Path | None,
    srt_path: Path | None,
    bgm_path: Path | None,
    output_mp4: Path,
    bgm_volume: float = 0.14,
    keep_clip_audio: bool = False,
    font_name: str = "Baloo 2",
    progress_cb: Any = None,
) -> dict[str, Any]:
    """Render a cohesive 2-20 min vlog timeline rapidly with FFmpeg (consistent style, BGM, and ASS subtitles)."""
    ffmpeg_bin = find_binary("ffmpeg")
    ffprobe_bin = find_binary("ffprobe")
    vcodec, vcodec_args = _detect_h264_encoder(ffmpeg_bin)
    res_wh = plan.get("target_resolution") or [1920, 1080]
    target_w, target_h = int(res_wh[0]), int(res_wh[1])
    segments = plan.get("segments") or []
    if not segments:
        raise RuntimeError("Không có segment nào trong timeline vlog.")

    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        seg_files: list[Path] = []
        total_segs = len(segments)

        for idx, seg in enumerate(segments, start=1):
            if progress_cb:
                progress_cb(idx, total_segs)
            src_p = Path(seg["abs_path"])
            st = float(seg.get("start") or 0.0)
            dur = max(0.5, float(seg.get("duration") or 3.0))
            seg_out = tmp_path / f"seg_{idx:04d}.mp4"
            vf = (
                f"crop='min(iw,ih*{target_w}/{target_h})':'min(ih,iw*{target_h}/{target_w})',"
                f"scale={target_w}:{target_h}:flags=lanczos,eq=contrast=1.03:saturation=1.06,setsar=1,fps=30,format=yuv420p"
            )
            cmd = [
                ffmpeg_bin,
                "-y",
                "-ss",
                f"{st:.3f}",
                "-t",
                f"{dur:.3f}",
                "-i",
                str(src_p),
                "-vf",
                vf,
                "-c:v",
                vcodec,
                *vcodec_args,
                "-pix_fmt",
                "yuv420p",
            ]
            if keep_clip_audio:
                if _has_audio_stream(ffprobe_bin, src_p):
                    cmd.extend(["-af", "aresample=44100,volume=0.35", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k"])
                else:
                    cmd = [
                        ffmpeg_bin,
                        "-y",
                        "-ss",
                        f"{st:.3f}",
                        "-t",
                        f"{dur:.3f}",
                        "-i",
                        str(src_p),
                        "-f",
                        "lavfi",
                        "-t",
                        f"{dur:.3f}",
                        "-i",
                        "anullsrc=r=44100:cl=stereo",
                        "-map",
                        "0:v:0",
                        "-map",
                        "1:a:0",
                        "-vf",
                        vf,
                        "-c:v",
                        vcodec,
                        *vcodec_args,
                        "-pix_fmt",
                        "yuv420p",
                        "-c:a",
                        "aac",
                        "-ar",
                        "44100",
                        "-ac",
                        "2",
                        "-b:a",
                        "128k",
                        "-shortest",
                    ]
            else:
                cmd.append("-an")
            cmd.append(str(seg_out))
            subprocess.run(cmd, capture_output=True, check=True, timeout=180)
            seg_files.append(seg_out)

        concat_list = tmp_path / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in seg_files),
            encoding="utf-8",
        )
        merged_video = tmp_path / "merged_raw.mp4"
        subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                str(merged_video),
            ],
            capture_output=True,
            check=True,
            timeout=180,
        )

        # Final composite: ASS subtitles + unified Voice + continuous BGM across entire video
        ass_file = tmp_path / "subs.ass"
        has_ass = False
        if srt_path and srt_path.exists():
            srt_to_ass_file(srt_path, ass_file, width=target_w, height=target_h, font_name=font_name)
            has_ass = True

        comp_cmd = [ffmpeg_bin, "-y", "-i", str(merged_video)]
        audio_inputs: list[tuple[str, float]] = []
        has_voice = bool(voice_wav and voice_wav.exists())
        has_bgm = bool(bgm_path and bgm_path.exists())

        if has_voice:
            comp_cmd.extend(["-i", str(voice_wav)])
            audio_inputs.append(("voice", 1.0))
        if has_bgm:
            comp_cmd.extend(["-stream_loop", "-1", "-i", str(bgm_path)])
            audio_inputs.append(("bgm", float(bgm_volume)))

        vf_final = ""
        if has_ass:
            ass_esc = ass_file.as_posix().replace(":", "\\:")
            vf_final = f"ass='{ass_esc}'"

        filter_complex_parts: list[str] = []
        if vf_final:
            filter_complex_parts.append(f"[0:v]{vf_final}[vout]")
            v_map = "[vout]"
        else:
            v_map = "0:v"

        mix_labels: list[str] = []
        next_idx = 1
        if keep_clip_audio:
            filter_complex_parts.append("[0:a]aresample=44100,volume=0.38[clipa]")
            mix_labels.append("[clipa]")
        for kind, vol in audio_inputs:
            lbl = f"a_{kind}"
            filter_complex_parts.append(f"[{next_idx}:a]aresample=44100,volume={vol:.3f}[{lbl}]")
            mix_labels.append(f"[{lbl}]")
            next_idx += 1

        a_map = ""
        if len(mix_labels) > 1:
            filter_complex_parts.append(
                f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=longest:dropout_transition=2:normalize=0,alimiter=limit=0.95[aout]"
            )
            a_map = "[aout]"
        elif len(mix_labels) == 1:
            a_map = mix_labels[0]

        if filter_complex_parts:
            comp_cmd.extend(["-filter_complex", ";".join(filter_complex_parts)])
        comp_cmd.extend(["-map", v_map])
        if a_map:
            comp_cmd.extend(["-map", a_map, "-c:a", "aac", "-ar", "44100", "-b:a", "192k"])
        else:
            comp_cmd.extend(["-an"])

        if vf_final:
            comp_cmd.extend(["-c:v", vcodec, *vcodec_args, "-pix_fmt", "yuv420p"])
        else:
            comp_cmd.extend(["-c:v", "copy"])

        comp_cmd.extend(["-shortest", "-movflags", "+faststart", str(output_mp4)])
        subprocess.run(comp_cmd, capture_output=True, check=True, timeout=600)

    ffprobe_bin = find_binary("ffprobe")
    final_dur = round(float(probe_duration(ffprobe_bin, output_mp4)), 2)
    return {
        "ok": True,
        "output_path": str(output_mp4),
        "duration_sec": final_dur,
        "width": target_w,
        "height": target_h,
        "segments_count": len(segments),
    }
