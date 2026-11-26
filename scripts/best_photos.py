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
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

import numpy as np
import requests

import face_privacy as _fp

MEDIA_VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")


def _best_photos_dir(project_root: Path) -> Path:
    return Path(project_root) / "05_output" / "best_photos"


def _manifest_path(project_root: Path) -> Path:
    return _best_photos_dir(project_root) / "manifest.json"


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
        item_copy["size_bytes"] = int(fp.stat().st_size)
        valid_photos.append(item_copy)

    return {
        "updated_at": int(data.get("updated_at") or 0),
        "focus": str(data.get("focus") or "auto"),
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

    cur = load_best_photos_state(project_root)
    cur["photos"] = [p for p in (cur.get("photos") or []) if p.get("filename") != clean_name]
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
    wanted = {str(x).replace("\\", "/").strip() for x in (selected_clips or []) if str(x).strip()}
    out: list[tuple[Path, str]] = []
    for p in raw_dir.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in MEDIA_VIDEO_EXTS:
            continue
        rel = p.relative_to(raw_dir).as_posix()
        if wanted and rel not in wanted and p.name not in wanted:
            continue
        out.append((p, rel))
    out.sort(key=lambda item: item[1].lower())
    return out


def _score_candidate_frame(
    cv2: Any,
    frame_small: np.ndarray,
    face_engine: Any,
    focus: str,
) -> dict[str, Any]:
    sh, sw = frame_small.shape[:2]
    gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)

    # 1. Sharpness: Laplacian variance + Tenengrad mean
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mean = float(np.sqrt(gx * gx + gy * gy).mean())
    sharp_norm = min(1.0, (lap_var / 420.0) * 0.65 + (grad_mean / 42.0) * 0.35)

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

    # 4. Face composition (YuNet) when auto/portrait
    face_score = 0.0
    face_count = 0
    if face_engine is not None and focus in ("auto", "portrait"):
        try:
            dets = face_engine.detect_and_embed(frame_small, score_threshold=0.58, min_box_px=20)
        except Exception:
            dets = []
        face_count = len(dets)
        if dets:
            best_fq = 0.0
            for d in dets:
                bx, by, bw, bh = d["box"]
                # Penalize clipped edge faces
                mx = min(bx, sw - (bx + bw))
                my = min(by, sh - (by + bh))
                edge_ok = 1.0 if (mx >= 6 and my >= 6) else 0.55
                fq = float(d.get("quality", 0.6)) * edge_ok
                if fq > best_fq:
                    best_fq = fq
            face_score = min(1.0, best_fq)

    if focus == "portrait":
        local_score = (
            sharp_norm * 0.36
            + face_score * 0.42
            + expo_norm * 0.12
            + contrast_norm * 0.06
            + color_norm * 0.04
        )
    elif focus == "scenic":
        local_score = (
            sharp_norm * 0.44
            + expo_norm * 0.22
            + contrast_norm * 0.18
            + color_norm * 0.16
        )
    else:
        local_score = (
            sharp_norm * 0.38
            + expo_norm * 0.18
            + contrast_norm * 0.14
            + color_norm * 0.10
            + face_score * 0.20
        )

    # Compact visual fingerprint for scene dedup
    fp_patch = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA).astype(np.float32).flatten()
    fp_patch = fp_patch - float(fp_patch.mean())
    fp_vec = _fp._l2_norm(fp_patch)

    return {
        "local_score": float(round(local_score, 4)),
        "sharpness": float(round(sharp_norm, 3)),
        "face_count": int(face_count),
        "fp_vec": fp_vec,
    }


