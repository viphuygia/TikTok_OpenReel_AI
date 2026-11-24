#!/usr/bin/env python3
"""
OpenCV YuNet + SFace Face Detection, Clustering & Selective Face Masking Engine.

Stores lightweight ONNX models in shared `03_voice_clone/model/opencv_face/`
and per-project face clusters / config / thumbnails in `<project_root>/04_workspace/face_privacy/`.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
FACE_MODEL_DIR = REPO_ROOT / "03_voice_clone" / "model" / "opencv_face"
MEDIA_VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")

YUNET_MODEL_NAME = "face_detection_yunet_2023mar.onnx"
SFACE_MODEL_NAME = "face_recognition_sface_2021dec.onnx"

YUNET_URLS = [
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
]
SFACE_URLS = [
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
]

FACE_EMOJI_CATALOG: dict[str, str] = {
    "cool": "1f60e.webp",
    "disguise": "1f978.webp",
    "laugh": "1f602.webp",
    "giggle": "1f92d.webp",
    "hearts": "1f970.webp",
    "cat": "1f638.webp",
    "robot": "1f916.webp",
}

DEFAULT_FACE_PRIVACY_CONFIG: dict[str, Any] = {
    "enabled": False,
    "mode": "blur_selected",  # "blur_selected" | "keep_selected"
    "style": "gaussian",      # "gaussian" | "pixelate" | "emoji"
    "icon": "cool",           # key in FACE_EMOJI_CATALOG or "random_person"
    "padding": 1.25,
    "selected_face_ids": [],
}

_CV2_MOD: Any = None
_CV2_LOCK = threading.Lock()
_MODEL_LOCK = threading.Lock()
_HW_ENC_CACHE: tuple[str, list[str]] | None = None
_EMOJI_BGRA_CACHE: np.ndarray | None = None
_EMOJI_ICON_CACHE: dict[str, np.ndarray] = {}


def _ensure_cv2() -> Any:
    global _CV2_MOD
    if _CV2_MOD is not None:
        return _CV2_MOD
    with _CV2_LOCK:
        if _CV2_MOD is not None:
            return _CV2_MOD
        try:
            import cv2  # type: ignore
            _CV2_MOD = cv2
            return _CV2_MOD
        except ImportError:
            print("[FacePrivacy] Đang tự động cài đặt opencv-contrib-python...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "opencv-contrib-python"],
                check=False,
            )
            importlib.invalidate_caches()
            import cv2  # type: ignore
            _CV2_MOD = cv2
            return _CV2_MOD


def _download_file(urls: list[str], dest: Path, min_bytes: int = 50_000) -> bool:
    if dest.exists() and dest.stat().st_size >= min_bytes:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    for url in urls:
        try:
            try:
                import requests
                with requests.get(url, stream=True, timeout=60, allow_redirects=True) as resp:
                    if resp.status_code != 200:
                        continue
                    with tmp.open("wb") as f:
                        for chunk in resp.iter_content(chunk_size=131072):
                            if chunk:
                                f.write(chunk)
            except ImportError:
                import urllib.request
                with urllib.request.urlopen(url, timeout=60) as resp:
                    tmp.write_bytes(resp.read())
            if tmp.exists() and tmp.stat().st_size >= min_bytes:
                os.replace(tmp, dest)
                return True
        except Exception:
            pass
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
    return dest.exists() and dest.stat().st_size >= min_bytes


def _ensure_face_models() -> tuple[Path | None, Path | None]:
    with _MODEL_LOCK:
        yunet_p = FACE_MODEL_DIR / YUNET_MODEL_NAME
        sface_p = FACE_MODEL_DIR / SFACE_MODEL_NAME
        ok_yn = _download_file(YUNET_URLS, yunet_p, min_bytes=50_000)
        ok_sf = _download_file(SFACE_URLS, sface_p, min_bytes=1_000_000)
        return (yunet_p if ok_yn else None, sface_p if ok_sf else None)


def _l2_norm(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm <= 1e-8:
        return vec
    return (vec / norm).astype(np.float32)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


class _FaceEngine:
    """Wrapper over OpenCV YuNet+SFace with offline Haar+HSV/HOG fallback."""

    def __init__(self) -> None:
        self.cv2 = _ensure_cv2()
        yunet_p, sface_p = _ensure_face_models()
        self.use_onnx = False
        self.detector: Any = None
        self.recognizer: Any = None
        self.haar: Any = None

        if (
            yunet_p is not None
            and sface_p is not None
            and hasattr(self.cv2, "FaceDetectorYN")
            and hasattr(self.cv2, "FaceRecognizerSF")
        ):
            try:
                self.detector = self.cv2.FaceDetectorYN.create(
                    str(yunet_p),
                    "",
                    (320, 320),
                    0.62,
                    0.3,
                    5000,
                )
                self.recognizer = self.cv2.FaceRecognizerSF.create(str(sface_p), "")
                self.use_onnx = True
            except Exception as exc:
                print(f"[FacePrivacy WARN] Không khởi tạo được YuNet/SFace ({exc}), chuyển sang fallback.")
                self.use_onnx = False

        if not self.use_onnx:
            haar_xml = Path(self.cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            self.haar = self.cv2.CascadeClassifier(str(haar_xml))

    def _fallback_embed(self, bgr_img: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
        cv2 = self.cv2
        ih, iw = bgr_img.shape[:2]
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(iw, x + w), min(ih, y + h)
        crop = bgr_img[y1:y2, x1:x2]
        if crop.size == 0:
            return np.zeros((128,), dtype=np.float32)
        small = cv2.resize(crop, (32, 32), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist_h = cv2.calcHist([hsv], [0], None, [32], [0, 180]).flatten()
        hist_s = cv2.calcHist([hsv], [1], None, [32], [0, 256]).flatten()
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        patch = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA).astype(np.float32).flatten()
        vec = np.concatenate([hist_h / (hist_h.sum() + 1e-6), hist_s / (hist_s.sum() + 1e-6), patch / 255.0]).astype(np.float32)
        return _l2_norm(vec)

    def detect_and_embed(
        self,
        bgr_img: np.ndarray,
        score_threshold: float = 0.62,
        min_box_px: int = 20,
    ) -> list[dict[str, Any]]:
        cv2 = self.cv2
        ih, iw = bgr_img.shape[:2]
        results: list[dict[str, Any]] = []

        if self.use_onnx and self.detector is not None and self.recognizer is not None:
            self.detector.setInputSize((iw, ih))
            if hasattr(self.detector, "setScoreThreshold"):
                self.detector.setScoreThreshold(float(score_threshold))
            _, faces = self.detector.detect(bgr_img)
            if faces is None or len(faces) == 0:
                return []
            for row in faces:
                bx, by, bw, bh = float(row[0]), float(row[1]), float(row[2]), float(row[3])
                score = float(row[14]) if len(row) > 14 else 0.75
                if score < score_threshold or bw < min_box_px or bh < min_box_px:
                    continue
                if bx + bw <= 0 or by + bh <= 0 or bx >= iw or by >= ih:
                    continue
                # Frontal symmetry check using eye + nose landmarks
                rx, lx, nx = float(row[4]), float(row[6]), float(row[8])
                eye_span = abs(lx - rx)
                frontal = 0.7
                if eye_span > 4.0:
                    mid_x = 0.5 * (rx + lx)
                    asym = abs(nx - mid_x) / (0.5 * eye_span)
                    frontal = max(0.3, 1.0 - min(0.7, asym * 0.45))
                try:
                    aligned = self.recognizer.alignCrop(bgr_img, row)
                    feat = self.recognizer.feature(aligned).reshape(-1).astype(np.float32)
                    emb = _l2_norm(feat)
                except Exception:
                    emb = self._fallback_embed(bgr_img, int(bx), int(by), int(bw), int(bh))
                area_bonus = min(1.0, (bw * bh) / float(max(1, (min(iw, ih) * 0.28) ** 2)))
                quality = float(score * (0.55 + 0.25 * frontal + 0.20 * area_bonus))
                results.append(
                    {
                        "box": (bx, by, bw, bh),
                        "score": score,
                        "quality": quality,
                        "emb": emb,
                    }
                )
            return results

        if self.haar is not None and not self.haar.empty():
            gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            rects = self.haar.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(min_box_px, min_box_px))
            for (x, y, w, h) in rects:
                emb = self._fallback_embed(bgr_img, int(x), int(y), int(w), int(h))
                quality = 0.7 + 0.3 * min(1.0, (w * h) / float(max(1, (min(iw, ih) * 0.28) ** 2)))
                results.append(
                    {
                        "box": (float(x), float(y), float(w), float(h)),
                        "score": 0.75,
                        "quality": float(quality),
                        "emb": emb,
                    }
                )
        return results


def _privacy_dir(project_root: Path) -> Path:
    return Path(project_root) / "04_workspace" / "face_privacy"


def normalize_face_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    raw = cfg if isinstance(cfg, dict) else {}
    mode = str(raw.get("mode") or "blur_selected").strip()
    if mode not in ("blur_selected", "keep_selected"):
        mode = "blur_selected"
    style = str(raw.get("style") or "gaussian").strip()
    if style not in ("gaussian", "pixelate", "emoji"):
        style = "gaussian"
    icon = str(raw.get("icon") or "cool").strip()
    if icon != "random_person" and icon not in FACE_EMOJI_CATALOG:
        icon = "cool"
    try:
        padding = float(raw.get("padding") or 1.25)
    except (TypeError, ValueError):
        padding = 1.25
    padding = round(max(1.0, min(2.2, padding)), 2)

    raw_ids = raw.get("selected_face_ids")
    if not isinstance(raw_ids, list):
        raw_ids = []
    seen: set[str] = set()
    sel_ids: list[str] = []
    for x in raw_ids:
        sx = str(x or "").strip()
        if sx and sx not in seen:
            seen.add(sx)
            sel_ids.append(sx)

    return {
        "enabled": bool(raw.get("enabled", False)),
        "mode": mode,
        "style": style,
        "icon": icon,
        "padding": padding,
        "selected_face_ids": sel_ids,
    }


def _strip_embeddings_for_ui(faces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in faces:
        if not isinstance(f, dict):
            continue
        out.append(
            {
                "id": str(f.get("id") or ""),
                "label": str(f.get("label") or ""),
                "appearances": int(f.get("appearances") or 0),
                "clip_count": int(f.get("clip_count") or 0),
                "clip_names": list(f.get("clip_names") or []),
                "thumb_name": str(f.get("thumb_name") or ""),
                "score": float(f.get("score") or 0.0),
            }
        )
    return out


def load_face_privacy_state(project_root: Path) -> dict[str, Any]:
    p_dir = _privacy_dir(project_root)
    json_p = p_dir / "faces.json"
    if not json_p.exists():
        return {
            "updated_at": 0,
            "clip_signature": [],
            "faces": [],
            "config": dict(DEFAULT_FACE_PRIVACY_CONFIG),
        }
    try:
        data = json.loads(json_p.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("Invalid faces.json")
    except Exception:
        return {
            "updated_at": 0,
            "clip_signature": [],
            "faces": [],
            "config": dict(DEFAULT_FACE_PRIVACY_CONFIG),
        }
    return {
        "updated_at": int(data.get("updated_at") or 0),
        "clip_signature": data.get("clip_signature") if isinstance(data.get("clip_signature"), list) else [],
        "faces": data.get("faces") if isinstance(data.get("faces"), list) else [],
        "config": normalize_face_config(data.get("config")),
    }


def _write_faces_json(project_root: Path, state_data: dict[str, Any]) -> None:
    p_dir = _privacy_dir(project_root)
    p_dir.mkdir(parents=True, exist_ok=True)
    json_p = p_dir / "faces.json"
    tmp_p = p_dir / "faces.tmp.json"
    tmp_p.write_text(json.dumps(state_data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_p, json_p)


def save_face_privacy_config(project_root: Path, cfg_patch: dict[str, Any]) -> dict[str, Any]:
    cur = load_face_privacy_state(project_root)
    merged_cfg = normalize_face_config({**(cur.get("config") or {}), **(cfg_patch or {})})
    cur["config"] = merged_cfg
    _write_faces_json(project_root, cur)
    return {
        "updated_at": cur["updated_at"],
        "clip_signature": cur["clip_signature"],
        "faces": _strip_embeddings_for_ui(cur["faces"]),
        "config": merged_cfg,
    }


def _collect_raw_videos(project_root: Path) -> list[Path]:
    raw_dir = Path(project_root) / "02_video_tho"
    if not raw_dir.exists():
        return []
    files = [
        p
        for p in raw_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in MEDIA_VIDEO_EXTS
    ]
    files.sort(key=lambda p: p.relative_to(raw_dir).as_posix().lower())
    return files


def _build_clip_signature(videos: list[Path], raw_dir: Path) -> list[dict[str, Any]]:
    sig: list[dict[str, Any]] = []
    for p in videos:
        try:
            st = p.stat()
            sig.append(
                {
                    "name": p.relative_to(raw_dir).as_posix(),
                    "size": int(st.st_size),
                    "mtime": int(st.st_mtime),
                }
            )
        except OSError:
            pass
    return sig


def _crop_face_avatar(cv2: Any, orig_frame: np.ndarray, box_orig: tuple[float, float, float, float]) -> np.ndarray | None:
    oh, ow = orig_frame.shape[:2]
    bx, by, bw, bh = box_orig
    cx = bx + bw * 0.5
    cy = by + bh * 0.48
    side = max(bw, bh) * 1.68  # ~35% extra margin around head/hair
    x1 = max(0, int(round(cx - side * 0.5)))
    y1 = max(0, int(round(cy - side * 0.5)))
    x2 = min(ow, int(round(cx + side * 0.5)))
    y2 = min(oh, int(round(cy + side * 0.5)))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    crop = orig_frame[y1:y2, x1:x2]
    ch, cw = crop.shape[:2]
    if abs(ch - cw) > 2:
        sq = max(ch, cw)
        canvas = np.zeros((sq, sq, 3), dtype=np.uint8)
        yo = (sq - ch) // 2
        xo = (sq - cw) // 2
        canvas[yo : yo + ch, xo : xo + cw] = crop
        crop = canvas
    return cv2.resize(crop, (160, 160), interpolation=cv2.INTER_AREA if max(ch, cw) > 160 else cv2.INTER_CUBIC)


def _sample_video_frames(cv2: Any, video_path: Path, max_samples: int = 10) -> list[tuple[int, np.ndarray]]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []
    frames: list[tuple[int, np.ndarray]] = []
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        if fps < 1.0 or fps > 120.0:
            fps = 30.0
        if total > 0:
            dur = total / fps
            want = min(max_samples, max(2, int(round(dur / 1.1)) + 1)) if dur > 1.5 else min(4, total)
            if total <= want:
                indices = list(range(total))
            else:
                lo = min(total - 1, max(0, int(total * 0.03)))
                hi = max(lo, int(total * 0.96))
                indices = sorted(set(int(round(x)) for x in np.linspace(lo, hi, num=want)))
            idx_set = set(indices)
            max_idx = indices[-1]
            # Sequential grab/retrieve avoids slow H264 random keyframe seeks when short
            for fi in range(max_idx + 1):
                if fi in idx_set:
                    ok, fr = cap.read()
                    if not ok or fr is None:
                        break
                    frames.append((fi, fr))
                else:
                    if not cap.grab():
                        break
        else:
            step = max(1, int(round(fps * 1.2)))
            fi = 0
            while len(frames) < max_samples:
                if fi % step == 0:
                    ok, fr = cap.read()
                    if not ok or fr is None:
                        break
                    frames.append((fi, fr))
                else:
                    if not cap.grab():
                        break
                fi += 1
    finally:
        cap.release()
    return frames


def scan_project_faces(
    project_root: Path,
    force: bool = False,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Scan raw clips in `02_video_tho/`, cluster unique faces, and save thumbnails + `faces.json`."""
    def _report(done: int, total: int, clip_name: str = "") -> None:
        if progress_cb is not None:
            try:
                progress_cb(int(done), int(total), str(clip_name or ""))
            except Exception:
                pass

    project_root = Path(project_root)
    raw_dir = project_root / "02_video_tho"
    p_dir = _privacy_dir(project_root)
    thumbs_dir = p_dir / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    videos = _collect_raw_videos(project_root)
    clip_sig = _build_clip_signature(videos, raw_dir)
    prev_state = load_face_privacy_state(project_root)
    prev_cfg = normalize_face_config(prev_state.get("config"))

    if not force and prev_state.get("clip_signature") == clip_sig and prev_state.get("updated_at"):
        faces_prev = prev_state.get("faces") or []
        thumbs_ok = all(
            (thumbs_dir / str(f.get("thumb_name") or "")).exists()
            for f in faces_prev
            if f.get("thumb_name")
        )
        if thumbs_ok:
            _report(len(videos), len(videos), "")
            return {
                "ok": True,
                "cached": True,
                "updated_at": prev_state["updated_at"],
                "clip_count": len(videos),
                "faces": _strip_embeddings_for_ui(faces_prev),
                "config": prev_cfg,
            }

    if not videos:
        for old_img in thumbs_dir.glob("*.jpg"):
            old_img.unlink(missing_ok=True)
        if prev_state.get("clip_signature") != clip_sig:
            prev_cfg["selected_face_ids"] = []
        state_data = {
            "updated_at": int(time.time()),
            "clip_signature": clip_sig,
            "faces": [],
            "config": prev_cfg,
        }
        _write_faces_json(project_root, state_data)
        _report(0, 0, "")
        return {
            "ok": True,
            "cached": False,
            "updated_at": state_data["updated_at"],
            "clip_count": 0,
            "faces": [],
            "config": prev_cfg,
        }

    _report(0, len(videos), "")
    engine = _FaceEngine()
    cv2 = engine.cv2
    sim_threshold = 0.35 if engine.use_onnx else 0.78

    clusters: list[dict[str, Any]] = []

    for idx, vp in enumerate(videos, start=1):
        rel_name = vp.relative_to(raw_dir).as_posix()
        _report(idx - 1, len(videos), rel_name)
        sampled = _sample_video_frames(cv2, vp, max_samples=10)
        for fi, orig_frame in sampled:
            oh, ow = orig_frame.shape[:2]
            if oh <= 0 or ow <= 0:
                continue
            scale = min(1.0, 640.0 / float(max(oh, ow)))
            scan_frame = (
                cv2.resize(orig_frame, (max(1, int(round(ow * scale))), max(1, int(round(oh * scale)))), interpolation=cv2.INTER_AREA)
                if scale < 1.0
                else orig_frame
            )
            dets = engine.detect_and_embed(scan_frame, score_threshold=0.62, min_box_px=24)
            if not dets:
                continue

            # Assign each face in this frame without collapsing 2 people in the same frame into 1 cluster
            used_cidx: set[int] = set()
            # Match strongest/highest quality detections first
            dets_sorted = sorted(dets, key=lambda d: d["quality"], reverse=True)
            for det in dets_sorted:
                emb: np.ndarray = det["emb"]
                best_ci = -1
                best_sim = -1.0
                for ci, cl in enumerate(clusters):
                    if ci in used_cidx:
                        continue
                    sim = _cosine_sim(emb, cl["emb"])
                    if sim > best_sim:
                        best_sim = sim
                        best_ci = ci

                bx, by, bw, bh = det["box"]
                orig_box = (bx / scale, by / scale, bw / scale, bh / scale)
                q = float(det["quality"])
                f_key = (rel_name, fi)

                if best_ci >= 0 and best_sim >= sim_threshold:
                    used_cidx.add(best_ci)
                    cl = clusters[best_ci]
                    cl["count"] += 1
                    cl["clips"].add(rel_name)
                    cl["frame_keys"].add(f_key)
                    cl["emb_sum"] = cl["emb_sum"] + emb
                    cl["emb"] = _l2_norm(cl["emb_sum"])
                    cl["best_score"] = max(cl["best_score"], float(det["score"]))
                    if q > cl["best_quality"] or cl["avatar"] is None:
                        av = _crop_face_avatar(cv2, orig_frame, orig_box)
                        if av is not None:
                            cl["best_quality"] = q
                            cl["avatar"] = av
                else:
                    av = _crop_face_avatar(cv2, orig_frame, orig_box)
                    if av is None:
                        continue
                    new_idx = len(clusters)
                    used_cidx.add(new_idx)
                    clusters.append(
                        {
                            "emb_sum": emb.copy(),
                            "emb": emb.copy(),
                            "count": 1,
                            "clips": {rel_name},
                            "frame_keys": {f_key},
                            "best_score": float(det["score"]),
                            "best_quality": q,
                            "avatar": av,
                        }
                    )
        _report(idx, len(videos), rel_name)

    # Conservative post-merge across poses if embeddings converged and they never co-occur in the same frame
    merge_thresh = 0.42 if engine.use_onnx else 0.85
    merged = True
    while merged and len(clusters) > 1:
        merged = False
        best_pair: tuple[int, int, float] | None = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                if clusters[i]["frame_keys"] & clusters[j]["frame_keys"]:
                    continue
                sim = _cosine_sim(clusters[i]["emb"], clusters[j]["emb"])
                if sim >= merge_thresh and (best_pair is None or sim > best_pair[2]):
                    best_pair = (i, j, sim)
        if best_pair is not None:
            i, j, _ = best_pair
            ci, cj = clusters[i], clusters[j]
            ci["count"] += cj["count"]
            ci["clips"] |= cj["clips"]
            ci["frame_keys"] |= cj["frame_keys"]
            ci["emb_sum"] = ci["emb_sum"] + cj["emb_sum"]
            ci["emb"] = _l2_norm(ci["emb_sum"])
            ci["best_score"] = max(ci["best_score"], cj["best_score"])
            if cj["best_quality"] > ci["best_quality"] and cj["avatar"] is not None:
                ci["best_quality"] = cj["best_quality"]
                ci["avatar"] = cj["avatar"]
            clusters.pop(j)
            merged = True

    clusters.sort(
        key=lambda c: (len(c["clips"]), c["count"], c["best_quality"]),
        reverse=True,
    )

    for old_img in thumbs_dir.glob("*.jpg"):
        old_img.unlink(missing_ok=True)

    faces_out: list[dict[str, Any]] = []
    valid_new_ids: set[str] = set()
    for idx, cl in enumerate(clusters, start=1):
        fid = f"face_{idx:02d}"
        thumb_name = f"{fid}.jpg"
        av = cl.get("avatar")
        if av is not None:
            ok_enc, buf = cv2.imencode(".jpg", av, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            if ok_enc:
                (thumbs_dir / thumb_name).write_bytes(buf.tobytes())
        valid_new_ids.add(fid)
        faces_out.append(
            {
                "id": fid,
                "label": f"Người #{idx}",
                "appearances": int(cl["count"]),
                "clip_count": len(cl["clips"]),
                "clip_names": sorted(cl["clips"]),
                "thumb_name": thumb_name,
                "score": round(float(cl["best_score"]), 3),
                "embedding": [round(float(v), 6) for v in cl["emb"].tolist()],
            }
        )

    # Re-read latest config so concurrent UI edits during background scan aren't overwritten
    latest_cfg = normalize_face_config(load_face_privacy_state(project_root).get("config"))
    if prev_state.get("clip_signature") != clip_sig:
        latest_cfg["selected_face_ids"] = []
    else:
        latest_cfg["selected_face_ids"] = [x for x in latest_cfg["selected_face_ids"] if x in valid_new_ids]

    state_data = {
        "updated_at": int(time.time()),
        "clip_signature": clip_sig,
        "faces": faces_out,
        "config": latest_cfg,
    }
    _write_faces_json(project_root, state_data)
    return {
        "ok": True,
        "cached": False,
        "updated_at": state_data["updated_at"],
        "clip_count": len(videos),
        "faces": _strip_embeddings_for_ui(faces_out),
        "config": latest_cfg,
    }


def _detect_h264_encoder_fast(ffmpeg_bin: str, width: int) -> tuple[str, list[str]]:
    global _HW_ENC_CACHE
    if _HW_ENC_CACHE is not None:
        enc, base_args = _HW_ENC_CACHE
    else:
        enc, base_args = ("libx264", ["-preset", "fast", "-crf", "14"])
        try:
            probe = subprocess.run(
                [
                    ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                    "-c:v", "h264_nvenc", "-f", "null", "-",
                ],
                capture_output=True,
                timeout=10,
            )
            if probe.returncode == 0:
                enc = "h264_nvenc"
                base_args = ["-preset", "p5", "-rc", "vbr", "-cq", "13"]
        except Exception:
            pass
        _HW_ENC_CACHE = (enc, base_args)

    if width >= 3000:
        b_target, b_max, b_buf = ("42M", "65M", "80M")
    elif width >= 2200:
        b_target, b_max, b_buf = ("26M", "38M", "48M")
    else:
        b_target, b_max, b_buf = ("16M", "24M", "30M")
    return enc, [*base_args, "-b:v", b_target, "-maxrate", b_max, "-bufsize", b_buf]


def _get_sunglasses_emoji_bgra(cv2: Any) -> np.ndarray:
    """Create a crisp 256x256 vector-style cool sunglasses emoji BGRA sticker."""
    global _EMOJI_BGRA_CACHE
    if _EMOJI_BGRA_CACHE is not None:
        return _EMOJI_BGRA_CACHE

    sz = 256
    img = np.zeros((sz, sz, 4), dtype=np.uint8)
    cx, cy, r = sz // 2, sz // 2, 112

    # Radial gradient yellow circle
    yy, xx = np.mgrid[0:sz, 0:sz]
    dx = xx - cx
    dy = yy - cy
    dist = np.sqrt(dx * dx + dy * dy)
    inside = dist <= r
    t = np.clip(dist / float(r), 0.0, 1.0)
    # Center bright warm yellow -> edge amber gold (BGR)
    b = (70 * (1.0 - t) + 12 * t).astype(np.uint8)
    g = (228 * (1.0 - t) + 168 * t).astype(np.uint8)
    red = (254 * (1.0 - t) + 245 * t).astype(np.uint8)
    img[inside, 0] = b[inside]
    img[inside, 1] = g[inside]
    img[inside, 2] = red[inside]
    alpha = np.clip((r - dist + 1.5) * 180.0, 0.0, 255.0).astype(np.uint8)
    img[:, :, 3] = alpha

    # Subtle top shine
    cv2.ellipse(img, (cx - 24, cy - 62), (46, 20), -18, 0, 360, (205, 250, 255, 110), -1, cv2.LINE_AA)
    # Outer rim
    cv2.circle(img, (cx, cy), r - 1, (8, 128, 210, 255), 4, cv2.LINE_AA)

    # Dark stylish sunglasses bridge + temples + lenses (BGR + A)
    dark = (28, 22, 15, 255)
    cv2.line(img, (cx - 98, cy - 18), (cx + 98, cy - 18), dark, 12, cv2.LINE_AA)
    cv2.line(img, (cx - 20, cy - 12), (cx + 20, cy - 12), dark, 10, cv2.LINE_AA)

    for sign in (-1, 1):
        lx = cx + sign * 48
        ly = cy - 6
        pts = np.array(
            [
                [lx - 40, ly - 18],
                [lx + 40, ly - 18],
                [lx + 36, ly + 14],
                [lx + 20, ly + 26],
                [lx - 20, ly + 26],
                [lx - 36, ly + 14],
            ],
            dtype=np.int32,
        )
        cv2.fillPoly(img, [pts], (24, 18, 12, 255), cv2.LINE_AA)
        cv2.polylines(img, [pts], True, (52, 42, 30, 255), 3, cv2.LINE_AA)
        # Diagonal glossy lens glare
        cv2.line(img, (lx - 22, ly - 10), (lx - 6, ly + 12), (245, 245, 245, 150), 5, cv2.LINE_AA)
        cv2.line(img, (lx - 8, ly - 10), (lx + 2, ly + 4), (245, 245, 245, 110), 3, cv2.LINE_AA)

    # Confident smirk smile
    cv2.ellipse(img, (cx + 4, cy + 32), (46, 28), 0, 18, 150, (35, 38, 92, 255), 8, cv2.LINE_AA)

    _EMOJI_BGRA_CACHE = img
    return img


def _get_emoji_icon_bgra(cv2: Any, icon_id: str) -> np.ndarray:
    """Load high-res 512x512 Noto emoji .webp with alpha from assets/animated_stickers, cached thread-safely."""
    clean_id = icon_id if icon_id in FACE_EMOJI_CATALOG else "cool"
    cached = _EMOJI_ICON_CACHE.get(clean_id)
    if cached is not None:
        return cached
    with _MODEL_LOCK:
        cached = _EMOJI_ICON_CACHE.get(clean_id)
        if cached is not None:
            return cached
        fname = FACE_EMOJI_CATALOG.get(clean_id, "1f60e.webp")
        icon_path = REPO_ROOT / "assets" / "animated_stickers" / fname
        if icon_path.exists():
            try:
                raw_bytes = np.fromfile(str(icon_path), dtype=np.uint8)
                decoded = cv2.imdecode(raw_bytes, cv2.IMREAD_UNCHANGED)
                if decoded is not None and decoded.ndim == 3:
                    if decoded.shape[2] == 3:
                        alpha_ch = np.full((decoded.shape[0], decoded.shape[1], 1), 255, dtype=np.uint8)
                        decoded = np.concatenate([decoded, alpha_ch], axis=2)
                    if decoded.shape[2] == 4:
                        _EMOJI_ICON_CACHE[clean_id] = decoded
                        return decoded
            except Exception:
                pass
        fallback = _get_sunglasses_emoji_bgra(cv2)
        _EMOJI_ICON_CACHE[clean_id] = fallback
        return fallback


def _apply_roi_mask(
    cv2: Any,
    frame: np.ndarray,
    boxes: list[tuple[Any, ...]],
    style: str,
) -> None:
    fh, fw = frame.shape[:2]

    for box in boxes:
        if len(box) >= 5:
            x1, y1, x2, y2, icon_id = int(box[0]), int(box[1]), int(box[2]), int(box[3]), str(box[4] or "cool")
        else:
            x1, y1, x2, y2, icon_id = int(box[0]), int(box[1]), int(box[2]), int(box[3]), "cool"
        x1c = max(0, min(fw - 1, x1))
        y1c = max(0, min(fh - 1, y1))
        x2c = max(0, min(fw, x2))
        y2c = max(0, min(fh, y2))
        rw = x2c - x1c
        rh = y2c - y1c
        if rw < 6 or rh < 6:
            continue

        if style == "emoji":
            emoji_src = _get_emoji_icon_bgra(cv2, icon_id)
            cx = (x1 + x2) * 0.5
            cy = (y1 + y2) * 0.5
            d = max(12, int(round(max(x2 - x1, y2 - y1) * 1.04)))
            ex1 = int(round(cx - d * 0.5))
            ey1 = int(round(cy - d * 0.5))
            ex2 = ex1 + d
            ey2 = ey1 + d
            fx1 = max(0, ex1)
            fy1 = max(0, ey1)
            fx2 = min(fw, ex2)
            fy2 = min(fh, ey2)
            if fx2 - fx1 < 4 or fy2 - fy1 < 4:
                continue
            resized = cv2.resize(
                emoji_src,
                (d, d),
                interpolation=cv2.INTER_AREA if d < emoji_src.shape[0] else cv2.INTER_LINEAR,
            )
            sx1 = fx1 - ex1
            sy1 = fy1 - ey1
            sx2 = sx1 + (fx2 - fx1)
            sy2 = sy1 + (fy2 - fy1)
            crop_e = resized[sy1:sy2, sx1:sx2]
            alpha = (crop_e[:, :, 3:4].astype(np.float32)) / 255.0
            roi = frame[fy1:fy2, fx1:fx2].astype(np.float32)
            blended = crop_e[:, :, :3].astype(np.float32) * alpha + roi * (1.0 - alpha)
            frame[fy1:fy2, fx1:fx2] = np.clip(blended, 0, 255).astype(np.uint8)
            continue

        roi = frame[y1c:y2c, x1c:x2c]
        if style == "pixelate":
            pw = max(6, min(14, rw // 12))
            ph = max(6, min(14, rh // 12))
            small = cv2.resize(roi, (pw, ph), interpolation=cv2.INTER_LINEAR)
            effect = cv2.resize(small, (rw, rh), interpolation=cv2.INTER_NEAREST)
            feather_k = max(3, (min(rw, rh) // 10) | 1)
        else:
            # Ultra-fast strong Gaussian blur: downscale -> blur -> upscale
            sw = max(10, min(36, rw // 9))
            sh = max(10, min(36, rh // 9))
            small = cv2.resize(roi, (sw, sh), interpolation=cv2.INTER_AREA)
            small = cv2.GaussianBlur(small, (11, 11), 0)
            effect = cv2.resize(small, (rw, rh), interpolation=cv2.INTER_LINEAR)
            feather_k = max(7, (min(rw, rh) // 4) | 1)

        mask = np.zeros((rh, rw), dtype=np.float32)
        ax_x = max(2, int(round(rw * 0.43)))
        ax_y = max(2, int(round(rh * 0.45)))
        cv2.ellipse(mask, (rw // 2, rh // 2), (ax_x, ax_y), 0, 0, 360, 1.0, -1)
        mask = cv2.GaussianBlur(mask, (feather_k, feather_k), 0)
        mask_3 = mask[:, :, None]
        blended = effect.astype(np.float32) * mask_3 + roi.astype(np.float32) * (1.0 - mask_3)
        frame[y1c:y2c, x1c:x2c] = np.clip(blended, 0, 255).astype(np.uint8)


def _match_cluster_id(
    emb: np.ndarray,
    cluster_items: list[tuple[str, np.ndarray]],
    match_thresh: float,
) -> tuple[str | None, float]:
    best_id: str | None = None
    best_sim = -1.0
    for cid, cemb in cluster_items:
        sim = _cosine_sim(emb, cemb)
        if sim > best_sim:
            best_sim = sim
            best_id = cid
    if best_sim >= match_thresh:
        return best_id, best_sim
    return None, best_sim


def _build_masked_frame_boxes(
    keyframes: list[tuple[int, list[dict[str, Any]]]],
    *,
    mode: str,
    selected_ids: set[str],
    padding: float,
    orig_w: int,
    orig_h: int,
    fps: float,
    total_frames: int,
    onnx_mode: bool,
    icon_mode: str = "cool",
) -> dict[int, list[tuple[int, int, int, int, str]]]:
    """Link detections into smooth spatial tracks, classify target identities, and interpolate per frame."""
    if not keyframes:
        return {}

    sim_thresh = 0.33 if onnx_mode else 0.74
    strong_thresh = 0.36 if onnx_mode else 0.80
    max_gap_frames = max(8, int(round(fps * 0.50)))
    pad_edge_frames = max(2, int(round(fps * 0.20)))

    # 1. Link detections across keyframes into spatial tracks
    # Each track node: {"frame": f_idx, "cx": cx, "cy": cy, "w": bw, "h": bh, "best_id": str|None, "best_sim": float}
    spatial_tracks: list[list[dict[str, Any]]] = []
    for f_idx, dets in keyframes:
        unmatched_tracks = set(range(len(spatial_tracks)))
        # Match nearest active track from recent frames
        candidates: list[tuple[float, int, int]] = []
        for di, d in enumerate(dets):
            dcx, dcy, dw, dh = d["cx"], d["cy"], d["w"], d["h"]
            diag = max(20.0, (dw + dh) * 0.5)
            for ti in unmatched_tracks:
                last = spatial_tracks[ti][-1]
                f_gap = f_idx - last["frame"]
                if f_gap <= 0 or f_gap > max_gap_frames:
                    continue
                dist = float(np.hypot(dcx - last["cx"], dcy - last["cy"]))
                ref_size = max(diag, (last["w"] + last["h"]) * 0.5)
                allowed_dist = ref_size * (1.25 + 0.15 * (f_gap / max(1.0, fps * 0.15)))
                if dist <= allowed_dist:
                    candidates.append((dist / ref_size, di, ti))
        candidates.sort(key=lambda x: x[0])

        matched_dets: set[int] = set()
        matched_trks: set[int] = set()
        for _, di, ti in candidates:
            if di in matched_dets or ti in matched_trks:
                continue
            matched_dets.add(di)
            matched_trks.add(ti)
            d = dets[di]
            spatial_tracks[ti].append({"frame": f_idx, **d})

        for di, d in enumerate(dets):
            if di not in matched_dets:
                spatial_tracks.append([{"frame": f_idx, **d}])

    # 2. Classify each track observation (inheriting identity cleanly across brief head turns)
    target_segments: list[list[dict[str, Any]]] = []
    id_hold_frames = max(6, int(round(fps * 0.65)))

    for trk in spatial_tracks:
        cur_seg: list[dict[str, Any]] = []
        for i, node in enumerate(trk):
            cid = node["best_id"] if (node["best_id"] is not None and node["best_sim"] >= sim_thresh) else None
            if cid is None:
                # Look at nearest strong identification along this continuous spatial track
                best_neighbor_dist = id_hold_frames + 1
                for j, other in enumerate(trk):
                    if other["best_id"] is not None and other["best_sim"] >= strong_thresh:
                        fdist = abs(other["frame"] - node["frame"])
                        if fdist < best_neighbor_dist:
                            best_neighbor_dist = fdist
                            cid = other["best_id"]

            if mode == "blur_selected":
                should_mask = bool(cid is not None and cid in selected_ids)
            else:
                if not selected_ids:
                    should_mask = True
                else:
                    should_mask = not (cid is not None and cid in selected_ids)

            if should_mask:
                cur_seg.append({**node, "resolved_cid": cid})
            else:
                if cur_seg:
                    target_segments.append(cur_seg)
                    cur_seg = []
        if cur_seg:
            target_segments.append(cur_seg)

    if not target_segments:
        return {}

    # 3. Interpolate frame-by-frame boxes + add temporal & spatial padding
    frame_boxes: dict[int, list[tuple[int, int, int, int, str]]] = {}
    icon_keys = list(FACE_EMOJI_CATALOG.keys())

    def _pick_seg_icon(seg: list[dict[str, Any]], seg_idx: int) -> str:
        if icon_mode != "random_person":
            return icon_mode if icon_mode in FACE_EMOJI_CATALOG else "cool"
        counts: dict[str, int] = {}
        for item in seg:
            c = item.get("resolved_cid")
            if c:
                counts[str(c)] = counts.get(str(c), 0) + 1
        if counts:
            dom = max(counts.items(), key=lambda kv: kv[1])[0]
            digits = "".join(ch for ch in dom if ch.isdigit())
            idx_pick = (int(digits) - 1) if digits else sum(ord(ch) for ch in dom)
            return icon_keys[idx_pick % len(icon_keys)]
        return icon_keys[seg_idx % len(icon_keys)]

    def _add_box(fi: int, cx: float, cy: float, bw: float, bh: float, icon_id: str) -> None:
        ew = bw * padding
        eh = bh * padding * 1.06
        x1 = max(0, int(round(cx - ew * 0.5)))
        y1 = max(0, int(round(cy - eh * 0.48)))
        x2 = min(orig_w, int(round(cx + ew * 0.5)))
        y2 = min(orig_h, int(round(cy + eh * 0.52)))
        if x2 - x1 >= 4 and y2 - y1 >= 4:
            frame_boxes.setdefault(fi, []).append((x1, y1, x2, y2, icon_id))

    max_frame_idx = max(0, total_frames - 1) if total_frames > 0 else 10**7

    for seg_idx, seg in enumerate(target_segments):
        seg_icon = _pick_seg_icon(seg, seg_idx)
        first = seg[0]
        f0 = int(first["frame"])
        for fi in range(max(0, f0 - pad_edge_frames), f0):
            _add_box(fi, first["cx"], first["cy"], first["w"], first["h"], seg_icon)

        for k in range(len(seg) - 1):
            a = seg[k]
            b = seg[k + 1]
            fa = int(a["frame"])
            fb = int(b["frame"])
            span = max(1, fb - fa)
            for fi in range(fa, fb):
                alpha = (fi - fa) / float(span)
                _add_box(
                    fi,
                    a["cx"] * (1.0 - alpha) + b["cx"] * alpha,
                    a["cy"] * (1.0 - alpha) + b["cy"] * alpha,
                    a["w"] * (1.0 - alpha) + b["w"] * alpha,
                    a["h"] * (1.0 - alpha) + b["h"] * alpha,
                    seg_icon,
                )

        last = seg[-1]
        fl = int(last["frame"])
        _add_box(fl, last["cx"], last["cy"], last["w"], last["h"], seg_icon)
        for fi in range(fl + 1, min(max_frame_idx + 1, fl + 1 + pad_edge_frames)):
            _add_box(fi, last["cx"], last["cy"], last["w"], last["h"], seg_icon)

    return frame_boxes


def apply_face_privacy_to_clip(
    clip_path: Path,
    project_root: Path,
    override_cfg: dict[str, Any] | None = None,
    ffmpeg_bin: str = "ffmpeg",
) -> bool:
    """
    Detect, track & mask selected (or bystander) faces inside `clip_path` in-place.
    Returns True if masking was applied, False if skipped (disabled or no target faces found).
    """
    clip_path = Path(clip_path)
    if not clip_path.exists() or not clip_path.is_file():
        return False

    state = load_face_privacy_state(project_root)
    merged_raw = {**(state.get("config") or {})}
    if isinstance(override_cfg, dict):
        if "face_blur_enabled" in override_cfg:
            merged_raw["enabled"] = override_cfg["face_blur_enabled"]
        if "face_blur_mode" in override_cfg:
            merged_raw["mode"] = override_cfg["face_blur_mode"]
        if "face_blur_style" in override_cfg:
            merged_raw["style"] = override_cfg["face_blur_style"]
        if "face_blur_icon" in override_cfg:
            merged_raw["icon"] = override_cfg["face_blur_icon"]
        if "face_blur_padding" in override_cfg:
            merged_raw["padding"] = override_cfg["face_blur_padding"]
        if "face_blur_ids" in override_cfg:
            merged_raw["selected_face_ids"] = override_cfg["face_blur_ids"]
        for k in ("enabled", "mode", "style", "icon", "padding", "selected_face_ids"):
            if k in override_cfg:
                merged_raw[k] = override_cfg[k]

    cfg = normalize_face_config(merged_raw)
    if not cfg["enabled"]:
        return False

    mode = cfg["mode"]
    style = cfg["style"]
    padding = float(cfg["padding"])
    selected_ids = set(cfg["selected_face_ids"])

    if mode == "blur_selected" and not selected_ids:
        return False

    cluster_items: list[tuple[str, np.ndarray]] = []
    for f in state.get("faces") or []:
        fid = str(f.get("id") or "").strip()
        emb_list = f.get("embedding")
        if fid and isinstance(emb_list, list) and emb_list:
            vec = _l2_norm(np.array(emb_list, dtype=np.float32))
            cluster_items.append((fid, vec))

    if mode == "blur_selected":
        cluster_ids_present = {cid for cid, _ in cluster_items}
        if not (selected_ids & cluster_ids_present):
            return False

    engine = _FaceEngine()
    cv2 = engine.cv2
    match_thresh = 0.33 if engine.use_onnx else 0.74

    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        return False

    orig_w = 0
    orig_h = 0
    fps = 30.0
    total_frames = 0
    keyframes: list[tuple[int, list[dict[str, Any]]]] = []
    try:
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        if fps < 1.0 or fps > 120.0:
            fps = 30.0
        known_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if orig_w <= 0 or orig_h <= 0:
            return False

        scale = min(1.0, 640.0 / float(max(orig_h, orig_w)))
        sw = max(1, int(round(orig_w * scale)))
        sh = max(1, int(round(orig_h * scale)))
        step = 4
        fi = 0
        while True:
            is_sample = (fi % step == 0) or (known_total > 0 and fi == known_total - 1)
            if not is_sample:
                if not cap.grab():
                    break
                fi += 1
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            scan_frame = cv2.resize(frame, (sw, sh), interpolation=cv2.INTER_AREA) if scale < 1.0 else frame
            dets = engine.detect_and_embed(scan_frame, score_threshold=0.58, min_box_px=18)
            if dets:
                kf_list: list[dict[str, Any]] = []
                for d in dets:
                    bx, by, bw, bh = d["box"]
                    cid, sim = _match_cluster_id(d["emb"], cluster_items, match_thresh) if cluster_items else (None, -1.0)
                    kf_list.append(
                        {
                            "cx": (bx + bw * 0.5) / scale,
                            "cy": (by + bh * 0.5) / scale,
                            "w": bw / scale,
                            "h": bh / scale,
                            "best_id": cid,
                            "best_sim": sim,
                        }
                    )
                keyframes.append((fi, kf_list))
            fi += 1
        total_frames = fi
    finally:
        cap.release()

    if not keyframes or total_frames <= 0:
        return False

    frame_boxes = _build_masked_frame_boxes(
        keyframes,
        mode=mode,
        selected_ids=selected_ids,
        padding=padding,
        orig_w=orig_w,
        orig_h=orig_h,
        fps=fps,
        total_frames=total_frames,
        onnx_mode=engine.use_onnx,
        icon_mode=cfg["icon"],
    )
    if not frame_boxes:
        return False

    # Pass 2: Apply ROI masking and stream to FFmpeg encoder preserving audio & bt709 color profile
    vcodec, vargs = _detect_h264_encoder_fast(ffmpeg_bin, max(orig_w, orig_h))
    tmp_out = clip_path.with_suffix(".fmask.tmp.mp4")
    if tmp_out.exists():
        tmp_out.unlink(missing_ok=True)

    cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{orig_w}x{orig_h}",
        "-r",
        f"{fps:.3f}",
        "-i",
        "-",
        "-i",
        str(clip_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a?",
        "-c:v",
        vcodec,
        *vargs,
        "-pix_fmt",
        "yuv420p",
        "-colorspace",
        "bt709",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-c:a",
        "copy",
        "-shortest",
        "-movflags",
        "+faststart",
        str(tmp_out),
    ]

    cap2 = cv2.VideoCapture(str(clip_path))
    if not cap2.isOpened():
        return False

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    broken_pipe = False
    try:
        fi = 0
        while True:
            ok, frame = cap2.read()
            if not ok or frame is None:
                break
            if frame.shape[0] != orig_h or frame.shape[1] != orig_w:
                frame = cv2.resize(frame, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
            boxes = frame_boxes.get(fi)
            if boxes:
                _apply_roi_mask(cv2, frame, boxes, style)
            if not frame.flags["C_CONTIGUOUS"]:
                frame = np.ascontiguousarray(frame)
            if proc.stdin is not None:
                try:
                    proc.stdin.write(memoryview(frame))
                except BrokenPipeError:
                    broken_pipe = True
                    break
            fi += 1
    finally:
        cap2.release()
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except Exception:
                pass
        stderr_data = b""
        if proc.stderr is not None:
            try:
                stderr_data = proc.stderr.read() or b""
            except Exception:
                pass
        ret = proc.wait(timeout=240)

    if broken_pipe or ret != 0 or not tmp_out.exists() or tmp_out.stat().st_size <= 1024:
        err_msg = stderr_data.decode("utf-8", errors="replace").strip()[-400:]
        if tmp_out.exists():
            tmp_out.unlink(missing_ok=True)
        raise RuntimeError(f"FFmpeg lỗi khi xuất video che mặt ({ret}): {err_msg}")

    os.replace(tmp_out, clip_path)
    return True
