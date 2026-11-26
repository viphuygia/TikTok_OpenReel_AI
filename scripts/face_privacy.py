#!/usr/bin/env python3
"""
OpenCV YuNet + SFace Face Detection, Clustering & Selective Face Masking Engine.

Stores lightweight ONNX models in shared `03_voice_clone/model/opencv_face/`
and per-project face clusters / config / thumbnails in `<project_root>/04_workspace/face_privacy/`.
"""

from __future__ import annotations

import difflib
import importlib
import json
import os
import re
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
PLATE_MODEL_NAME = "license_plate_yolo.onnx"
PLATE_OCR_MODEL_NAME = "cct_xs_v1_global.onnx"

YUNET_URLS = [
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
]
SFACE_URLS = [
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
]
PLATE_URLS = [
    "https://huggingface.co/morsetechlab/yolov11-license-plate-detection/resolve/main/license-plate-finetune-v1n.onnx",
    "https://huggingface.co/joker5914/yolov8n-license-plate/resolve/main/best.onnx",
    "https://huggingface.co/ml-debi/yolov8-license-plate-detection/resolve/main/best.onnx",
]
PLATE_OCR_URLS = [
    "https://github.com/ankandrew/fast-plate-ocr/releases/download/arg-plates/cct_xs_v1_global.onnx",
]
PLATE_OCR_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_"

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
    "hold_sec": 0.65,
    "selected_face_ids": [],
    "plate_blur_enabled": False,
    "plate_blur_mode": "blur_all",   # "blur_all" | "blur_selected" | "keep_selected"
    "plate_blur_style": "pixelate",  # "pixelate" | "gaussian" | "solid"
    "selected_plate_ids": [],
}

_CV2_MOD: Any = None
_CV2_LOCK = threading.Lock()
_MODEL_LOCK = threading.Lock()
_PLATE_ENGINE_LOCK = threading.Lock()
_PLATE_ENGINE_CACHE: "_PlateEngine | None" = None
_PLATE_OCR_LOCK = threading.Lock()
_PLATE_OCR_CACHE: "_PlateOcrEngine | None" = None
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


def _ensure_plate_model() -> Path | None:
    with _MODEL_LOCK:
        plate_p = FACE_MODEL_DIR / PLATE_MODEL_NAME
        ok = _download_file(PLATE_URLS, plate_p, min_bytes=1_000_000)
        return plate_p if ok else None


class _PlateEngine:
    """YOLOv8/YOLO11 ONNX license plate detector running via onnxruntime."""

    def __init__(self, model_path: Path) -> None:
        import onnxruntime as ort  # type: ignore

        self.cv2 = _ensure_cv2()
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
        ih = int(shape[2]) if len(shape) >= 4 and isinstance(shape[2], (int, np.integer)) and int(shape[2]) > 0 else 640
        iw = int(shape[3]) if len(shape) >= 4 and isinstance(shape[3], (int, np.integer)) and int(shape[3]) > 0 else 640
        self.in_h = ih
        self.in_w = iw

    def detect(
        self,
        bgr_img: np.ndarray,
        conf_threshold: float = 0.35,
        nms_threshold: float = 0.45,
    ) -> list[dict[str, float]]:
        cv2 = self.cv2
        oh, ow = bgr_img.shape[:2]
        if oh <= 0 or ow <= 0:
            return []

        ratio = min(float(self.in_w) / float(ow), float(self.in_h) / float(oh))
        nw = max(1, int(round(ow * ratio)))
        nh = max(1, int(round(oh * ratio)))
        pad_x = (self.in_w - nw) // 2
        pad_y = (self.in_h - nh) // 2

        resized = cv2.resize(
            bgr_img,
            (nw, nh),
            interpolation=cv2.INTER_AREA if ratio < 1.0 else cv2.INTER_LINEAR,
        )
        canvas = np.full((self.in_h, self.in_w, 3), 114, dtype=np.uint8)
        canvas[pad_y : pad_y + nh, pad_x : pad_x + nw] = resized

        rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) * (1.0 / 255.0)
        blob = np.transpose(rgb, (2, 0, 1))[None, ...]

        with self._run_lock:
            outputs = self.session.run(None, {self.input_name: blob})
        if not outputs:
            return []

        arr = np.asarray(outputs[0], dtype=np.float32)
        if arr.ndim == 3:
            arr = arr[0]
        if arr.ndim != 2 or arr.shape[0] == 0 or arr.shape[1] < 5:
            return []

        # Standard YOLO raw head (4+C, N) -> transpose to (N, 4+C)
        if arr.shape[0] < arr.shape[1] and arr.shape[0] <= 64:
            arr = arr.T

        # Handle end-to-end NMS exports if shape is (N, 6) and cols [x1, y1, x2, y2, score, cls]
        if arr.shape[1] == 6 and arr.shape[0] <= 300 and np.all(arr[:, 2] >= arr[:, 0]) and np.all(arr[:, 3] >= arr[:, 1]):
            results: list[dict[str, float]] = []
            for row in arr:
                score = float(row[4])
                if score < conf_threshold:
                    continue
                x1, y1, x2, y2 = float(row[0]), float(row[1]), float(row[2]), float(row[3])
                if max(x2, y2) <= 1.5 and self.in_w > 32:
                    x1, x2 = x1 * self.in_w, x2 * self.in_w
                    y1, y2 = y1 * self.in_h, y2 * self.in_h
                ox1 = (x1 - pad_x) / ratio
                oy1 = (y1 - pad_y) / ratio
                ox2 = (x2 - pad_x) / ratio
                oy2 = (y2 - pad_y) / ratio
                bw = ox2 - ox1
                bh = oy2 - oy1
                if bw < 16 or bh < 8 or bw > ow * 0.65 or bh > oh * 0.45:
                    continue
                results.append({"cx": (ox1 + ox2) * 0.5, "cy": (oy1 + oy2) * 0.5, "w": bw, "h": bh, "score": score})
            return results

        scores = arr[:, 4] if arr.shape[1] == 5 else arr[:, 4:].max(axis=1)
        keep = scores >= conf_threshold
        if not np.any(keep):
            return []

        cand = arr[keep]
        cand_scores = scores[keep]
        if float(cand[:, 2:4].max()) <= 1.5 and self.in_w > 32:
            cand = cand.copy()
            cand[:, 0] *= self.in_w
            cand[:, 1] *= self.in_h
            cand[:, 2] *= self.in_w
            cand[:, 3] *= self.in_h

        xywh_boxes: list[list[float]] = []
        valid_scores: list[float] = []
        parsed: list[tuple[float, float, float, float, float]] = []

        for row, sc in zip(cand, cand_scores):
            cx = (float(row[0]) - pad_x) / ratio
            cy = (float(row[1]) - pad_y) / ratio
            bw = float(row[2]) / ratio
            bh = float(row[3]) / ratio
            if bw < 16 or bh < 8 or bw > ow * 0.65 or bh > oh * 0.45:
                continue
            if cx + bw * 0.5 <= 0 or cy + bh * 0.5 <= 0 or cx - bw * 0.5 >= ow or cy - bh * 0.5 >= oh:
                continue
            xywh_boxes.append([cx - bw * 0.5, cy - bh * 0.5, bw, bh])
            valid_scores.append(float(sc))
            parsed.append((cx, cy, bw, bh, float(sc)))

        if not xywh_boxes:
            return []

        idxs = cv2.dnn.NMSBoxes(xywh_boxes, valid_scores, float(conf_threshold), float(nms_threshold))
        if len(idxs) == 0:
            return []

        flat_idxs = np.asarray(idxs).reshape(-1).tolist()
        return [
            {
                "cx": parsed[i][0],
                "cy": parsed[i][1],
                "w": parsed[i][2],
                "h": parsed[i][3],
                "score": parsed[i][4],
            }
            for i in flat_idxs
        ]


