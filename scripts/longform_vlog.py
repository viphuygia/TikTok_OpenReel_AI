#!/usr/bin/env python3
"""Broadcast-Quality Long-Form Vlog Engine (>90s to 20m) — Hybrid Remotion Overlays + 4K FFmpeg Master."""

from __future__ import annotations

import asyncio
import base64
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any
import wave

import numpy as np
import soundfile as sf

import style_dna as _sd
import voice_engine as _ve
from prepare_clips import find_binary, probe_duration

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIR_REMOTION = PROJECT_ROOT / "remotion_studio"
MEDIA_VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")

FALLBACK_VLOG_POOL: dict[str, list[str]] = {
    "opening": [
        "Cuối cùng cũng có một ngày thật thảnh thơi để tạm gác công việc sang một bên và xách máy lên đường.",
        "Hôm nay tụi mình chọn khởi hành sớm một chút để kịp đón ánh nắng dịu nhất và tận hưởng không khí trong lành.",
        "Chỉ cần rời khỏi nhịp sống ồn ào vài tiếng đồng hồ thôi là tâm trạng đã thấy nhẹ nhàng và háo hức hơn hẳn.",
        "Mọi thứ đã chuẩn bị gọn gàng từ tối hôm trước, bây giờ chỉ việc tận hưởng trọn vẹn từng khoảnh khắc phía trước.",
    ],
    "journey": [
        "Đoạn đường di chuyển buổi sáng thoáng đãng hơn mong đợi, hai bên cảnh vật thay đổi dần mang lại cảm giác rất dễ chịu.",
        "Đi chậm lại một nhịp để ngắm nhìn khung cảnh dọc đường giúp chuyến đi trở nên thú vị ngay từ những phút đầu tiên.",
        "Ánh sáng xuyên qua tán cây tạo nên những mảng màu tự nhiên, lên khung hình nhìn cực kỳ có chiều sâu.",
        "Tiếng gió nhẹ và bầu không khí mát mẻ khiến ai nấy trong nhóm đều quên hết cảm giác mệt mỏi thường ngày.",
        "Càng đi sâu vào không gian ngoài trời, mọi âm thanh dường như trở nên rõ nét và bình yên hơn rất nhiều.",
    ],
    "discovery": [
        "Vừa đặt chân tới nơi, ấn tượng đầu tiên chính là khoảng không gian mở rộng rãi và cực kỳ thoáng đãng.",
        "Mỗi góc nhỏ ở đây đều có nét riêng, chỉ cần đưa máy lên đúng hướng sáng là đã thu được những thước phim ưng ý.",
        "Tụi mình dành ít phút đi dạo một vòng quan sát xung quanh trước khi chọn vị trí đẹp nhất để dừng chân.",
        "Góc nhìn từ khu vực này bao quát được cả khung cảnh rộng lớn, rất hợp để giữ lại làm điểm nhấn cho vlog hôm nay.",
        "Không gian gần gũi với thiên nhiên mang lại cảm giác thư thái mà hiếm khi tìm thấy giữa phố thị đông đúc.",
    ],
    "activity": [
        "Bắt tay vào chuẩn bị mọi thứ cùng nhau luôn là phần vui và nhiều tiếng cười nhất trong mỗi chuyến đi.",
        "Từng công đoạn nhỏ được chia nhau làm gọn gàng, vừa làm vừa trò chuyện nên chẳng mấy chốc đã tươm tất.",
        "Khi mọi đồ đạc đã vào đúng vị trí, cả khu vực nhỏ trông ấm cúng và tràn đầy sức sống hẳn lên.",
        "Mùi thơm lan tỏa hòa cùng tiếng nói cười xung quanh khiến không khí trở nên gần gũi và đáng nhớ vô cùng.",
        "Những khoảnh khắc tự nhiên không cần diễn xuất này chính là điều khiến tụi mình thích quay vlog lưu lại nhất.",
        "Thử thưởng thức thành quả ngay tại chỗ giữa khung cảnh thoáng mát mang lại cảm giác ngon và trọn vị hơn hẳn.",
    ],
    "relaxation": [
        "Sau khi mọi thứ xong xuôi là khoảng thời gian lặng lẽ ngồi nghỉ ngơi, nhâm nhi chút đồ uống và ngắm cảnh.",
        "Không cần lịch trình dày đặc, chỉ ngồi trò chuyện rôm rả với bạn bè như vậy cũng đủ thấy ngày cuối tuần thật giá trị.",
        "Khoảnh khắc ngồi thư giãn lắng nghe âm thanh tự nhiên xung quanh giúp đầu óc được nạp lại năng lượng hoàn toàn.",
        "Gió thổi nhè nhẹ khiến buổi chiều trôi qua êm ả, nhìn lại từng đoạn quay đều thấy rõ sự thoải mái trên nét mặt mọi người.",
        "Có những buổi chiều bình yên thế này mới thấy đôi khi hạnh phúc chỉ nằm ở những điều thật giản đơn.",
    ],
    "golden_hour": [
        "Càng về cuối buổi chiều, ánh nắng dịu xuống chuyển sang sắc vàng ấm áp phủ khắp không gian.",
        "Đây luôn là khung giờ đẹp nhất trong ngày để ghi lại những cú máy ngược sáng đầy cảm xúc.",
        "Bầu trời chuyển màu chậm rãi báo hiệu một ngày trải nghiệm tuyệt vời sắp khép lại.",
        "Từng chi tiết nhỏ dưới ánh hoàng hôn đều trở nên mềm mại và điện ảnh hơn mà không cần chỉnh sửa quá nhiều.",
    ],
    "closing": [
        "Thu dọn gọn gàng trước khi ra về để giữ không gian luôn sạch đẹp như lúc tụi mình mới đặt chân tới.",
        "Một ngày rời xa màn hình và tận hưởng trọn vẹn ngoài trời đã khép lại với thật nhiều kỷ niệm đẹp.",
        "Cảm ơn bạn đã dành thời gian đồng hành cùng tụi mình từ đầu tới cuối thước phim này.",
        "Nếu thấy thích không khí của chuyến đi hôm nay, đừng quên lưu video và hẹn gặp bạn ở tập tiếp theo nhé.",
    ],
}


def _natural_sort_key(name: str) -> list[Any]:
    return [int(tok) if tok.isdigit() else tok.lower() for tok in re.split(r"(\d+)", name)]


