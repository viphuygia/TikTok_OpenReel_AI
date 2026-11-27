#!/usr/bin/env python3
"""
Hybrid AI Best Photos Extractor (`05_output/best_photos/`):
Stage 1: Fast local OpenCV + YuNet sharpness, exposure, color, face quality & scene dedup scoring.
Stage 2: Contact-sheet AI Vision selection via Gemini Vision API (or Antigravity CLI fallback)
         with automatic local fallback so it never blocks on quota/offline errors.
Stage 3: Full-resolution JPG extraction (+ optional project face/plate privacy masking) & ZIP export.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

import numpy as np
import requests

import face_privacy as _fp

MEDIA_VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")
PHOTO_TASTE_RULES_PATH = _fp.REPO_ROOT / "04_workspace" / "photo_taste_rules.md"
DEFAULT_PHOTO_TASTE_RULES = """# SỔ TAY GU CHỌN ẢNH ĐẸP AI (OPENREEL STUDIO)

## ✅ ƯU TIÊN DUYỆT (ĐIỂM CAO)
- Dáng đứng hoặc bước đi đã vào phom gọn gàng, cân đối, tự nhiên.
- Ảnh chính diện / bán thân: khuôn mặt rõ nét, ánh mắt sáng mở tự nhiên, nụ cười dễ chịu.
- Video QUAY LƯNG / NGHIÊNG (không thấy mặt): VẪN DUYỆT ĐIỂM CAO nếu dáng đẹp, tóc & trang phục vào nếp gọn gàng, khung cảnh sạch thoáng và ánh sáng đẹp.
- Chủ thể nổi bật, không bị cắt cụt đầu/chân khó chịu, bối cảnh hài hòa.

## 🚫 BẮT BUỘC LOẠI / TRỪ ĐIỂM NẶNG
- Tóc bay rối che mặt hoặc tung tóe thiếu kiểm soát giữa lúc xoay người (-2.5 điểm).
- Tay/chân giơ lỡ cỡ giữa chuyển động, đang vung tay chưa vào dáng (-2.0 điểm).
- Nhắm mắt, chớp mắt nửa chừng, há miệng hoặc méo miệng vì đang nói (-3.0 điểm).
- Nhòe chuyển động trên khuôn mặt hoặc người đi đường đè ngay lên chủ thể (-1.5 điểm).