def _get_plate_engine() -> _PlateEngine | None:
    global _PLATE_ENGINE_CACHE
    if _PLATE_ENGINE_CACHE is not None:
        return _PLATE_ENGINE_CACHE
    with _PLATE_ENGINE_LOCK:
        if _PLATE_ENGINE_CACHE is not None:
            return _PLATE_ENGINE_CACHE
        model_p = _ensure_plate_model()
        if model_p is None:
            print("[PlatePrivacy WARN] Không tải được model nhận diện biển số ONNX.")
            return None
        try:
            _PLATE_ENGINE_CACHE = _PlateEngine(model_p)
            return _PLATE_ENGINE_CACHE
        except Exception as exc:
            print(f"[PlatePrivacy WARN] Không khởi tạo được ONNXRuntime cho biển số ({exc}).")
            return None


def _ensure_plate_ocr_model() -> Path | None:
    with _MODEL_LOCK:
        ocr_p = FACE_MODEL_DIR / PLATE_OCR_MODEL_NAME
        ok = _download_file(PLATE_OCR_URLS, ocr_p, min_bytes=500_000)
        return ocr_p if ok else None


class _PlateOcrEngine:
    """Lightweight ONNX license plate OCR recognizer (`cct_xs_v1_global.onnx`)."""

    def __init__(self, model_path: Path) -> None:
        import onnxruntime as ort  # type: ignore

        self.cv2 = _ensure_cv2()
        self._run_lock = threading.Lock()
        avail = ort.get_available_providers()
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if "CUDAExecutionProvider" in avail else ["CPUExecutionProvider"]
        try:
            self.session = ort.InferenceSession(str(model_path), providers=providers)
        except Exception:
            self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])

        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.input_type = str(inp.type or "")
        shape = inp.shape
        # Check NHWC (B, 64, 128, 3) vs NCHW (B, 3, 64, 128)
        self.nchw = bool(len(shape) == 4 and shape[1] in (1, 3))
        if self.nchw:
            self.in_h = int(shape[2]) if isinstance(shape[2], (int, np.integer)) and int(shape[2]) > 0 else 64
            self.in_w = int(shape[3]) if isinstance(shape[3], (int, np.integer)) and int(shape[3]) > 0 else 128
            self.channels = int(shape[1]) if isinstance(shape[1], (int, np.integer)) and int(shape[1]) > 0 else 3
        else:
            self.in_h = int(shape[1]) if len(shape) == 4 and isinstance(shape[1], (int, np.integer)) and int(shape[1]) > 0 else 64
            self.in_w = int(shape[2]) if len(shape) == 4 and isinstance(shape[2], (int, np.integer)) and int(shape[2]) > 0 else 128
            self.channels = int(shape[3]) if len(shape) == 4 and isinstance(shape[3], (int, np.integer)) and int(shape[3]) > 0 else 3
        self.expect_uint8 = "uint8" in self.input_type.lower()

    def read_text(self, bgr_crop: np.ndarray) -> str:
        if bgr_crop is None or bgr_crop.size == 0:
            return ""
        cv2 = self.cv2
        resized = cv2.resize(bgr_crop, (self.in_w, self.in_h), interpolation=cv2.INTER_LINEAR)
        if self.channels == 1:
            arr_img = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)[..., None]
        else:
            arr_img = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        if self.expect_uint8:
            tensor = arr_img.astype(np.uint8)
        else:
            tensor = arr_img.astype(np.float32) * (1.0 / 255.0)

        if self.nchw:
            tensor = np.transpose(tensor, (2, 0, 1))
        batch = tensor[None, ...]

        with self._run_lock:
            outputs = self.session.run(None, {self.input_name: batch})
        if not outputs:
            return ""

        raw = np.asarray(outputs[0], dtype=np.float32)
        if raw.ndim >= 3:
            raw = raw[0]
        if raw.ndim == 2 and raw.shape[1] == len(PLATE_OCR_ALPHABET):
            logits = raw
        else:
            flat = raw.reshape(-1)
            n_alpha = len(PLATE_OCR_ALPHABET)
            if flat.size == 0 or flat.size % n_alpha != 0:
                return ""
            logits = flat.reshape(-1, n_alpha)

        idxs = np.argmax(logits, axis=1)
        chars: list[str] = []
        for idx in idxs:
            ii = int(idx)
            if 0 <= ii < len(PLATE_OCR_ALPHABET):
                ch = PLATE_OCR_ALPHABET[ii]
                if ch != "_" and ch.isalnum():
                    chars.append(ch)
        return "".join(chars).upper()