def _probe_video_meta(ffprobe_bin: str, video_path: Path) -> dict[str, Any]:
    meta = {"duration_sec": 5.0, "width": 1920, "height": 1080}
    try:
        res = subprocess.run(
            [
                ffprobe_bin,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height:format=duration",
                "-of",
                "json",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0 and res.stdout:
            parsed = json.loads(res.stdout)
            streams = parsed.get("streams") or []
            if streams:
                meta["width"] = int(streams[0].get("width") or 1920)
                meta["height"] = int(streams[0].get("height") or 1080)
            dur = float((parsed.get("format") or {}).get("duration") or 0.0)
            if dur > 0:
                meta["duration_sec"] = round(dur, 2)
            return meta
    except Exception:
        pass
    try:
        meta["duration_sec"] = max(0.5, round(float(probe_duration(ffprobe_bin, video_path)), 2))
    except Exception:
        pass
    return meta


def collect_ordered_raw_clips(
    raw_dir: Path,
    ordered_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Collect raw video files in strict chronological / user-specified order with resolution metadata."""
    if not raw_dir.exists():
        return []
    ffprobe_bin = find_binary("ffprobe")
    all_files: dict[str, Path] = {}
    raw_candidates = [
        p for p in raw_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in MEDIA_VIDEO_EXTS
    ]
    raw_candidates.sort(
        key=lambda x: (int(x.stat().st_mtime), _natural_sort_key(x.relative_to(raw_dir).as_posix()))
    )
    for p in raw_candidates:
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
        info = _probe_video_meta(ffprobe_bin, p)
        w = int(info["width"])
        h = int(info["height"])
        out.append(
            {
                "order": idx,
                "rel_path": rel,
                "abs_path": str(p),
                "name": p.name,
                "duration_sec": max(0.5, float(info["duration_sec"])),
                "width": w,
                "height": h,
                "is_4k": max(w, h) >= 3000,
                "mtime": int(p.stat().st_mtime),
            }
        )
    return out


def resolve_target_resolution(
    ordered_clips: list[dict[str, Any]],
    aspect_ratio: str = "16:9",
    quality_preset: str = "auto_source",
) -> tuple[int, int, str]:
    """Choose 4K / 2K / 1080p output resolution matching source quality or explicit preset."""
    qp = (quality_preset or "auto_source").strip().lower()
    is_landscape = aspect_ratio == "16:9"
    max_src_dim = max([max(int(c.get("width") or 0), int(c.get("height") or 0)) for c in ordered_clips] or [1920])

    if qp == "auto_source":
        if max_src_dim >= 3000:
            qp = "4k"
        elif max_src_dim >= 2200:
            qp = "2k"
        else:
            qp = "1080p"

    if qp == "4k":
        return (3840, 2160, "4K UHD") if is_landscape else (2160, 3840, "4K UHD")
    if qp == "2k":
        return (2560, 1440, "2K QHD") if is_landscape else (1440, 2560, "2K QHD")
    return (1920, 1080, "Full HD 1080p") if is_landscape else (1080, 1920, "Full HD 1080p")


VIBE_EDITING_PROFILES: dict[str, dict[str, Any]] = {
    "detective_mystery": {
        "shot_sec": 3.4,
        "sentence_pause_sec": 0.35,
        "voice_rate_offset": "+4%",
        "word_multiplier": 1.65,
        "color_preset": "cinema_contrast",
        "title_style": "detective_noir",
        "subtitle_style": "highlight_bold",
        "accent_color": "#EF4444",
        "force_vfx": True,
        "motion_zoom": True,
        "vignette": True,
        "flash_cut": True,
        "chapter_sfx": True,
    },
    "field_report": {
        "shot_sec": 3.6,
        "sentence_pause_sec": 0.38,
        "voice_rate_offset": "+4%",
        "word_multiplier": 1.60,
        "color_preset": "cinema_contrast",
        "title_style": "detective_noir",
        "subtitle_style": "highlight_bold",
        "accent_color": "#F59E0B",
        "force_vfx": True,
        "motion_zoom": True,
        "vignette": True,
        "flash_cut": True,
        "chapter_sfx": True,
    },
    "pov_comedy": {
        "shot_sec": 3.8,
        "sentence_pause_sec": 0.32,
        "voice_rate_offset": "+5%",
        "word_multiplier": 1.48,
        "color_preset": "fresh_cool",
        "title_style": "comic_pop",
        "subtitle_style": "highlight_bold",
        "accent_color": "#FACC15",
        "force_vfx": True,
        "motion_zoom": True,
        "vignette": False,
        "flash_cut": True,
        "chapter_sfx": True,
    },
    "creative_internet": {
        "shot_sec": 4.0,
        "sentence_pause_sec": 0.38,
        "voice_rate_offset": "+4%",
        "word_multiplier": 1.40,
        "color_preset": "fresh_cool",
        "title_style": "comic_pop",
        "subtitle_style": "highlight_bold",
        "accent_color": "#38BDF8",
        "force_vfx": True,
        "motion_zoom": True,
        "vignette": False,
        "flash_cut": True,
        "chapter_sfx": False,
    },
    "cinematic_deep": {
        "shot_sec": 6.4,
        "sentence_pause_sec": 0.95,
        "voice_rate_offset": "-4%",
        "word_multiplier": 0.95,
        "color_preset": "soft_film",
        "title_style": "cinema_letterbox",
        "subtitle_style": "cinema_box",
        "accent_color": "#A78BFA",
        "force_vfx": True,
    },
    "outdoor_picnic": {
        "shot_sec": 6.2,
        "sentence_pause_sec": 0.85,
        "voice_rate_offset": "",
        "word_multiplier": 1.0,
        "color_preset": "warm_sunset",
        "title_style": "campfire_warm",
        "subtitle_style": "warm_vlog_gold",
        "accent_color": "#F59E0B",
        "force_vfx": False,
    },
    "travel_vlog": {
        "shot_sec": 5.8,
        "sentence_pause_sec": 0.80,
        "voice_rate_offset": "",
        "word_multiplier": 1.02,
        "color_preset": "fresh_cool",
        "title_style": "adventure_bold",
        "subtitle_style": "mint_nature",
        "accent_color": "#38BDF8",
        "force_vfx": False,
    },
    "food_cafe": {
        "shot_sec": 5.4,
        "sentence_pause_sec": 0.72,
        "voice_rate_offset": "",
        "word_multiplier": 1.05,
        "color_preset": "warm_sunset",
        "title_style": "pastel_soft",
        "subtitle_style": "cinema_box",
        "accent_color": "#FB7185",
        "force_vfx": False,
    },
    "daily_story": {
        "shot_sec": 6.2,
        "sentence_pause_sec": 0.85,
        "voice_rate_offset": "",
        "word_multiplier": 1.0,
        "color_preset": "natural",
        "title_style": "editorial_minimal",
        "subtitle_style": "editorial_clean",
        "accent_color": "#34D399",
        "force_vfx": False,
    },
}


def get_vibe_editing_profile(content_vibe: str | None) -> dict[str, Any]:
    key = str(content_vibe or "outdoor_picnic").strip()
    if key == "learned_dna":
        key = "outdoor_picnic"
    return dict(VIBE_EDITING_PROFILES.get(key) or VIBE_EDITING_PROFILES["outdoor_picnic"])


def build_longform_timeline_plan(
    ordered_clips: list[dict[str, Any]],
    target_duration_sec: float = 300.0,
    auto_fit_duration: bool = False,
    aspect_ratio: str = "16:9",
    quality_preset: str = "auto_source",
    shot_jitter_sec: float = 0.0,
    target_shot_sec: float = 6.2,
) -> dict[str, Any]:
    """Slice raw clips into crisp chronological 4.5-8.5s vlog highlight cuts grouped into chapters."""
    if not ordered_clips:
        raise RuntimeError("Chưa có video thô nào trong 02_video_tho/ để dựng Timeline dài.")

    total_raw = sum(float(c.get("duration_sec") or 0.0) for c in ordered_clips)
    if auto_fit_duration or target_duration_sec <= 0:
        eff_target = max(95.0, min(1200.0, total_raw))
    else:
        eff_target = max(95.0, min(1200.0, float(target_duration_sec)))

    target_w, target_h, quality_label = resolve_target_resolution(
        ordered_clips, aspect_ratio=aspect_ratio, quality_preset=quality_preset
    )
    segments: list[dict[str, Any]] = []

    if total_raw >= eff_target * 0.92:
        ratio = eff_target / max(1.0, total_raw)
        for c in ordered_clips:
            c_dur = float(c["duration_sec"])
            alloc_dur = max(3.5, min(c_dur, c_dur * ratio))
            # Trim shaky camera start/stop edges on longer raw clips
            edge_trim = min(1.1, c_dur * 0.08) if c_dur > 10.0 else 0.0
            usable_start = edge_trim
            usable_end = max(usable_start + 1.0, c_dur - edge_trim)
            usable_span = usable_end - usable_start

            shot_step = max(2.2, min(9.0, float(target_shot_sec or 6.2)))
            min_shot = max(2.0, shot_step * 0.65)
            max_shot = max(4.2, shot_step * 1.35)
            if alloc_dur <= max(6.5, shot_step * 1.4):
                n_shots = 1
            else:
                n_shots = max(2, min(16, int(round(alloc_dur / shot_step))))

            per_shot = max(min_shot, min(max_shot, alloc_dur / n_shots))
            # Pick highlight sub-shots evenly distributed chronologically across usable_span
            for si in range(n_shots):
                if usable_span <= per_shot * n_shots + 0.5:
                    st = usable_start + si * (usable_span / n_shots)
                    dur_s = min(per_shot, usable_end - st)
                else:
                    slot = usable_span / n_shots
                    max_shift = max(0.0, slot - per_shot)
                    jitter = min(max_shift, max(0.0, float(shot_jitter_sec or 0.0)))
                    st = usable_start + si * slot + max(0.0, (slot - per_shot) * 0.35)
                    if jitter > 0.05:
                        st = min(usable_end - per_shot, usable_start + si * slot + jitter)
                    dur_s = min(per_shot, usable_end - st)
                dur_s = round(max(2.5, dur_s), 2)
                en = round(min(c_dur, st + dur_s), 2)
                if en - st < 1.8:
                    continue
                segments.append(
                    {
                        "index": len(segments) + 1,
                        "source": c["rel_path"],
                        "abs_path": c["abs_path"],
                        "clip_order": c["order"],
                        "start": round(st, 2),
                        "end": en,
                        "duration": round(en - st, 2),
                        "speed": 1.0,
                    }
                )
    else:
        # Raw footage is shorter than target: cycle chronologically in highlight 5-8s shots
        needed = eff_target
        pass_idx = 0
        while needed > 1.5 and pass_idx < 8:
            pass_idx += 1
            for c in ordered_clips:
                if needed <= 1.2:
                    break
                c_dur = float(c["duration_sec"])
                n_shots = max(1, min(6, int(round(c_dur / 6.5))))
                shot_len = min(8.0, max(3.0, c_dur / n_shots), needed)
                sub_offset = ((pass_idx - 1) * 1.7) % max(0.5, c_dur - shot_len)
                for si in range(n_shots):
                    if needed <= 1.2:
                        break
                    st = round(min(max(0.0, c_dur - 2.0), sub_offset + si * (c_dur / n_shots)), 2)
                    use_dur = round(min(shot_len, c_dur - st, needed), 2)
                    if use_dur < 1.5:
                        continue
                    segments.append(
                        {
                            "index": len(segments) + 1,
                            "source": c["rel_path"],
                            "abs_path": c["abs_path"],
                            "clip_order": c["order"],
                            "start": st,
                            "end": round(st + use_dur, 2),
                            "duration": use_dur,
                            "speed": 1.0,
                        }
                    )
                    needed -= use_dur

    # Assign timeline timestamps and clean Chapters
    cursor = 0.0
    for seg in segments:
        seg["timeline_start"] = round(cursor, 2)
        cursor += float(seg["duration"])
        seg["timeline_end"] = round(cursor, 2)

    actual_total = round(cursor, 2)
    num_chapters = min(6, max(3, int(round(actual_total / 60.0))))
    num_chapters = min(num_chapters, max(1, len(segments)))
    chapter_len_target = actual_total / float(num_chapters)

    chapters: list[dict[str, Any]] = []
    cur_chap = 1
    chap_start = 0.0
    chap_shots: list[dict[str, Any]] = []
    for si, seg in enumerate(segments):
        should_split = (
            cur_chap < num_chapters
            and chap_shots
            and float(seg["timeline_start"]) >= cur_chap * chapter_len_target
            and (len(segments) - si) >= (num_chapters - cur_chap)
        )
        if should_split:
            chapters.append(
                {
                    "index": cur_chap,
                    "start_sec": round(chap_start, 2),
                    "end_sec": round(float(chap_shots[-1]["timeline_end"]), 2),
                    "shot_count": len(chap_shots),
                    "lead_clip": chap_shots[0]["abs_path"],
                    "lead_duration": float(chap_shots[0]["duration"]),
                }
            )
            cur_chap += 1
            chap_start = float(seg["timeline_start"])
            chap_shots = []
        seg["chapter_index"] = cur_chap
        seg["is_chapter_start"] = len(chap_shots) == 0
        chap_shots.append(seg)

    if chap_shots:
        chapters.append(
            {
                "index": cur_chap,
                "start_sec": round(chap_start, 2),
                "end_sec": round(actual_total, 2),
                "shot_count": len(chap_shots),
                "lead_clip": chap_shots[0]["abs_path"],
                "lead_duration": float(chap_shots[0]["duration"]),
            }
        )

    return {
        "mode": "long_vlog",
        "aspect_ratio": aspect_ratio,
        "quality_preset": quality_preset,
        "quality_label": quality_label,
        "target_resolution": [target_w, target_h],
        "target_duration_sec": actual_total,
        "raw_total_duration_sec": round(total_raw, 2),
        "segments": segments,
        "chapters": chapters,
    }


def _extract_clip_preview_frame_b64(clip_abs_path: str, duration_sec: float, seek_sec: float | None = None) -> str:
    """Grab 1 lightweight 360px JPEG frame at seek_sec (or 35% of clip duration) as base64 for AI vision."""
    ffmpeg_bin = find_binary("ffmpeg")
    seek_t = round(max(0.0, float(seek_sec)) if seek_sec is not None else max(0.0, float(duration_sec or 1.0) * 0.35), 2)
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


def _extract_clip_preview_frame_jpg(
    clip_abs_path: str,
    duration_sec: float,
    out_jpg: Path,
    seek_sec: float | None = None,
) -> bool:
    """Save 1 lightweight 480px JPEG frame at seek_sec (or 35% of clip duration) to disk for agy CLI vision."""
    ffmpeg_bin = find_binary("ffmpeg")
    seek_t = round(max(0.0, float(seek_sec)) if seek_sec is not None else max(0.0, float(duration_sec or 1.0) * 0.35), 2)
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


def _deduplicate_sentences(text: str, seen: list[str]) -> str:
    """Remove duplicate or near-duplicate sentences (SequenceMatcher > 0.78) across chapters."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]
    kept: list[str] = []
    for s in sents:
        norm = re.sub(r"[^\w\s]", "", s.lower()).strip()
        if not norm:
            continue
        is_dup = any(SequenceMatcher(None, norm, prev).ratio() >= 0.78 for prev in seen)
        if not is_dup:
            seen.append(norm)
            kept.append(s)
    return " ".join(kept)


def _extract_json_block(raw: str) -> dict[str, Any] | None:
    cleaned = (raw or "").strip()
    cleaned = re.sub(r"```json\s*|```\s*", "", cleaned).strip()
    m = re.search(r"\{.*\}", cleaned, flags=re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def generate_longform_chapter_script(
    plan: dict[str, Any],
    ordered_clips: list[dict[str, Any]],
    topic_note: str = "",
    content_vibe: str = "outdoor_picnic",
    vlog_title: str = "",
    gemini_api_key: str = "",
    agy_caller: Any = None,
    preview_dir: Path | None = None,
    avoid_title_style: str = "",
    preferred_title_style: str = "",
    preferred_subtitle_style: str = "",
    preferred_accent_color: str = "",
) -> dict[str, Any]:
    """Generate structured non-repeating Vlog chapters with Intro/Chapter cards/Outro & breathing narration."""
    vibe_meta = _sd.get_content_vibe_meta(content_vibe if content_vibe != "learned_dna" else "outdoor_picnic")
    vp_prof = get_vibe_editing_profile(content_vibe)
    topic = (topic_note or "").strip() or "Chuyến dã ngoại trải nghiệm thiên nhiên cuối tuần"
    chapters_plan = plan.get("chapters") or [
        {"index": 1, "start_sec": 0.0, "end_sec": float(plan.get("target_duration_sec") or 300.0)}
    ]
    n_chap = len(chapters_plan)
    total_dur = float(plan.get("target_duration_sec") or 300.0)
    # Scale narration density by Vibe Editing Profile (e.g. +30% for Detective/Field Report, calm for Camping)
    word_mult = float(vp_prof.get("word_multiplier") or 1.0)
    target_total_words = max(120, min(1850, int(round(total_dur * 1.05 * word_mult))))
    words_per_chap = max(38, int(round(target_total_words / max(1, n_chap))))
    blocks_per_chap = 4 if word_mult >= 1.35 else 2

    segments_plan = plan.get("segments") or []
    clip_summary = ", ".join(
        f"Cảnh {c['order']}: {Path(c['name']).stem} ({c['duration_sec']:.0f}s)" for c in ordered_clips[:24]
    )

    # Group timeline segments & representative frames strictly by Chapter so AI sees what happens in EACH chapter
    chapter_frame_specs: list[dict[str, Any]] = []
    chap_desc_lines: list[str] = []
    frames_per_chap = 3 if n_chap <= 4 else 2
    for ch in chapters_plan:
        ch_idx = int(ch.get("index") or 1)
        ch_st = float(ch.get("start_sec") or 0.0)
        ch_en = float(ch.get("end_sec") or total_dur)
        ch_segs = [s for s in segments_plan if int(s.get("chapter_index") or 0) == ch_idx]
        if not ch_segs and segments_plan:
            ch_segs = [
                s for s in segments_plan
                if float(s.get("timeline_end") or 0.0) > ch_st and float(s.get("timeline_start") or 0.0) < ch_en
            ]
        ch_clip_names: list[str] = []
        for s in ch_segs:
            nm = Path(str(s.get("source") or s.get("abs_path") or "")).stem
            if nm and nm not in ch_clip_names:
                ch_clip_names.append(nm)
        clip_tag = f" [Cảnh quay: {', '.join(ch_clip_names[:5])}]" if ch_clip_names else ""
        chap_desc_lines.append(f"- Chương {ch_idx} ({ch_st:.0f}s -> {ch_en:.0f}s){clip_tag}")

        if ch_segs:
            ratios = [0.18, 0.52, 0.84] if frames_per_chap == 3 else [0.24, 0.72]
            picked_indices: list[int] = []
            for r in ratios:
                si = min(len(ch_segs) - 1, max(0, int(round(r * (len(ch_segs) - 1)))))
                if si not in picked_indices or len(ch_segs) == 1:
                    picked_indices.append(si)
                    seg = ch_segs[si]
                    seg_dur = float(seg.get("duration") or 2.0)
                    seek_in_clip = float(seg.get("start") or 0.0) + seg_dur * (0.25 if len(picked_indices) == 1 else 0.65)
                    tl_st = float(seg.get("timeline_start") or ch_st)
                    tl_en = float(seg.get("timeline_end") or (tl_st + seg_dur))
                    tl_t = tl_st + seg_dur * 0.5
                    chapter_frame_specs.append(
                        {
                            "frame_id": f"F{len(chapter_frame_specs) + 1:02d}",
                            "chapter_index": ch_idx,
                            "ch_start": ch_st,
                            "ch_end": ch_en,
                            "tl_start": tl_st,
                            "tl_end": tl_en,
                            "timeline_sec": tl_t,
                            "abs_path": str(seg.get("abs_path") or ""),
                            "duration_sec": seg_dur,
                            "seek_sec": seek_in_clip,
                            "clip_name": Path(str(seg.get("source") or seg.get("abs_path") or "")).name,
                        }
                    )

    if not chapter_frame_specs:
        # Fallback if plan has no segments
        sample_clips = ordered_clips[:8]
        if len(ordered_clips) > 8:
            step = len(ordered_clips) / 8.0
            sample_clips = [ordered_clips[int(i * step)] for i in range(8)]
        for i, sc in enumerate(sample_clips):
            ch_idx = min(n_chap, 1 + int(i * n_chap / max(1, len(sample_clips))))
            chapter_frame_specs.append(
                {
                    "chapter_index": ch_idx,
                    "ch_start": 0.0,
                    "ch_end": total_dur,
                    "timeline_sec": 0.0,
                    "abs_path": str(sc.get("abs_path") or ""),
                    "duration_sec": float(sc.get("duration_sec") or 2.0),
                    "seek_sec": None,
                    "clip_name": str(sc.get("name") or ""),
                }
            )

    chapter_desc = "\n".join(chap_desc_lines)

    json_prompt = (
        f"Bạn là Đạo diễn Vlog YouTube & TikTok chuyên nghiệp. Hãy viết kịch bản lời bình cho video Vlog dài {total_dur:.0f} giây (~{total_dur/60:.1f} phút) "
        f"chia thành đúng {n_chap} Chương theo đúng trình tự thời gian:\n{chapter_desc}\n\n"
        f"Chủ đề / Ghi chú: {topic}\n"
        f"Tiêu đề gợi ý: {vlog_title or topic}\n"
        f"Phong cách: {vibe_meta.get('prompt_hint') or vibe_meta.get('label')}\n"
        f"Danh sách clip thô theo thứ tự: {clip_summary}\n\n"
        "YÊU CẦU CỰC KỲ QUAN TRỌNG:\n"
        "- ĐÚNG NGỮ CẢNH TỪNG CHƯƠNG: Lời bình của Chương nào CHỈ được mô tả đúng hình ảnh thực tế của Chương đó (dựa trên các khung hình được gắn nhãn [Chương X]). TUYỆT ĐỐI không kể trước sự việc của Chương sau (ví dụ chưa đốt lửa thì không được nói lửa tắt).\n"
        "- PHONG CÁCH ĐẠO DIỄN: Nếu Chủ đề/Ghi chú có chỉ định vai diễn đột phá (như Thám tử điều tra, POV Hài hước, Phóng sự kịch tính...), hãy nhập vai TRIỆT ĐỂ giọng điệu đó (đặt câu hỏi bí ẩn, châm biếm duyên dáng hoặc dẫn dắt hồi hộp); nếu không chỉ định thì giữ giọng kể chuyện tự nhiên.\n"
        f"- Tổng lời thoại toàn video khoảng {target_total_words} từ (~{words_per_chap} từ mỗi chương, chia thành {blocks_per_chap} đoạn ngắn 22-30 từ/đoạn rải đều trong chương).\n"
        "- Viết dàn trải đều cho TẤT CẢ các chương từ đầu tới cuối video, không dồn chữ vào đầu video.\n"
        "- TUYỆT ĐỐI KHÔNG lặp lại câu văn hoặc ý diễn đạt giữa các chương.\n"
        "- TUYỆT ĐỐI KHÔNG nhắc giỏ hàng, chốt đơn, freeship hay bán hàng.\n"
        "- Trả về DUY NHẤT JSON hợp lệ theo đúng cấu trúc sau (không giải thích thêm):\n"
        "{\n"
        '  "video_title": "TIÊU ĐỀ NGẮN GỌN ẤN TƯỢNG (<= 45 ký tự)",\n'
        '  "video_subtitle": "Dòng mô tả ngắn (<= 65 ký tự)",\n'
        '  "outro_title": "CẢM ƠN BẠN ĐÃ ĐỒNG HÀNH!",\n'
        f'  "outro_cta": "{vibe_meta.get("cta_default") or "Theo dõi để xem những hành trình tiếp theo nhé!"}",\n'
        '  "visual_direction": {\n'
        '    "title_style": "cinematic_glass | editorial_minimal | campfire_warm | adventure_bold | pastel_soft",\n'
        '    "subtitle_style": "editorial_clean | warm_vlog_gold | mint_nature | cinema_box | highlight_bold",\n'
        '    "accent_color": "#F59E0B"\n'
        '  },\n'
        '  "chapters": [\n'
        '    {\n'
        '      "index": 1,\n'
        '      "chapter_title": "TÊN CHƯƠNG NGẮN (<= 26 ký tự)",\n'
        '      "chapter_subtitle": "Mô tả nhanh 1 dòng (<= 45 ký tự)",\n'
        '      "sticker": {"emoji": "🏕️", "label": "DỰNG TRẠI BÊN HỒ", "sublabel": "Khởi đầu hành trình", "position": "top-right"},\n'
        '      "visual_cues": [\n'
        '        {"frame_id": "F01", "variant": "pointer | free_pop", "target_x": 58, "target_y": 62, "show_arrow": true, "emoji": "🦀", "label": "Gọi đúng tên vật thể nhìn thấy trong frame_id đó", "sublabel": "Mô tả ngắn đúng chi tiết trên ảnh", "position": "center-left", "offset_ratio": 0.36},\n'
        '        {"frame_id": "F02", "variant": "lower_third | free_pop", "show_arrow": false, "emoji": "🐱", "label": "Điểm nhấn hoặc từ khóa khớp lời thoại frame_id", "sublabel": "Ghi chú bối cảnh thực tế trong ảnh", "position": "bottom-left", "offset_ratio": 0.72}\n'
        '      ],\n'
        '      "narration_blocks": [\n'
        '        {"offset_ratio": 0.14, "text": "Đoạn lời bình mở chương bám sát ảnh đầu chương (~20-26 từ)."},\n'
        '        {"offset_ratio": 0.58, "text": "Đoạn lời bình tiếp nối bám sát ảnh sau của chương (~20-26 từ)."}\n'
        '      ]\n'
        '    }\n'
        '  ]\n'
        '}'
    )

    parsed_ai: dict[str, Any] | None = None
    ai_source = "structured_fallback"

    api_key = str(gemini_api_key or "").strip()
    if api_key:
        try:
            import urllib.request

            parts_payload: list[dict[str, Any]] = [{"text": json_prompt}]
            for spec in chapter_frame_specs:
                b64 = _extract_clip_preview_frame_b64(
                    spec["abs_path"],
                    float(spec["duration_sec"]),
                    seek_sec=spec.get("seek_sec"),
                )
                if b64:
                    parts_payload.append(
                        {
                            "text": (
                                f"[{spec.get('frame_id', 'F00')} | Chương {spec['chapter_index']} | "
                                f"Cảnh {spec.get('tl_start', spec['timeline_sec']):.1f}s->{spec.get('tl_end', spec['timeline_sec'] + 4.0):.1f}s "
                                f"| {spec['clip_name']}]"
                            )
                        }
                    )
                    parts_payload.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            req = urllib.request.Request(
                url,
                data=json.dumps({"contents": [{"parts": parts_payload}]}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                cands = data.get("candidates") or []
                if cands:
                    raw_txt = " ".join(
                        str(p.get("text") or "") for p in ((cands[0].get("content") or {}).get("parts") or [])
                    )
                    cand_json = _extract_json_block(raw_txt)
                    if cand_json and isinstance(cand_json.get("chapters"), list) and cand_json["chapters"]:
                        parsed_ai = cand_json
                        ai_source = "gemini_vision"
        except Exception as exc:
            print(f"[LongForm] Gemini Vision script error ({exc})")

    if parsed_ai is None and agy_caller is not None:
        try:
            frame_lines: list[str] = []
            if preview_dir is not None:
                shutil.rmtree(preview_dir, ignore_errors=True)
                preview_dir.mkdir(parents=True, exist_ok=True)
                for idx, spec in enumerate(chapter_frame_specs, start=1):
                    out_jpg = preview_dir / f"ch{spec['chapter_index']:02d}_scene_{idx:02d}.jpg"
                    if _extract_clip_preview_frame_jpg(
                        spec["abs_path"],
                        float(spec["duration_sec"]),
                        out_jpg,
                        seek_sec=spec.get("seek_sec"),
                    ):
                        frame_lines.append(
                            f"- [{spec.get('frame_id', f'F{idx:02d}')} | Chương {spec['chapter_index']} "
                            f"| Cảnh {spec.get('tl_start', spec['timeline_sec']):.1f}s->{spec.get('tl_end', spec['timeline_sec'] + 4.0):.1f}s "
                            f"| {spec['clip_name']}]: {out_jpg}"
                        )
            agy_prompt = json_prompt
            if frame_lines:
                agy_prompt += (
                    "\n\n=== BẮT BUỘC XEM ẢNH KHUNG HÌNH TRƯỚC KHI TRẢ LỜI ===\n"
                    "Hãy dùng tool đọc/xem TẤT CẢ các file ảnh `.jpg` bên dưới trước khi viết JSON. "
                    "Mỗi `visual_cues` PHẢI gắn đúng `frame_id` (`F01`, `F02`...), chỉ gọi tên & tọa độ (`target_x`, `target_y`) của vật thể THẬT SỰ nhìn thấy trong chính file ảnh đó:\n"
                    + "\n".join(frame_lines)
                )
            agy_raw = str(agy_caller(agy_prompt) or "").strip()
            cand_json = _extract_json_block(agy_raw)
            if cand_json and isinstance(cand_json.get("chapters"), list) and cand_json["chapters"]:
                parsed_ai = cand_json
                ai_source = "agy_cli"
            elif len(agy_raw.split()) >= 80:
                # AI returned plain prose instead of JSON: slice prose cleanly across chapters
                clean_prose = re.sub(r"```[a-zA-Z]*\s*", "", agy_raw).replace("```", "")
                clean_prose = re.sub(r"^#+\s+.*$", "", clean_prose, flags=re.M).strip()
                sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_prose) if s.strip()]
                per_c = max(2, len(sents) // max(1, n_chap))
                synth_chapters = []
                for ci, ch in enumerate(chapters_plan):
                    chunk = sents[ci * per_c : (ci + 1) * per_c if ci < n_chap - 1 else len(sents)]
                    mid = max(1, len(chunk) // 2)
                    blocks = []
                    if chunk[:mid]:
                        blocks.append({"offset_ratio": 0.14, "text": " ".join(chunk[:mid])})
                    if chunk[mid:]:
                        blocks.append({"offset_ratio": 0.58, "text": " ".join(chunk[mid:])})
                    synth_chapters.append(
                        {
                            "index": ch["index"],
                            "chapter_title": f"CHẶNG {ch['index']}",
                            "chapter_subtitle": "",
                            "narration_blocks": blocks,
                        }
                    )
                parsed_ai = {
                    "video_title": (vlog_title or topic)[:45],
                    "video_subtitle": "Nhật ký hành trình & trải nghiệm",
                    "chapters": synth_chapters,
                }
                ai_source = "agy_cli"
        except Exception as exc:
            print(f"[LongForm] agy CLI script error ({exc})")

    # Build rich, strictly non-repeating fallback / normalize AI chapters
    seen_norms: list[str] = []
    phase_order = ["opening", "journey", "discovery", "activity", "relaxation", "golden_hour"]
    default_titles = [
        ("KHỞI HÀNH", "Chuẩn bị & bắt đầu hành trình"),
        ("TRÊN ĐƯỜNG ĐI", "Những khung hình dọc đường"),
        ("KHÁM PHÁ ĐIỂM DỪNG", "Không gian thoáng đãng & thiên nhiên"),
        ("TRẢI NGHIỆM & THƯỞNG THỨC", "Những khoảnh khắc cùng bạn bè"),
        ("HOÀNG HÔN & CHILL", "Khoảng lặng êm ả cuối ngày"),
        ("TỔNG KẾT KỶ NIỆM", "Lưu giữ hành trình đáng nhớ"),
    ]
    used_fallback: set[str] = set()

    def _pick_unique_fallback(phase_key: str, count: int = 2) -> str:
        pool = FALLBACK_VLOG_POOL.get(phase_key, []) + FALLBACK_VLOG_POOL["activity"]
        picked: list[str] = []
        for s in pool:
            if s not in used_fallback:
                used_fallback.add(s)
                picked.append(s)
                if len(picked) >= count:
                    break
        return " ".join(picked)

    all_style_combos = [
        ("campfire_warm", "warm_vlog_gold", "#F59E0B"),
        ("adventure_bold", "mint_nature", "#38BDF8"),
        ("editorial_minimal", "editorial_clean", "#34D399"),
        ("pastel_soft", "cinema_box", "#FB7185"),
        ("cinematic_glass", "highlight_bold", "#A78BFA"),
    ]
    vibe_visual_defaults = {
        "outdoor_picnic": all_style_combos[0],
        "travel_vlog": all_style_combos[1],
        "daily_story": all_style_combos[2],
        "food_cafe": all_style_combos[3],
        "creative_internet": all_style_combos[4],
    }
    def_ts, def_ss, def_ac = vibe_visual_defaults.get(
        content_vibe, all_style_combos[4]
    )
    if avoid_title_style and def_ts == avoid_title_style:
        idx_cur = next((i for i, c in enumerate(all_style_combos) if c[0] == avoid_title_style), 0)
        def_ts, def_ss, def_ac = all_style_combos[(idx_cur + 1) % len(all_style_combos)]
    raw_vd = (parsed_ai or {}).get("visual_direction") if isinstance((parsed_ai or {}).get("visual_direction"), dict) else {}
    valid_title_styles = {
        "cinematic_glass", "editorial_minimal", "campfire_warm",
        "adventure_bold", "pastel_soft", "detective_noir",
        "comic_pop", "cinema_letterbox",
    }
    valid_sub_styles = {"editorial_clean", "warm_vlog_gold", "mint_nature", "cinema_box", "highlight_bold"}
    raw_ts = str(raw_vd.get("title_style") or "").strip().split("|")[0].strip()
    raw_ss = str(raw_vd.get("subtitle_style") or "").strip().split("|")[0].strip()
    raw_ac = str(raw_vd.get("accent_color") or "").strip()
    picked_ts = raw_ts if raw_ts in valid_title_styles else def_ts
    if avoid_title_style and picked_ts == avoid_title_style:
        picked_ts = def_ts
    picked_ss = raw_ss if raw_ss in valid_sub_styles else def_ss
    picked_ac = raw_ac if re.fullmatch(r"#[0-9a-fA-F]{6}", raw_ac) else def_ac
    if vp_prof.get("force_vfx") and not preferred_title_style:
        picked_ts = str(vp_prof.get("title_style") or picked_ts)
        picked_ss = str(vp_prof.get("subtitle_style") or picked_ss)
        picked_ac = str(vp_prof.get("accent_color") or picked_ac)
    if preferred_title_style in valid_title_styles:
        picked_ts = preferred_title_style
    if preferred_subtitle_style in valid_sub_styles:
        picked_ss = preferred_subtitle_style
    if re.fullmatch(r"#[0-9a-fA-F]{6}", str(preferred_accent_color or "").strip()):
        picked_ac = str(preferred_accent_color).strip()
    final_visual_dir = {
        "title_style": picked_ts,
        "subtitle_style": picked_ss,
        "accent_color": picked_ac,
    }
    default_chapter_stickers = [
        ("🏕️", "KHỞI HÀNH", "Mở đầu chuyến đi", "top-right"),
        ("🚗", "TRÊN ĐƯỜNG", "Khung cảnh dọc đường", "top-left"),
        ("🌿", "KHÁM PHÁ", "Không gian thiên nhiên", "top-right"),
        ("🔥", "TRẢI NGHIỆM", "Khoảnh khắc đáng nhớ", "bottom-right"),
        ("🌅", "THƯ GIÃN", "Nhịp sống chậm lại", "top-right"),
        ("✨", "KỶ NIỆM", "Lưu giữ hành trình", "top-left"),
    ]

    ai_chapters = (parsed_ai or {}).get("chapters") or []
    final_chapters: list[dict[str, Any]] = []
    for ci, ch_plan in enumerate(chapters_plan):
        ai_ch = ai_chapters[ci] if ci < len(ai_chapters) and isinstance(ai_chapters[ci], dict) else {}
        def_t, def_sub = default_titles[min(ci, len(default_titles) - 1)]
        c_title = str(ai_ch.get("chapter_title") or def_t).strip()[:30]
        c_sub = str(ai_ch.get("chapter_subtitle") or def_sub).strip()[:50]
        raw_stk = ai_ch.get("sticker") if isinstance(ai_ch.get("sticker"), dict) else {}
        def_em, def_sl, def_ssub, def_pos = default_chapter_stickers[ci % len(default_chapter_stickers)]
        stk_pos = str(raw_stk.get("position") or def_pos).strip()
        if stk_pos not in {"top-right", "top-left", "bottom-right"}:
            stk_pos = def_pos
        clean_sticker = {
            "emoji": str(raw_stk.get("emoji") or def_em).strip()[:4] or def_em,
            "label": str(raw_stk.get("label") or c_title or def_sl).strip()[:24],
            "sublabel": str(raw_stk.get("sublabel") or def_ssub).strip()[:32],
            "position": stk_pos,
        }
        raw_cues = ai_ch.get("visual_cues") if isinstance(ai_ch.get("visual_cues"), list) else []
        clean_cues: list[dict[str, Any]] = []
        valid_variants = {"callout", "lower_third", "floating_lottie", "pill", "pointer", "free_pop"}
        valid_positions = {"top-right", "top-left", "bottom-right", "bottom-left", "center-left", "center-right"}
        fallback_variants = ["callout", "lower_third", "floating_lottie"]
        fallback_positions = ["center-left", "bottom-left", "center-right", "top-right"]
        for cue_i, rc in enumerate(raw_cues[:2]):
            if not isinstance(rc, dict):
                continue
            cv = str(rc.get("variant") or fallback_variants[(ci + cue_i) % len(fallback_variants)]).strip()
            if cv not in valid_variants:
                cv = fallback_variants[(ci + cue_i) % len(fallback_variants)]
            cp = str(rc.get("position") or fallback_positions[(ci + cue_i) % len(fallback_positions)]).strip()
            if cp not in valid_positions:
                cp = fallback_positions[(ci + cue_i) % len(fallback_positions)]
            cl = str(rc.get("label") or clean_sticker["label"]).strip()[:34]
            csub = str(rc.get("sublabel") or clean_sticker["sublabel"]).strip()[:52]
            if not cl:
                continue
            try:
                off_r = float(rc.get("offset_ratio") or (0.35 + cue_i * 0.35))
            except Exception:
                off_r = 0.35 + cue_i * 0.35
            try:
                tx = float(rc.get("target_x") if rc.get("target_x") is not None else 56)
            except Exception:
                tx = 56.0
            try:
                ty = float(rc.get("target_y") if rc.get("target_y") is not None else 58)
            except Exception:
                ty = 58.0
            fid = str(rc.get("frame_id") or "").strip().upper()
            matched_spec = next((sp for sp in chapter_frame_specs if sp.get("frame_id") == fid), None)
            if matched_spec is None:
                ch_specs = [sp for sp in chapter_frame_specs if int(sp.get("chapter_index") or 0) == int(ch_plan["index"])]
                if ch_specs:
                    matched_spec = ch_specs[min(cue_i, len(ch_specs) - 1)]
            cue_obj: dict[str, Any] = {
                "frame_id": matched_spec.get("frame_id", fid) if matched_spec else fid,
                "variant": cv,
                "emoji": str(rc.get("emoji") or clean_sticker["emoji"]).strip()[:4] or clean_sticker["emoji"],
                "label": cl,
                "sublabel": csub,
                "position": cp,
                "target_x": max(12.0, min(88.0, tx)),
                "target_y": max(16.0, min(82.0, ty)),
                "show_arrow": bool(rc.get("show_arrow")) if "show_arrow" in rc else (cv in {"pointer", "free_pop"}),
                "offset_ratio": max(0.22, min(0.84, off_r)),
            }
            if matched_spec and matched_spec.get("tl_start") is not None and matched_spec.get("tl_end") is not None:
                tl_s = float(matched_spec["tl_start"])
                tl_e = float(matched_spec["tl_end"])
                if tl_e - tl_s >= 1.8:
                    cue_obj["start_sec"] = round(tl_s + 0.15, 2)
                    cue_obj["end_sec"] = round(tl_e - 0.1, 2)
            clean_cues.append(cue_obj)
        raw_blocks = ai_ch.get("narration_blocks") if isinstance(ai_ch.get("narration_blocks"), list) else []

        clean_blocks: list[dict[str, Any]] = []
        phase_key = phase_order[min(ci, len(phase_order) - 1)]
        if ci == n_chap - 1 and n_chap > 2:
            phase_key = "closing"

        for bi, blk in enumerate(raw_blocks[:4]):
            if not isinstance(blk, dict):
                continue
            deduped = _deduplicate_sentences(str(blk.get("text") or ""), seen_norms)
            if deduped:
                clean_blocks.append(
                    {
                        "offset_ratio": float(blk.get("offset_ratio") if blk.get("offset_ratio") is not None else (0.14 + bi * 0.42)),
                        "text": deduped,
                    }
                )

        if not clean_blocks:
            t1 = _deduplicate_sentences(_pick_unique_fallback(phase_key, 2), seen_norms)
            t2 = _deduplicate_sentences(
                _pick_unique_fallback("closing" if ci == n_chap - 1 else phase_order[min(ci + 1, len(phase_order) - 1)], 2),
                seen_norms,
            )
            if t1:
                clean_blocks.append({"offset_ratio": 0.14, "text": t1})
            if t2:
                clean_blocks.append({"offset_ratio": 0.58, "text": t2})

        final_chapters.append(
            {
                "index": ch_plan["index"],
                "chapter_title": c_title,
                "chapter_subtitle": c_sub,
                "sticker": clean_sticker,
                "visual_cues": clean_cues,
                "start_sec": float(ch_plan["start_sec"]),
                "end_sec": float(ch_plan["end_sec"]),
                "narration_blocks": clean_blocks,
            }
        )

    final_title = str(vlog_title or (parsed_ai or {}).get("video_title") or topic).strip()[:48]
    final_sub = str((parsed_ai or {}).get("video_subtitle") or vibe_meta.get("label") or "Nhật ký Vlog").strip()[:68]
    outro_title = str((parsed_ai or {}).get("outro_title") or "CẢM ƠN BẠN ĐÃ ĐỒNG HÀNH!").strip()[:50]
    outro_cta = str((parsed_ai or {}).get("outro_cta") or vibe_meta.get("cta_default") or "Lưu lại & hẹn gặp ở tập sau nha!").strip()[:70]

    return {
        "ai_source": ai_source,
        "video_title": final_title,
        "video_subtitle": final_sub,
        "outro_title": outro_title,
        "outro_cta": outro_cta,
        "visual_direction": final_visual_dir,
        "chapters": final_chapters,
    }


def generate_longform_vlog_script(
    ordered_clips: list[dict[str, Any]],
    target_duration_sec: float,
    topic_note: str = "",
    content_vibe: str = "outdoor_picnic",
    gemini_api_key: str = "",
    agy_caller: Any = None,
    preview_dir: Path | None = None,
) -> tuple[str, str]:
    """Compatibility helper returning flat (display_text, tts_text) from structured chapter script."""
    dummy_plan = build_longform_timeline_plan(ordered_clips, target_duration_sec=target_duration_sec)
    ch_script = generate_longform_chapter_script(
        plan=dummy_plan,
        ordered_clips=ordered_clips,
        topic_note=topic_note,
        content_vibe=content_vibe,
        gemini_api_key=gemini_api_key,
        agy_caller=agy_caller,
        preview_dir=preview_dir,
    )
    disp = " ".join(
        blk["text"]
        for ch in ch_script["chapters"]
        for blk in ch["narration_blocks"]
    ).strip()
    return disp, _sd.convert_display_to_tts_script(disp)


def _synth_edge_tts_wav(text: str, out_wav: Path, voice: str, rate: str, pitch: str) -> bool:
    try:
        import edge_tts

        mp3_p = out_wav.with_suffix(".mp3")

        async def _run() -> None:
            comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
            await asyncio.wait_for(comm.save(str(mp3_p)), timeout=15.0)

        asyncio.run(_run())
        ffmpeg_bin = find_binary("ffmpeg")
        subprocess.run(
            [ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error", "-i", str(mp3_p), "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(out_wav)],
            check=True,
            timeout=60,
        )
        mp3_p.unlink(missing_ok=True)
        return out_wav.exists() and out_wav.stat().st_size > 1000
    except Exception as exc:
        print(f"[LongForm TTS] Edge-TTS error: {exc}")
        return False


def _synth_piper_wav(text: str, out_wav: Path, model_key: str, length_scale: float, speaker_id: int | None) -> bool:
    try:
        from piper.voice import PiperVoice
        from piper.config import SynthesisConfig

        meta = _ve.PIPER_VOICE_MODELS.get(model_key) or _ve.PIPER_VOICE_MODELS["vi_VN-vais1000-medium"]
        _ve.PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
        onnx_p = _ve.PIPER_VOICES_DIR / meta["filename"]
        if not onnx_p.exists():
            import urllib.request

            urllib.request.urlretrieve(f"{_ve.PIPER_HF_BASE}{meta['hf_path']}", str(onnx_p))
            urllib.request.urlretrieve(f"{_ve.PIPER_HF_BASE}{meta['hf_path']}.json", f"{onnx_p}.json")

        voice = PiperVoice.load(str(onnx_p))
        syn_cfg = SynthesisConfig(length_scale=length_scale, speaker_id=(speaker_id if speaker_id is not None and speaker_id >= 0 else None))
        tmp_raw = out_wav.with_name(f"{out_wav.stem}_raw.wav")
        with wave.open(str(tmp_raw), "wb") as wf:
            voice.synthesize_wav(text, wf, syn_config=syn_cfg)
        ffmpeg_bin = find_binary("ffmpeg")
        subprocess.run(
            [ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error", "-i", str(tmp_raw), "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(out_wav)],
            check=True,
            timeout=60,
        )
        tmp_raw.unlink(missing_ok=True)
        return out_wav.exists() and out_wav.stat().st_size > 1000
    except Exception as exc:
        print(f"[LongForm TTS] Piper error: {exc}")
        return False


def _split_display_caption_lines(text: str, max_words: int = 9) -> list[str]:
    words = [w for w in (text or "").strip().split() if w]
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or (len(cur) >= 5 and w.endswith((",", ".", "!", "?"))):
            lines.append(" ".join(cur))
            cur = []
    if cur:
        lines.append(" ".join(cur))
    return lines


def _clean_tts_text(text: str) -> str:
    txt = re.sub(r"[*_`~#\[\](){}<>]", " ", str(text or ""))
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _trim_pcm_silence(pcm: np.ndarray, sample_rate: int, thresh: float = 0.008) -> np.ndarray:
    arr = np.asarray(pcm, dtype=np.float32).reshape(-1)
    if len(arr) < int(sample_rate * 0.05):
        return arr
    idx = np.where(np.abs(arr) >= thresh)[0]
    if len(idx) == 0:
        return arr
    pad = int(sample_rate * 0.03)
    st = max(0, int(idx[0]) - pad)
    en = min(len(arr), int(idx[-1]) + pad)
    return arr[st:en]


def _parse_phonetic_overrides(raw_map: str | dict[str, str] | None) -> list[tuple[str, str]]:
    if isinstance(raw_map, dict):
        return [(str(k).strip(), str(v).strip()) for k, v in raw_map.items() if str(k).strip() and str(v).strip()]
    pairs: list[tuple[str, str]] = []
    for line in str(raw_map or "").splitlines():
        ln = line.strip()
        if not ln or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        if k.strip() and v.strip():
            pairs.append((k.strip(), v.strip()))
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs


def _apply_phonetic_overrides(text: str, pairs: list[tuple[str, str]]) -> str:
    out = str(text or "")
    for src, dst in pairs:
        out = re.sub(rf"(?<!\w){re.escape(src)}(?!\w)", dst, out, flags=re.IGNORECASE)
    return out


def _vlog_edge_rate(raw_rate: str, override_rate: str = "") -> str:
    ov = str(override_rate or "").strip()
    if re.fullmatch(r"[+-]?\d+%", ov):
        return ov if ov[0] in "+-" else f"+{ov}"
    r = (raw_rate or "+0%").strip()
    if r.startswith("-") and len(r) >= 3:
        return r
    return "-5%"


def build_longform_voice_and_srt(
    chapter_script: dict[str, Any],
    plan: dict[str, Any],
    out_wav_path: Path,
    out_srt_path: Path,
    voice_preset: str = "edge_hoaimy_koc",
    sentence_pause_sec: float = 0.85,
    voice_rate_override: str = "",
    phonetic_overrides: str | dict[str, str] | None = None,
    progress_cb: Any = None,
) -> dict[str, Any]:
    """Synthesize calm sentence-spaced vlog narration distributed evenly across the entire video."""
    preset = _ve.resolve_voice_preset(voice_preset)
    engine = str(preset.get("tts_engine") or "edge_tts")
    vlog_edge_rate = _vlog_edge_rate(str(preset.get("edge_rate") or "+0%"), override_rate=voice_rate_override)
    rate_pct = 0
    m_rate = re.match(r"([+-]?\d+)%", vlog_edge_rate)
    if m_rate:
        rate_pct = int(m_rate.group(1))
    vlog_piper_scale = max(0.88, min(1.30, float(preset.get("piper_length_scale") or 1.0) * (1.0 - rate_pct / 100.0 + 0.05)))
    sr = 24000
    total_dur = float(plan.get("target_duration_sec") or 300.0)
    master_samples = np.zeros(int(round(total_dur * sr)), dtype=np.float32)

    ffmpeg_bin = find_binary("ffmpeg")
    srt_entries: list[tuple[float, float, str]] = []
    sentence_pause_sec = max(0.2, min(2.5, float(sentence_pause_sec if sentence_pause_sec is not None else 0.85)))
    phonetic_pairs = _parse_phonetic_overrides(phonetic_overrides)

    piper_voice_obj = None
    piper_syn_cfg = None
    f5_model = None
    f5_ref_wav: Path | None = None
    f5_ref_text = ""
    f5_tmp_dir_obj = None
    base_f5 = float(preset.get("speed") or 1.0) * 0.94
    if str(voice_rate_override or "").strip():
        base_f5 = 1.0 + (rate_pct / 100.0)
    vlog_f5_speed = max(0.80, min(1.15, base_f5))

    def _ensure_f5_model_and_ref(explicit_ref: str | None = None) -> bool:
        nonlocal f5_model, f5_ref_wav, f5_ref_text, f5_tmp_dir_obj
        if f5_model is not None and f5_ref_wav is not None:
            return True
        try:
            ref_raw = _ve.find_ref_audio(explicit_ref)
            f5_tmp_dir_obj = tempfile.TemporaryDirectory()
            ref_norm_p = Path(f5_tmp_dir_obj.name) / "ref_norm.wav"
            f5_ref_wav, was_clipped = _ve.normalize_reference_audio(ref_raw, ref_norm_p)
            r_txt_p = ref_raw.with_suffix(".txt")
            if not r_txt_p.exists() and _ve.DEFAULT_REF_TEXT_FILE.exists():
                r_txt_p = _ve.DEFAULT_REF_TEXT_FILE
            elif not r_txt_p.exists() and _ve.FALLBACK_REF_TEXT_FILE.exists():
                r_txt_p = _ve.FALLBACK_REF_TEXT_FILE
            r_txt = r_txt_p.read_text(encoding="utf-8-sig").strip() if r_txt_p.exists() and not was_clipped else ""
            if not r_txt:
                r_txt = _ve.transcribe_audio_text(f5_ref_wav, model_size="small")
                if not r_txt_p.exists():
                    r_txt_p.write_text(r_txt + "\n", encoding="utf-8")
            f5_ref_text = r_txt.strip().lower()
            if f5_ref_text and f5_ref_text[-1] not in ".!?":
                f5_ref_text += "."
            f5_model = _ve.get_cached_f5_model()
            return True
        except Exception as exc:
            print(f"[LongForm F5-TTS Init WARN] {exc}")
            f5_model = None
            if f5_tmp_dir_obj is not None:
                f5_tmp_dir_obj.cleanup()
                f5_tmp_dir_obj = None
            return False

    if engine == "f5_tts":
        if not _ensure_f5_model_and_ref(preset.get("ref_audio")):
            print("[LongForm F5-TTS Init WARN] -> fallback Edge-TTS")
    elif engine == "piper_tts":
        try:
            from piper.voice import PiperVoice
            from piper.config import SynthesisConfig

            model_key = str(preset.get("piper_model") or "vi_VN-vais1000-medium")
            meta = _ve.PIPER_VOICE_MODELS.get(model_key) or _ve.PIPER_VOICE_MODELS["vi_VN-vais1000-medium"]
            _ve.PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
            onnx_p = _ve.PIPER_VOICES_DIR / meta["filename"]
            if not onnx_p.exists():
                import urllib.request

                urllib.request.urlretrieve(f"{_ve.PIPER_HF_BASE}{meta['hf_path']}", str(onnx_p))
                urllib.request.urlretrieve(f"{_ve.PIPER_HF_BASE}{meta['hf_path']}.json", f"{onnx_p}.json")
            piper_voice_obj = PiperVoice.load(str(onnx_p))
            sp_id = preset.get("piper_speaker")
            piper_syn_cfg = SynthesisConfig(
                length_scale=vlog_piper_scale,
                speaker_id=(sp_id if sp_id is not None and sp_id >= 0 else None),
            )
        except Exception as exc:
            print(f"[LongForm Piper Init WARN] {exc}")
            piper_voice_obj = None

    def _ensure_piper_fallback() -> bool:
        nonlocal piper_voice_obj, piper_syn_cfg
        if piper_voice_obj is not None and piper_syn_cfg is not None:
            return True
        try:
            from piper.voice import PiperVoice
            from piper.config import SynthesisConfig

            model_key = str(preset.get("piper_model") or "vi_VN-vais1000-medium")
            meta = _ve.PIPER_VOICE_MODELS.get(model_key) or _ve.PIPER_VOICE_MODELS["vi_VN-vais1000-medium"]
            _ve.PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
            onnx_p = _ve.PIPER_VOICES_DIR / meta["filename"]
            if not onnx_p.exists():
                import urllib.request

                urllib.request.urlretrieve(f"{_ve.PIPER_HF_BASE}{meta['hf_path']}", str(onnx_p))
                urllib.request.urlretrieve(f"{_ve.PIPER_HF_BASE}{meta['hf_path']}.json", f"{onnx_p}.json")
            piper_voice_obj = PiperVoice.load(str(onnx_p))
            sp_id = preset.get("piper_speaker")
            piper_syn_cfg = SynthesisConfig(
                length_scale=vlog_piper_scale,
                speaker_id=(sp_id if sp_id is not None and sp_id >= 0 else None),
            )
            return True
        except Exception as exc:
            print(f"[LongForm Piper Fallback WARN] {exc}")
            return False

    def _run_f5_infer(sent_txt: str, out_w: Path) -> bool:
        if f5_model is None or f5_ref_wav is None:
            return False
        for _attempt in range(2):
            try:
                gen_norm = _ve.normalize_vietnamese_script(sent_txt)
                part_wav, part_sr, _ = f5_model.infer(
                    ref_file=str(f5_ref_wav),
                    ref_text=f5_ref_text,
                    gen_text=gen_norm,
                    speed=vlog_f5_speed,
                    nfe_step=16,
                    cfg_strength=2.0,
                    sway_sampling_coef=-1.0,
                    seed=42,
                    remove_silence=False,
                )
                if part_wav is not None and len(part_wav) > 0:
                    arr_1d = np.asarray(part_wav, dtype=np.float32).reshape(-1)
                    out_sr = int(part_sr or sr)
                    if out_sr == sr:
                        sf.write(str(out_w), arr_1d, sr, subtype="PCM_16")
                    else:
                        tmp_raw = out_w.with_name(f"{out_w.stem}_f5raw.wav")
                        sf.write(str(tmp_raw), arr_1d, out_sr)
                        subprocess.run(
                            [ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error", "-i", str(tmp_raw), "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(out_w)],
                            check=True,
                            timeout=60,
                        )
                        tmp_raw.unlink(missing_ok=True)
                    if out_w.exists() and out_w.stat().st_size > 800:
                        return True
            except Exception as exc:
                print(f"[LongForm F5-TTS Infer WARN] {exc}")
        return False

    is_male_preset = str(preset.get("gender") or "").lower() == "male" or "namminh" in str(preset.get("edge_voice") or "").lower()
    hybrid_f5_ref = "03_voice_clone/voices/nam_minh_local_ref.wav" if is_male_preset else "03_voice_clone/voices/hoai_my_local_ref.wav"

    def _synth_one_sentence(sent_txt: str, out_w: Path) -> bool:
        if engine == "f5_tts" and f5_model is not None and f5_ref_wav is not None:
            if _run_f5_infer(sent_txt, out_w):
                return True
        if engine == "piper_tts" and _ensure_piper_fallback():
            try:
                tmp_raw = out_w.with_name(f"{out_w.stem}_praw.wav")
                with wave.open(str(tmp_raw), "wb") as wf:
                    piper_voice_obj.synthesize_wav(sent_txt, wf, syn_config=piper_syn_cfg)
                subprocess.run(
                    [ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error", "-i", str(tmp_raw), "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(out_w)],
                    check=True,
                    timeout=60,
                )
                tmp_raw.unlink(missing_ok=True)
                if out_w.exists() and out_w.stat().st_size > 800:
                    return True
            except Exception:
                pass
        if edge_circuit_open:
            pass
        else:
            for _edge_try, _wait_s in enumerate((1.5, 3.5), start=1):
                if _synth_edge_tts_wav(
                    sent_txt,
                    out_w,
                    str(preset.get("edge_voice") or "vi-VN-HoaiMyNeural"),
                    vlog_edge_rate,
                    str(preset.get("edge_pitch") or "+0Hz"),
                ):
                    edge_consecutive_fails = 0
                    time.sleep(0.22)
                    return True
                print(f"[LongForm Edge-TTS Retry {_edge_try}/2] Đợi {_wait_s:.1f}s rồi thử lại...")
                time.sleep(_wait_s)
            edge_consecutive_fails += 1
            if edge_consecutive_fails >= 2:
                edge_circuit_open = True
                print("[LongForm Edge-TTS] Mạng/API Edge-TTS bị giới hạn liên tiếp -> chuyển sang F5-TTS Local cùng màu giọng cho các câu tiếp theo.")
        if _ensure_f5_model_and_ref(hybrid_f5_ref) and _run_f5_infer(sent_txt, out_w):
            return True
        if _ensure_piper_fallback():
            try:
                tmp_raw = out_w.with_name(f"{out_w.stem}_pfb.wav")
                with wave.open(str(tmp_raw), "wb") as wf:
                    piper_voice_obj.synthesize_wav(sent_txt, wf, syn_config=piper_syn_cfg)
                subprocess.run(
                    [ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error", "-i", str(tmp_raw), "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(out_w)],
                    check=True,
                    timeout=60,
                )
                tmp_raw.unlink(missing_ok=True)
                if out_w.exists() and out_w.stat().st_size > 800:
                    return True
            except Exception:
                pass
        return False

    # Pass 1: Synthesize all blocks sentence-by-sentence with 0.85s natural breathing pauses
    edge_consecutive_fails = 0
    edge_circuit_open = False
    chapters_all = chapter_script.get("chapters") or []
    total_blocks = sum(len(ch.get("narration_blocks") or []) for ch in chapters_all)
    done_blocks = 0
    synthesized_blocks: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_p = Path(tmpdir)
        for ch_pos, ch in enumerate(chapters_all, start=1):
            ch_idx = int(ch.get("index") or ch_pos)
            for bi, blk in enumerate(ch.get("narration_blocks") or [], start=1):
                done_blocks += 1
                if callable(progress_cb):
                    try:
                        progress_cb(done_blocks, max(1, total_blocks), f"Chương {ch_idx} · Đoạn {done_blocks}/{max(1, total_blocks)}")
                    except Exception:
                        pass
                disp_txt = str(blk.get("text") or "").strip()
                if not disp_txt:
                    continue
                raw_sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", disp_txt) if s.strip()] or [disp_txt]
                sent_pcms: list[np.ndarray] = []
                sent_disp: list[str] = []
                for si, s_disp in enumerate(raw_sents, start=1):
                    s_speak = _clean_tts_text(_apply_phonetic_overrides(s_disp, phonetic_pairs))
                    if not s_speak:
                        continue
                    s_wav = tmp_p / f"ch{ch_idx}_b{bi}_s{si}.wav"
                    if not _synth_one_sentence(s_speak, s_wav):
                        continue
                    pcm, p_sr = sf.read(str(s_wav), dtype="float32")
                    pcm_1d = _trim_pcm_silence(np.asarray(pcm, dtype=np.float32).reshape(-1), int(p_sr))
                    if len(pcm_1d) >= 300:
                        sent_pcms.append(pcm_1d)
                        sent_disp.append(s_disp)
                if not sent_pcms:
                    continue

                # Join sentences with 0.85s calm breathing pause
                pause_arr = np.zeros(int(round(sentence_pause_sec * sr)), dtype=np.float32)
                joined_parts: list[np.ndarray] = []
                sent_offsets: list[tuple[float, float, str]] = []
                cur_offset = 0.0
                for idx_s, (spcm, sdisp) in enumerate(zip(sent_pcms, sent_disp)):
                    if idx_s > 0:
                        joined_parts.append(pause_arr)
                        cur_offset += sentence_pause_sec
                    sdur = len(spcm) / float(sr)
                    joined_parts.append(spcm)
                    sent_offsets.append((cur_offset, cur_offset + sdur, sdisp))
                    cur_offset += sdur

                blk_pcm = np.concatenate(joined_parts)
                synthesized_blocks.append(
                    {
                        "chapter_index": ch_idx,
                        "offset_ratio": float(blk.get("offset_ratio") if blk.get("offset_ratio") is not None else 0.14),
                        "pcm": blk_pcm,
                        "duration": len(blk_pcm) / float(sr),
                        "sent_offsets": sent_offsets,
                    }
                )

    if f5_model is not None:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
            pass
    if f5_tmp_dir_obj is not None:
        try:
            f5_tmp_dir_obj.cleanup()
        except Exception:
            pass

    # Pass 2: Chapter-Locked Placement — keep each chapter's narration strictly inside its own [start_sec .. end_sec]
    safe_start = 4.8 if total_dur >= 20.0 else 0.3
    safe_end = max(safe_start + 3.0, total_dur - (6.5 if total_dur >= 20.0 else 0.4))

    chapters_plan = plan.get("chapters") or []
    chap_windows: dict[int, tuple[float, float]] = {}
    for ci, ch in enumerate(chapters_plan):
        ch_idx = int(ch.get("index") or (ci + 1))
        raw_st = float(ch.get("start_sec") or 0.0)
        raw_en = float(ch.get("end_sec") or total_dur)
        is_first = ci == 0
        is_last = ci == len(chapters_plan) - 1
        win_st = max(safe_start if is_first else raw_st + 2.0, raw_st + (1.0 if is_first else 2.0))
        win_en = min(safe_end if is_last else raw_en - 1.4, raw_en - (1.0 if is_last else 1.4))
        if win_en <= win_st + 1.2:
            win_st = max(safe_start, raw_st + 0.5)
            win_en = min(safe_end, max(win_st + 1.5, raw_en - 0.5))
        chap_windows[ch_idx] = (win_st, win_en)

    blocks_by_chap: dict[int, list[dict[str, Any]]] = {}
    for b_info in synthesized_blocks:
        blocks_by_chap.setdefault(int(b_info["chapter_index"]), []).append(b_info)

    placed_blocks = 0
    placed_sentences: list[tuple[float, float, str]] = []
    for ch_idx in sorted(blocks_by_chap.keys()):
        ch_blocks = blocks_by_chap[ch_idx]
        win_st, win_en = chap_windows.get(ch_idx, (safe_start, safe_end))
        ch_span = max(0.5, win_en - win_st)
        ch_speech = sum(float(b["duration"]) for b in ch_blocks)
        n_c = len(ch_blocks)
        free_pool = max(0.0, ch_span - ch_speech)

        if n_c == 1:
            off_r = max(0.0, min(0.75, float(ch_blocks[0].get("offset_ratio") or 0.14)))
            lead_gap = min(free_pool * 0.45, ch_span * off_r * 0.45)
            cursor_t = win_st + lead_gap
            gap_after_each = 0.0
        else:
            lead_gap = (free_pool / float(n_c)) * 0.28
            gap_after_each = (free_pool - lead_gap) / float(max(1, n_c - 1)) if n_c > 1 else 0.0
            # Keep last block comfortably before win_en so trailing B-roll breathes
            if n_c >= 2 and free_pool > 2.5:
                lead_gap = free_pool * 0.14
                tail_reserve = free_pool * 0.22
                gap_after_each = max(0.8, (free_pool - lead_gap - tail_reserve) / float(n_c - 1))
            cursor_t = win_st + lead_gap

        for b_info in ch_blocks:
            b_pcm = b_info["pcm"]
            if cursor_t + 0.8 >= win_en:
                break
            max_samples_in_win = max(0, int(round((win_en - cursor_t) * sr)))
            st_idx = int(round(cursor_t * sr))
            en_idx = min(len(master_samples), st_idx + len(b_pcm), st_idx + max_samples_in_win)
            copy_len = en_idx - st_idx
            if copy_len <= 0:
                break
            master_samples[st_idx:en_idx] += b_pcm[:copy_len]
            placed_blocks += 1

            for s_off_st, s_off_en, s_disp in b_info["sent_offsets"]:
                abs_st = cursor_t + s_off_st
                abs_en = min(cursor_t + s_off_en, cursor_t + copy_len / float(sr))
                if abs_en <= abs_st + 0.15:
                    continue
                placed_sentences.append((abs_st, abs_en, s_disp))

            cursor_t += (copy_len / float(sr)) + gap_after_each

    out_wav_path.parent.mkdir(parents=True, exist_ok=True)
    raw_master = out_wav_path.with_name(f"{out_wav_path.stem}_raw.wav")
    sf.write(str(raw_master), np.clip(master_samples, -0.98, 0.98), sr)

    eq_prefix = _ve.VOCAL_EQ_FILTERS.get(str(preset.get("vocal_eq") or "neutral"), "")
    try:
        subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(raw_master),
                "-af",
                f"highpass=f=75,lowpass=f=11500,{eq_prefix}acompressor=threshold=-18dB:ratio=2.5:attack=12:release=140:makeup=2dB,alimiter=limit=0.95",
                "-ar",
                str(sr),
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(out_wav_path),
            ],
            check=True,
            timeout=90,
        )
        raw_master.unlink(missing_ok=True)
    except Exception:
        os.replace(str(raw_master), str(out_wav_path))

    # Align SRT subtitles directly to the real mastered WAV via Faster-Whisper word timestamps
    whisper_words: list[dict[str, Any]] = []
    if placed_sentences and out_wav_path.exists():
        w_model = None
        try:
            w_model = _ve.load_whisper("small")
            segs_gen, _ = w_model.transcribe(
                str(out_wav_path),
                language="vi",
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 350},
                word_timestamps=True,
                beam_size=3,
            )
            whisper_words = _ve.extract_word_timestamps(list(segs_gen))
        except Exception as exc:
            print(f"[LongForm Whisper Align WARN] {exc}")
        finally:
            if w_model is not None:
                del w_model
            try:
                import gc, torch

                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    for abs_st, abs_en, s_disp in placed_sentences:
        s_start, s_end = _sd._trim_wav_beat_silence(out_wav_path, abs_st, abs_en)
        sent_ww = [
            w
            for w in whisper_words
            if isinstance(w, dict)
            and (abs_st - 0.15) <= ((float(w.get("start") or 0.0) + float(w.get("end") or 0.0)) * 0.5) <= (abs_en + 0.15)
        ]
        tokens = s_disp.split()
        if sent_ww and tokens:
            aligned_w = _sd._align_tokens_to_beat_window(tokens, s_start, s_end, sent_ww)
            grp = _sd._group_words_to_srt_entries(aligned_w, max_words=9)
            for gs, ge, gt in grp:
                if ge > gs + 0.12 and gt:
                    srt_entries.append((gs, ge, gt))
            continue

        lines = _split_display_caption_lines(s_disp, max_words=9)
        total_chars = max(1, sum(len(ln) for ln in lines))
        cur_l = s_start
        span_s = max(0.2, s_end - s_start)
        for ln in lines:
            ln_dur = (len(ln) / float(total_chars)) * span_s
            ln_end = min(s_end, cur_l + ln_dur)
            if ln_end > cur_l + 0.15:
                srt_entries.append((cur_l, ln_end, ln))
            cur_l = ln_end

    srt_blocks: list[str] = []
    for idx, (st_s, en_s, txt) in enumerate(srt_entries, start=1):
        srt_blocks.append(f"{idx}\n{_ve.format_srt_timestamp(st_s)} --> {_ve.format_srt_timestamp(en_s)}\n{txt}\n")
    out_srt_path.parent.mkdir(parents=True, exist_ok=True)
    out_srt_path.write_text("\n".join(srt_blocks), encoding="utf-8")

    return {
        "ok": True,
        "placed_blocks": placed_blocks,
        "srt_lines": len(srt_entries),
        "preset_id": preset.get("id"),
        "preset_label": preset.get("label"),
    }


def _find_remotion_tools() -> tuple[str | None, str | None]:
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    browser = None
    for cand in (
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ):
        if cand.exists():
            browser = str(cand)
            break
    return npx, browser


def render_vlog_remotion_overlays(
    plan: dict[str, Any],
    chapter_script: dict[str, Any],
    out_dir: Path,
    aspect_ratio: str = "16:9",
    channel_name: str = "VLOG JOURNAL",
    sticker_density: str = "normal",
    sticker_style: str = "pill_minimal",
) -> list[dict[str, Any]]:
    """Render transparent Remotion WebM overlays for VlogIntro, VlogChapterCards, VlogStickers, and VlogOutro."""
    npx, browser_exe = _find_remotion_tools()
    if not npx or not (DIR_REMOTION / "src" / "Root.tsx").exists():
        return []

    vd = chapter_script.get("visual_direction") if isinstance(chapter_script.get("visual_direction"), dict) else {}
    title_style = str(vd.get("title_style") or "cinematic_glass")
    accent_color = str(vd.get("accent_color") or "#F59E0B")

    out_dir.mkdir(parents=True, exist_ok=True)
    is_portrait = aspect_ratio != "16:9"
    # Render Remotion overlays at crisp 1080p/1920x1080 then upscale onto 4K/2K master cleanly (~3x faster)
    ov_w, ov_h = (1080, 1920) if is_portrait else (1920, 1080)
    total_dur = float(plan.get("target_duration_sec") or 300.0)
    overlays: list[dict[str, Any]] = []

    bundle_dir = out_dir / "_bundle"
    entry_arg = "src/index.ts"
    try:
        b_proc = subprocess.run(
            [npx, "remotion", "bundle", "src/index.ts", str(bundle_dir), "--log=error"],
            cwd=str(DIR_REMOTION),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if b_proc.returncode == 0 and (bundle_dir / "index.html").exists():
            entry_arg = str(bundle_dir)
    except Exception:
        pass

    def _render_one(
        comp_id: str,
        props_dict: dict[str, Any],
        filename: str,
        start_sec: float,
        dur_sec: float = 4.0,
    ) -> None:
        props_file = out_dir / f"{Path(filename).stem}_props.json"
        out_webm = out_dir / filename
        props_file.write_text(json.dumps(props_dict, ensure_ascii=False), encoding="utf-8")
        cmd = [
            npx,
            "remotion",
            "render",
            entry_arg,
            comp_id,
            str(out_webm),
            f"--props={props_file}",
            "--image-format=png",
            "--codec=vp9",
            "--pixel-format=yuva420p",
        ]
        if browser_exe:
            cmd.append(f"--browser-executable={browser_exe}")
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(DIR_REMOTION),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            if proc.returncode == 0 and out_webm.exists() and out_webm.stat().st_size > 2000:
                overlays.append(
                    {
                        "path": out_webm,
                        "start_sec": round(max(0.0, start_sec), 2),
                        "duration_sec": round(max(0.5, dur_sec), 2),
                    }
                )
            else:
                err_tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-300:]
                print(f"[LongForm Remotion WARN] {comp_id} failed ({proc.returncode}): {err_tail}")
        except Exception as exc:
            print(f"[LongForm Remotion] Skip {comp_id} ({exc})")

    # 1. Intro Card (4.5s at 0.2s)
    _render_one(
        "VlogIntro",
        {
            "title": chapter_script.get("video_title") or "CHUYẾN ĐI ĐÁNG NHỚ",
            "subtitle": chapter_script.get("video_subtitle") or "",
            "badgeText": f"{channel_name.upper()} · {plan.get('quality_label', '4K')}",
            "accentColor": accent_color,
            "titleStyle": title_style,
            "durationSec": 4.5,
            "width": ov_w,
            "height": ov_h,
            "aspectRatio": aspect_ratio,
        },
        "intro_overlay.webm",
        0.2,
        4.5,
    )

    # 2. Chapter Cards & Contextual Animated Stickers
    chapters_list = chapter_script.get("chapters") or []
    stk_mode = str(sticker_density or "normal").strip().lower()
    for ci, ch in enumerate(chapters_list):
        c_idx = int(ch.get("index") or 1)
        ch_start = float(ch.get("start_sec") or 0.0)
        ch_end = float(ch.get("end_sec") or total_dur)
        place_t = max(5.2, ch_start + 0.4) if c_idx == 1 else ch_start + 0.3
        if place_t >= total_dur - 8.5:
            continue
        _render_one(
            "VlogChapterCard",
            {
                "chapterNumber": f"{c_idx:02d}",
                "title": ch.get("chapter_title") or f"CHẶNG {c_idx}",
                "subtitle": ch.get("chapter_subtitle") or "",
                "accentColor": accent_color,
                "titleStyle": title_style,
                "durationSec": 3.5,
                "width": ov_w,
                "height": ov_h,
                "aspectRatio": aspect_ratio,
            },
            f"chapter_{c_idx:02d}.webm",
            place_t,
            3.5,
        )

        # Render contextual animated sticker(s) inside EVERY chapter (4.5s each)
        stk = ch.get("sticker") if isinstance(ch.get("sticker"), dict) else None
        stk_style = str(sticker_style or "pill_minimal").strip().lower()
        if stk_style not in {"pill_minimal", "ai_director_rich", "hybrid", "ai_vision_pointer", "ai_pop_sticker"}:
            stk_style = "pill_minimal"
        if stk_mode != "off" and (stk or ch.get("visual_cues")) and (ch_end - ch_start) >= 10.0:
            if stk_style == "pill_minimal":
                stk_ratios = [0.32, 0.70] if stk_mode == "rich" else [0.45]
                for s_i, s_rat in enumerate(stk_ratios):
                    stk_t = max(place_t + 3.8 + s_i * 5.2, ch_start + (ch_end - ch_start) * s_rat)
                    if stk_t < min(ch_end - 1.5, total_dur - 5.5) and stk:
                        _render_one(
                            "VlogStickerOverlay",
                            {
                                "emoji": str(stk.get("emoji") or "✨"),
                                "label": str(stk.get("label") or ch.get("chapter_title") or "KHOẢNH KHẮC"),
                                "sublabel": str(stk.get("sublabel") or ""),
                                "position": str(stk.get("position") or ("top-right" if (c_idx + s_i) % 2 == 1 else "top-left")),
                                "variant": "pill",
                                "accentColor": accent_color,
                                "durationSec": 4.5,
                                "width": ov_w,
                                "height": ov_h,
                                "aspectRatio": aspect_ratio,
                            },
                            f"sticker_{c_idx:02d}_{s_i + 1}.webm",
                            stk_t,
                            4.5,
                        )
            else:
                raw_cues = [c for c in (ch.get("visual_cues") or []) if isinstance(c, dict)]
                if not raw_cues:
                    fb_variants = ["callout", "lower_third", "floating_lottie"]
                    fb_positions = ["center-left", "bottom-left", "center-right", "top-right"]
                    n_blocks = ch.get("narration_blocks") or []
                    b_snip = ""
                    if n_blocks and isinstance(n_blocks[0], dict):
                        b_words = str(n_blocks[0].get("text") or "").split()
                        b_snip = " ".join(b_words[:8]) + ("..." if len(b_words) > 8 else "")
                    raw_cues = [
                        {
                            "variant": fb_variants[ci % len(fb_variants)],
                            "emoji": str((stk or {}).get("emoji") or "✨"),
                            "label": str((stk or {}).get("label") or ch.get("chapter_title") or "KHOẢNH KHẮC"),
                            "sublabel": b_snip or str((stk or {}).get("sublabel") or ch.get("chapter_subtitle") or ""),
                            "position": fb_positions[ci % len(fb_positions)],
                            "offset_ratio": 0.44,
                        },
                        {
                            "variant": fb_variants[(ci + 1) % len(fb_variants)],
                            "emoji": str((stk or {}).get("emoji") or "🌿"),
                            "label": str(ch.get("chapter_subtitle") or (stk or {}).get("sublabel") or "Điểm nhấn"),
                            "sublabel": str((stk or {}).get("label") or ""),
                            "position": fb_positions[(ci + 2) % len(fb_positions)],
                            "offset_ratio": 0.74,
                        },
                    ]
                cue_items: list[dict[str, Any]] = []
                if stk_style == "hybrid" and stk:
                    cue_items.append(
                        {
                            "variant": "pill",
                            "emoji": str(stk.get("emoji") or "✨"),
                            "label": str(stk.get("label") or ch.get("chapter_title") or "KHOẢNH KHẮC"),
                            "sublabel": str(stk.get("sublabel") or ""),
                            "position": str(stk.get("position") or ("top-right" if c_idx % 2 == 1 else "top-left")),
                            "offset_ratio": 0.34,
                        }
                    )
                    if raw_cues:
                        c0 = dict(raw_cues[0])
                        c0["offset_ratio"] = max(0.62, float(c0.get("offset_ratio") or 0.68))
                        cue_items.append(c0)
                else:
                    max_cues = 2 if stk_mode == "rich" else 1
                    cue_items = raw_cues[:max_cues]
                    if stk_style == "ai_vision_pointer" and cue_items:
                        ptr_presets = [(58.0, 62.0), (42.0, 56.0), (64.0, 52.0), (46.0, 64.0)]
                        norm_items: list[dict[str, Any]] = []
                        for qi, q in enumerate(cue_items):
                            qd = dict(q)
                            if qi == 0 or qd.get("variant") == "pointer":
                                qd["variant"] = "pointer"
                            px_d, py_d = ptr_presets[(ci + qi) % len(ptr_presets)]
                            qd["target_x"] = float(qd.get("target_x") or px_d)
                            qd["target_y"] = float(qd.get("target_y") or py_d)
                            norm_items.append(qd)
                        cue_items = norm_items
                    elif stk_style == "ai_pop_sticker" and cue_items:
                        kw_emojis = [
                            (r"mèo", "🐱"), (r"cua|ghẹ|hải sản", "🦀"), (r"cá |ao cá", "🐟"),
                            (r"bánh kem|sinh nhật", "🎂"), (r"quà", "🎁"), (r"tiệc", "🥳"),
                            (r"cà phê|cafe", "☕"), (r"trà sữa", "🧋"), (r"bia|nhậu", "🍻"),
                            (r"phở|bún|mì|lẩu|món|ăn", "🍜"), (r"biển|sóng", "🌊"), (r"xe|lái", "🚗"),
                            (r"hoa|vườn|cây", "🌸"), (r"nắng|sáng", "☀️"), (r"vui|cười", "😂"),
                        ]
                        ch_text_all = " ".join(str(b.get("text") or "") for b in (ch.get("narration_blocks") or [])).lower()
                        pop_items: list[dict[str, Any]] = []
                        for qi, q in enumerate(cue_items):
                            qd = dict(q)
                            qd["variant"] = "free_pop"
                            if "show_arrow" not in qd:
                                qd["show_arrow"] = (qi == 0)
                            if str(qd.get("emoji") or "") in ("", "✨") and ch_text_all:
                                for pat, em_k in kw_emojis:
                                    if re.search(pat, f"{qd.get('label', '')} {ch_text_all}".lower()):
                                        qd["emoji"] = em_k
                                        break
                            pop_items.append(qd)
                        cue_items = pop_items

                # Sprinkle extra random corner sticker / label cues across longer chapters so video never feels static
                ch_len = ch_end - ch_start
                target_extra = (2 if stk_mode == "rich" else 1) if ch_len >= 22.0 else 0
                if target_extra > 0:
                    ambient_pool = [
                        ("👀", "CHÚ Ý CHI TIẾT", "Xem kỹ khoảnh khắc này", "top-left", "pill"),
                        ("💡", "ĐIỂM NHẤN", "Góc quay thực tế", "top-right", "floating_lottie"),
                        ("🔥", "ĐOẠN HAY", "Đừng bỏ lỡ chi tiết này", "bottom-left", "lower_third"),
                        ("✨", "KHOẢNH KHẮC", "Nhịp sống chân thực", "center-right", "free_pop"),
                        ("🎯", "TIÊU ĐIỂM", "Đang vào cao trào", "top-left", "callout"),
                    ]
                    extra_ratios = [0.24, 0.78] if target_extra >= 2 else [0.76]
                    for ex_i, ex_rat in enumerate(extra_ratios):
                        em_a, lbl_a, sub_a, pos_a, var_a = ambient_pool[(ci + ex_i * 2) % len(ambient_pool)]
                        cue_items.append(
                            {
                                "variant": "free_pop" if stk_style == "ai_pop_sticker" else var_a,
                                "emoji": str((stk or {}).get("emoji") or em_a),
                                "label": lbl_a,
                                "sublabel": sub_a,
                                "position": pos_a,
                                "show_arrow": False,
                                "offset_ratio": ex_rat,
                            }
                        )

                for s_i, cue in enumerate(cue_items):
                    off_r = float(cue.get("offset_ratio") or (0.36 + s_i * 0.34))
                    cue_dur = 4.5
                    if cue.get("start_sec") is not None and cue.get("end_sec") is not None:
                        c_s = float(cue["start_sec"])
                        c_e = float(cue["end_sec"])
                        stk_t = max(place_t + 3.6, c_s)
                        if c_e - stk_t >= 1.8:
                            cue_dur = round(max(2.0, min(4.5, c_e - stk_t)), 2)
                        else:
                            stk_t = max(place_t + 3.8 + s_i * 5.2, ch_start + (ch_end - ch_start) * off_r)
                    else:
                        stk_t = max(place_t + 3.8 + s_i * 5.2, ch_start + (ch_end - ch_start) * off_r)
                    if stk_t < min(ch_end - 1.5, total_dur - 5.5):
                        _render_one(
                            "VlogStickerOverlay",
                            {
                                "emoji": str(cue.get("emoji") or "✨"),
                                "label": str(cue.get("label") or ch.get("chapter_title") or "KHOẢNH KHẮC"),
                                "sublabel": str(cue.get("sublabel") or ""),
                                "position": str(cue.get("position") or "center-left"),
                                "variant": str(cue.get("variant") or "callout"),
                                "targetX": float(cue.get("target_x") or 56.0),
                                "targetY": float(cue.get("target_y") or 58.0),
                                "showArrow": bool(cue.get("show_arrow", True)),
                                "accentColor": accent_color,
                                "durationSec": cue_dur,
                                "width": ov_w,
                                "height": ov_h,
                                "aspectRatio": aspect_ratio,
                            },
                            f"sticker_{c_idx:02d}_{s_i + 1}.webm",
                            stk_t,
                            cue_dur,
                        )

    # 3. Outro Card (6.0s at end of video)
    outro_dur = min(6.0, max(3.5, total_dur * 0.1))
    _render_one(
        "VlogOutro",
        {
            "title": chapter_script.get("outro_title") or "CẢM ƠN BẠN ĐÃ ĐỒNG HÀNH!",
            "subtitle": "Hẹn gặp lại trong những hành trình tiếp theo",
            "ctaText": chapter_script.get("outro_cta") or "",
            "channelName": channel_name,
            "accentColor": accent_color,
            "titleStyle": title_style,
            "durationSec": outro_dur,
            "width": ov_w,
            "height": ov_h,
            "aspectRatio": aspect_ratio,
        },
        "outro_overlay.webm",
        max(0.0, total_dur - outro_dur),
        outro_dur,
    )
    return overlays


def _sec_to_ass_time(sec: float) -> str:
    s = max(0.0, float(sec))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    rem = s % 60.0
    return f"{h}:{m:02d}:{rem:05.2f}"


def _hex_to_ass_bgr(hex_col: str, alpha_hex: str = "00") -> str:
    h = (hex_col or "").strip().lstrip("#")
    if len(h) == 6:
        rr, gg, bb = h[0:2], h[2:4], h[4:6]
        return f"&H{alpha_hex}{bb.upper()}{gg.upper()}{rr.upper()}"
    return f"&H{alpha_hex}0BF59E"


def srt_to_ass_file(
    srt_path: Path,
    ass_path: Path,
    width: int = 1920,
    height: int = 1080,
    font_name: str = "Baloo 2",
    subtitle_style: str = "editorial_clean",
    accent_color: str = "#F59E0B",
) -> Path:
    """Convert SRT subtitles into AI-directed Vlog ASS subtitles across 5 distinct visual presets."""
    is_landscape = width > height
    font_size = int(round(height * (0.040 if is_landscape else 0.033)))
    margin_v = int(round(height * (0.056 if is_landscape else 0.165)))
    margin_lr = int(round(width * 0.07))
    outline_px = max(2, int(round(font_size * 0.055)))
    shadow_px = max(2, int(round(font_size * 0.05)))

    presets = {
        "editorial_clean": {
            "primary": "&H00F8FAFC",
            "outline_col": "&H220F172A",
            "back_col": "&H78000000",
            "border_style": 1,
            "outline": outline_px,
            "shadow": shadow_px,
            "fad": r"\fad(160,160)\blur0.5",
        },
        "warm_vlog_gold": {
            "primary": "&H007CE0FF",
            "outline_col": "&H15080D16",
            "back_col": "&H90060B14",
            "border_style": 1,
            "outline": outline_px + 1,
            "shadow": shadow_px + 1,
            "fad": r"\fad(180,180)\blur0.4",
        },
        "mint_nature": {
            "primary": "&H00D4FFE8",
            "outline_col": "&H20061C14",
            "back_col": "&H85041812",
            "border_style": 1,
            "outline": outline_px,
            "shadow": shadow_px + 1,
            "fad": r"\fad(150,150)\blur0.5",
        },
        "cinema_box": {
            "primary": "&H00F8FAFC",
            "outline_col": "&HB50B101B",
            "back_col": "&HB50B101B",
            "border_style": 3,
            "outline": max(10, int(round(font_size * 0.25))),
            "shadow": 0,
            "fad": r"\fad(140,140)",
        },
        "highlight_bold": {
            "primary": "&H00FFFFFF",
            "outline_col": "&H18000000",
            "back_col": "&H88000000",
            "border_style": 1,
            "outline": outline_px + 1,
            "shadow": shadow_px + 1,
            "fad": r"\fad(130,130)\blur0.4",
        },
    }
    st_cfg = presets.get(subtitle_style, presets["editorial_clean"])
    accent_ass = _hex_to_ass_bgr(accent_color, "00")

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
        f"Style: Default,{font_name},{font_size},{st_cfg['primary']},&H0067E8F9,{st_cfg['outline_col']},{st_cfg['back_col']},"
        f"-1,0,0,0,100,100,0.4,0,{st_cfg['border_style']},{st_cfg['outline']},{st_cfg['shadow']},2,{margin_lr},{margin_lr},{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events: list[str] = []
    if srt_path.exists():
        raw = srt_path.read_text(encoding="utf-8-sig")
        blocks = re.split(r"\r?\n\r?\n+", raw.strip())
        for blk_idx, blk in enumerate(blocks):
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
            if subtitle_style == "highlight_bold" or (blk_idx % 3 == 1 and len(txt.split()) >= 5):
                words = txt.split()
                split_at = max(1, len(words) - 2)
                head_txt = " ".join(words[:split_at])
                tail_txt = " ".join(words[split_at:])
                styled_txt = f"{head_txt} {{\\c{accent_ass}&}}{tail_txt}{{\\c{st_cfg['primary']}&}}"
            else:
                styled_txt = txt
            events.append(
                f"Dialogue: 0,{_sec_to_ass_time(st)},{_sec_to_ass_time(en)},Default,,0,0,0,,{{{st_cfg['fad']}}}{styled_txt}"
            )

    ass_path.parent.mkdir(parents=True, exist_ok=True)
    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return ass_path


def _detect_h264_encoder(ffmpeg_bin: str, width: int = 1920, is_master: bool = True) -> tuple[str, list[str]]:
    if width >= 3000:
        b_target, b_max, b_buf = ("28M", "45M", "60M") if is_master else ("42M", "65M", "80M")
    elif width >= 2200:
        b_target, b_max, b_buf = ("16M", "24M", "32M") if is_master else ("26M", "38M", "48M")
    else:
        b_target, b_max, b_buf = ("10M", "16M", "22M") if is_master else ("16M", "24M", "30M")

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
            cq = "16" if is_master else "13"
            return "h264_nvenc", ["-preset", "p6" if is_master else "p5", "-rc", "vbr", "-cq", cq, "-b:v", b_target, "-maxrate", b_max, "-bufsize", b_buf]
    except Exception:
        pass
    crf = "16" if is_master else "13"
    return "libx264", ["-preset", "medium" if is_master else "fast", "-crf", crf, "-maxrate", b_max, "-bufsize", b_buf]


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


COLOR_PRESET_FILTERS: dict[str, str] = {
    "natural": "eq=contrast=1.02:saturation=1.05",
    "warm_sunset": "colorbalance=rs=0.06:gs=0.02:bs=-0.05:rm=0.04:bm=-0.04,eq=contrast=1.05:saturation=1.12",
    "fresh_cool": "colorbalance=rs=-0.04:gs=0.02:bs=0.06:rm=-0.03:bm=0.05,eq=contrast=1.03:saturation=1.08",
    "cinema_contrast": "colorbalance=rs=0.03:bs=-0.03:gs=-0.01,eq=contrast=1.09:brightness=-0.02:saturation=0.96",
    "soft_film": "colorbalance=rs=0.03:gs=0.02:bs=0.01,eq=contrast=0.98:brightness=0.02:saturation=1.06",
}


def render_longform_ffmpeg_vlog(
    plan: dict[str, Any],
    voice_wav: Path | None,
    srt_path: Path | None,
    bgm_path: Path | None,
    output_mp4: Path,
    overlays: list[dict[str, Any]] | None = None,
    bgm_volume: float = 0.20,
    keep_clip_audio: bool = False,
    font_name: str = "Baloo 2",
    subtitle_style: str = "editorial_clean",
    accent_color: str = "#F59E0B",
    color_preset: str = "natural",
    content_vibe: str = "outdoor_picnic",
    progress_cb: Any = None,
) -> dict[str, Any]:
    """Render 4K/2K/1080p Vlog master with Remotion transparent overlays, sidechain ducking, & crisp ASS subs."""
    vp_prof = get_vibe_editing_profile(content_vibe)
    use_zoom = bool(vp_prof.get("motion_zoom"))
    use_vignette = bool(vp_prof.get("vignette"))
    use_flash = bool(vp_prof.get("flash_cut"))
    ffmpeg_bin = find_binary("ffmpeg")
    ffprobe_bin = find_binary("ffprobe")
    res_wh = plan.get("target_resolution") or [1920, 1080]
    target_w, target_h = int(res_wh[0]), int(res_wh[1])
    vcodec_seg, vargs_seg = _detect_h264_encoder(ffmpeg_bin, width=max(target_w, target_h), is_master=False)
    vcodec_master, vargs_master = _detect_h264_encoder(ffmpeg_bin, width=max(target_w, target_h), is_master=True)

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
            dur = max(0.5, round(float(seg.get("duration") or 3.0) * 30.0) / 30.0)
            seg_out = tmp_path / f"seg_{idx:04d}.mp4"
            fade_part = ",fade=t=in:st=0:d=0.35" if (seg.get("is_chapter_start") and idx > 1) else (",fade=t=in:st=0:d=0.14" if (use_flash and idx > 1) else "")
            color_filter = COLOR_PRESET_FILTERS.get(str(color_preset or "natural"), COLOR_PRESET_FILTERS["natural"])
            zoom_expr = (
                f",zoompan=z='min(1.07,1+0.065*it/{dur:.3f})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={target_w}x{target_h}:fps=30"
                if (use_zoom and idx % 2 == 1)
                else ""
            )
            vig_expr = ",vignette=PI/4.8" if use_vignette else ""
            vf = (
                f"crop='min(iw,ih*{target_w}/{target_h})':'min(ih,iw*{target_h}/{target_w})',"
                f"scale={target_w}:{target_h}:flags=lanczos{zoom_expr},unsharp=3:3:0.35:3:3:0.0,"
                f"{color_filter}{vig_expr},setsar=1,fps=30,format=yuv420p{fade_part}"
            )
            color_tags = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
            if keep_clip_audio and not _has_audio_stream(ffprobe_bin, src_p):
                cmd = [
                    ffmpeg_bin, "-y", "-ss", f"{st:.3f}", "-t", f"{dur:.3f}", "-i", str(src_p),
                    "-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
                    "-map", "0:v:0", "-map", "1:a:0", "-vf", vf,
                    "-c:v", vcodec_seg, *vargs_seg, "-pix_fmt", "yuv420p", *color_tags,
                    "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k", "-shortest", str(seg_out),
                ]
            else:
                cmd = [
                    ffmpeg_bin, "-y", "-ss", f"{st:.3f}", "-t", f"{dur:.3f}", "-i", str(src_p),
                    "-vf", vf, "-c:v", vcodec_seg, *vargs_seg, "-pix_fmt", "yuv420p", *color_tags,
                ]
                if keep_clip_audio:
                    cmd.extend(["-af", "aresample=44100,volume=0.45", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k"])
                else:
                    cmd.append("-an")
                cmd.append(str(seg_out))
            subprocess.run(cmd, capture_output=True, check=True, timeout=240)
            seg_files.append(seg_out)

        concat_list = tmp_path / "concat.txt"
        concat_list.write_text("\n".join(f"file '{p.as_posix()}'" for p in seg_files), encoding="utf-8")
        merged_video = tmp_path / "merged_raw.mp4"
        subprocess.run(
            [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(merged_video)],
            capture_output=True,
            check=True,
            timeout=240,
        )

        # Single final master pass: Remotion transparent overlays + ASS subs + sidechain ducked audio
        ass_file = tmp_path / "subs.ass"
        has_ass = False
        if srt_path and srt_path.exists():
            srt_to_ass_file(
                srt_path,
                ass_file,
                width=target_w,
                height=target_h,
                font_name=font_name,
                subtitle_style=subtitle_style,
                accent_color=accent_color,
            )
            has_ass = True

        comp_cmd = [ffmpeg_bin, "-y", "-i", str(merged_video)]
        next_idx = 1

        valid_overlays = [
            ov for ov in (overlays or [])
            if isinstance(ov, dict) and ov.get("path") and Path(ov["path"]).exists()
        ]
        ov_inputs: list[tuple[int, float, float]] = []
        for ov in valid_overlays:
            st_sec = max(0.0, float(ov.get("start_sec") or 0.0))
            dur_ov = float(ov.get("duration_sec") or 0.0)
            comp_cmd.extend(["-c:v", "libvpx-vp9", "-i", str(ov["path"])])
            ov_inputs.append((next_idx, st_sec, dur_ov))
            next_idx += 1

        has_voice = bool(voice_wav and voice_wav.exists())
        has_bgm = bool(bgm_path and bgm_path.exists())
        voice_idx = None
        bgm_idx = None
        if has_voice:
            comp_cmd.extend(["-i", str(voice_wav)])
            voice_idx = next_idx
            next_idx += 1
        if has_bgm:
            comp_cmd.extend(["-stream_loop", "-1", "-i", str(bgm_path)])
            bgm_idx = next_idx
            next_idx += 1

        filter_parts: list[str] = []
        cur_v = "0:v"
        if has_ass:
            ass_esc = ass_file.as_posix().replace(":", "\\:")
            filter_parts.append(f"[{cur_v}]ass='{ass_esc}'[vsub]")
            cur_v = "vsub"

        for oi, (in_idx, st_sec, dur_ov) in enumerate(ov_inputs):
            ov_lbl = f"ov{oi}"
            out_lbl = f"vov{oi}"
            filter_parts.append(
                f"[{in_idx}:v]scale={target_w}:{target_h}:flags=lanczos,format=yuva420p,setpts=PTS-STARTPTS+{st_sec:.3f}/TB[{ov_lbl}]"
            )
            en_expr = f":enable='between(t,{st_sec:.3f},{st_sec + dur_ov + 0.1:.3f})'" if dur_ov > 0.0 else ""
            filter_parts.append(f"[{cur_v}][{ov_lbl}]overlay=0:0:eof_action=pass:shortest=0{en_expr}[{out_lbl}]")
            cur_v = out_lbl

        v_map = f"[{cur_v}]" if cur_v != "0:v" else "0:v"

        # Audio pipeline with true sidechain ducking when narration speaks
        bed_labels: list[str] = []
        if keep_clip_audio:
            filter_parts.append("[0:a]aresample=44100,aformat=channel_layouts=stereo,volume=0.45[clipa]")
            bed_labels.append("[clipa]")
        if bgm_idx is not None:
            filter_parts.append(f"[{bgm_idx}:a]aresample=44100,aformat=channel_layouts=stereo,volume={float(bgm_volume):.3f}[bgma]")
            bed_labels.append("[bgma]")

        a_map = ""
        if voice_idx is not None and bed_labels:
            if len(bed_labels) > 1:
                filter_parts.append(f"{''.join(bed_labels)}amix=inputs={len(bed_labels)}:duration=first:normalize=0[bed_mix]")
                bed_lbl = "[bed_mix]"
            else:
                bed_lbl = bed_labels[0]
            filter_parts.append(f"[{voice_idx}:a]aresample=44100,aformat=channel_layouts=stereo,asplit=2[v_sc][v_mix]")
            filter_parts.append(f"{bed_lbl}[v_sc]sidechaincompress=threshold=0.025:ratio=6:attack=80:release=650:makeup=1[bed_ducked]")
            filter_parts.append("[v_mix][bed_ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[aout]")
            a_map = "[aout]"
        elif voice_idx is not None:
            filter_parts.append(f"[{voice_idx}:a]aresample=44100,aformat=channel_layouts=stereo,alimiter=limit=0.95[aout]")
            a_map = "[aout]"
        elif len(bed_labels) > 1:
            filter_parts.append(f"{''.join(bed_labels)}amix=inputs={len(bed_labels)}:duration=first:normalize=0,alimiter=limit=0.95[aout]")
            a_map = "[aout]"
        elif len(bed_labels) == 1:
            a_map = bed_labels[0]

        if filter_parts:
            comp_cmd.extend(["-filter_complex", ";".join(filter_parts)])
        comp_cmd.extend(["-map", v_map])
        if a_map:
            comp_cmd.extend(["-map", a_map, "-c:a", "aac", "-ar", "44100", "-b:a", "256k"])
        else:
            comp_cmd.extend(["-an"])

        if v_map == "0:v":
            comp_cmd.extend(["-c:v", "copy"])
        else:
            comp_cmd.extend(
                [
                    "-c:v", vcodec_master, *vargs_master,
                    "-pix_fmt", "yuv420p",
                    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                ]
            )

        comp_cmd.extend(["-shortest", "-movflags", "+faststart", str(output_mp4)])
        subprocess.run(comp_cmd, capture_output=True, check=True, timeout=900)

    final_dur = round(float(probe_duration(ffprobe_bin, output_mp4)), 2)
    return {
        "ok": True,
        "output_path": str(output_mp4),
        "duration_sec": final_dur,
        "width": target_w,
        "height": target_h,
        "quality_label": plan.get("quality_label") or f"{target_w}x{target_h}",
        "segments_count": len(segments),
        "chapters_count": len(plan.get("chapters") or []),
        "overlays_count": len(ov_inputs),
    }