## 📏 THANG ĐIỂM KHẮT KHE (CHỐNG CHẤM ẢO 9+)
- Dưới 6.5: Có lỗi chuyển động, tóc bay rối, nhắm mắt hoặc lỡ nhịp -> LOẠI.
- 7.0 – 7.9: Ảnh xem ổn, bố cục khá nhưng dáng hoặc biểu cảm chưa thật sự nổi bật.
- 8.0 – 8.9: Ảnh ĐẸP, dáng & tóc gọn gàng, ánh sáng tốt — duyệt đăng mạng xã hội ngay.
- 9.0 – 10.0: RẤT HIẾM — khoảnh khắc xuất sắc về cả thần thái, dáng đứng, ánh sáng và bố cục.
"""
GFPGAN_MODEL_NAME = "gfpgan_1.4.onnx"
GFPGAN_URLS = [
    "https://github.com/facefusion/facefusion-assets/releases/download/models-3.0.0/gfpgan_1.4.onnx",
    "https://huggingface.co/facefusion/models-3.0.0/resolve/main/gfpgan_1.4.onnx",
    "https://huggingface.co/datasets/Gourieff/ReActor/resolve/main/models/facerestore_models/GFPGANv1.4.onnx",
]
_GFPGAN_LOCK = threading.Lock()
_GFPGAN_CACHE: "_GfpganEngine | None" = None


def _best_photos_dir(project_root: Path) -> Path:
    return Path(project_root) / "05_output" / "best_photos"


def _thumbs_dir(project_root: Path) -> Path:
    return _best_photos_dir(project_root) / "_thumbs"


def _write_thumb_jpg(cv2: Any, img: np.ndarray, thumb_fp: Path, max_side: int = 480) -> None:
    if img is None or img.size == 0:
        return
    h, w = img.shape[:2]
    m = max(h, w)
    if m > max_side and m > 0:
        scale = float(max_side) / float(m)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    else:
        resized = img
    ok, buf = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if ok:
        thumb_fp.parent.mkdir(parents=True, exist_ok=True)
        thumb_fp.write_bytes(buf.tobytes())


def ensure_best_photo_thumb(project_root: Path, filename: str, max_side: int = 480) -> Path:
    clean_name = Path(str(filename or "").strip()).name
    if not clean_name or not re.match(r"^[a-zA-Z0-9_.-]+$", clean_name):
        raise ValueError("Tên file ảnh không hợp lệ.")
    out_dir = _best_photos_dir(project_root).resolve()
    orig_fp = (out_dir / clean_name).resolve()
    if not orig_fp.is_relative_to(out_dir) or not orig_fp.exists() or not orig_fp.is_file():
        raise FileNotFoundError("Không tìm thấy ảnh.")

    thumbs_dir = _thumbs_dir(project_root).resolve()
    thumb_fp = (thumbs_dir / clean_name).resolve()
    if (
        thumb_fp.is_relative_to(thumbs_dir)
        and thumb_fp.exists()
        and thumb_fp.is_file()
        and thumb_fp.stat().st_size > 0
        and thumb_fp.stat().st_mtime >= orig_fp.stat().st_mtime
    ):
        return thumb_fp

    try:
        cv2 = _fp._ensure_cv2()
        raw_bytes = np.fromfile(str(orig_fp), dtype=np.uint8)
        img = cv2.imdecode(raw_bytes, cv2.IMREAD_COLOR)
        if img is not None and img.size > 0:
            _write_thumb_jpg(cv2, img, thumb_fp, max_side=max_side)
            if thumb_fp.exists() and thumb_fp.stat().st_size > 0:
                return thumb_fp
    except Exception:
        pass
    return orig_fp


def _manifest_path(project_root: Path) -> Path:
    return _best_photos_dir(project_root) / "manifest.json"


def load_photo_taste_rules() -> str:
    try:
        if PHOTO_TASTE_RULES_PATH.exists() and PHOTO_TASTE_RULES_PATH.is_file():
            txt = PHOTO_TASTE_RULES_PATH.read_text(encoding="utf-8-sig").strip()
            if txt:
                return txt
    except Exception:
        pass
    return DEFAULT_PHOTO_TASTE_RULES.strip()


def save_photo_taste_rules(content: str) -> str:
    clean = str(content or "").strip() or DEFAULT_PHOTO_TASTE_RULES.strip()
    PHOTO_TASTE_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PHOTO_TASTE_RULES_PATH.with_suffix(".tmp.md")
    tmp.write_text(clean + "\n", encoding="utf-8")
    os.replace(tmp, PHOTO_TASTE_RULES_PATH)
    return clean


def reset_photo_taste_rules() -> str:
    return save_photo_taste_rules(DEFAULT_PHOTO_TASTE_RULES)


def append_photo_taste_rule(note: str) -> str:
    clean_note = re.sub(r"\s+", " ", str(note or "")).strip().lstrip("-*• ")
    if not clean_note:
        return load_photo_taste_rules()
    cur = load_photo_taste_rules()
    bullet = f"- {clean_note}"
    if bullet.lower() in cur.lower():
        return cur
    marker = "## 📏 THANG ĐIỂM"
    if marker in cur:
        idx = cur.index(marker)
        head = cur[:idx].rstrip()
        tail = cur[idx:]
        updated = f"{head}\n{bullet}\n\n{tail}"
    else:
        updated = f"{cur.rstrip()}\n{bullet}"
    return save_photo_taste_rules(updated)


def _format_ts_str(sec: float) -> str:
    s = max(0, int(round(sec)))
    mm, ss = divmod(s, 60)
    hh, mm = divmod(mm, 60)
    if hh > 0:
        return f"{hh:02d}:{mm:02d}:{ss:02d}"
    return f"{mm:02d}:{ss:02d}"


def load_best_photos_state(project_root: Path) -> dict[str, Any]:
    out_dir = _best_photos_dir(project_root)
    man_p = _manifest_path(project_root)
    if not man_p.exists():
        return {
            "updated_at": 0,
            "focus": "auto",
            "ai_used": False,
            "ai_channel": "",
            "ai_note": "",
            "apply_privacy": False,
            "photos": [],
        }
    try:
        data = json.loads(man_p.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("Invalid manifest")
    except Exception:
        return {
            "updated_at": 0,
            "focus": "auto",
            "ai_used": False,
            "ai_channel": "",
            "ai_note": "",
            "apply_privacy": False,
            "photos": [],
        }

    raw_photos = data.get("photos") if isinstance(data.get("photos"), list) else []
    valid_photos: list[dict[str, Any]] = []
    for item in raw_photos:
        if not isinstance(item, dict):
            continue
        fn = Path(str(item.get("filename") or "")).name
        if not fn or not re.match(r"^[a-zA-Z0-9_.-]+$", fn):
            continue
        fp = out_dir / fn
        if not fp.exists() or not fp.is_file():
            continue
        item_copy = dict(item)
        item_copy["filename"] = fn
        st_stat = fp.stat()
        item_copy["size_bytes"] = int(st_stat.st_size)
        item_copy["updated_at"] = int(item.get("updated_at") or int(st_stat.st_mtime))
        valid_photos.append(item_copy)

    return {
        "updated_at": int(data.get("updated_at") or 0),
        "focus": str(data.get("focus") or "auto"),
        "count_mode": str(data.get("count_mode") or "per_video"),
        "save_mode": str(data.get("save_mode") or "replace_selected"),
        "min_score": float(data.get("min_score") if data.get("min_score") is not None else 7.5),
        "ai_used": bool(data.get("ai_used", False)),
        "ai_channel": str(data.get("ai_channel") or ""),
        "ai_note": str(data.get("ai_note") or ""),
        "apply_privacy": bool(data.get("apply_privacy", False)),
        "photos": valid_photos,
    }


def _write_manifest(project_root: Path, data: dict[str, Any]) -> None:
    out_dir = _best_photos_dir(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    man_p = _manifest_path(project_root)
    tmp_p = out_dir / "manifest.tmp.json"
    tmp_p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_p, man_p)


def delete_best_photo(project_root: Path, filename: str) -> dict[str, Any]:
    clean_name = Path(str(filename or "").strip()).name
    if not clean_name or not re.match(r"^[a-zA-Z0-9_.-]+$", clean_name):
        raise ValueError("Tên file ảnh không hợp lệ.")
    out_dir = _best_photos_dir(project_root).resolve()
    target = (out_dir / clean_name).resolve()
    if not target.is_relative_to(out_dir):
        raise ValueError("Đường dẫn ảnh không hợp lệ.")
    if target.exists() and target.is_file():
        target.unlink(missing_ok=True)
    orig_target = (out_dir / "_orig" / clean_name).resolve()
    if orig_target.is_relative_to(out_dir) and orig_target.exists() and orig_target.is_file():
        orig_target.unlink(missing_ok=True)
    thumb_target = (out_dir / "_thumbs" / clean_name).resolve()
    if thumb_target.is_relative_to(out_dir) and thumb_target.exists() and thumb_target.is_file():
        thumb_target.unlink(missing_ok=True)

    cur = load_best_photos_state(project_root)
    cur["photos"] = [p for p in (cur.get("photos") or []) if p.get("filename") != clean_name]
    cur["updated_at"] = int(time.time())
    _write_manifest(project_root, cur)
    return cur


def clear_all_best_photos(project_root: Path) -> dict[str, Any]:
    out_dir = _best_photos_dir(project_root)
    if out_dir.exists():
        for fp in out_dir.glob("*.jpg"):
            fp.unlink(missing_ok=True)
        for sub_name in ("_orig", "_thumbs"):
            sub_dir = out_dir / sub_name
            if sub_dir.exists():
                for fp in sub_dir.glob("*.jpg"):
                    fp.unlink(missing_ok=True)
    cur = load_best_photos_state(project_root)
    cur["photos"] = []
    cur["updated_at"] = int(time.time())
    _write_manifest(project_root, cur)
    return cur


def build_best_photos_zip(project_root: Path) -> Path:
    st = load_best_photos_state(project_root)
    photos = st.get("photos") or []
    out_dir = _best_photos_dir(project_root)
    ws_dir = Path(project_root) / "04_workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)
    zip_path = ws_dir / "best_photos_export.zip"
    tmp_zip = ws_dir / "best_photos_export.tmp.zip"

    added = 0
    with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_STORED) as zf:
        for item in photos:
            fn = str(item.get("filename") or "")
            fp = out_dir / fn
            if fp.exists() and fp.is_file():
                zf.write(fp, arcname=fn)
                added += 1
        if added == 0 and out_dir.exists():
            for fp in sorted(out_dir.glob("*.jpg")):
                zf.write(fp, arcname=fp.name)
                added += 1

    if added == 0:
        tmp_zip.unlink(missing_ok=True)
        raise FileNotFoundError("Chưa có ảnh đẹp nào để nén tải về.")

    os.replace(tmp_zip, zip_path)
    return zip_path


def _collect_source_videos(project_root: Path, selected_clips: list[str] | None = None) -> list[tuple[Path, str]]:
    raw_dir = Path(project_root) / "02_video_tho"
    if not raw_dir.exists():
        return []
    wanted_norm: set[str] = set()
    for x in (selected_clips or []):
        s = str(x).replace("\\", "/").strip().strip("/")
        if not s:
            continue
        low = s.lower()
        if low.startswith("02_video_tho/"):
            low = low[len("02_video_tho/"):]
        if low:
            wanted_norm.add(low)
    out: list[tuple[Path, str]] = []
    for p in raw_dir.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in MEDIA_VIDEO_EXTS:
            continue
        rel = p.relative_to(raw_dir).as_posix()
        if wanted_norm and rel.lower() not in wanted_norm and p.name.lower() not in wanted_norm:
            continue
        out.append((p, rel))
    out.sort(key=lambda item: item[1].lower())
    return out


def _score_candidate_frame(
    cv2: Any,
    frame_small: np.ndarray,
    face_engine: Any,
    focus: str,
    prev_tiny_gray: np.ndarray | None = None,
) -> dict[str, Any]:
    sh, sw = frame_small.shape[:2]
    gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)

    # 1. Sharpness: Laplacian variance + Tenengrad mean
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mean = float(np.sqrt(gx * gx + gy * gy).mean())
    sharp_norm = min(1.0, (lap_var / 420.0) * 0.65 + (grad_mean / 42.0) * 0.35)

    # 1b. Motion stability against immediate neighbor frame (penalize mid-motion / flying hair / waving hands)
    cur_tiny_gray = cv2.resize(gray, (160, 90), interpolation=cv2.INTER_AREA).astype(np.float32)
    if prev_tiny_gray is not None and prev_tiny_gray.shape == cur_tiny_gray.shape:
        motion_diff = float(np.abs(cur_tiny_gray - prev_tiny_gray).mean())
        stability_norm = max(0.0, min(1.0, 1.0 - motion_diff / 20.0))
    else:
        stability_norm = 0.78

    # 2. Exposure & contrast balance
    mean_luma = float(gray.mean())
    std_luma = float(gray.std())
    if mean_luma < 42.0:
        expo_norm = max(0.05, mean_luma / 42.0 * 0.55)
    elif mean_luma > 224.0:
        expo_norm = max(0.05, (255.0 - mean_luma) / 31.0 * 0.55)
    else:
        dist_mid = abs(mean_luma - 126.0) / 100.0
        expo_norm = max(0.35, 1.0 - dist_mid * 0.45)
    contrast_norm = min(1.0, std_luma / 62.0)

    # 3. Color richness (HSV saturation)
    hsv = cv2.cvtColor(frame_small, cv2.COLOR_BGR2HSV)
    sat_mean = float(hsv[:, :, 1].mean()) / 255.0
    color_norm = min(1.0, sat_mean * 1.9)

    # 4. Face composition + direct face sharpness (YuNet) when auto/portrait
    face_score = 0.0
    face_count = 0
    best_face_lap = 0.0
    best_face_norm: tuple[float, float, float, float] | None = None
    if face_engine is not None and focus in ("auto", "portrait"):
        try:
            dets = face_engine.detect_and_embed(frame_small, score_threshold=0.58, min_box_px=20)
        except Exception:
            dets = []
        face_count = len(dets)
        if dets:
            best_fq = -1.0
            for d in dets:
                bx, by, bw, bh = d["box"]
                mx = min(bx, sw - (bx + bw))
                my = min(by, sh - (by + bh))
                edge_ok = 1.0 if (mx >= 6 and my >= 6) else 0.55
                fx1 = max(0, int(round(bx)))
                fy1 = max(0, int(round(by)))
                fx2 = min(sw, int(round(bx + bw)))
                fy2 = min(sh, int(round(by + bh)))
                face_lap = 0.0
                if fx2 - fx1 >= 8 and fy2 - fy1 >= 8:
                    face_lap = float(cv2.Laplacian(gray[fy1:fy2, fx1:fx2], cv2.CV_64F).var())
                face_sharp = min(1.0, face_lap / 260.0)
                fq = float(d.get("quality", 0.6)) * edge_ok * (0.35 + 0.65 * face_sharp)
                if fq > best_fq and sw > 0 and sh > 0:
                    best_fq = fq
                    best_face_lap = face_lap
                    best_face_norm = (
                        float(fx1) / float(sw),
                        float(fy1) / float(sh),
                        float(fx2) / float(sw),
                        float(fy2) / float(sh),
                    )
            face_score = min(1.0, max(0.0, best_fq))

    if focus == "portrait":
        local_score = (
            sharp_norm * 0.30
            + stability_norm * 0.16
            + face_score * 0.38
            + expo_norm * 0.08
            + contrast_norm * 0.04
            + color_norm * 0.04
        )
    elif focus == "scenic":
        local_score = (
            sharp_norm * 0.38
            + stability_norm * 0.22
            + expo_norm * 0.16
            + contrast_norm * 0.12
            + color_norm * 0.12
        )
    else:
        local_score = (
            sharp_norm * 0.32
            + stability_norm * 0.18
            + expo_norm * 0.14
            + contrast_norm * 0.10
            + color_norm * 0.08
            + face_score * 0.18
        )

    backview_score = (
        sharp_norm * 0.40
        + stability_norm * 0.26
        + expo_norm * 0.14
        + contrast_norm * 0.10
        + color_norm * 0.10
    )

    # Penalize motion-blurred faces even if mirror/background lights are sharp
    if face_count > 0 and best_face_lap < 55.0:
        local_score *= 0.55

    # Compact visual fingerprint for scene dedup
    fp_patch = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA).astype(np.float32).flatten()
    fp_patch = fp_patch - float(fp_patch.mean())
    fp_vec = _fp._l2_norm(fp_patch)

    return {
        "local_score": float(round(local_score, 4)),
        "backview_score": float(round(backview_score, 4)),
        "sharpness": float(round(sharp_norm, 3)),
        "stability": float(round(stability_norm, 3)),
        "face_count": int(face_count),
        "best_face_norm": best_face_norm,
        "fp_vec": fp_vec,
    }


def _make_candidate_tile(
    cv2: Any,
    orig_frame: np.ndarray,
    best_face_norm: tuple[float, float, float, float] | None,
    is_portrait: bool,
) -> np.ndarray:
    oh, ow = orig_frame.shape[:2]
    tw, th = (360, 640) if is_portrait else (480, 320)
    r_tile = min(float(tw) / float(max(1, ow)), float(th) / float(max(1, oh)))
    nw, nh = max(1, int(round(ow * r_tile))), max(1, int(round(oh * r_tile)))
    tile_resized = cv2.resize(orig_frame, (nw, nh), interpolation=cv2.INTER_AREA)
    tile_canvas = np.full((th, tw, 3), 20, dtype=np.uint8)
    xo, yo = (tw - nw) // 2, (th - nh) // 2
    tile_canvas[yo : yo + nh, xo : xo + nw] = tile_resized

    if best_face_norm is not None and ow > 32 and oh > 32:
        nx1, ny1, nx2, ny2 = best_face_norm
        fx1 = nx1 * ow
        fy1 = ny1 * oh
        fx2 = nx2 * ow
        fy2 = ny2 * oh
        fw = max(8.0, fx2 - fx1)
        fh = max(8.0, fy2 - fy1)
        cx = (fx1 + fx2) * 0.5
        cy = (fy1 + fy2) * 0.5
        half_side = max(fw, fh) * 0.95
        x1 = max(0, int(round(cx - half_side)))
        y1 = max(0, int(round(cy - half_side)))
        x2 = min(ow, int(round(cx + half_side)))
        y2 = min(oh, int(round(cy + half_side)))
        if (x2 - x1) >= 16 and (y2 - y1) >= 16:
            crop = orig_frame[y1:y2, x1:x2]
            inset_sz = 136 if is_portrait else 116
            ch, cw = crop.shape[:2]
            scale_in = min(float(inset_sz) / float(cw), float(inset_sz) / float(ch))
            iw = max(1, int(round(cw * scale_in)))
            ih = max(1, int(round(ch * scale_in)))
            inset = cv2.resize(crop, (iw, ih), interpolation=cv2.INTER_AREA)
            ix = tw - iw - 6
            iy = th - ih - 6
            if ix >= 4 and iy >= 4:
                tile_canvas[iy : iy + ih, ix : ix + iw] = inset
                cv2.rectangle(tile_canvas, (ix - 1, iy - 1), (ix + iw, iy + ih), (80, 230, 255), 2)
                cv2.rectangle(tile_canvas, (ix, iy), (ix + 46, iy + 16), (12, 16, 24), -1)
                cv2.putText(tile_canvas, "ZOOM", (ix + 4, iy + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120, 240, 255), 1, cv2.LINE_AA)

    return tile_canvas


def _collect_candidates(
    videos: list[tuple[Path, str]],
    *,
    pool_size: int,
    focus: str,
    progress_cb: Callable[[int, str], None] | None = None,
    pct_start: int = 8,
    pct_span: int = 38,
) -> tuple[list[dict[str, Any]], bool]:
    cv2 = _fp._ensure_cv2()
    face_engine = _fp._FaceEngine() if focus in ("auto", "portrait") else None

    total_clips = len(videos)
    total_budget = max(24, min(110, max(pool_size * 4, total_clips * 10))) if total_clips > 1 else max(18, min(42, pool_size * 3))
    per_clip = max(6, min(36, int(round(total_budget / float(max(1, total_clips))))))

    raw_candidates: list[dict[str, Any]] = []
    face_frame_hits = 0
    total_eval_frames = 0

    def _push_evaluated(
        vp: Path,
        rel_name: str,
        fps: float,
        fi: int,
        orig_frame: np.ndarray,
        prev_tiny: np.ndarray | None,
    ) -> None:
        nonlocal face_frame_hits, total_eval_frames
        oh, ow = orig_frame.shape[:2]
        if oh <= 0 or ow <= 0:
            return
        scale = min(1.0, 640.0 / float(max(oh, ow)))
        small = (
            cv2.resize(orig_frame, (max(1, int(round(ow * scale))), max(1, int(round(oh * scale)))), interpolation=cv2.INTER_AREA)
            if scale < 1.0
            else orig_frame
        )
        metrics = _score_candidate_frame(cv2, small, face_engine, focus, prev_tiny_gray=prev_tiny)
        total_eval_frames += 1
        if metrics["face_count"] > 0:
            face_frame_hits += 1
        tile_canvas = _make_candidate_tile(
            cv2,
            orig_frame,
            metrics.get("best_face_norm"),
            is_portrait=(oh > ow),
        )
        raw_candidates.append(
            {
                "video_path": vp,
                "clip_rel": rel_name,
                "clip_name": vp.name,
                "frame_idx": int(fi),
                "timestamp_sec": round(float(fi) / fps, 2),
                "orig_w": int(ow),
                "orig_h": int(oh),
                "tile": tile_canvas,
                **metrics,
            }
        )

    for c_idx, (vp, rel_name) in enumerate(videos, start=1):
        if progress_cb is not None and pct_span > 0:
            pct = pct_start + int(round((c_idx - 1) / float(max(1, total_clips)) * pct_span))
            progress_cb(pct, f"Đang tìm điểm dừng dáng & quét nét clip {c_idx}/{total_clips}: {vp.name}...")

        cap = cv2.VideoCapture(str(vp))
        if not cap.isOpened():
            continue
        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
            if fps < 1.0 or fps > 120.0:
                fps = 30.0

            if total_frames > 0:
                lo = min(total_frames - 1, max(0, int(total_frames * 0.03)))
                hi = max(lo, int(total_frames * 0.96))
                span = hi - lo + 1
                want = min(per_clip, max(2, span))
                sub_k = max(1, min(3, 90 // max(1, want)))
                edges = np.linspace(lo, hi + 1, num=want + 1)

                probe_to_bucket: dict[int, int] = {}
                bucket_last_fi: dict[int, int] = {}
                prev_map: dict[int, int] = {}
                all_probes: list[int] = []
                for b_idx in range(want):
                    b_start = max(lo, min(hi, int(round(edges[b_idx]))))
                    b_end = max(b_start, min(hi, int(round(edges[b_idx + 1])) - 1))
                    if sub_k == 1 or b_end == b_start:
                        b_idxs = [(b_start + b_end) // 2]
                    else:
                        b_idxs = sorted(set(int(round(x)) for x in np.linspace(b_start, b_end, num=sub_k)))
                    for p_fi in b_idxs:
                        if p_fi not in probe_to_bucket:
                            probe_to_bucket[p_fi] = b_idx
                            all_probes.append(p_fi)
                            if p_fi >= 2:
                                prev_map[p_fi - 2] = p_fi
                    bucket_last_fi[b_idx] = b_idxs[-1]

                all_probes.sort()
                if all_probes:
                    max_idx = all_probes[-1]
                    probe_set = set(all_probes)
                    prev_tiny_buf: dict[int, np.ndarray] = {}
                    bucket_best: dict[int, tuple[float, int, np.ndarray, np.ndarray | None]] = {}
                    last_tiny: np.ndarray | None = None
                    last_tiny_fi = -999

                    for fi in range(max_idx + 1):
                        need_prev = fi in prev_map
                        need_probe = fi in probe_set
                        if need_prev or need_probe:
                            ok, fr = cap.read()
                            if not ok or fr is None:
                                break
                            tiny_gray = cv2.cvtColor(cv2.resize(fr, (160, 90), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
                            if need_prev:
                                prev_tiny_buf[prev_map[fi]] = tiny_gray
                            if need_probe:
                                b_idx = probe_to_bucket[fi]
                                ref_tiny = prev_tiny_buf.pop(fi, None)
                                if ref_tiny is None and last_tiny is not None and (fi - last_tiny_fi) <= 12:
                                    ref_tiny = last_tiny
                                m_diff = float(np.abs(tiny_gray - ref_tiny).mean()) if (ref_tiny is not None and ref_tiny.shape == tiny_gray.shape) else 8.0
                                cur_b = bucket_best.get(b_idx)
                                if cur_b is None or m_diff < cur_b[0]:
                                    bucket_best[b_idx] = (m_diff, fi, fr, ref_tiny)
                                if fi == bucket_last_fi.get(b_idx) and b_idx in bucket_best:
                                    _, win_fi, win_fr, win_prev = bucket_best.pop(b_idx)
                                    _push_evaluated(vp, rel_name, fps, win_fi, win_fr, win_prev)
                            last_tiny = tiny_gray
                            last_tiny_fi = fi
                        else:
                            if not cap.grab():
                                break

                    for b_idx in sorted(bucket_best.keys()):
                        _, win_fi, win_fr, win_prev = bucket_best[b_idx]
                        _push_evaluated(vp, rel_name, fps, win_fi, win_fr, win_prev)
            else:
                for fi, fr in _fp._sample_video_frames(cv2, vp, max_samples=per_clip):
                    _push_evaluated(vp, rel_name, fps, fi, fr, None)
        finally:
            cap.release()

    if not raw_candidates:
        return [], False

    is_back_view = bool(total_eval_frames > 0 and (face_frame_hits / float(total_eval_frames)) < 0.15)
    if is_back_view:
        for c in raw_candidates:
            c["local_score"] = c["backview_score"]

    def _is_dup(cand: dict[str, Any], chosen_list: list[dict[str, Any]]) -> bool:
        vec = cand["fp_vec"]
        for ex in chosen_list:
            sim = float(np.dot(vec, ex["fp_vec"]))
            same_clip = cand["clip_rel"] == ex["clip_rel"]
            close_time = abs(cand["timestamp_sec"] - ex["timestamp_sec"]) < (1.4 if total_clips == 1 else 2.2)
            if sim >= 0.96 or (same_clip and close_time and sim >= 0.91):
                return True
        return False

    chosen: list[dict[str, Any]] = []
    if total_clips > 1:
        by_clip: dict[str, list[dict[str, Any]]] = {}
        for c in raw_candidates:
            by_clip.setdefault(c["clip_rel"], []).append(c)
        for rel_key in sorted(by_clip.keys()):
            if len(chosen) >= pool_size:
                break
            best_in_clip = max(by_clip[rel_key], key=lambda x: x["local_score"])
            if not _is_dup(best_in_clip, chosen):
                chosen.append(best_in_clip)

    remaining_sorted = sorted(raw_candidates, key=lambda x: x["local_score"], reverse=True)
    for cand in remaining_sorted:
        if len(chosen) >= pool_size:
            break
        if any(cand is ex for ex in chosen):
            continue
        if not _is_dup(cand, chosen):
            chosen.append(cand)

    if len(chosen) < pool_size:
        for cand in remaining_sorted:
            if len(chosen) >= pool_size:
                break
            if any(cand is ex for ex in chosen):
                continue
            chosen.append(cand)

    for idx, c in enumerate(chosen, start=1):
        c["cid"] = idx
    return chosen, is_back_view


def _build_contact_sheets(candidates: list[dict[str, Any]], max_per_sheet: int = 9) -> list[tuple[bytes, list[int]]]:
    cv2 = _fp._ensure_cv2()
    sheets: list[tuple[bytes, list[int]]] = []
    if not candidates:
        return sheets

    pad = 8
    for start in range(0, len(candidates), max_per_sheet):
        chunk = candidates[start : start + max_per_sheet]
        n = len(chunk)
        th, tw = chunk[0]["tile"].shape[:2]
        cols = 3 if n > 4 else (2 if n > 1 else 1)
        rows = (n + cols - 1) // cols
        canvas_w = cols * tw + (cols + 1) * pad
        canvas_h = rows * th + (rows + 1) * pad
        canvas = np.full((canvas_h, canvas_w, 3), 16, dtype=np.uint8)

        cids: list[int] = []
        for idx, cand in enumerate(chunk):
            r = idx // cols
            c = idx % cols
            x = pad + c * (tw + pad)
            y = pad + r * (th + pad)
            tile = cand["tile"].copy()
            if tile.shape[:2] != (th, tw):
                tile = cv2.resize(tile, (tw, th), interpolation=cv2.INTER_AREA)
            cid = int(cand["cid"])
            cids.append(cid)

            tag = f"#{cid:02d}"
            cv2.rectangle(tile, (8, 8), (94, 46), (12, 12, 16), -1)
            cv2.rectangle(tile, (8, 8), (94, 46), (255, 200, 40), 2)
            cv2.putText(tile, tag, (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.95, (255, 225, 90), 2, cv2.LINE_AA)
            canvas[y : y + th, x : x + tw] = tile

        ok, buf = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if ok:
            sheets.append((buf.tobytes(), cids))
    return sheets


def _parse_ai_picks_response(raw_text: str) -> tuple[list[dict[str, Any]], bool]:
    txt = str(raw_text or "").strip()
    if not txt:
        return [], False
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt, flags=re.I)
    if m:
        txt = m.group(1).strip()
    try:
        parsed = json.loads(txt)
    except Exception:
        m2 = re.search(r"\{[\s\S]*\}", txt)
        if not m2:
            return [], False
        try:
            parsed = json.loads(m2.group(0))
        except Exception:
            return [], False
    if isinstance(parsed, dict):
        if "picks" not in parsed or not isinstance(parsed.get("picks"), list):
            return [], False
        picks = parsed.get("picks") or []
    elif isinstance(parsed, list):
        picks = parsed
    else:
        return [], False

    out: list[dict[str, Any]] = []
    for item in picks:
        if not isinstance(item, dict):
            continue
        try:
            cid = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        try:
            sc = float(item.get("score") or 8.0)
        except (TypeError, ValueError):
            sc = 8.0
        sc = round(max(1.0, min(10.0, sc)), 1)
        reason = str(item.get("reason") or "").strip()[:140]
        out.append({"id": cid, "score": sc, "reason": reason})
    return out, True


def _parse_ai_picks_json(raw_text: str) -> list[dict[str, Any]]:
    picks, _ = _parse_ai_picks_response(raw_text)
    return picks


def _select_with_ai(
    candidates: list[dict[str, Any]],
    *,
    count: int,
    focus: str,
    min_score: float = 0.0,
    is_back_view: bool = False,
    rules_text: str = "",
    gemini_api_key: str,
    gemini_model: str,
    agy_fallback: Callable[[str, list[Path]], str] | None,
    tmp_dir: Path,
) -> tuple[list[dict[str, Any]], bool, str, str]:
    focus_hint = {
        "portrait": "ƯU TIÊN CHÂN DUNG & BIỂU CẢM: người cười tự nhiên, mở mắt rõ, không nhắm mắt, không há miệng nói dở, không che mặt.",
        "scenic": "ƯU TIÊN CẢNH & DÁNG ĐẸP: ánh sáng đẹp, góc rộng thoáng, bố cục gọn mắt; người quay lưng hay chính diện đều duyệt nếu dáng đẹp & gọn.",
        "auto": "CÂN BẰNG: ảnh nét, vào dáng ổn định, ánh sáng đẹp; nếu thấy mặt phải mở mắt tự nhiên, nếu quay lưng/nghiêng vẫn duyệt cao khi dáng đẹp & tóc gọn.",
    }.get(focus, "Ảnh nét, vào dáng ổn định, ánh sáng đẹp, bố cục hài hòa.")

    backview_note = (
        "\n⚠️ ĐẶC BIỆT (QUAY LƯNG / TOÀN THÂN): Clip này quay từ phía sau hoặc không cận mặt — KHÔNG trừ điểm vì không thấy mặt. Hãy đánh giá cao dáng đứng/bước đi đẹp tự nhiên, tóc & trang phục gọn gàng, khung cảnh thoáng."
        if is_back_view
        else ""
    )
    rules_block = (rules_text or load_photo_taste_rules()).strip()

    sheets = _build_contact_sheets(candidates, max_per_sheet=9)
    if not sheets:
        return [], False, "local", "Không tạo được ảnh lưới ứng viên."

    max_pick = min(count, len(candidates))
    if min_score > 0:
        qty_instruction = (
            f"và chọn TỐI ĐA {max_pick} tấm THẬT SỰ ĐẠT CHUẨN (>= {min_score:.1f} điểm) theo Sổ tay Gu Ảnh dưới đây. "
            f'TUYỆT ĐỐI KHÔNG lấy thêm ảnh dưới chuẩn để lấp cho đủ số lượng — nếu chỉ có 1-2 tấm đạt chuẩn thì chỉ trả 1-2 tấm; nếu toàn bộ bị lỗi/mờ/tóc rối/nhắm mắt thì trả về `{{"picks": []}}`.'
        )
    else:
        qty_instruction = f"và chọn đúng {max_pick} tấm TỐT NHẤT theo đúng Sổ tay Gu Ảnh dưới đây."

    valid_cids = [int(c["cid"]) for c in candidates]
    prompt = (
        f"Bạn là biên tập viên ảnh khắt khe. Mỗi ô trên ảnh lưới là 1 ứng viên (#01, #02...); "
        f"nếu ở góc dưới bên phải ô có khung nhỏ `ZOOM` thì đó là ảnh phóng to cận mặt từ video 4K — HÃY SOI KỸ ĐÔI MẮT, MIỆNG VÀ TÓC CON TRÊN KHUNG ZOOM ĐÓ, đồng thời đánh giá dáng & bố cục trên toàn ô, "
        f"{qty_instruction}\n"
        f"Tiêu chí chế độ hiện tại: {focus_hint}{backview_note}\n\n"
        f"--- SỔ TAY GU ẢNH CỦA CHỦ KÊNH ---\n{rules_block}\n---\n\n"
        f"Trả về DUY NHẤT JSON hợp lệ theo mẫu:\n"
        f'{{"picks": [{{"id": 3, "score": 8.4, "reason": "Vào dáng gọn, tóc gọn, ánh sáng đẹp"}}]}}\n'
        f"Lưu ý: id là số nguyên trong danh sách {valid_cids}. Chấm điểm THẬT KHẮT KHE (đừng nịnh 9+ nếu còn lỗi nhẹ như tóc hơi rối hay tay chưa gọn), reason tiếng Việt <= 14 từ."
    )

    api_key = str(gemini_api_key or "").strip()
    model_id = str(gemini_model or "gemini-2.5-flash").strip() or "gemini-2.5-flash"

    # Channel 1: Direct Gemini Vision API Key
    if api_key:
        try:
            parts: list[dict[str, Any]] = [{"text": prompt}]
            for jpg_bytes, _ in sheets:
                parts.append(
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": base64.b64encode(jpg_bytes).decode("ascii"),
                        }
                    }
                )
            gen_cfg: dict[str, Any] = {
                "temperature": 0.25,
                "responseMimeType": "application/json",
            }
            if any(tag in model_id for tag in ("2.5", "3")):
                gen_cfg["thinkingConfig"] = {"thinkingBudget": 512}
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
            resp = requests.post(
                endpoint,
                json={"contents": [{"parts": parts}], "generationConfig": gen_cfg},
                headers={"Content-Type": "application/json"},
                timeout=90,
            )
            if resp.status_code < 400:
                data = resp.json()
                cands = data.get("candidates") or []
                if cands:
                    out_parts = cands[0].get("content", {}).get("parts") or []
                    txt = "\n".join(str(pt.get("text") or "") for pt in out_parts if isinstance(pt, dict) and pt.get("text"))
                    picks, parsed_ok = _parse_ai_picks_response(txt)
                    if parsed_ok and (picks or min_score > 0):
                        return picks, True, "gemini_api", ""
                err_note = "Gemini API không trả kết quả JSON hợp lệ."
            else:
                try:
                    err_msg = resp.json().get("error", {}).get("message") or f"HTTP {resp.status_code}"
                except Exception:
                    err_msg = f"HTTP {resp.status_code}"
                err_note = f"Gemini API lỗi ({err_msg})"
        except Exception as exc:
            err_note = f"Lỗi kết nối Gemini API ({exc})"
    else:
        err_note = "Chưa nhập Gemini API Key."

    # Channel 2: Antigravity CLI fallback if available
    if agy_fallback is not None:
        sheet_paths: list[Path] = []
        try:
            tmp_dir.mkdir(parents=True, exist_ok=True)
            for s_idx, (jpg_bytes, _) in enumerate(sheets, start=1):
                sp = tmp_dir / f"_contact_sheet_{s_idx}.jpg"
                sp.write_bytes(jpg_bytes)
                sheet_paths.append(sp)
            agy_prompt = (
                f"{prompt}\nHãy đọc các file ảnh lưới đính kèm bằng tool read_file theo đúng đường dẫn:\n"
                + "\n".join(str(sp) for sp in sheet_paths)
            )
            txt = agy_fallback(agy_prompt, sheet_paths)
            picks, parsed_ok = _parse_ai_picks_response(txt)
            if parsed_ok and (picks or min_score > 0):
                return picks, True, "agy_cli", ""
        except Exception as exc:
            err_note = f"{err_note} · AGY fallback lỗi ({exc})"
        finally:
            for sp in sheet_paths:
                sp.unlink(missing_ok=True)

    return [], False, "local_fallback", f"{err_note} — đã tự động chấm nét & bố cục Local."


def _apply_privacy_to_single_frame(
    cv2: Any,
    frame: np.ndarray,
    project_root: Path,
    face_engine: Any,
    plate_engine: Any,
    cluster_items: list[tuple[str, np.ndarray]],
    plate_clusters: list[dict[str, Any]],
    plate_ocr: Any,
    cfg: dict[str, Any],
) -> None:
    oh, ow = frame.shape[:2]
    if cfg.get("enabled") and face_engine is not None:
        mode = cfg["mode"]
        sel_ids = set(cfg["selected_face_ids"])
        if mode == "keep_selected" or sel_ids:
            scale = min(1.0, 640.0 / float(max(oh, ow)))
            scan_frame = cv2.resize(frame, (max(1, int(round(ow * scale))), max(1, int(round(oh * scale)))), interpolation=cv2.INTER_AREA) if scale < 1.0 else frame
            dets = face_engine.detect_and_embed(scan_frame, score_threshold=0.58, min_box_px=18)
            match_thresh = 0.33 if face_engine.use_onnx else 0.74
            padding = float(cfg.get("padding") or 1.25)
            icon_mode = str(cfg.get("icon") or "cool")
            boxes: list[tuple[int, int, int, int, str]] = []
            for d in dets:
                bx, by, bw, bh = d["box"]
                cid, _ = _fp._match_cluster_id(d["emb"], cluster_items, match_thresh) if cluster_items else (None, -1.0)
                should_mask = bool(cid in sel_ids) if mode == "blur_selected" else (True if not sel_ids else not (cid in sel_ids))
                if not should_mask:
                    continue
                cx, cy = (bx + bw * 0.5) / scale, (by + bh * 0.5) / scale
                ew, eh = (bw / scale) * padding, (bh / scale) * padding * 1.06
                x1, y1 = max(0, int(round(cx - ew * 0.5))), max(0, int(round(cy - eh * 0.48)))
                x2, y2 = min(ow, int(round(cx + ew * 0.5))), min(oh, int(round(cy + eh * 0.52)))
                if x2 - x1 >= 6 and y2 - y1 >= 6:
                    boxes.append((x1, y1, x2, y2, "cool" if icon_mode == "random_person" else icon_mode))
            if boxes:
                _fp._apply_roi_mask(cv2, frame, boxes, str(cfg.get("style") or "gaussian"))

    if cfg.get("plate_blur_enabled") and plate_engine is not None:
        pmode = str(cfg.get("plate_blur_mode") or "blur_all")
        sel_pids = set(cfg.get("selected_plate_ids") or [])
        pdets = plate_engine.detect(frame, conf_threshold=0.35, nms_threshold=0.45)
        pboxes: list[tuple[int, int, int, int]] = []
        for pd in pdets:
            should_mask = True
            if pmode != "blur_all":
                pcrop = _fp._extract_plate_crop(frame, pd["cx"], pd["cy"], pd["w"], pd["h"])
                ptxt = plate_ocr.read_text(pcrop) if (plate_ocr is not None and pcrop is not None) else ""
                pemb = _fp._plate_visual_embed(cv2, pcrop) if pcrop is not None else np.zeros((0,), dtype=np.float32)
                pid, _ = _fp._match_plate_cluster_id(ptxt, pemb, plate_clusters)
                should_mask = bool(pid in sel_pids) if pmode == "blur_selected" else (True if not sel_pids else not (pid in sel_pids))
            if not should_mask:
                continue
            ew, eh = float(pd["w"]) * 1.25, float(pd["h"]) * 1.30
            x1 = max(0, int(round(float(pd["cx"]) - ew * 0.5)))
            y1 = max(0, int(round(float(pd["cy"]) - eh * 0.5)))
            x2 = min(ow, int(round(float(pd["cx"]) + ew * 0.5)))
            y2 = min(oh, int(round(float(pd["cy"]) + eh * 0.5)))
            if x2 - x1 >= 8 and y2 - y1 >= 6:
                pboxes.append((x1, y1, x2, y2))
        if pboxes:
            _fp._apply_plate_mask(cv2, frame, pboxes, str(cfg.get("plate_blur_style") or "pixelate"))


def _apply_natural_sharpen(cv2: Any, bgr_img: np.ndarray, strength: float = 1.0) -> np.ndarray:
    """Crisp micro-contrast & unsharp mask on LAB luminance channel without color haloing."""
    lab = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    blur = cv2.GaussianBlur(l_ch, (0, 0), sigmaX=1.2)
    w = 0.55 * float(strength)
    sharp_l = cv2.addWeighted(l_ch, 1.0 + w, blur, -w, 0)
    clahe = cv2.createCLAHE(clipLimit=1.35, tileGridSize=(8, 8))
    clahe_l = clahe.apply(sharp_l)
    final_l = cv2.addWeighted(sharp_l, 0.85, clahe_l, 0.15, 0)
    merged = cv2.merge([final_l, a_ch, b_ch])
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


class _GfpganEngine:
    """Optional GFPGAN v1.4 ONNX face restoration via existing onnxruntime."""

    def __init__(self, model_path: Path) -> None:
        import onnxruntime as ort  # type: ignore

        self.cv2 = _fp._ensure_cv2()
        self._run_lock = threading.Lock()
        avail = ort.get_available_providers()
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if "CUDAExecutionProvider" in avail else ["CPUExecutionProvider"]
        try:
            self.session = ort.InferenceSession(str(model_path), providers=providers)
        except Exception:
            self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        shape = inp.shape
        self.in_h = int(shape[2]) if len(shape) == 4 and isinstance(shape[2], (int, np.integer)) and int(shape[2]) > 0 else 512
        self.in_w = int(shape[3]) if len(shape) == 4 and isinstance(shape[3], (int, np.integer)) and int(shape[3]) > 0 else 512

    def restore_face(self, bgr_crop: np.ndarray) -> np.ndarray:
        cv2 = self.cv2
        ch, cw = bgr_crop.shape[:2]
        resized = cv2.resize(bgr_crop, (self.in_w, self.in_h), interpolation=cv2.INTER_CUBIC)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
        tensor = ((rgb / 255.0) - 0.5) / 0.5
        blob = np.transpose(tensor, (2, 0, 1))[None, ...]
        with self._run_lock:
            out = self.session.run(None, {self.input_name: blob})
        if not out:
            return bgr_crop
        arr = np.asarray(out[0], dtype=np.float32)
        if arr.ndim == 4:
            arr = arr[0]
        if arr.shape[0] == 3:
            arr = np.transpose(arr, (1, 2, 0))
        arr = np.clip((arr * 0.5 + 0.5) * 255.0, 0.0, 255.0).astype(np.uint8)
        restored_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        if restored_bgr.shape[:2] != (ch, cw):
            restored_bgr = cv2.resize(
                restored_bgr,
                (cw, ch),
                interpolation=cv2.INTER_AREA if cw < self.in_w else cv2.INTER_CUBIC,
            )
        return restored_bgr


def _get_gfpgan_engine() -> _GfpganEngine | None:
    global _GFPGAN_CACHE
    if _GFPGAN_CACHE is not None:
        return _GFPGAN_CACHE
    with _GFPGAN_LOCK:
        if _GFPGAN_CACHE is not None:
            return _GFPGAN_CACHE
        model_p = _fp.FACE_MODEL_DIR / GFPGAN_MODEL_NAME
        if not _fp._download_file(GFPGAN_URLS, model_p, min_bytes=50_000_000):
            print("[BestPhotos WARN] Không tải được model GFPGAN ONNX, chuyển sang tăng nét OpenCV.")
            return None
        try:
            _GFPGAN_CACHE = _GfpganEngine(model_p)
            return _GFPGAN_CACHE
        except Exception as exc:
            print(f"[BestPhotos WARN] Không khởi tạo được GFPGAN ONNX ({exc}).")
            return None


def enhance_photo_frame(
    cv2: Any,
    bgr_img: np.ndarray,
    *,
    enhance_mode: str = "none",
    face_engine: Any = None,
) -> tuple[np.ndarray, str]:
    mode = str(enhance_mode or "none").strip()
    if mode not in ("none", "sharpen", "ai_face"):
        mode = "none"
    if mode == "none":
        return bgr_img, "none"
    if mode == "sharpen":
        return _apply_natural_sharpen(cv2, bgr_img, strength=1.0), "sharpen"

    # mode == "ai_face": mild natural sharpen overall + GFPGAN face restore blended naturally
    gfp = _get_gfpgan_engine()
    if gfp is None:
        return _apply_natural_sharpen(cv2, bgr_img, strength=1.0), "sharpen"

    out_img = _apply_natural_sharpen(cv2, bgr_img, strength=0.55)
    feng = face_engine if face_engine is not None else _fp._FaceEngine()
    oh, ow = out_img.shape[:2]
    scale = min(1.0, 640.0 / float(max(oh, ow)))
    scan_fr = (
        cv2.resize(out_img, (max(1, int(round(ow * scale))), max(1, int(round(oh * scale)))), interpolation=cv2.INTER_AREA)
        if scale < 1.0
        else out_img
    )
    dets = feng.detect_and_embed(scan_fr, score_threshold=0.52, min_box_px=16)
    for d in dets:
        bx, by, bw, bh = d["box"]
        cx = (bx + bw * 0.5) / scale
        cy = (by + bh * 0.48) / scale
        side = max(bw / scale, bh / scale) * 1.68
        x1 = max(0, int(round(cx - side * 0.5)))
        y1 = max(0, int(round(cy - side * 0.5)))
        x2 = min(ow, int(round(cx + side * 0.5)))
        y2 = min(oh, int(round(cy + side * 0.5)))
        rw, rh = x2 - x1, y2 - y1
        if rw < 16 or rh < 16:
            continue
        crop = out_img[y1:y2, x1:x2]
        sq = max(rw, rh)
        sq_crop = crop if rw == rh else cv2.resize(crop, (sq, sq), interpolation=cv2.INTER_CUBIC)
        restored_sq = gfp.restore_face(sq_crop)
        restored = restored_sq if restored_sq.shape[:2] == (rh, rw) else cv2.resize(restored_sq, (rw, rh), interpolation=cv2.INTER_CUBIC)
        # Blend 72% GFPGAN + 28% original with feathered elliptical mask for natural identity
        blended_face = cv2.addWeighted(restored, 0.72, crop, 0.28, 0)
        mask = np.zeros((rh, rw), dtype=np.float32)
        cv2.ellipse(mask, (rw // 2, rh // 2), (max(2, int(rw * 0.44)), max(2, int(rh * 0.45))), 0, 0, 360, 1.0, -1)
        fk = max(7, (min(rw, rh) // 5) | 1)
        mask = cv2.GaussianBlur(mask, (fk, fk), 0)[:, :, None]
        comp = blended_face.astype(np.float32) * mask + crop.astype(np.float32) * (1.0 - mask)
        out_img[y1:y2, x1:x2] = np.clip(comp, 0, 255).astype(np.uint8)
    return out_img, "ai_face"


def _score_fullres_for_peak(cv2: Any, frame: np.ndarray, face_engine: Any) -> float:
    oh, ow = frame.shape[:2]
    scale = min(1.0, 640.0 / float(max(oh, ow)))
    small = (
        cv2.resize(frame, (max(1, int(round(ow * scale))), max(1, int(round(oh * scale)))), interpolation=cv2.INTER_AREA)
        if scale < 1.0
        else frame
    )
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    full_lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if face_engine is not None:
        try:
            dets = face_engine.detect_and_embed(small, score_threshold=0.55, min_box_px=16)
        except Exception:
            dets = []
        if dets:
            best_lap = 0.0
            sh, sw = small.shape[:2]
            for d in dets:
                bx, by, bw, bh = d["box"]
                fx1, fy1 = max(0, int(round(bx))), max(0, int(round(by)))
                fx2, fy2 = min(sw, int(round(bx + bw))), min(sh, int(round(by + bh)))
                if fx2 - fx1 >= 8 and fy2 - fy1 >= 8:
                    best_lap = max(best_lap, float(cv2.Laplacian(gray[fy1:fy2, fx1:fx2], cv2.CV_64F).var()))
            if best_lap > 0.0:
                return best_lap * 0.75 + full_lap * 0.25
    return full_lap


def _extract_sharpest_near_frame(
    cv2: Any,
    cap: Any,
    target_fi: int,
    *,
    total_frames: int,
    face_engine: Any = None,
    radius: int = 5,
) -> tuple[np.ndarray | None, int]:
    """Seek slightly before target_fi and pick the sharpest frame inside +-radius window to dodge VFR/motion blur."""
    start_fi = max(0, int(target_fi) - radius)
    end_fi = int(target_fi) + radius
    if total_frames > 0:
        end_fi = min(total_frames - 1, end_fi)
    cap.set(cv2.CAP_PROP_POS_FRAMES, float(start_fi))
    best_frame: np.ndarray | None = None
    best_fi = int(target_fi)
    best_score = -1.0
    n_read = max(1, end_fi - start_fi + 1)
    for offset in range(n_read):
        ok, fr = cap.read()
        if not ok or fr is None:
            break
        cur_fi = start_fi + offset
        sc = _score_fullres_for_peak(cv2, fr, face_engine)
        if sc > best_score or best_frame is None:
            best_score = sc
            best_frame = fr
            best_fi = cur_fi
    return best_frame, best_fi


def enhance_best_photo(
    project_root: Path,
    filename: str,
    *,
    enhance_mode: str = "ai_face",
) -> dict[str, Any]:
    clean_name = Path(str(filename or "").strip()).name
    if not clean_name or not re.match(r"^[a-zA-Z0-9_.-]+$", clean_name):
        raise ValueError("Tên file ảnh không hợp lệ.")
    out_dir = _best_photos_dir(project_root).resolve()
    target_fp = (out_dir / clean_name).resolve()
    if not target_fp.is_relative_to(out_dir) or not target_fp.exists() or not target_fp.is_file():
        raise FileNotFoundError("Không tìm thấy file ảnh cần xử lý.")

    orig_dir = (out_dir / "_orig").resolve()
    orig_dir.mkdir(parents=True, exist_ok=True)
    orig_fp = (orig_dir / clean_name).resolve()
    if not orig_fp.exists():
        shutil.copy2(target_fp, orig_fp)

    mode = str(enhance_mode or "ai_face").strip()
    if mode not in ("none", "sharpen", "ai_face"):
        mode = "ai_face"

    cv2 = _fp._ensure_cv2()
    raw_bytes = np.fromfile(str(orig_fp), dtype=np.uint8)
    src_img = cv2.imdecode(raw_bytes, cv2.IMREAD_COLOR)
    if src_img is None:
        raise RuntimeError("Không đọc được dữ liệu ảnh gốc.")

    thumb_fp = (_thumbs_dir(project_root) / clean_name).resolve()
    if mode == "none":
        shutil.copy2(orig_fp, target_fp)
        applied = "none"
        _write_thumb_jpg(cv2, src_img, thumb_fp)
    else:
        enh_img, applied = enhance_photo_frame(cv2, src_img, enhance_mode=mode)
        ok_enc, buf = cv2.imencode(".jpg", enh_img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if not ok_enc:
            raise RuntimeError("Không lưu được ảnh sau khi làm nét.")
        target_fp.write_bytes(buf.tobytes())
        _write_thumb_jpg(cv2, enh_img, thumb_fp)

    now_ts = int(time.time())
    cur = load_best_photos_state(project_root)
    new_sz = int(target_fp.stat().st_size)
    for item in cur.get("photos") or []:
        if item.get("filename") == clean_name:
            item["enhanced"] = applied
            item["size_bytes"] = new_sz
            item["updated_at"] = now_ts
    cur["updated_at"] = now_ts
    _write_manifest(project_root, cur)
    return cur


def _sanitize_clip_stem(clip_rel: str) -> str:
    stem = Path(clip_rel).stem
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", stem).strip("_")
    return safe[:36] or "clip"


def nudge_best_photo(
    project_root: Path,
    filename: str,
    delta_sec: float = 0.2,
) -> dict[str, Any]:
    """Shift a previously extracted photo by delta_sec (+-0.2s) directly from its source clip."""
    clean_name = Path(str(filename or "").strip()).name
    if not clean_name or not re.match(r"^[a-zA-Z0-9_.-]+$", clean_name):
        raise ValueError("Tên file ảnh không hợp lệ.")

    project_root = Path(project_root)
    cur = load_best_photos_state(project_root)
    photos = cur.get("photos") or []
    target_item = next((x for x in photos if x.get("filename") == clean_name), None)
    if target_item is None:
        raise FileNotFoundError("Không tìm thấy metadata của ảnh cần chỉnh thời điểm.")

    clip_rel = str(target_item.get("clip_rel") or target_item.get("clip_name") or "").strip()
    src_clips = _collect_source_videos(project_root, selected_clips=[clip_rel] if clip_rel else None)
    if not src_clips:
        src_clips = _collect_source_videos(project_root, selected_clips=[str(target_item.get("clip_name") or "")])
    if not src_clips:
        raise FileNotFoundError(f"Không tìm thấy video gốc `{clip_rel}` trong 02_video_tho.")
    clip_path = src_clips[0][0]

    cv2 = _fp._ensure_cv2()
    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        raise RuntimeError(f"Không mở được video gốc `{clip_path.name}`.")
    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        if fps < 1.0 or fps > 120.0:
            fps = 30.0
        cur_ts = float(target_item.get("timestamp_sec") or 0.0)
        new_ts = max(0.0, cur_ts + float(delta_sec))
        if total_frames > 0:
            max_ts = max(0.0, (total_frames - 1) / fps)
            new_ts = min(max_ts, new_ts)
        target_fi = max(0, int(round(new_ts * fps)))
        seek_fi = max(0, target_fi - 2)
        cap.set(cv2.CAP_PROP_POS_FRAMES, float(seek_fi))
        full_frame = None
        for cur_fi in range(seek_fi, target_fi + 1):
            ok, fr = cap.read()
            if not ok or fr is None:
                break
            if cur_fi == target_fi:
                full_frame = fr
                break
        if full_frame is None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, float(target_fi))
            ok, fr = cap.read()
            if ok and fr is not None:
                full_frame = fr
    finally:
        cap.release()

    if full_frame is None:
        raise RuntimeError("Không trích xuất được khung hình tại thời điểm mới.")

    out_dir = _best_photos_dir(project_root).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target_fp = (out_dir / clean_name).resolve()
    orig_dir = (out_dir / "_orig").resolve()
    orig_dir.mkdir(parents=True, exist_ok=True)
    orig_fp = (orig_dir / clean_name).resolve()

    ok_orig, orig_buf = cv2.imencode(".jpg", full_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok_orig:
        raise RuntimeError("Không mã hóa được ảnh mới.")
    orig_fp.write_bytes(orig_buf.tobytes())

    thumb_fp = (_thumbs_dir(project_root) / clean_name).resolve()
    enh_mode = str(target_item.get("enhanced") or "none").strip()
    if enh_mode in ("sharpen", "ai_face"):
        enh_img, applied_enh = enhance_photo_frame(cv2, full_frame, enhance_mode=enh_mode)
        ok_enh, enh_buf = cv2.imencode(".jpg", enh_img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        target_fp.write_bytes(enh_buf.tobytes() if ok_enh else orig_buf.tobytes())
        _write_thumb_jpg(cv2, enh_img if ok_enh else full_frame, thumb_fp)
    else:
        applied_enh = "none"
        target_fp.write_bytes(orig_buf.tobytes())
        _write_thumb_jpg(cv2, full_frame, thumb_fp)

    now_ts = int(time.time())
    fh, fw = full_frame.shape[:2]
    target_item["timestamp_sec"] = round(float(new_ts), 2)
    target_item["timestamp_str"] = _format_ts_str(float(new_ts))
    target_item["width"] = int(fw)
    target_item["height"] = int(fh)
    target_item["enhanced"] = applied_enh
    target_item["size_bytes"] = int(target_fp.stat().st_size)
    target_item["updated_at"] = now_ts

    cur["updated_at"] = now_ts
    _write_manifest(project_root, cur)
    return cur


def _unique_photo_filename(fname: str, used_names: set[str]) -> str:
    clean = Path(str(fname or "photo.jpg")).name
    if clean.lower() not in used_names:
        used_names.add(clean.lower())
        return clean
    stem = Path(clean).stem
    ext = Path(clean).suffix or ".jpg"
    m = re.match(r"^(.+?)_(\d+)$", stem)
    base, start_n = (m.group(1), int(m.group(2)) + 1) if m else (stem, 2)
    n = max(2, start_n)
    while True:
        cand = f"{base}_{n:02d}{ext}"
        if cand.lower() not in used_names:
            used_names.add(cand.lower())
            return cand
        n += 1


def extract_best_photos(
    project_root: Path,
    *,
    count: int = 10,
    count_mode: str = "per_video",
    save_mode: str = "replace_selected",
    min_score: float = 7.5,
    focus: str = "auto",
    selected_clips: list[str] | None = None,
    use_ai: bool = True,
    apply_privacy: bool = False,
    enhance_mode: str = "none",
    gemini_api_key: str = "",
    gemini_model: str = "gemini-2.5-flash",
    agy_fallback: Callable[[str, list[Path]], str] | None = None,
    progress_cb: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    def _rep(pct: int, msg: str) -> None:
        if progress_cb is not None:
            try:
                progress_cb(int(pct), str(msg))
            except Exception:
                pass

    project_root = Path(project_root)
    count = max(1, min(30, int(count or 10)))
    count_mode = "total" if str(count_mode or "per_video").strip() == "total" else "per_video"
    save_mode_clean = str(save_mode or "replace_selected").strip()
    if save_mode_clean not in ("replace_selected", "append", "replace_all"):
        save_mode_clean = "replace_selected"
    save_mode = save_mode_clean
    try:
        ms_val = float(min_score if min_score is not None else 7.5)
    except (TypeError, ValueError):
        ms_val = 7.5
    min_score = 0.0 if ms_val <= 0.0 else round(max(5.0, min(9.5, ms_val)), 1)
    focus = focus if focus in ("auto", "portrait", "scenic") else "auto"

    videos = _collect_source_videos(project_root, selected_clips=selected_clips)
    if not videos:
        raise RuntimeError("Không có video thô nào trong `02_video_tho` để trích xuất ảnh đẹp.")

    _rep(5, "Đang khởi tạo bộ chấm nét, ổn định dáng & Sổ tay Gu Ảnh...")
    rules_text = load_photo_taste_rules()
    ws_tmp = project_root / "04_workspace" / "_best_photos_tmp"

    selected_entries: list[tuple[dict[str, Any], float, str, str]] = []
    skipped_clips: list[str] = []
    ai_used = False
    ai_channel = "local"
    ai_note = ""

    if count_mode == "per_video":
        total_v = len(videos)
        used_stems: dict[str, int] = {}
        for v_idx, (vp, rel_name) in enumerate(videos, start=1):
            base_pct = 6 + int(round((v_idx - 1) / float(max(1, total_v)) * 66))
            _rep(base_pct, f"Video {v_idx}/{total_v}: Đang lọc ứng viên {vp.name}...")
            pool_size = min(18, max(9, count * 3)) if use_ai else count
            clip_cands, clip_back_view = _collect_candidates(
                [(vp, rel_name)],
                pool_size=pool_size,
                focus=focus,
                progress_cb=None,
            )
            if not clip_cands:
                continue

            base_stem = _sanitize_clip_stem(rel_name)
            seen_cnt = used_stems.get(base_stem, 0) + 1
            used_stems[base_stem] = seen_cnt
            clip_stem = base_stem if seen_cnt == 1 else f"{base_stem}_{seen_cnt}"

            by_cid = {int(c["cid"]): c for c in clip_cands}
            clip_picks: list[tuple[dict[str, Any], float, str]] = []
            if use_ai:
                _rep(base_pct + int(round(33 / float(max(1, total_v)))), f"Video {v_idx}/{total_v}: AI đang soi {len(clip_cands)} ứng viên từ {vp.name}...")
                picks, c_ai_used, c_ai_ch, c_ai_note = _select_with_ai(
                    clip_cands,
                    count=count,
                    focus=focus,
                    min_score=min_score,
                    is_back_view=clip_back_view,
                    rules_text=rules_text,
                    gemini_api_key=gemini_api_key,
                    gemini_model=gemini_model,
                    agy_fallback=agy_fallback,
                    tmp_dir=ws_tmp,
                )
                if c_ai_used:
                    ai_used = True
                    ai_channel = c_ai_ch
                elif c_ai_note and not ai_note:
                    ai_note = c_ai_note

                seen_cids: set[int] = set()
                for pk in sorted(picks, key=lambda x: float(x.get("score") or 0.0), reverse=True):
                    cid = int(pk["id"])
                    sc_val = float(pk["score"])
                    if c_ai_used and min_score > 0 and sc_val < min_score:
                        continue
                    if cid in by_cid and cid not in seen_cids:
                        seen_cids.add(cid)
                        clip_picks.append((by_cid[cid], sc_val, str(pk.get("reason") or "")))
                        if len(clip_picks) >= count:
                            break
                if (not c_ai_used or min_score <= 0) and len(clip_picks) < min(count, len(clip_cands)):
                    for c in sorted(clip_cands, key=lambda x: x["local_score"], reverse=True):
                        if int(c["cid"]) in seen_cids:
                            continue
                        seen_cids.add(int(c["cid"]))
                        loc_score = round(min(8.8, max(5.5, 5.2 + c["local_score"] * 3.8)), 1)
                        clip_picks.append((c, loc_score, "Nét ổn định, bố cục hài hòa (bổ sung Local)"))
                        if len(clip_picks) >= count:
                            break
                if c_ai_used and min_score > 0 and not clip_picks:
                    skipped_clips.append(vp.name)
            else:
                for c in sorted(clip_cands, key=lambda x: x["local_score"], reverse=True)[:count]:
                    loc_score = round(min(9.0, max(5.8, 5.4 + c["local_score"] * 3.8)), 1)
                    if min_score <= 0 or loc_score >= min_score:
                        clip_picks.append((c, loc_score, "Nét cao, dáng ổn định & sáng đẹp (Offline)"))

            for sub_idx, (cand, sc, reason) in enumerate(clip_picks, start=1):
                fname = f"{clip_stem}_{sub_idx:02d}.jpg"
                selected_entries.append((cand, sc, reason, fname))
    else:
        pool_size = min(27, max(12, count * 2 + 4)) if use_ai else count
        candidates, any_back_view = _collect_candidates(videos, pool_size=pool_size, focus=focus, progress_cb=progress_cb)
        if not candidates:
            raise RuntimeError("Không đọc được khung hình hợp lệ nào từ các video.")
        by_cid = {int(c["cid"]): c for c in candidates}
        clip_picks = []
        if use_ai:
            _rep(54, f"Đang gửi {len(candidates)} ảnh ứng viên cho AI Vision soi kỹ...")
            picks, ai_used, ai_channel, ai_note = _select_with_ai(
                candidates,
                count=count,
                focus=focus,
                min_score=min_score,
                is_back_view=any_back_view,
                rules_text=rules_text,
                gemini_api_key=gemini_api_key,
                gemini_model=gemini_model,
                agy_fallback=agy_fallback,
                tmp_dir=ws_tmp,
            )
            seen_cids = set()
            for pk in sorted(picks, key=lambda x: float(x.get("score") or 0.0), reverse=True):
                cid = int(pk["id"])
                sc_val = float(pk["score"])
                if ai_used and min_score > 0 and sc_val < min_score:
                    continue
                if cid in by_cid and cid not in seen_cids:
                    seen_cids.add(cid)
                    clip_picks.append((by_cid[cid], sc_val, str(pk.get("reason") or "")))
                    if len(clip_picks) >= count:
                        break
            if (not ai_used or min_score <= 0) and len(clip_picks) < min(count, len(candidates)):
                for c in sorted(candidates, key=lambda x: x["local_score"], reverse=True):
                    if int(c["cid"]) in seen_cids:
                        continue
                    seen_cids.add(int(c["cid"]))
                    loc_score = round(min(8.8, max(5.5, 5.2 + c["local_score"] * 3.8)), 1)
                    clip_picks.append((c, loc_score, "Ảnh sắc nét, cân bằng sáng (bổ sung Local)"))
                    if len(clip_picks) >= count:
                        break
        else:
            for c in sorted(candidates, key=lambda x: x["local_score"], reverse=True)[:count]:
                loc_score = round(min(9.0, max(5.8, 5.4 + c["local_score"] * 3.8)), 1)
                if min_score <= 0 or loc_score >= min_score:
                    clip_picks.append((c, loc_score, "Độ nét cao, cân bằng sáng & bố cục tốt (Offline)"))

        for rank_idx, (cand, sc, reason) in enumerate(clip_picks, start=1):
            selected_entries.append((cand, sc, reason, f"photo_{rank_idx:02d}.jpg"))

    if skipped_clips:
        skip_msg = f"Đã bỏ qua {len(skipped_clips)} clip không đạt >= {min_score:.1f}đ ({', '.join(skipped_clips[:3])}{'...' if len(skipped_clips) > 3 else ''})"
        ai_note = f"{ai_note} · {skip_msg}".strip(" ·") if ai_note else skip_msg

    if not selected_entries:
        if min_score > 0 and ai_used:
            prev_st = load_best_photos_state(project_root)
            zero_msg = f"Không có ảnh nào đạt ngưỡng >= {min_score:.1f}đ (đã giữ nguyên ảnh cũ). Thử hạ 'Độ gắt lọc ảnh' nếu muốn lấy thêm."
            _rep(100, zero_msg)
            return {
                "ok": True,
                "new_count": 0,
                **prev_st,
                "ai_used": True,
                "ai_channel": ai_channel,
                "ai_note": zero_msg,
                "min_score": float(min_score),
            }
        raise RuntimeError("Không trích xuất được ảnh nào từ các video đã chọn.")

    _rep(76, f"Đang xuất {len(selected_entries)} ảnh độ phân giải gốc (JPG 95%)...")

    priv_state = _fp.load_face_privacy_state(project_root) if apply_privacy else {}
    priv_cfg = _fp.normalize_face_config(priv_state.get("config")) if apply_privacy else {}
    priv_face_eng = _fp._FaceEngine() if (apply_privacy and priv_cfg.get("enabled")) else None
    priv_plate_eng = _fp._get_plate_engine() if (apply_privacy and priv_cfg.get("plate_blur_enabled")) else None
    priv_plate_ocr = (
        _fp._get_plate_ocr_engine()
        if (apply_privacy and priv_cfg.get("plate_blur_enabled") and priv_cfg.get("plate_blur_mode") != "blur_all")
        else None
    )
    priv_face_items: list[tuple[str, np.ndarray]] = []
    priv_plate_items: list[dict[str, Any]] = []
    if apply_privacy:
        for f in priv_state.get("faces") or []:
            fid = str(f.get("id") or "").strip()
            emb_l = f.get("embedding")
            if fid and isinstance(emb_l, list) and emb_l:
                priv_face_items.append((fid, _fp._l2_norm(np.array(emb_l, dtype=np.float32))))
        for pl in priv_state.get("plates") or []:
            pid = str(pl.get("id") or "").strip()
            ptxt = re.sub(r"[^A-Z0-9]", "", str(pl.get("plate_text") or "").upper())
            emb_l = pl.get("embedding")
            evec = _fp._l2_norm(np.array(emb_l, dtype=np.float32)) if isinstance(emb_l, list) and emb_l else np.zeros((0,), dtype=np.float32)
            if pid and (len(ptxt) >= 4 or evec.size > 0):
                priv_plate_items.append({"id": pid, "plate_text": ptxt, "emb": evec})

    out_dir = _best_photos_dir(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    orig_dir = out_dir / "_orig"
    thumbs_dir = _thumbs_dir(project_root)
    prev_state = load_best_photos_state(project_root)
    prev_photos = list(prev_state.get("photos") or [])

    if save_mode == "replace_all":
        for old_jpg in out_dir.glob("*.jpg"):
            old_jpg.unlink(missing_ok=True)
        for sub_d in (orig_dir, thumbs_dir):
            if sub_d.exists():
                for old_sub in sub_d.glob("*.jpg"):
                    old_sub.unlink(missing_ok=True)
        kept_photos: list[dict[str, Any]] = []
    elif save_mode == "replace_selected":
        processed_keys = {rel.lower() for _, rel in videos} | {p.name.lower() for p, _ in videos}
        kept_photos = []
        for old_item in prev_photos:
            old_fn = Path(str(old_item.get("filename") or "")).name
            c_rel = str(old_item.get("clip_rel") or "").replace("\\", "/").strip().lower()
            c_name = str(old_item.get("clip_name") or "").strip().lower()
            if (c_rel and c_rel in processed_keys) or (c_name and c_name in processed_keys):
                if old_fn:
                    (out_dir / old_fn).unlink(missing_ok=True)
                    (orig_dir / old_fn).unlink(missing_ok=True)
                    (thumbs_dir / old_fn).unlink(missing_ok=True)
            else:
                kept_photos.append(dict(old_item))
    else:  # append
        kept_photos = [dict(x) for x in prev_photos]

    used_names: set[str] = {str(x.get("filename") or "").lower() for x in kept_photos if x.get("filename")}
    unique_entries: list[tuple[dict[str, Any], float, str, str]] = []
    for cand, sc, reason, raw_fname in selected_entries:
        unique_entries.append((cand, sc, reason, _unique_photo_filename(raw_fname, used_names)))
    selected_entries = unique_entries

    enh_mode = str(enhance_mode or "none").strip()
    if enh_mode not in ("none", "sharpen", "ai_face"):
        enh_mode = "none"
    peak_face_eng = _fp._FaceEngine() if (focus in ("auto", "portrait") or enh_mode == "ai_face") else None

    cv2 = _fp._ensure_cv2()
    by_video: dict[Path, list[tuple[int, dict[str, Any], float, str, str]]] = {}
    for rank, (cand, sc, reason, fname) in enumerate(selected_entries, start=1):
        by_video.setdefault(cand["video_path"], []).append((rank, cand, sc, reason, fname))

    extracted_by_rank: dict[int, dict[str, Any]] = {}
    done_cnt = 0
    for vp, jobs in by_video.items():
        cap = cv2.VideoCapture(str(vp))
        if not cap.isOpened():
            continue
        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            vid_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
            if vid_fps < 1.0 or vid_fps > 120.0:
                vid_fps = 30.0
            for rank, cand, sc, reason, fname in sorted(jobs, key=lambda x: x[1]["frame_idx"]):
                fi = int(cand["frame_idx"])
                full_frame, picked_fi = _extract_sharpest_near_frame(
                    cv2,
                    cap,
                    fi,
                    total_frames=total_frames,
                    face_engine=peak_face_eng,
                    radius=5,
                )
                if full_frame is None:
                    full_frame = cand["tile"]
                    picked_fi = fi
                if apply_privacy and (priv_face_eng is not None or priv_plate_eng is not None):
                    _apply_privacy_to_single_frame(
                        cv2,
                        full_frame,
                        project_root,
                        priv_face_eng,
                        priv_plate_eng,
                        priv_face_items,
                        priv_plate_items,
                        priv_plate_ocr,
                        priv_cfg,
                    )
                applied_enh = "none"
                if enh_mode != "none":
                    full_frame, applied_enh = enhance_photo_frame(
                        cv2,
                        full_frame,
                        enhance_mode=enh_mode,
                        face_engine=peak_face_eng,
                    )
                out_fp = out_dir / fname
                thumb_fp = thumbs_dir / fname
                fh, fw = full_frame.shape[:2]
                ts_val = round(float(picked_fi) / vid_fps, 2)
                ok_enc, buf = cv2.imencode(".jpg", full_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                if ok_enc:
                    out_fp.write_bytes(buf.tobytes())
                    _write_thumb_jpg(cv2, full_frame, thumb_fp)
                    now_item_ts = int(time.time())
                    extracted_by_rank[rank] = {
                        "filename": fname,
                        "rank": int(rank),
                        "score": float(sc),
                        "reason": reason,
                        "enhanced": applied_enh,
                        "clip_rel": cand["clip_rel"],
                        "clip_name": cand["clip_name"],
                        "timestamp_sec": float(ts_val),
                        "timestamp_str": _format_ts_str(float(ts_val)),
                        "width": int(fw),
                        "height": int(fh),
                        "size_bytes": int(out_fp.stat().st_size),
                        "updated_at": now_item_ts,
                    }
                done_cnt += 1
                pct = 76 + int(round((done_cnt / float(max(1, len(selected_entries)))) * 22))
                _rep(pct, f"Đang xuất ảnh {done_cnt}/{len(selected_entries)}...")
        finally:
            cap.release()

    new_photos = [extracted_by_rank[r] for r in sorted(extracted_by_rank.keys())]
    photos_out = kept_photos + new_photos
    for idx_r, p_item in enumerate(photos_out, start=1):
        p_item["rank"] = int(idx_r)
    state_data = {
        "updated_at": int(time.time()),
        "focus": focus,
        "count_mode": count_mode,
        "save_mode": save_mode,
        "min_score": float(min_score),
        "enhance_mode": enh_mode,
        "ai_used": bool(ai_used),
        "ai_channel": ai_channel,
        "ai_note": ai_note,
        "apply_privacy": bool(apply_privacy),
        "photos": photos_out,
    }
    _write_manifest(project_root, state_data)
    _rep(100, f"Hoàn tất! Thêm {len(new_photos)} ảnh (tổng {len(photos_out)} ảnh đẹp).")
    return {"ok": True, "new_count": len(new_photos), **state_data}