def _get_plate_ocr_engine() -> _PlateOcrEngine | None:
    global _PLATE_OCR_CACHE
    if _PLATE_OCR_CACHE is not None:
        return _PLATE_OCR_CACHE
    with _PLATE_OCR_LOCK:
        if _PLATE_OCR_CACHE is not None:
            return _PLATE_OCR_CACHE
        ocr_p = _ensure_plate_ocr_model()
        if ocr_p is None:
            print("[PlatePrivacy WARN] Không tải được model OCR biển số ONNX.")
            return None
        try:
            _PLATE_OCR_CACHE = _PlateOcrEngine(ocr_p)
            return _PLATE_OCR_CACHE
        except Exception as exc:
            print(f"[PlatePrivacy WARN] Không khởi tạo được OCR biển số ({exc}).")
            return None


def _plate_visual_embed(cv2: Any, crop: np.ndarray) -> np.ndarray:
    if crop is None or crop.size == 0:
        return np.zeros((160,), dtype=np.float32)
    small = cv2.resize(crop, (48, 24), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    patch = cv2.resize(gray, (12, 6), interpolation=cv2.INTER_AREA).astype(np.float32).flatten() / 255.0
    patch = patch - float(patch.mean())
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx * gx + gy * gy)
    edge_patch = cv2.resize(mag, (8, 4), interpolation=cv2.INTER_AREA).flatten()
    edge_patch = edge_patch / (float(edge_patch.max()) + 1e-6)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist_h = cv2.calcHist([hsv], [0], None, [24], [0, 180]).flatten()
    hist_s = cv2.calcHist([hsv], [1], None, [32], [0, 256]).flatten()
    vec = np.concatenate(
        [
            patch,
            edge_patch,
            hist_h / (hist_h.sum() + 1e-6),
            hist_s / (hist_s.sum() + 1e-6),
        ]
    ).astype(np.float32)
    return _l2_norm(vec)


def _plate_text_similarity(a: str, b: str) -> float:
    sa = re.sub(r"[^A-Z0-9]", "", str(a or "").upper())
    sb = re.sub(r"[^A-Z0-9]", "", str(b or "").upper())
    if len(sa) < 4 or len(sb) < 4:
        return 0.0
    ratio = difflib.SequenceMatcher(None, sa, sb).ratio()
    if len(sa) >= 5 and len(sb) >= 5 and sa[-4:] == sb[-4:]:
        ratio = max(ratio, 0.82)
    return float(ratio)