def _collect_candidates(
    videos: list[tuple[Path, str]],
    *,
    pool_size: int,
    focus: str,
    progress_cb: Callable[[int, str], None] | None = None,
) -> list[dict[str, Any]]:
    cv2 = _fp._ensure_cv2()
    face_engine = _fp._FaceEngine() if focus in ("auto", "portrait") else None

    total_clips = len(videos)
    # Aim ~60-96 total scanned frames distributed across clips
    total_budget = max(24, min(110, max(pool_size * 4, total_clips * 10)))
    per_clip = max(5, min(20, int(round(total_budget / float(max(1, total_clips))))))

    raw_candidates: list[dict[str, Any]] = []
    for c_idx, (vp, rel_name) in enumerate(videos, start=1):
        if progress_cb is not None:
            pct = 8 + int(round((c_idx - 1) / float(max(1, total_clips)) * 38))
            progress_cb(pct, f"Đang quét nét clip {c_idx}/{total_clips}: {vp.name}...")

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
                indices = sorted(set(int(round(x)) for x in np.linspace(lo, hi, num=want)))
                idx_set = set(indices)
                max_idx = indices[-1]
                sampled: list[tuple[int, np.ndarray]] = []
                for fi in range(max_idx + 1):
                    if fi in idx_set:
                        ok, fr = cap.read()
                        if not ok or fr is None:
                            break
                        sampled.append((fi, fr))
                    else:
                        if not cap.grab():
                            break
            else:
                sampled = _fp._sample_video_frames(cv2, vp, max_samples=per_clip)

            for fi, orig_frame in sampled:
                oh, ow = orig_frame.shape[:2]
                if oh <= 0 or ow <= 0:
                    continue
                scale = min(1.0, 640.0 / float(max(oh, ow)))
                small = (
                    cv2.resize(orig_frame, (max(1, int(round(ow * scale))), max(1, int(round(oh * scale)))), interpolation=cv2.INTER_AREA)
                    if scale < 1.0
                    else orig_frame
                )
                metrics = _score_candidate_frame(cv2, small, face_engine, focus)

                # Build medium preview tile for contact sheet (keep in RAM cleanly; ~32 tiles total)
                tw, th = 480, 360
                r_tile = min(float(tw) / float(ow), float(th) / float(oh))
                nw, nh = max(1, int(round(ow * r_tile))), max(1, int(round(oh * r_tile)))
                tile_resized = cv2.resize(orig_frame, (nw, nh), interpolation=cv2.INTER_AREA)
                tile_canvas = np.full((th, tw, 3), 20, dtype=np.uint8)
                xo, yo = (tw - nw) // 2, (th - nh) // 2
                tile_canvas[yo : yo + nh, xo : xo + nw] = tile_resized

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
        finally:
            cap.release()

    if not raw_candidates:
        return []

    def _is_dup(cand: dict[str, Any], chosen_list: list[dict[str, Any]]) -> bool:
        vec = cand["fp_vec"]
        for ex in chosen_list:
            sim = float(np.dot(vec, ex["fp_vec"]))
            same_clip = cand["clip_rel"] == ex["clip_rel"]
            close_time = abs(cand["timestamp_sec"] - ex["timestamp_sec"]) < 2.2
            if sim >= 0.955 or (same_clip and close_time and sim >= 0.90):
                return True
        return False

    chosen: list[dict[str, Any]] = []
    # Guarantee top-1 from each clip first when total clips <= pool_size
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

    # Relaxed fill if dedup was too strict
    if len(chosen) < pool_size:
        for cand in remaining_sorted:
            if len(chosen) >= pool_size:
                break
            if any(cand is ex for ex in chosen):
                continue
            chosen.append(cand)

    for idx, c in enumerate(chosen, start=1):
        c["cid"] = idx
    return chosen


def _build_contact_sheets(candidates: list[dict[str, Any]], max_per_sheet: int = 16) -> list[tuple[bytes, list[int]]]:
    cv2 = _fp._ensure_cv2()
    sheets: list[tuple[bytes, list[int]]] = []
    if not candidates:
        return sheets

    tw, th = 480, 360
    pad = 8
    for start in range(0, len(candidates), max_per_sheet):
        chunk = candidates[start : start + max_per_sheet]
        n = len(chunk)
        cols = 4 if n > 9 else (3 if n > 4 else min(2, max(1, n)))
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
            cid = int(cand["cid"])
            cids.append(cid)

            tag = f"#{cid:02d}"
            cv2.rectangle(tile, (8, 8), (94, 46), (12, 12, 16), -1)
            cv2.rectangle(tile, (8, 8), (94, 46), (255, 200, 40), 2)
            cv2.putText(tile, tag, (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.95, (255, 225, 90), 2, cv2.LINE_AA)
            canvas[y : y + th, x : x + tw] = tile

        ok, buf = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if ok:
            sheets.append((buf.tobytes(), cids))
    return sheets


def _parse_ai_picks_json(raw_text: str) -> list[dict[str, Any]]:
    txt = str(raw_text or "").strip()
    if not txt:
        return []
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt, flags=re.I)
    if m:
        txt = m.group(1).strip()
    try:
        parsed = json.loads(txt)
    except Exception:
        m2 = re.search(r"\{[\s\S]*\}", txt)
        if not m2:
            return []
        try:
            parsed = json.loads(m2.group(0))
        except Exception:
            return []
    picks = parsed.get("picks") if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
    out: list[dict[str, Any]] = []
    if isinstance(picks, list):
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
    return out