def _match_plate_cluster_id(
    text: str,
    emb: np.ndarray,
    plate_items: list[dict[str, Any]],
    text_thresh: float = 0.68,
    vis_thresh: float = 0.86,
) -> tuple[str | None, float]:
    best_id: str | None = None
    best_score = -1.0
    clean_t = re.sub(r"[^A-Z0-9]", "", str(text or "").upper())
    for item in plate_items:
        pid = str(item.get("id") or "")
        ptxt = str(item.get("plate_text") or "")
        pemb = item.get("emb")
        if len(clean_t) >= 4 and len(ptxt) >= 4:
            sc = _plate_text_similarity(clean_t, ptxt)
            ok = sc >= text_thresh
        elif isinstance(pemb, np.ndarray) and pemb.size == emb.size and emb.size > 0:
            sc = _cosine_sim(emb, pemb)
            ok = sc >= vis_thresh
        else:
            continue
        if ok and sc > best_score:
            best_score = sc
            best_id = pid
    return best_id, best_score


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

    try:
        hold_sec = float(raw.get("hold_sec") if raw.get("hold_sec") is not None else 0.65)
    except (TypeError, ValueError):
        hold_sec = 0.65
    hold_sec = round(max(0.15, min(2.5, hold_sec)), 2)

    plate_mode = str(raw.get("plate_blur_mode") or "blur_all").strip()
    if plate_mode not in ("blur_all", "blur_selected", "keep_selected"):
        plate_mode = "blur_all"

    plate_style = str(raw.get("plate_blur_style") or "pixelate").strip()
    if plate_style not in ("pixelate", "gaussian", "solid"):
        plate_style = "pixelate"

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

    raw_plate_ids = raw.get("selected_plate_ids")
    if not isinstance(raw_plate_ids, list):
        raw_plate_ids = []
    seen_p: set[str] = set()
    sel_plate_ids: list[str] = []
    for x in raw_plate_ids:
        sx = str(x or "").strip()
        if sx and sx not in seen_p:
            seen_p.add(sx)
            sel_plate_ids.append(sx)

    return {
        "enabled": bool(raw.get("enabled", False)),
        "mode": mode,
        "style": style,
        "icon": icon,
        "padding": padding,
        "hold_sec": hold_sec,
        "selected_face_ids": sel_ids,
        "plate_blur_enabled": bool(raw.get("plate_blur_enabled", False)),
        "plate_blur_mode": plate_mode,
        "plate_blur_style": plate_style,
        "selected_plate_ids": sel_plate_ids,
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


def _strip_plates_for_ui(plates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pl in plates:
        if not isinstance(pl, dict):
            continue
        out.append(
            {
                "id": str(pl.get("id") or ""),
                "label": str(pl.get("label") or ""),
                "plate_text": str(pl.get("plate_text") or ""),
                "appearances": int(pl.get("appearances") or 0),
                "clip_count": int(pl.get("clip_count") or 0),
                "clip_names": list(pl.get("clip_names") or []),
                "thumb_name": str(pl.get("thumb_name") or ""),
                "score": float(pl.get("score") or 0.0),
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
            "plate_updated_at": 0,
            "plate_clip_signature": [],
            "plates": [],
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
            "plate_updated_at": 0,
            "plate_clip_signature": [],
            "plates": [],
            "config": dict(DEFAULT_FACE_PRIVACY_CONFIG),
        }
    return {
        "updated_at": int(data.get("updated_at") or 0),
        "clip_signature": data.get("clip_signature") if isinstance(data.get("clip_signature"), list) else [],
        "faces": data.get("faces") if isinstance(data.get("faces"), list) else [],
        "plate_updated_at": int(data.get("plate_updated_at") or 0),
        "plate_clip_signature": data.get("plate_clip_signature") if isinstance(data.get("plate_clip_signature"), list) else [],
        "plates": data.get("plates") if isinstance(data.get("plates"), list) else [],
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
        "plate_updated_at": cur["plate_updated_at"],
        "plate_clip_signature": cur["plate_clip_signature"],
        "plates": _strip_plates_for_ui(cur["plates"]),
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
        for old_img in thumbs_dir.glob("face_*.jpg"):
            old_img.unlink(missing_ok=True)
        if prev_state.get("clip_signature") != clip_sig:
            prev_cfg["selected_face_ids"] = []
        state_data = {
            "updated_at": int(time.time()),
            "clip_signature": clip_sig,
            "faces": [],
            "plate_updated_at": prev_state.get("plate_updated_at", 0),
            "plate_clip_signature": prev_state.get("plate_clip_signature", []),
            "plates": prev_state.get("plates", []),
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

    for old_img in thumbs_dir.glob("face_*.jpg"):
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

    # Re-read latest config so concurrent UI edits / plate scans aren't overwritten
    latest_state = load_face_privacy_state(project_root)
    latest_cfg = normalize_face_config(latest_state.get("config"))
    if prev_state.get("clip_signature") != clip_sig:
        latest_cfg["selected_face_ids"] = []
    else:
        latest_cfg["selected_face_ids"] = [x for x in latest_cfg["selected_face_ids"] if x in valid_new_ids]

    state_data = {
        "updated_at": int(time.time()),
        "clip_signature": clip_sig,
        "faces": faces_out,
        "plate_updated_at": latest_state.get("plate_updated_at", 0),
        "plate_clip_signature": latest_state.get("plate_clip_signature", []),
        "plates": latest_state.get("plates", []),
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


def _crop_plate_thumb(cv2: Any, orig_frame: np.ndarray, cx: float, cy: float, bw: float, bh: float) -> np.ndarray | None:
    oh, ow = orig_frame.shape[:2]
    ew = bw * 1.24
    eh = bh * 1.32
    x1 = max(0, int(round(cx - ew * 0.5)))
    y1 = max(0, int(round(cy - eh * 0.5)))
    x2 = min(ow, int(round(cx + ew * 0.5)))
    y2 = min(oh, int(round(cy + eh * 0.5)))
    if x2 - x1 < 8 or y2 - y1 < 6:
        return None
    crop = orig_frame[y1:y2, x1:x2]
    tw, th = 180, 96
    ch, cw = crop.shape[:2]
    ratio = min(float(tw) / float(cw), float(th) / float(ch))
    nw = max(1, int(round(cw * ratio)))
    nh = max(1, int(round(ch * ratio)))
    resized = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_AREA if ratio < 1.0 else cv2.INTER_CUBIC)
    canvas = np.full((th, tw, 3), 18, dtype=np.uint8)
    xo = (tw - nw) // 2
    yo = (th - nh) // 2
    canvas[yo : yo + nh, xo : xo + nw] = resized
    return canvas


def _extract_plate_crop(orig_frame: np.ndarray, cx: float, cy: float, bw: float, bh: float) -> np.ndarray | None:
    oh, ow = orig_frame.shape[:2]
    ew = bw * 1.06
    eh = bh * 1.08
    x1 = max(0, int(round(cx - ew * 0.5)))
    y1 = max(0, int(round(cy - eh * 0.5)))
    x2 = min(ow, int(round(cx + ew * 0.5)))
    y2 = min(oh, int(round(cy + eh * 0.5)))
    if x2 - x1 < 10 or y2 - y1 < 6:
        return None
    return orig_frame[y1:y2, x1:x2]


def scan_project_plates(
    project_root: Path,
    force: bool = False,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Scan raw clips in `02_video_tho/`, detect + OCR + cluster unique license plates, and save thumbs into `faces.json`."""
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

    if not force and prev_state.get("plate_clip_signature") == clip_sig and prev_state.get("plate_updated_at"):
        plates_prev = prev_state.get("plates") or []
        thumbs_ok = all(
            (thumbs_dir / str(pl.get("thumb_name") or "")).exists()
            for pl in plates_prev
            if pl.get("thumb_name")
        )
        if thumbs_ok:
            _report(len(videos), len(videos), "")
            return {
                "ok": True,
                "cached": True,
                "plate_updated_at": prev_state["plate_updated_at"],
                "clip_count": len(videos),
                "plates": _strip_plates_for_ui(plates_prev),
                "config": prev_cfg,
            }

    if not videos:
        for old_img in thumbs_dir.glob("plate_*.jpg"):
            old_img.unlink(missing_ok=True)
        latest_state = load_face_privacy_state(project_root)
        latest_cfg = normalize_face_config(latest_state.get("config"))
        if prev_state.get("plate_clip_signature") != clip_sig:
            latest_cfg["selected_plate_ids"] = []
        state_data = {
            "updated_at": int(latest_state.get("updated_at") or 0),
            "clip_signature": latest_state.get("clip_signature") or [],
            "faces": latest_state.get("faces") or [],
            "plate_updated_at": int(time.time()),
            "plate_clip_signature": clip_sig,
            "plates": [],
            "config": latest_cfg,
        }
        _write_faces_json(project_root, state_data)
        _report(0, 0, "")
        return {
            "ok": True,
            "cached": False,
            "plate_updated_at": state_data["plate_updated_at"],
            "clip_count": 0,
            "plates": [],
            "config": latest_cfg,
        }

    _report(0, len(videos), "")
    plate_engine = _get_plate_engine()
    if plate_engine is None:
        raise RuntimeError("Không khởi tạo được model nhận diện biển số ONNX.")
    ocr_engine = _get_plate_ocr_engine()
    cv2 = plate_engine.cv2

    clusters: list[dict[str, Any]] = []

    def _pick_cluster_text(cl_item: dict[str, Any]) -> str:
        votes: dict[str, int] = cl_item.get("text_votes") or {}
        if not votes:
            return ""
        # Prefer longest/most frequent clean OCR text
        return max(votes.items(), key=lambda kv: (kv[1], len(kv[0])))[0]

    for idx, vp in enumerate(videos, start=1):
        rel_name = vp.relative_to(raw_dir).as_posix()
        _report(idx - 1, len(videos), rel_name)
        sampled = _sample_video_frames(cv2, vp, max_samples=12)
        for fi, orig_frame in sampled:
            oh, ow = orig_frame.shape[:2]
            if oh <= 0 or ow <= 0:
                continue
            dets = plate_engine.detect(orig_frame, conf_threshold=0.35, nms_threshold=0.45)
            if not dets:
                continue

            used_cidx: set[int] = set()
            dets_sorted = sorted(dets, key=lambda d: float(d["score"]) * (d["w"] * d["h"]), reverse=True)
            for d in dets_sorted:
                cx, cy, bw, bh, score = float(d["cx"]), float(d["cy"]), float(d["w"]), float(d["h"]), float(d["score"])
                crop = _extract_plate_crop(orig_frame, cx, cy, bw, bh)
                if crop is None:
                    continue
                text = ocr_engine.read_text(crop) if ocr_engine is not None else ""
                emb = _plate_visual_embed(cv2, crop)
                area_bonus = min(1.0, (bw * bh) / float(max(1, (min(ow, oh) * 0.16) ** 2)))
                q = float(score * (0.55 + 0.30 * area_bonus + (0.15 if len(text) >= 5 else 0.0)))

                best_ci = -1
                best_sc = -1.0
                for ci, cl in enumerate(clusters):
                    if ci in used_cidx:
                        continue
                    cl_text = _pick_cluster_text(cl)
                    if len(text) >= 4 and len(cl_text) >= 4:
                        sc = _plate_text_similarity(text, cl_text)
                        ok = sc >= 0.68
                    else:
                        sc = _cosine_sim(emb, cl["emb"])
                        ok = sc >= 0.86
                    if ok and sc > best_sc:
                        best_sc = sc
                        best_ci = ci

                f_key = (rel_name, fi)
                if best_ci >= 0:
                    used_cidx.add(best_ci)
                    cl = clusters[best_ci]
                    cl["count"] += 1
                    cl["clips"].add(rel_name)
                    cl["frame_keys"].add(f_key)
                    cl["emb_sum"] = cl["emb_sum"] + emb
                    cl["emb"] = _l2_norm(cl["emb_sum"])
                    cl["best_score"] = max(cl["best_score"], score)
                    if len(text) >= 4:
                        cl["text_votes"][text] = cl["text_votes"].get(text, 0) + 1
                    if q > cl["best_quality"] or cl["thumb"] is None:
                        th_img = _crop_plate_thumb(cv2, orig_frame, cx, cy, bw, bh)
                        if th_img is not None:
                            cl["best_quality"] = q
                            cl["thumb"] = th_img
                else:
                    th_img = _crop_plate_thumb(cv2, orig_frame, cx, cy, bw, bh)
                    if th_img is None:
                        continue
                    new_idx = len(clusters)
                    used_cidx.add(new_idx)
                    votes = {text: 1} if len(text) >= 4 else {}
                    clusters.append(
                        {
                            "emb_sum": emb.copy(),
                            "emb": emb.copy(),
                            "text_votes": votes,
                            "count": 1,
                            "clips": {rel_name},
                            "frame_keys": {f_key},
                            "best_score": score,
                            "best_quality": q,
                            "thumb": th_img,
                        }
                    )
        _report(idx, len(videos), rel_name)

    # Post-merge clusters sharing strong OCR text and never co-occurring in the same frame
    merged = True
    while merged and len(clusters) > 1:
        merged = False
        best_pair: tuple[int, int, float] | None = None
        for i in range(len(clusters)):
            ti = _pick_cluster_text(clusters[i])
            for j in range(i + 1, len(clusters)):
                if clusters[i]["frame_keys"] & clusters[j]["frame_keys"]:
                    continue
                tj = _pick_cluster_text(clusters[j])
                if len(ti) >= 4 and len(tj) >= 4:
                    sc = _plate_text_similarity(ti, tj)
                    ok = sc >= 0.72
                else:
                    sc = _cosine_sim(clusters[i]["emb"], clusters[j]["emb"])
                    ok = sc >= 0.90
                if ok and (best_pair is None or sc > best_pair[2]):
                    best_pair = (i, j, sc)
        if best_pair is not None:
            i, j, _ = best_pair
            ci, cj = clusters[i], clusters[j]
            ci["count"] += cj["count"]
            ci["clips"] |= cj["clips"]
            ci["frame_keys"] |= cj["frame_keys"]
            ci["emb_sum"] = ci["emb_sum"] + cj["emb_sum"]
            ci["emb"] = _l2_norm(ci["emb_sum"])
            ci["best_score"] = max(ci["best_score"], cj["best_score"])
            for k_txt, k_cnt in cj["text_votes"].items():
                ci["text_votes"][k_txt] = ci["text_votes"].get(k_txt, 0) + k_cnt
            if cj["best_quality"] > ci["best_quality"] and cj["thumb"] is not None:
                ci["best_quality"] = cj["best_quality"]
                ci["thumb"] = cj["thumb"]
            clusters.pop(j)
            merged = True

    clusters.sort(
        key=lambda c: (len(c["clips"]), c["count"], c["best_quality"]),
        reverse=True,
    )

    for old_img in thumbs_dir.glob("plate_*.jpg"):
        old_img.unlink(missing_ok=True)

    plates_out: list[dict[str, Any]] = []
    valid_new_ids: set[str] = set()
    for idx, cl in enumerate(clusters, start=1):
        pid = f"plate_{idx:02d}"
        thumb_name = f"{pid}.jpg"
        th_img = cl.get("thumb")
        if th_img is not None:
            ok_enc, buf = cv2.imencode(".jpg", th_img, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            if ok_enc:
                (thumbs_dir / thumb_name).write_bytes(buf.tobytes())
        valid_new_ids.add(pid)
        best_text = _pick_cluster_text(cl)
        label = best_text if best_text else f"Biển #{idx}"
        plates_out.append(
            {
                "id": pid,
                "label": label,
                "plate_text": best_text,
                "appearances": int(cl["count"]),
                "clip_count": len(cl["clips"]),
                "clip_names": sorted(cl["clips"]),
                "thumb_name": thumb_name,
                "score": round(float(cl["best_score"]), 3),
                "embedding": [round(float(v), 6) for v in cl["emb"].tolist()],
            }
        )

    latest_state = load_face_privacy_state(project_root)
    latest_cfg = normalize_face_config(latest_state.get("config"))
    if prev_state.get("plate_clip_signature") != clip_sig:
        latest_cfg["selected_plate_ids"] = []
    else:
        latest_cfg["selected_plate_ids"] = [x for x in latest_cfg["selected_plate_ids"] if x in valid_new_ids]

    state_data = {
        "updated_at": int(latest_state.get("updated_at") or 0),
        "clip_signature": latest_state.get("clip_signature") or [],
        "faces": latest_state.get("faces") or [],
        "plate_updated_at": int(time.time()),
        "plate_clip_signature": clip_sig,
        "plates": plates_out,
        "config": latest_cfg,
    }
    _write_faces_json(project_root, state_data)
    return {
        "ok": True,
        "cached": False,
        "plate_updated_at": state_data["plate_updated_at"],
        "clip_count": len(videos),
        "plates": _strip_plates_for_ui(plates_out),
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


def _apply_plate_mask(
    cv2: Any,
    frame: np.ndarray,
    boxes: list[tuple[int, int, int, int]],
    plate_style: str,
) -> None:
    """Apply strong rectangular feathered privacy masking to detected license plates."""
    fh, fw = frame.shape[:2]
    for (x1, y1, x2, y2) in boxes:
        x1c = max(0, min(fw - 1, int(x1)))
        y1c = max(0, min(fh - 1, int(y1)))
        x2c = max(0, min(fw, int(x2)))
        y2c = max(0, min(fh, int(y2)))
        rw = x2c - x1c
        rh = y2c - y1c
        if rw < 8 or rh < 6:
            continue

        roi = frame[y1c:y2c, x1c:x2c]
        if plate_style == "solid":
            effect = np.full((rh, rw, 3), (24, 24, 28), dtype=np.uint8)
        elif plate_style == "gaussian":
            sw = max(6, min(20, rw // 14))
            sh = max(4, min(14, rh // 12))
            small = cv2.resize(roi, (sw, sh), interpolation=cv2.INTER_AREA)
            small = cv2.GaussianBlur(small, (15, 15), 0)
            effect = cv2.resize(small, (rw, rh), interpolation=cv2.INTER_LINEAR)
        else:
            pw = max(4, min(10, rw // 14))
            ph = max(3, min(8, rh // 10))
            small = cv2.resize(roi, (pw, ph), interpolation=cv2.INTER_LINEAR)
            effect = cv2.resize(small, (rw, rh), interpolation=cv2.INTER_NEAREST)

        mask = np.ones((rh, rw), dtype=np.float32)
        border = max(1, min(4, min(rw, rh) // 10))
        if border > 1 and rw > border * 2 and rh > border * 2:
            mask[:border, :] = 0.0
            mask[-border:, :] = 0.0
            mask[:, :border] = 0.0
            mask[:, -border:] = 0.0
            k = (border * 2 + 1) | 1
            mask = cv2.GaussianBlur(mask, (k, k), 0)
        mask_3 = mask[:, :, None]
        blended = effect.astype(np.float32) * mask_3 + roi.astype(np.float32) * (1.0 - mask_3)
        frame[y1c:y2c, x1c:x2c] = np.clip(blended, 0, 255).astype(np.uint8)


def _build_plate_frame_boxes(
    plate_keyframes: list[tuple[int, list[dict[str, Any]]]],
    *,
    orig_w: int,
    orig_h: int,
    fps: float,
    total_frames: int,
    hold_sec: float = 0.65,
    mode: str = "blur_all",
    selected_ids: set[str] | None = None,
) -> dict[int, list[tuple[int, int, int, int]]]:
    """Link detected license plates into spatial tracks, filter by mode if selective, and interpolate per frame."""
    if not plate_keyframes:
        return {}

    max_gap_frames = max(8, int(round(fps * max(0.55, hold_sec * 0.90))))
    pad_edge_frames = max(3, int(round(fps * min(0.80, max(0.30, hold_sec * 0.70)))))
    id_hold_frames = max(10, int(round(fps * max(0.90, hold_sec * 1.40))))
    sel_set = set(selected_ids or set())

    tracks: list[list[dict[str, Any]]] = []
    for f_idx, dets in plate_keyframes:
        unmatched = set(range(len(tracks)))
        candidates: list[tuple[float, int, int]] = []
        for di, d in enumerate(dets):
            dcx, dcy, dw, dh = float(d["cx"]), float(d["cy"]), float(d["w"]), float(d["h"])
            diag = max(24.0, (dw + dh) * 0.5)
            for ti in unmatched:
                last = tracks[ti][-1]
                f_gap = f_idx - int(last["frame"])
                if f_gap <= 0 or f_gap > max_gap_frames:
                    continue
                dist = float(np.hypot(dcx - float(last["cx"]), dcy - float(last["cy"])))
                ref_size = max(diag, (float(last["w"]) + float(last["h"])) * 0.5)
                allowed_dist = ref_size * (1.65 + 0.30 * (f_gap / max(1.0, fps * 0.15)))
                if dist <= allowed_dist:
                    candidates.append((dist / ref_size, di, ti))
        candidates.sort(key=lambda x: x[0])

        matched_d: set[int] = set()
        matched_t: set[int] = set()
        for _, di, ti in candidates:
            if di in matched_d or ti in matched_t:
                continue
            matched_d.add(di)
            matched_t.add(ti)
            tracks[ti].append({"frame": float(f_idx), **dets[di]})

        for di, d in enumerate(dets):
            if di not in matched_d:
                tracks.append([{"frame": float(f_idx), **d}])

    target_segments: list[list[dict[str, Any]]] = []
    if mode == "blur_all":
        target_segments = tracks
    else:
        for trk in tracks:
            cur_seg: list[dict[str, Any]] = []
            for node in trk:
                pid = node.get("best_id")
                if pid is None:
                    best_neighbor_dist = id_hold_frames + 1
                    for other in trk:
                        opid = other.get("best_id")
                        if opid is not None:
                            fdist = abs(int(other["frame"]) - int(node["frame"]))
                            if fdist < best_neighbor_dist:
                                best_neighbor_dist = fdist
                                pid = opid
                if mode == "blur_selected":
                    should_mask = bool(pid is not None and pid in sel_set)
                else:
                    # keep_selected: keep ONLY matched selected plates; mask everything else including unrecognized/blurry plates
                    should_mask = True if not sel_set else not (pid is not None and pid in sel_set)

                if should_mask:
                    cur_seg.append(node)
                else:
                    if cur_seg:
                        target_segments.append(cur_seg)
                        cur_seg = []
            if cur_seg:
                target_segments.append(cur_seg)

    if not target_segments:
        return {}

    frame_boxes: dict[int, list[tuple[int, int, int, int]]] = {}
    max_frame_idx = max(0, total_frames - 1) if total_frames > 0 else 10**7

    def _add_pbox(fi: int, cx: float, cy: float, bw: float, bh: float) -> None:
        ew = bw * 1.25
        eh = bh * 1.30
        x1 = max(0, int(round(cx - ew * 0.5)))
        y1 = max(0, int(round(cy - eh * 0.5)))
        x2 = min(orig_w, int(round(cx + ew * 0.5)))
        y2 = min(orig_h, int(round(cy + eh * 0.5)))
        if x2 - x1 >= 8 and y2 - y1 >= 6:
            frame_boxes.setdefault(fi, []).append((x1, y1, x2, y2))

    for trk in target_segments:
        first = trk[0]
        f0 = int(first["frame"])
        for fi in range(max(0, f0 - pad_edge_frames), f0):
            _add_pbox(fi, float(first["cx"]), float(first["cy"]), float(first["w"]), float(first["h"]))
        for k in range(len(trk) - 1):
            a = trk[k]
            b = trk[k + 1]
            fa = int(a["frame"])
            fb = int(b["frame"])
            span = max(1, fb - fa)
            for fi in range(fa, fb):
                alpha = (fi - fa) / float(span)
                _add_pbox(
                    fi,
                    float(a["cx"]) * (1.0 - alpha) + float(b["cx"]) * alpha,
                    float(a["cy"]) * (1.0 - alpha) + float(b["cy"]) * alpha,
                    float(a["w"]) * (1.0 - alpha) + float(b["w"]) * alpha,
                    float(a["h"]) * (1.0 - alpha) + float(b["h"]) * alpha,
                )
        last = trk[-1]
        fl = int(last["frame"])
        _add_pbox(fl, float(last["cx"]), float(last["cy"]), float(last["w"]), float(last["h"]))
        for fi in range(fl + 1, min(max_frame_idx + 1, fl + 1 + pad_edge_frames)):
            _add_pbox(fi, float(last["cx"]), float(last["cy"]), float(last["w"]), float(last["h"]))

    return frame_boxes


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
    hold_sec: float = 0.65,
) -> dict[int, list[tuple[int, int, int, int, str]]]:
    """Link detections into smooth spatial tracks, classify target identities, and interpolate per frame."""
    if not keyframes:
        return {}

    sim_thresh = 0.33 if onnx_mode else 0.74
    strong_thresh = 0.36 if onnx_mode else 0.80
    hold_sec = max(0.15, min(2.5, float(hold_sec or 0.65)))
    max_gap_frames = max(10, int(round(fps * max(0.80, hold_sec * 1.45))))
    pad_edge_frames = max(2, int(round(fps * hold_sec)))

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
    id_hold_frames = max(10, int(round(fps * max(1.00, hold_sec * 1.75))))

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
    Detect, track & mask selected (or bystander) faces and/or license plates inside `clip_path` in-place.
    Returns True if masking was applied, False if skipped (disabled or no target regions found).
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
        if "face_blur_hold_sec" in override_cfg:
            merged_raw["hold_sec"] = override_cfg["face_blur_hold_sec"]
        if "face_blur_ids" in override_cfg:
            merged_raw["selected_face_ids"] = override_cfg["face_blur_ids"]
        if "plate_blur_ids" in override_cfg:
            merged_raw["selected_plate_ids"] = override_cfg["plate_blur_ids"]
        for k in (
            "enabled",
            "mode",
            "style",
            "icon",
            "padding",
            "hold_sec",
            "selected_face_ids",
            "plate_blur_enabled",
            "plate_blur_mode",
            "plate_blur_style",
            "selected_plate_ids",
        ):
            if k in override_cfg:
                merged_raw[k] = override_cfg[k]

    cfg = normalize_face_config(merged_raw)
    face_active = bool(cfg["enabled"])
    plate_active = bool(cfg["plate_blur_enabled"])
    if not face_active and not plate_active:
        return False

    mode = cfg["mode"]
    style = cfg["style"]
    padding = float(cfg["padding"])
    hold_sec = float(cfg["hold_sec"])
    plate_mode = cfg["plate_blur_mode"]
    plate_style = cfg["plate_blur_style"]
    selected_ids = set(cfg["selected_face_ids"])
    selected_plate_ids = set(cfg["selected_plate_ids"])

    cluster_items: list[tuple[str, np.ndarray]] = []
    if face_active:
        if mode == "blur_selected" and not selected_ids:
            face_active = False
        else:
            for f in state.get("faces") or []:
                fid = str(f.get("id") or "").strip()
                emb_list = f.get("embedding")
                if fid and isinstance(emb_list, list) and emb_list:
                    vec = _l2_norm(np.array(emb_list, dtype=np.float32))
                    cluster_items.append((fid, vec))
            if mode == "blur_selected":
                cluster_ids_present = {cid for cid, _ in cluster_items}
                if not (selected_ids & cluster_ids_present):
                    face_active = False

    plate_clusters: list[dict[str, Any]] = []
    if plate_active and plate_mode != "blur_all":
        for pl in state.get("plates") or []:
            pid = str(pl.get("id") or "").strip()
            ptxt = re.sub(r"[^A-Z0-9]", "", str(pl.get("plate_text") or "").upper())
            emb_list = pl.get("embedding")
            emb_vec = _l2_norm(np.array(emb_list, dtype=np.float32)) if isinstance(emb_list, list) and emb_list else np.zeros((0,), dtype=np.float32)
            if pid and (len(ptxt) >= 4 or emb_vec.size > 0):
                plate_clusters.append({"id": pid, "plate_text": ptxt, "emb": emb_vec})
        if plate_mode == "blur_selected":
            plate_ids_present = {str(x["id"]) for x in plate_clusters}
            if not (selected_plate_ids & plate_ids_present):
                plate_active = False

    if not face_active and not plate_active:
        return False

    face_engine = _FaceEngine() if face_active else None
    plate_engine = _get_plate_engine() if plate_active else None
    if plate_engine is None:
        plate_active = False
    plate_ocr_engine = _get_plate_ocr_engine() if (plate_active and plate_mode != "blur_all") else None
    if not face_active and not plate_active:
        return False

    cv2 = face_engine.cv2 if face_engine is not None else _ensure_cv2()
    match_thresh = (0.33 if face_engine.use_onnx else 0.74) if face_engine is not None else 0.33

    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        return False

    orig_w = 0
    orig_h = 0
    fps = 30.0
    total_frames = 0
    keyframes: list[tuple[int, list[dict[str, Any]]]] = []
    plate_keyframes: list[tuple[int, list[dict[str, Any]]]] = []
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
        step = 3
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

            if face_active and face_engine is not None:
                scan_frame = cv2.resize(frame, (sw, sh), interpolation=cv2.INTER_AREA) if scale < 1.0 else frame
                dets = face_engine.detect_and_embed(scan_frame, score_threshold=0.58, min_box_px=18)
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

            if plate_active and plate_engine is not None:
                p_dets = plate_engine.detect(frame, conf_threshold=0.35, nms_threshold=0.45)
                if p_dets:
                    if plate_mode != "blur_all" and plate_clusters:
                        enriched: list[dict[str, Any]] = []
                        for pd in p_dets:
                            pcrop = _extract_plate_crop(frame, pd["cx"], pd["cy"], pd["w"], pd["h"])
                            ptxt = plate_ocr_engine.read_text(pcrop) if (plate_ocr_engine is not None and pcrop is not None) else ""
                            pemb = _plate_visual_embed(cv2, pcrop) if pcrop is not None else np.zeros((0,), dtype=np.float32)
                            pid, _ = _match_plate_cluster_id(ptxt, pemb, plate_clusters)
                            enriched.append({**pd, "best_id": pid})
                        plate_keyframes.append((fi, enriched))
                    else:
                        plate_keyframes.append((fi, p_dets))

            fi += 1
        total_frames = fi
    finally:
        cap.release()

    if total_frames <= 0 or (not keyframes and not plate_keyframes):
        return False

    frame_boxes: dict[int, list[tuple[int, int, int, int, str]]] = (
        _build_masked_frame_boxes(
            keyframes,
            mode=mode,
            selected_ids=selected_ids,
            padding=padding,
            orig_w=orig_w,
            orig_h=orig_h,
            fps=fps,
            total_frames=total_frames,
            onnx_mode=bool(face_engine.use_onnx if face_engine is not None else True),
            icon_mode=cfg["icon"],
            hold_sec=hold_sec,
        )
        if (face_active and keyframes)
        else {}
    )
    plate_frame_boxes: dict[int, list[tuple[int, int, int, int]]] = (
        _build_plate_frame_boxes(
            plate_keyframes,
            orig_w=orig_w,
            orig_h=orig_h,
            fps=fps,
            total_frames=total_frames,
            hold_sec=hold_sec,
            mode=plate_mode,
            selected_ids=selected_plate_ids,
        )
        if (plate_active and plate_keyframes)
        else {}
    )
    if not frame_boxes and not plate_frame_boxes:
        return False

    # Pass 2: Apply face + plate ROI masking and stream to FFmpeg encoder preserving audio & bt709 color profile
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
            pboxes = plate_frame_boxes.get(fi)
            if pboxes:
                _apply_plate_mask(cv2, frame, pboxes, plate_style)
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
        raise RuntimeError(f"FFmpeg lỗi khi xuất video che riêng tư ({ret}): {err_msg}")

    os.replace(tmp_out, clip_path)
    return True