def _select_with_ai(
    candidates: list[dict[str, Any]],
    *,
    count: int,
    focus: str,
    gemini_api_key: str,
    gemini_model: str,
    agy_fallback: Callable[[str, list[Path]], str] | None,
    tmp_dir: Path,
) -> tuple[list[dict[str, Any]], bool, str, str]:
    focus_hint = {
        "portrait": "ƯU TIÊN CHÂN DUNG & BIỂU CẢM: người cười tự nhiên, mở mắt rõ, không nhắm mắt, không há miệng nói dở, không che mặt.",
        "scenic": "ƯU TIÊN CẢNH ĐẸP & BỐ CỤC: ánh sáng đẹp, góc rộng thoáng, màu sắc hài hòa, không vướng vật cản.",
        "auto": "CÂN BẰNG: ảnh nét nhất, ánh sáng đẹp, bố cục gọn mắt; nếu có người thì mắt mở rõ và biểu cảm tự nhiên.",
    }.get(focus, "Ảnh nét, sáng đẹp, biểu cảm tự nhiên, bố cục hài hòa.")

    sheets = _build_contact_sheets(candidates, max_per_sheet=16)
    if not sheets:
        return [], False, "local", "Không tạo được ảnh lưới ứng viên."

    valid_cids = [int(c["cid"]) for c in candidates]
    prompt = (
        f"Bạn là biên tập viên ảnh chuyên nghiệp. Hãy xem ảnh lưới ứng viên (mỗi ô có mã #01, #02...) "
        f"và chọn đúng {min(count, len(candidates))} tấm ĐẸP NHẤT.\n"
        f"Tiêu chí ưu tiên: {focus_hint}\n"
        f"BẮT BUỘC LOẠI BỎ ảnh bị nhắm mắt, biểu cảm đơ/méo miệng khi đang nói, rung mờ, tối hoặc cắt mất chủ thể.\n"
        f"Trả về DUY NHẤT JSON hợp lệ theo mẫu:\n"
        f'{{"picks": [{{"id": 3, "score": 9.3, "reason": "Nụ cười tự nhiên, ánh sáng đẹp, nét căng"}}]}}\n'
        f"Lưu ý: id là số nguyên trong danh sách {valid_cids}, score từ 1.0 đến 10.0, reason viết tiếng Việt ngắn gọn <= 12 từ."
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
                    picks = _parse_ai_picks_json(txt)
                    if picks:
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
            picks = _parse_ai_picks_json(txt)
            if picks:
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


def extract_best_photos(
    project_root: Path,
    *,
    count: int = 10,
    focus: str = "auto",
    selected_clips: list[str] | None = None,
    use_ai: bool = True,
    apply_privacy: bool = False,
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
    focus = focus if focus in ("auto", "portrait", "scenic") else "auto"

    videos = _collect_source_videos(project_root, selected_clips=selected_clips)
    if not videos:
        raise RuntimeError("Không có video thô nào trong `02_video_tho` để trích xuất ảnh đẹp.")

    _rep(5, "Đang khởi tạo bộ chấm nét OpenCV...")
    pool_size = min(32, max(16, count * 2 + 4)) if use_ai else count
    candidates = _collect_candidates(videos, pool_size=pool_size, focus=focus, progress_cb=progress_cb)
    if not candidates:
        raise RuntimeError("Không đọc được khung hình hợp lệ nào từ các video.")

    by_cid = {int(c["cid"]): c for c in candidates}
    selected_entries: list[tuple[dict[str, Any], float, str]] = []
    ai_used = False
    ai_channel = "local"
    ai_note = ""

    if use_ai:
        _rep(54, f"Đang gửi {len(candidates)} ảnh ứng viên cho AI Vision chọn Top {count}...")
        ws_tmp = project_root / "04_workspace" / "_best_photos_tmp"
        picks, ai_used, ai_channel, ai_note = _select_with_ai(
            candidates,
            count=count,
            focus=focus,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            agy_fallback=agy_fallback,
            tmp_dir=ws_tmp,
        )
        seen_cids: set[int] = set()
        for pk in picks:
            cid = int(pk["id"])
            if cid in by_cid and cid not in seen_cids:
                seen_cids.add(cid)
                selected_entries.append((by_cid[cid], float(pk["score"]), str(pk.get("reason") or "")))
                if len(selected_entries) >= count:
                    break
        if len(selected_entries) < min(count, len(candidates)):
            for c in sorted(candidates, key=lambda x: x["local_score"], reverse=True):
                if int(c["cid"]) in seen_cids:
                    continue
                seen_cids.add(int(c["cid"]))
                loc_score = round(min(9.6, max(5.5, 5.2 + c["local_score"] * 4.5)), 1)
                selected_entries.append((c, loc_score, "Ảnh sắc nét, cân bằng sáng (bổ sung theo chỉ số)"))
                if len(selected_entries) >= count:
                    break
    else:
        for c in sorted(candidates, key=lambda x: x["local_score"], reverse=True)[:count]:
            loc_score = round(min(9.8, max(5.8, 5.4 + c["local_score"] * 4.5)), 1)
            selected_entries.append((c, loc_score, "Độ nét cao, cân bằng sáng & bố cục tốt (Offline)"))

    _rep(76, f"Đang xuất {len(selected_entries)} ảnh độ phân giải gốc (JPG 95%)...")

    # Optional privacy engines prepared once
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
    for old_jpg in out_dir.glob("photo_*.jpg"):
        old_jpg.unlink(missing_ok=True)

    cv2 = _fp._ensure_cv2()
    # Group extractions by video path so each video opens once
    by_video: dict[Path, list[tuple[int, dict[str, Any], float, str]]] = {}
    for rank, (cand, sc, reason) in enumerate(selected_entries, start=1):
        by_video.setdefault(cand["video_path"], []).append((rank, cand, sc, reason))

    extracted_by_rank: dict[int, dict[str, Any]] = {}
    done_cnt = 0
    for vp, jobs in by_video.items():
        cap = cv2.VideoCapture(str(vp))
        if not cap.isOpened():
            continue
        try:
            for rank, cand, sc, reason in sorted(jobs, key=lambda x: x[1]["frame_idx"]):
                fi = int(cand["frame_idx"])
                cap.set(cv2.CAP_PROP_POS_FRAMES, float(fi))
                ok, full_frame = cap.read()
                if not ok or full_frame is None:
                    full_frame = cand["tile"]
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
                fname = f"photo_{rank:02d}.jpg"
                out_fp = out_dir / fname
                fh, fw = full_frame.shape[:2]
                ok_enc, buf = cv2.imencode(".jpg", full_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                if ok_enc:
                    out_fp.write_bytes(buf.tobytes())
                    extracted_by_rank[rank] = {
                        "filename": fname,
                        "rank": int(rank),
                        "score": float(sc),
                        "reason": reason,
                        "clip_rel": cand["clip_rel"],
                        "clip_name": cand["clip_name"],
                        "timestamp_sec": float(cand["timestamp_sec"]),
                        "timestamp_str": _format_ts_str(float(cand["timestamp_sec"])),
                        "width": int(fw),
                        "height": int(fh),
                        "size_bytes": int(out_fp.stat().st_size),
                    }
                done_cnt += 1
                pct = 76 + int(round((done_cnt / float(max(1, len(selected_entries)))) * 22))
                _rep(pct, f"Đang xuất ảnh {done_cnt}/{len(selected_entries)}...")
        finally:
            cap.release()

    photos_out = [extracted_by_rank[r] for r in sorted(extracted_by_rank.keys())]
    state_data = {
        "updated_at": int(time.time()),
        "focus": focus,
        "ai_used": bool(ai_used),
        "ai_channel": ai_channel,
        "ai_note": ai_note,
        "apply_privacy": bool(apply_privacy),
        "photos": photos_out,
    }
    _write_manifest(project_root, state_data)
    _rep(100, f"Hoàn tất! Đã trích xuất {len(photos_out)} ảnh đẹp.")
    return {"ok": True, **state_data}
