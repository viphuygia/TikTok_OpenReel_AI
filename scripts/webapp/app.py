#!/usr/bin/env python3
"""
Local Webapp Dashboard (Zero-Copy Local Architecture) cho hệ thống TikTok OpenReel AI.
Chạy trực tiếp trên môi trường ảo 03_voice_clone/venv tại http://localhost:8000.
"""

from __future__ import annotations

import asyncio
import base64
import gc
import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from .tunnel_service import tunnel_service
except ImportError:
    from scripts.webapp.tunnel_service import tunnel_service

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"

SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from audio_bgm import ensure_royalty_free_bgm_library
from style_dna import (
    FILE_CRITIC_REPORT,
    FILE_SCRIPT_OPTIONS,
    FILE_VOICE_BEATS,
    align_edit_plan_to_voice_beats,
    build_auto_critic_report_md,
    build_batch_mix_profile,
    generate_ai_wildcard_style_spec,
    generate_random_batch_mix_profiles,
    compute_target_word_budget,
    convert_display_to_tts_script,
    ensure_script_meets_duration,
    generate_three_script_options_fallback,
    get_effective_banned_words,
    is_brand_brief_ready,
    load_brand_brief,
    load_channel_script_dna_context,
    load_global_banned_words,
    load_script_options,
    load_style_dna,
    parse_raw_brand_brief_heuristic,
    reorder_clips_for_variant,
    repair_subtitles_and_beats,
    restore_display_text,
    sanitize_banned_text,
    sanitize_cta_text,
    save_brand_brief,
    save_global_banned_words,
    save_script_options,
    update_style_dna,
)
from remotion_renderer import (
    FILE_DEFAULT_OUTPUT,
    FILE_PREVIEW_FRAMES_DIR,
    FILE_REMOTION_PROPS,
    build_remotion_props,
    render_creative_review_frames,
    render_remotion_video,
    render_title_badge_preview,
    resolve_script_named_output_path,
)
from hyperframes_renderer import (
    get_hyperframes_status,
    render_hyperframes_video,
    refresh_project_paths as _refresh_renderer_paths,
)
from project_manager import (
    PROJECT_SCOPED_ROOTS,
    create_project as pm_create_project,
    ensure_project_dirs as pm_ensure_project_dirs,
    get_active_project_id,
    get_project_root,
    list_projects as pm_list_projects,
    set_active_project as pm_set_active_project,
)

ACTIVE_PROJECT_ID = get_active_project_id()
ACTIVE_PROJECT_ROOT = get_project_root(ACTIVE_PROJECT_ID)
pm_ensure_project_dirs(ACTIVE_PROJECT_ROOT)

DIR_VIDEO_MAU = PROJECT_ROOT / "01_video_mau"
DIR_FRAMES_MAU = PROJECT_ROOT / "04_workspace" / "frames" / "01_video_mau"
DIR_VIDEO_THO = ACTIVE_PROJECT_ROOT / "02_video_tho"
DIR_VOICE_CLONE = PROJECT_ROOT / "03_voice_clone"
DIR_VOICE_MODEL = DIR_VOICE_CLONE / "model"
DIR_VOICE_PROFILES = DIR_VOICE_CLONE / "voices"
DIR_WORKSPACE = ACTIVE_PROJECT_ROOT / "04_workspace"
DIR_FRAMES = DIR_WORKSPACE / "frames"
DIR_READY = DIR_WORKSPACE / "ready_for_openreel"
DIR_CLIPS = DIR_READY / "01_clips"
DIR_OUTPUT = ACTIVE_PROJECT_ROOT / "05_output"
DIR_OPENREEL = PROJECT_ROOT / "openreel_app"

MODEL_VOICE_WAV = DIR_VOICE_MODEL / "giong_mau.wav"
MODEL_REF_TEXT = DIR_VOICE_MODEL / "noi_dung_giong_mau.txt"
SYNC_VOICE_WAV = DIR_VOICE_CLONE / "giong_mau.wav"
SYNC_REF_TEXT = DIR_VOICE_CLONE / "noi_dung_giong_mau.txt"

FILE_STYLE_GUIDE = PROJECT_ROOT / "phong_cach_kenh.md"
FILE_SCRIPT = DIR_WORKSPACE / "kich_ban.txt"
FILE_EDIT_PLAN = DIR_WORKSPACE / "edit_plan.json"
FILE_TTS_WAV = DIR_READY / "02_giong_doc_ai.wav"
FILE_TTS_SRT = DIR_READY / "03_phu_de.srt"
FILE_DRAFT_MP4 = DIR_READY / "00_video_nhap_da_ghep.mp4"
FILE_CLIPS_MANIFEST = DIR_READY / "clips_manifest.json"
FILE_WEBAPP_CONFIG = DIR_WORKSPACE / "webapp_config.json"
FILE_OPENREEL_HOOK_MD = DIR_WORKSPACE / "openreel_hook_cta.md"
FILE_DIRECTOR_PLAN = DIR_WORKSPACE / "director_plan.json"
FILE_CRITIC_MD = DIR_WORKSPACE / "ai_critic_report.md"


def refresh_app_project_paths() -> None:
    global ACTIVE_PROJECT_ID, ACTIVE_PROJECT_ROOT
    global DIR_VIDEO_THO, DIR_WORKSPACE, DIR_FRAMES, DIR_READY, DIR_CLIPS, DIR_OUTPUT
    global FILE_SCRIPT, FILE_EDIT_PLAN, FILE_TTS_WAV, FILE_TTS_SRT, FILE_DRAFT_MP4, FILE_CLIPS_MANIFEST, FILE_WEBAPP_CONFIG
    global FILE_CRITIC_REPORT, FILE_SCRIPT_OPTIONS, FILE_VOICE_BEATS
    global FILE_OPENREEL_HOOK_MD, FILE_DIRECTOR_PLAN, FILE_CRITIC_MD
    global FILE_DEFAULT_OUTPUT, FILE_PREVIEW_FRAMES_DIR, FILE_REMOTION_PROPS
    ACTIVE_PROJECT_ID = get_active_project_id()
    ACTIVE_PROJECT_ROOT = get_project_root(ACTIVE_PROJECT_ID)
    pm_ensure_project_dirs(ACTIVE_PROJECT_ROOT)
    DIR_VIDEO_THO = ACTIVE_PROJECT_ROOT / "02_video_tho"
    DIR_WORKSPACE = ACTIVE_PROJECT_ROOT / "04_workspace"
    DIR_FRAMES = DIR_WORKSPACE / "frames"
    DIR_READY = DIR_WORKSPACE / "ready_for_openreel"
    DIR_CLIPS = DIR_READY / "01_clips"
    DIR_OUTPUT = ACTIVE_PROJECT_ROOT / "05_output"
    FILE_SCRIPT = DIR_WORKSPACE / "kich_ban.txt"
    FILE_EDIT_PLAN = DIR_WORKSPACE / "edit_plan.json"
    FILE_TTS_WAV = DIR_READY / "02_giong_doc_ai.wav"
    FILE_TTS_SRT = DIR_READY / "03_phu_de.srt"
    FILE_DRAFT_MP4 = DIR_READY / "00_video_nhap_da_ghep.mp4"
    FILE_CLIPS_MANIFEST = DIR_READY / "clips_manifest.json"
    FILE_WEBAPP_CONFIG = DIR_WORKSPACE / "webapp_config.json"
    FILE_CRITIC_REPORT = DIR_WORKSPACE / "ai_critic_report.md"
    FILE_SCRIPT_OPTIONS = DIR_WORKSPACE / "script_options.json"
    FILE_VOICE_BEATS = DIR_WORKSPACE / "voice_beats.json"
    FILE_OPENREEL_HOOK_MD = DIR_WORKSPACE / "openreel_hook_cta.md"
    FILE_DIRECTOR_PLAN = DIR_WORKSPACE / "director_plan.json"
    FILE_CRITIC_MD = DIR_WORKSPACE / "ai_critic_report.md"
    FILE_DEFAULT_OUTPUT = DIR_OUTPUT / "final_tiktok.mp4"
    FILE_PREVIEW_FRAMES_DIR = DIR_WORKSPACE / "render_preview_frames"
    FILE_REMOTION_PROPS = DIR_WORKSPACE / "remotion_props.json"
    _refresh_renderer_paths(ACTIVE_PROJECT_ROOT)

MEDIA_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
    ".m4v",
    ".wav",
    ".mp3",
    ".m4a",
    ".flac",
    ".ogg",
    ".aac",
}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}

PROTECTED_ROOT_PREFIXES = (
    "openreel_app",
    "scripts",
    ".agents",
    "03_voice_clone/venv",
)
PROTECTED_EXACT_FILES = {
    "03_voice_clone/model/model_last.pt",
    "03_voice_clone/model/vocab.txt",
    "03_voice_clone/model/config.json",
}

DEFAULT_CONFIG = {
    "cobalt_url": "https://api.cobalt.tools/",
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
    "gemini_effort": "medium",
    "agy_model": "gemini-3.8-flash-medium",
    "agy_effort": "medium",
}

GEMINI_EFFORT_BUDGET = {
    "low": 512,
    "medium": 2048,
    "high": 8192,
}

AGY_EFFORT_LEVELS = {"low", "medium", "high", "xhigh", "max"}

_openreel_proc: subprocess.Popen[Any] | None = None
_gpu_name_cache: str | None = None
_agy_models_cache: list[dict[str, str]] | None = None
_last_explorer_req: tuple[str, bool, float] | None = None


def configure_runtime_paths() -> None:
    """Thiết lập UTF-8 và bổ sung đường dẫn FFmpeg (WinGet) + CUDA DLL trên Windows."""
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUTF8"] = "1"

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


configure_runtime_paths()


def ensure_project_dirs() -> None:
    for d in (
        DIR_VIDEO_MAU,
        DIR_VIDEO_THO,
        DIR_VOICE_CLONE,
        DIR_VOICE_MODEL,
        DIR_WORKSPACE,
        DIR_FRAMES,
        DIR_READY,
        DIR_CLIPS,
        DIR_OUTPUT,
        STATIC_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)

    # Đồng bộ giọng mẫu sang 03_voice_clone/model/ nếu chưa có
    if not MODEL_VOICE_WAV.exists() and SYNC_VOICE_WAV.exists():
        shutil.copy2(SYNC_VOICE_WAV, MODEL_VOICE_WAV)
    if not MODEL_REF_TEXT.exists() and SYNC_REF_TEXT.exists():
        shutil.copy2(SYNC_REF_TEXT, MODEL_REF_TEXT)


ensure_project_dirs()


def find_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    raise RuntimeError(f"Không tìm thấy '{name}'. Hãy kiểm tra lại cài đặt FFmpeg.")


def to_rel_posix(path: Path) -> str:
    resolved = path.resolve()
    proj_resolved = ACTIVE_PROJECT_ROOT.resolve()
    if resolved == proj_resolved or resolved.is_relative_to(proj_resolved):
        return resolved.relative_to(proj_resolved).as_posix()
    return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()


def resolve_safe_path(rel_path: str) -> Path:
    cleaned = rel_path.strip().replace("\\", "/").lstrip("/")
    top_seg = cleaned.split("/", 1)[0]
    base_dir = ACTIVE_PROJECT_ROOT if top_seg in PROJECT_SCOPED_ROOTS else PROJECT_ROOT
    target = (base_dir / cleaned).resolve()
    root = base_dir.resolve()
    if target != root and not target.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Đường dẫn không hợp lệ (ngoài thư mục dự án).")
    return target


def assert_mutable_path(target: Path) -> None:
    rel = to_rel_posix(target)
    for prefix in PROTECTED_ROOT_PREFIXES:
        if rel == prefix or rel.startswith(prefix + "/"):
            raise HTTPException(status_code=403, detail=f"Không được phép chỉnh sửa vùng hệ thống: {rel}")
    if rel in PROTECTED_EXACT_FILES:
        raise HTTPException(status_code=403, detail=f"Không được phép xóa/ghi đè model cốt lõi: {rel}")


def sanitize_filename(name: str, fallback: str = "media") -> str:
    """Chuẩn hóa tên file an toàn (ASCII không dấu, không ký tự đặc biệt gây lỗi đường dẫn)."""
    normalized = unicodedata.normalize("NFKD", name or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[^\w\-. ]+", "_", ascii_text)
    ascii_text = re.sub(r"\s+", "_", ascii_text).strip("._-")
    if not ascii_text:
        return f"{fallback}_{int(time.time())}"
    return ascii_text[:80]


def probe_media(path: Path) -> dict[str, Any]:
    """Lấy metadata video/audio qua ffprobe."""
    stat = path.stat()
    try:
        rel = to_rel_posix(path)
        url = f"/files/{rel}"
    except ValueError:
        rel = str(path)
        url = ""
    info: dict[str, Any] = {
        "name": path.name,
        "rel_path": rel,
        "url": url,
        "size_bytes": stat.st_size,
        "size_mb": round(stat.st_size / (1024 * 1024), 2),
        "mtime": int(stat.st_mtime),
        "ext": path.suffix.lower(),
        "kind": "video" if path.suffix.lower() in VIDEO_EXTENSIONS else "audio",
        "duration_sec": 0.0,
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "sample_rate": 0,
        "channels": 0,
        "audio_codec": "",
        "video_codec": "",
    }
    try:
        ffprobe_bin = find_binary("ffprobe")
        res = subprocess.run(
            [
                ffprobe_bin,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=True,
        )
        data = json.loads(res.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        dur = float(fmt.get("duration") or 0.0)
        if dur == 0.0 and v_stream and v_stream.get("duration"):
            dur = float(v_stream["duration"])
        elif dur == 0.0 and a_stream and a_stream.get("duration"):
            dur = float(a_stream["duration"])
        info["duration_sec"] = round(dur, 2)

        if v_stream:
            info["width"] = int(v_stream.get("width") or 0)
            info["height"] = int(v_stream.get("height") or 0)
            info["video_codec"] = str(v_stream.get("codec_name") or "")
            r_fps = v_stream.get("r_frame_rate", "")
            if "/" in r_fps:
                num, den = r_fps.split("/", 1)
                try:
                    info["fps"] = round(float(num) / float(den or 1), 2)
                except ZeroDivisionError:
                    pass
        if a_stream:
            info["sample_rate"] = int(a_stream.get("sample_rate") or 0)
            info["channels"] = int(a_stream.get("channels") or 0)
            info["audio_codec"] = str(a_stream.get("codec_name") or "")
    except Exception:
        pass
    return info


def list_media_in_dir(target_dir: Path) -> list[dict[str, Any]]:
    if not target_dir.exists() or not target_dir.is_dir():
        return []
    files = [
        p
        for p in sorted(target_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
        if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS
    ]
    return [probe_media(p) for p in files]


def load_config() -> dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if FILE_WEBAPP_CONFIG.exists():
        try:
            stored = json.loads(FILE_WEBAPP_CONFIG.read_text(encoding="utf-8-sig"))
            if isinstance(stored, dict):
                cfg.update(stored)
        except Exception:
            pass
    return cfg


def save_config(cfg: dict[str, Any]) -> dict[str, Any]:
    merged = load_config()
    merged.update(cfg)
    FILE_WEBAPP_CONFIG.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return merged


def patch_av_open() -> None:
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


def transcribe_wav_with_faster_whisper(wav_path: Path, model_size: str = "small") -> tuple[str, str]:
    """Nhận diện tiếng Việt từ file wav bằng Faster-Whisper (ưu tiên GPU CUDA float16) và giải phóng VRAM ngay."""
    patch_av_open()
    from faster_whisper import WhisperModel
    import voice_engine as _ve

    use_cuda = False
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0 and _ve._preload_cuda_dlls():
            use_cuda = True
    except Exception:
        use_cuda = False

    model = None
    backend_used = "CPU (int8)"
    if use_cuda:
        for compute_type in ("float16", "int8_float16", "int8"):
            try:
                model = WhisperModel(model_size, device="cuda", compute_type=compute_type)
                backend_used = f"CUDA ({compute_type})"
                break
            except Exception:
                model = None
    if model is None:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")

    try:
        try:
            segments, _ = model.transcribe(
                str(wav_path),
                language="vi",
                beam_size=5,
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()
        except Exception:
            del model
            gc.collect()
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            backend_used = "CPU (int8 fallback)"
            segments, _ = model.transcribe(
                str(wav_path),
                language="vi",
                beam_size=5,
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()
    finally:
        del model
        gc.collect()
        torch_mod = sys.modules.get("torch")
        if torch_mod is not None:
            try:
                if torch_mod.cuda.is_available():
                    torch_mod.cuda.empty_cache()
            except Exception:
                pass

    return text, backend_used


def sync_voice_clone_files() -> None:
    """Đồng bộ giữa 03_voice_clone/model/ và 03_voice_clone/ để CLI và Webapp luôn nhất quán."""
    DIR_VOICE_PROFILES.mkdir(parents=True, exist_ok=True)
    if MODEL_VOICE_WAV.exists():
        shutil.copy2(MODEL_VOICE_WAV, SYNC_VOICE_WAV)
    if MODEL_REF_TEXT.exists():
        shutil.copy2(MODEL_REF_TEXT, SYNC_REF_TEXT)


def _slug_voice_id(name: str) -> str:
    norm = unicodedata.normalize("NFD", (name or "").replace("đ", "d").replace("Đ", "D"))
    ascii_str = "".join(ch for ch in norm if unicodedata.category(ch) != "Mn")
    slug = re.sub(r"[^a-z0-9_-]+", "_", ascii_str.lower()).strip("_-")
    return slug[:40] or f"voice_{int(time.time())}"


def _resolve_voice_target(
    profile_name: str = "",
    save_dir: str = "",
    filename: str = "",
) -> tuple[Path, Path, bool]:
    s_dir = (save_dir or "").strip()
    f_name = (filename or "").strip()
    p_name = (profile_name or "").strip()

    if s_dir.lower() in ("default", "giong_mau", "chinh", "03_voice_clone/model"):
        return MODEL_VOICE_WAV, MODEL_REF_TEXT, True

    if s_dir:
        target_dir = resolve_safe_path(s_dir)
        assert_mutable_path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        raw_stem = f_name or p_name or f"voice_{time.strftime('%Y%m%d_%H%M%S')}"
        slug = _slug_voice_id(Path(raw_stem).stem)
        return target_dir / f"{slug}.wav", target_dir / f"{slug}.txt", False

    clean = f_name or p_name
    if not clean or clean.lower() in ("default", "giong_mau", "chinh"):
        return MODEL_VOICE_WAV, MODEL_REF_TEXT, True
    DIR_VOICE_PROFILES.mkdir(parents=True, exist_ok=True)
    slug = _slug_voice_id(Path(clean).stem)
    return DIR_VOICE_PROFILES / f"{slug}.wav", DIR_VOICE_PROFILES / f"{slug}.txt", False


def _resolve_profile_in_voices(profile_id: str) -> Path:
    clean = (profile_id or "").strip().lstrip("/")
    if not clean or ".." in clean:
        raise HTTPException(status_code=400, detail="Mã giọng không hợp lệ.")
    cand = (DIR_VOICE_PROFILES / f"{clean}.wav").resolve()
    root_resolved = DIR_VOICE_PROFILES.resolve()
    if not cand.is_relative_to(root_resolved):
        raise HTTPException(status_code=403, detail="Đường dẫn ngoài thư mục voices.")
    return cand


def list_voice_save_directories() -> list[dict[str, str]]:
    """List folders where users can save extracted or recorded audio files."""
    roots = [
        ("03_voice_clone/voices", "Kho Giọng Đa Kênh (03_voice_clone/voices)"),
        ("06_assets_audio", "Kho Nhạc & SFX (06_assets_audio)"),
        ("02_video_tho", "Nguyên liệu (02_video_tho)"),
        ("04_workspace", "Workspace tạm (04_workspace)"),
    ]
    result: list[dict[str, str]] = []
    for folder_name, label in roots:
        base = PROJECT_ROOT / folder_name
        base.mkdir(parents=True, exist_ok=True)
        result.append({"rel_path": folder_name, "label": label})
        for sub in sorted(base.rglob("*")):
            if sub.is_dir() and not sub.name.startswith(".") and sub.name not in ("frames", "ready_for_openreel", "render_preview_frames"):
                rel = to_rel_posix(sub)
                result.append({"rel_path": rel, "label": f"  └─ {rel}"})
    return result


def list_voice_profiles() -> list[dict[str, Any]]:
    """Discover default voice plus all speaker profiles inside 03_voice_clone/voices/ (including subfolders)."""
    DIR_VOICE_PROFILES.mkdir(parents=True, exist_ok=True)
    profiles: list[dict[str, Any]] = []
    if MODEL_VOICE_WAV.exists():
        meta = probe_media(MODEL_VOICE_WAV)
        ref_t = MODEL_REF_TEXT.read_text(encoding="utf-8-sig").strip() if MODEL_REF_TEXT.exists() else ""
        profiles.append(
            {
                "id": "default",
                "name": "Giọng Mẫu Chính (giong_mau.wav)",
                "wav_path": str(MODEL_VOICE_WAV),
                "ref_text_path": str(MODEL_REF_TEXT) if MODEL_REF_TEXT.exists() else "",
                "ref_text": ref_t,
                "duration_sec": meta.get("duration_sec", 0.0),
                "url": f"/files/03_voice_clone/model/giong_mau.wav?t={meta.get('mtime', int(time.time()))}",
                "is_default": True,
            }
        )
    for wp in sorted(DIR_VOICE_PROFILES.rglob("*")):
        if wp.is_file() and wp.suffix.lower() in (".wav", ".mp3", ".m4a", ".flac"):
            txt_cand = wp.with_suffix(".txt")
            meta = probe_media(wp)
            ref_t = txt_cand.read_text(encoding="utf-8-sig").strip() if txt_cand.exists() else ""
            rel_id = wp.relative_to(DIR_VOICE_PROFILES).with_suffix("").as_posix()
            rel_url = to_rel_posix(wp)
            profiles.append(
                {
                    "id": rel_id,
                    "name": rel_id,
                    "wav_path": str(wp),
                    "ref_text_path": str(txt_cand) if txt_cand.exists() else "",
                    "ref_text": ref_t,
                    "duration_sec": meta.get("duration_sec", 0.0),
                    "url": f"/files/{rel_url}?t={meta.get('mtime', int(time.time()))}",
                    "is_default": False,
                }
            )
    return profiles


def get_voice_status_payload() -> dict[str, Any]:
    wav_info = probe_media(MODEL_VOICE_WAV) if MODEL_VOICE_WAV.exists() else None
    if wav_info:
        wav_info["url"] = f"/files/03_voice_clone/model/giong_mau.wav?t={wav_info['mtime']}"
    ref_text = ""
    if MODEL_REF_TEXT.exists():
        ref_text = MODEL_REF_TEXT.read_text(encoding="utf-8-sig").strip()
    elif SYNC_REF_TEXT.exists():
        ref_text = SYNC_REF_TEXT.read_text(encoding="utf-8-sig").strip()
    return {
        "exists": MODEL_VOICE_WAV.exists(),
        "wav": wav_info,
        "ref_text": ref_text,
        "profiles": list_voice_profiles(),
        "model_ready": (DIR_VOICE_MODEL / "model_last.pt").exists()
        and (DIR_VOICE_MODEL / "vocab.txt").exists(),
    }


def run_python_script(
    script_rel: str, args: list[str], timeout: int = 900
) -> dict[str, Any]:
    script_path = (PROJECT_ROOT / script_rel).resolve()
    cmd = [sys.executable, str(script_path), *args]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["TIKTOK_PROJECT_ID"] = ACTIVE_PROJECT_ID
    res = subprocess.run(
        cmd,
        cwd=str(ACTIVE_PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    combined_log = (res.stdout or "") + ("\n" + res.stderr if res.stderr else "")
    return {
        "ok": res.returncode == 0,
        "returncode": res.returncode,
        "command": " ".join(cmd),
        "log": combined_log.strip(),
    }


def is_port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    hosts = ("127.0.0.1", "::1") if host in ("127.0.0.1", "localhost", "::1") else (host,)
    for candidate in hosts:
        try:
            with socket.create_connection((candidate, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def get_gpu_name() -> str:
    global _gpu_name_cache
    if _gpu_name_cache is not None:
        return _gpu_name_cache

    gpu_label = "CPU Mode"
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
        if res.returncode == 0 and res.stdout.strip():
            first_line = next((line.strip() for line in res.stdout.splitlines() if line.strip()), "")
            if first_line:
                gpu_label = first_line
    except Exception:
        if sys.platform == "darwin":
            import platform

            if platform.machine().lower() in ("arm64", "aarch64"):
                gpu_label = "Apple MPS"

    _gpu_name_cache = gpu_label
    return gpu_label


def count_media_in_dir(target_dir: Path) -> int:
    if not target_dir.exists() or not target_dir.is_dir():
        return 0
    return sum(
        1
        for p in target_dir.iterdir()
        if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS
    )


def list_selectable_directories() -> list[dict[str, str]]:
    """Liệt kê các thư mục đích để lưu video/audio trong Tab 1 và duyệt file."""
    roots = [("01_video_mau", "Video mẫu (01_video_mau)"), ("02_video_tho", "Video thô (02_video_tho)")]
    result: list[dict[str, str]] = []
    for folder_name, label in roots:
        base = PROJECT_ROOT / folder_name
        base.mkdir(parents=True, exist_ok=True)
        result.append({"rel_path": folder_name, "label": label})
        for sub in sorted(base.rglob("*")):
            if sub.is_dir():
                rel = to_rel_posix(sub)
                result.append({"rel_path": rel, "label": f"  └─ {rel}"})
    return result


def convert_to_wav_24k_mono(src_path: Path, dst_wav: Path, trim_silence: bool = False) -> None:
    ffmpeg_bin = find_binary("ffmpeg")
    if trim_silence:
        af = (
            "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB,"
            "areverse,silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB,areverse"
        )
        try:
            subprocess.run(
                [
                    ffmpeg_bin,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(src_path),
                    "-vn",
                    "-af",
                    af,
                    "-acodec",
                    "pcm_s16le",
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    str(dst_wav),
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            info = probe_media(dst_wav)
            if info["duration_sec"] >= 0.4:
                return
        except Exception:
            pass

    subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "24000",
            "-ac",
            "1",
            str(dst_wav),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def convert_to_mp4(src_path: Path, dst_mp4: Path) -> None:
    info = probe_media(src_path)
    vcodec = str(info.get("video_codec") or "").lower()
    if src_path.suffix.lower() == ".mp4" and vcodec in ("h264", "avc1"):
        shutil.move(str(src_path), str(dst_mp4))
        return
    ffmpeg_bin = find_binary("ffmpeg")
    subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src_path),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(dst_mp4),
        ],
        check=True,
    )


def download_via_tikwm(url: str, target_dir: Path, mode: str) -> dict[str, Any]:
    resp = requests.post(
        "https://www.tikwm.com/api/",
        data={"url": url, "hd": 1},
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
        timeout=20,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"TikWM HTTP {resp.status_code}")
    payload = resp.json()
    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
        raise RuntimeError(f"TikWM lỗi: {payload.get('msg') or payload}")

    data = payload["data"]
    if mode == "audio":
        media_url = data.get("music") or data.get("play") or data.get("hdplay")
    else:
        media_url = data.get("hdplay") or data.get("play") or data.get("wmplay")

    if not media_url:
        raise RuntimeError("TikWM không trả về liên kết tải media.")

    ts = int(time.time())
    safe_stem = sanitize_filename(data.get("title") or f"tiktok_{data.get('id', ts)}", fallback=f"tiktok_{ts}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_dl = Path(tmpdir) / f"{safe_stem}.mp4"
        with requests.get(
            media_url,
            stream=True,
            timeout=60,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        ) as r:
            r.raise_for_status()
            with open(tmp_dl, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

        if mode == "audio":
            out_path = target_dir / f"{safe_stem}.wav"
            if out_path.exists():
                out_path = target_dir / f"{safe_stem}_{ts}.wav"
            convert_to_wav_24k_mono(tmp_dl, out_path, trim_silence=False)
        else:
            out_path = target_dir / f"{safe_stem}.mp4"
            if out_path.exists():
                out_path = target_dir / f"{safe_stem}_{ts}.mp4"
            convert_to_mp4(tmp_dl, out_path)

    return {
        "ok": True,
        "engine": "tikwm",
        "url": url,
        "file": probe_media(out_path),
    }


def download_via_cobalt(
    url: str, cobalt_url: str, target_dir: Path, mode: str
) -> dict[str, Any]:
    endpoint = cobalt_url.strip()
    if not endpoint:
        raise RuntimeError("Cobalt API URL đang để trống.")

    payload = {
        "url": url,
        "downloadMode": "audio" if mode == "audio" else "auto",
        "videoQuality": "1080",
        "filenameStyle": "basic",
    }
    timeout = 5 if "localhost" in endpoint or "127.0.0.1" in endpoint else 10
    resp = requests.post(
        endpoint,
        json=payload,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "TikTokOpenReelAI/1.0",
        },
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Cobalt HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    status = data.get("status")
    media_url = data.get("url")
    if status not in ("tunnel", "redirect", "stream") or not media_url:
        if status == "picker" and data.get("picker"):
            media_url = data["picker"][0].get("url")
        if not media_url:
            raise RuntimeError(f"Cobalt trả về trạng thái '{status}': {data.get('error', data)}")

    raw_name = data.get("filename") or Path(urlparse(media_url).path).name or f"cobalt_{int(time.time())}"
    stem = sanitize_filename(Path(unquote(raw_name)).stem, fallback="cobalt_media")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_dl = Path(tmpdir) / f"{stem}_raw.bin"
        with requests.get(media_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            cd = r.headers.get("Content-Disposition", "")
            ct = r.headers.get("Content-Type", "").lower()
            ext = ".mp4"
            if "filename=" in cd:
                ext = Path(cd.split("filename=")[-1].strip('"; ')).suffix or ext
            elif "audio" in ct or mode == "audio":
                ext = ".mp3" if "mpeg" in ct else ".wav"
            tmp_dl = Path(tmpdir) / f"{stem}{ext}"
            with open(tmp_dl, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

        if mode == "audio":
            out_path = target_dir / f"{stem}.wav"
            if out_path.exists():
                out_path = target_dir / f"{stem}_{int(time.time())}.wav"
            convert_to_wav_24k_mono(tmp_dl, out_path, trim_silence=False)
        else:
            out_path = target_dir / f"{stem}.mp4"
            if out_path.exists():
                out_path = target_dir / f"{stem}_{int(time.time())}.mp4"
            convert_to_mp4(tmp_dl, out_path)

    return {
        "ok": True,
        "engine": "cobalt",
        "url": url,
        "file": probe_media(out_path),
    }


def download_via_ytdlp(url: str, target_dir: Path, mode: str) -> dict[str, Any]:
    import yt_dlp

    ffmpeg_dir = str(Path(find_binary("ffmpeg")).parent)
    ts = int(time.time())

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        outtmpl = str(tmp_path / "%(title).80B_%(id)s.%(ext)s")

        ydl_opts: dict[str, Any] = {
            "outtmpl": outtmpl,
            "ffmpeg_location": ffmpeg_dir,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "restrictfilenames": True,
            "windowsfilenames": True,
            "overwrites": True,
            "nocheckcertificate": True,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                )
            },
        }
        if mode == "audio":
            ydl_opts["format"] = "bestaudio/best"
        else:
            ydl_opts["format"] = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
            ydl_opts["merge_output_format"] = "mp4"

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        downloaded_files = [p for p in tmp_path.iterdir() if p.is_file() and p.stat().st_size > 0]
        if not downloaded_files:
            raise RuntimeError("yt-dlp không tải được tệp đầu ra nào.")

        src_file = max(downloaded_files, key=lambda p: p.stat().st_size)
        raw_title = (info.get("title") if isinstance(info, dict) else None) or src_file.stem
        safe_stem = sanitize_filename(raw_title, fallback=f"video_{ts}")

        if mode == "audio":
            out_path = target_dir / f"{safe_stem}.wav"
            if out_path.exists():
                out_path = target_dir / f"{safe_stem}_{ts}.wav"
            convert_to_wav_24k_mono(src_file, out_path, trim_silence=False)
        else:
            src_info = probe_media(src_file)
            if not src_info.get("width") or not src_info.get("height"):
                raise RuntimeError("yt-dlp chỉ lấy được luồng âm thanh (không có video).")
            out_path = target_dir / f"{safe_stem}.mp4"
            if out_path.exists():
                out_path = target_dir / f"{safe_stem}_{ts}.mp4"
            convert_to_mp4(src_file, out_path)

    return {
        "ok": True,
        "engine": "yt-dlp",
        "url": url,
        "file": probe_media(out_path),
    }


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class ConfigUpdateReq(BaseModel):
    cobalt_url: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    gemini_effort: str | None = Field(default=None, pattern="^(low|medium|high)$")
    agy_model: str | None = None
    agy_effort: str | None = Field(default=None, pattern="^(low|medium|high|xhigh|max)$")


class AgyTestReq(BaseModel):
    model: str | None = None
    effort: str | None = Field(default=None, pattern="^(low|medium|high|xhigh|max)$")


class AgyStyleAnalyzeReq(BaseModel):
    model: str | None = None
    effort: str | None = Field(default=None, pattern="^(low|medium|high|xhigh|max)$")


class AgyWorkshopPlanReq(BaseModel):
    product_note: str = ""
    target_duration: float = 30.0
    preserve_clips: bool = True
    short_content_mode: str = "brand_brief"
    model: str | None = None
    effort: str | None = Field(default=None, pattern="^(low|medium|high|xhigh|max)$")


class OpenReelBuildReq(BaseModel):
    project_name: str = ""
    hook_text: str = ""
    cta_text: str = ""
    hook_y: float = 0.18
    hook_font_size: int = 56
    hook_color: str = "#FFFFFF"
    hook_stroke_color: str = "#000000"
    caption_style: str = Field(default="word-highlight", pattern="^(none|word-highlight|word-by-word|karaoke|bounce|typewriter)$")
    caption_color: str = "#FFFFFF"
    caption_highlight_color: str = "#FFE500"
    transition_type: str = "slide"
    use_ai_hook: bool = False


class GeminiTestReq(BaseModel):
    api_key: str | None = None
    model: str | None = None
    effort: str | None = Field(default=None, pattern="^(low|medium|high)$")


class GeminiStyleAnalyzeReq(BaseModel):
    model: str | None = None
    effort: str | None = Field(default=None, pattern="^(low|medium|high)$")


class GeminiWorkshopPlanReq(BaseModel):
    product_note: str = ""
    target_duration: float = 30.0
    preserve_clips: bool = True
    transition_level: str = "balanced"
    short_content_mode: str = "brand_brief"
    model: str | None = None
    effort: str | None = Field(default=None, pattern="^(low|medium|high)$")


class RemotionRenderReq(BaseModel):
    badge_style: str = "floral_plus_callouts"
    visual_theme: str = "auto"
    layout_style: str = "full"
    color_preset: str = "natural"
    creative_mode: str = "breakthrough_ai"
    camera_intensity: str = "dynamic_ai"
    bgm_track: str = "bgm_upbeat_tiktok.wav"
    brand: str = ""
    product_line: str = ""
    category: str = ""
    hook_text: str = ""
    cta_text: str = ""
    hook_y: float = 0.16
    subtitle_active_color: str = "#FFE500"
    bgm_volume: float | None = None
    render_engine: str = "remotion_classic"
    innovation_preset: str = "kinetic_pop"
    transition_level: str = "balanced"
    disable_flash_shake: bool = True
    icon_density: str = "balanced"
    sticker_density: str = "normal"
    sfx_level: str = "subtle"
    aspect_ratio: str = "9:16"
    content_vibe: str = "learned_dna"


class RemotionAiEditReq(BaseModel):
    instruction: str
    auto_render: bool = True


class BrandBriefReq(BaseModel):
    target_duration_sec: float = 25.0
    raw_brief: str = ""
    brand: str = ""
    product_line: str = ""
    category: str = ""
    usps: str = ""
    offer_cta: str = ""
    banned_words: str = ""
    phonetic_map: dict[str, str] = Field(default_factory=dict)


class BrandBriefExtractReq(BaseModel):
    raw_brief: str
    target_duration_sec: float = 25.0


class OneClickPipelineReq(BaseModel):
    target_duration_sec: float = 30.0
    product_note: str = ""
    regenerate_script: bool = False
    force_tts: bool = False
    preserve_clips: bool = True
    selected_option_id: str = ""
    batch_all_scripts: bool = False
    mix_variants: bool = True
    badge_style: str = "floral_plus_callouts"
    visual_theme: str = "auto"
    layout_style: str = "full"
    color_preset: str = "natural"
    creative_mode: str = "breakthrough_ai"
    camera_intensity: str = "dynamic_ai"
    bgm_track: str = "bgm_upbeat_tiktok.wav"
    render_engine: str = "remotion_classic"
    innovation_preset: str = "kinetic_pop"
    transition_level: str = "balanced"
    disable_flash_shake: bool = True
    icon_density: str = "balanced"
    sticker_density: str = "normal"
    sticker_style: str = "pill_minimal"
    mix_engines: bool = False
    creative_wildcard: bool = False
    tts_engine: str = "edge_tts"
    edge_voice: str = "vi-VN-HoaiMyNeural"
    voice_preset: str = "random_neural"
    sfx_level: str = "subtle"
    aspect_ratio: str = "9:16"
    content_vibe: str = "learned_dna"
    short_content_mode: str = "brand_brief"
    pipeline_category: str = "short_tiktok"
    ordered_clips: list[str] = Field(default_factory=list)
    keep_clip_audio: bool = False
    auto_fit_duration: bool = False
    quality_preset: str = "auto_source"
    vlog_title: str = ""
    preserve_longform_script: bool = False
    longform_random_mode: bool = False
    longform_random_count: int = 1
    mute_voice: bool = False
    hide_subtitles: bool = False
    subtitle_lang: str = "vi"
    pacing_preset: str = "auto"
    enable_motion_zoom: bool = False
    disable_vibe_filter: bool = False
    disclaimer_enabled: bool = False
    disclaimer_text: str = ""
    face_blur_enabled: bool = False
    face_blur_mode: str = "blur_selected"
    face_blur_style: str = "gaussian"
    face_blur_icon: str = "cool"
    face_blur_padding: float = 1.25
    face_blur_ids: list[str] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)
    project_configs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    sync: bool = False


class SelectScriptReq(BaseModel):
    option_id: str = "opt1"
    custom_script_display: str = ""
    custom_script_text: str = ""
    target_duration_sec: float | None = None
    preserve_clips: bool = True
    auto_export_mp4: bool = False
    badge_style: str = "floral_plus_callouts"
    visual_theme: str = "auto"
    layout_style: str = "full"
    color_preset: str = "natural"
    creative_mode: str = "breakthrough_ai"
    camera_intensity: str = "dynamic_ai"
    bgm_track: str = "bgm_upbeat_tiktok.wav"


class MkdirReq(BaseModel):
    parent_dir: str = "02_video_tho"
    folder_name: str


class RenameFileReq(BaseModel):
    rel_path: str
    new_name: str


class DeleteFileReq(BaseModel):
    rel_path: str


class OpenExplorerReq(BaseModel):
    rel_path: str = "04_workspace/ready_for_openreel"
    select_file: bool = False
    project_id: str = ""


class DownloadReq(BaseModel):
    urls: list[str]
    target_dir: str = "02_video_tho"
    mode: str = Field(default="video", pattern="^(video|audio)$")
    cobalt_url: str | None = None


class RefTextSaveReq(BaseModel):
    ref_text: str


class ExtractVoiceReq(BaseModel):
    source_path: str
    start: float = 0.0
    end: float = 10.0
    auto_transcribe: bool = True
    profile_name: str = ""
    save_dir: str = ""
    filename: str = ""


class VoiceProfileIdReq(BaseModel):
    profile_id: str


class VoiceProfileRefTextReq(BaseModel):
    profile_id: str
    ref_text: str


class StyleExtractReq(BaseModel):
    fps: float = 1.0
    whisper_model: str = "small"


class StyleGuideSaveReq(BaseModel):
    content: str


class TtsGenerateReq(BaseModel):
    script_text: str
    speed: float = 1.05
    nfe_step: int = 32
    whisper_model: str = "small"


class SrtSaveReq(BaseModel):
    content: str


class PrepareClipsReq(BaseModel):
    edit_plan: dict[str, Any]
    concat: bool = True


# ---------------------------------------------------------------------------
# FastAPI App & Static Mounts (Zero-Copy Local Architecture)
# ---------------------------------------------------------------------------

app = FastAPI(title="TikTok OpenReel AI - Local Dashboard", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DIR_FRAMES_MAU.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/01_video_mau", StaticFiles(directory=str(DIR_VIDEO_MAU)), name="dir_01_video_mau")
app.mount("/style_frames", StaticFiles(directory=str(DIR_FRAMES_MAU)), name="dir_style_frames")
app.mount("/02_video_tho", StaticFiles(directory=str(DIR_VIDEO_THO)), name="dir_02_video_tho")
app.mount("/03_voice_clone", StaticFiles(directory=str(DIR_VOICE_CLONE)), name="dir_03_voice_clone")
app.mount("/04_workspace", StaticFiles(directory=str(DIR_WORKSPACE)), name="dir_04_workspace")
app.mount("/05_output", StaticFiles(directory=str(DIR_OUTPUT)), name="dir_05_output")


@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy static/index.html")
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


@app.get("/files/{rel_path:path}")
def serve_local_file(rel_path: str):
    target = resolve_safe_path(rel_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file: {rel_path}")
    return FileResponse(str(target))


# ---------------------------------------------------------------------------
# System & File Management APIs
# ---------------------------------------------------------------------------


def get_public_config() -> dict[str, Any]:
    cfg = load_config()
    raw_key = str(cfg.get("gemini_api_key") or "").strip()
    masked = ""
    if raw_key:
        masked = f"{raw_key[:6]}...{raw_key[-4:]}" if len(raw_key) > 12 else "***"
    return {
        "cobalt_url": cfg.get("cobalt_url", DEFAULT_CONFIG["cobalt_url"]),
        "gemini_model": cfg.get("gemini_model", DEFAULT_CONFIG["gemini_model"]),
        "gemini_effort": cfg.get("gemini_effort", DEFAULT_CONFIG["gemini_effort"]),
        "gemini_api_key_set": bool(raw_key),
        "gemini_api_key_masked": masked,
        "agy_model": cfg.get("agy_model", DEFAULT_CONFIG["agy_model"]),
        "agy_effort": cfg.get("agy_effort", DEFAULT_CONFIG["agy_effort"]),
    }


def find_agy_executable() -> str | None:
    found = shutil.which("agy")
    if found:
        return found
    candidates = [
        Path(os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.EXE")),
        Path(os.path.expandvars(r"%USERPROFILE%\.gemini\bin\agy.exe")),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def list_agy_models(force_refresh: bool = False) -> list[dict[str, str]]:
    global _agy_models_cache
    if _agy_models_cache is not None and not force_refresh:
        return _agy_models_cache
    agy_exe = find_agy_executable()
    fallback = [
        {"id": "gemini-3.8-flash-medium", "label": "Gemini 3.8 Flash (Medium)"},
        {"id": "gemini-3.8-flash-high", "label": "Gemini 3.8 Flash (High)"},
        {"id": "gemini-4-argon-medium", "label": "Gemini 4 Argon (Medium)"},
        {"id": "gemini-4-hydrogen-medium", "label": "Gemini 4 Hydrogen (Medium)"},
        {"id": "claude-sonnet-5-5-medium", "label": "Claude Sonnet 5.5 (Medium)"},
    ]
    if not agy_exe:
        return fallback
    try:
        res = subprocess.run(
            [agy_exe, "models"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        models: list[dict[str, str]] = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("fetching"):
                continue
            if "\t" in line:
                mid, label = line.split("\t", 1)
                models.append({"id": mid.strip(), "label": label.strip()})
        if models:
            _agy_models_cache = models
            return models
    except Exception:
        pass
    return fallback


def call_agy_cli(
    prompt: str,
    *,
    model: str | None = None,
    effort: str | None = None,
    mode: str = "auto",
    disable_slash_commands: bool = False,
    timeout: int = 300,
) -> dict[str, Any]:
    agy_exe = find_agy_executable()
    if not agy_exe:
        raise HTTPException(
            status_code=400,
            detail="Không tìm thấy Antigravity CLI (`agy.exe`) trên máy. Hãy cài đặt Antigravity CLI hoặc dùng Gemini API Key.",
        )

    cmd: list[str] = [
        agy_exe,
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--mode",
        mode,
        "--dangerously-skip-permissions",
        "--print-timeout",
        f"{timeout}s",
    ]
    model_clean = model.strip() if model else ""
    if model_clean:
        cmd.extend(["--model", model_clean])
    has_effort_suffix = any(model_clean.endswith(f"-{lvl}") for lvl in AGY_EFFORT_LEVELS)
    if effort and effort.strip() in AGY_EFFORT_LEVELS and not has_effort_suffix:
        cmd.extend(["--effort", effort.strip()])
    if disable_slash_commands:
        cmd.append("--disable-slash-commands")

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout + 20,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail=f"Antigravity CLI vượt quá thời gian chờ ({timeout}s).",
        )

    result_payload: dict[str, Any] | None = None
    last_text_deltas: list[str] = []
    for raw_line in proc.stdout.splitlines():
        raw_line = raw_line.strip()
        if not raw_line.startswith("{"):
            continue
        try:
            ev = json.loads(raw_line)
        except Exception:
            continue
        if ev.get("event") == "step_update":
            su = ev.get("step_update") or {}
            if su.get("step_type") == "agent_response" and su.get("text_delta"):
                last_text_deltas.append(str(su["text_delta"]))
        elif ev.get("event") == "result" and isinstance(ev.get("result"), dict):
            result_payload = ev["result"]

    if proc.returncode != 0 and not result_payload:
        err = (proc.stderr or proc.stdout or "").strip()[:500]
        raise HTTPException(status_code=502, detail=f"Antigravity CLI lỗi (code {proc.returncode}): {err}")

    if result_payload and result_payload.get("status") not in (None, "SUCCESS"):
        raise HTTPException(
            status_code=502,
            detail=f"Antigravity CLI thất bại ({result_payload.get('status')}): {result_payload.get('error') or result_payload}",
        )

    response_text = ""
    duration_sec = None
    if result_payload:
        response_text = str(result_payload.get("response") or "").strip()
        duration_sec = result_payload.get("duration_seconds")
    if not response_text:
        response_text = "".join(last_text_deltas).strip()
    if "[agy] print timeout" in proc.stdout and not response_text:
        raise HTTPException(status_code=504, detail="Antigravity CLI hết thời gian chờ xử lý.")

    return {
        "response": response_text,
        "duration_seconds": duration_sec,
        "conversation_id": result_payload.get("conversation_id") if result_payload else None,
        "usage": result_payload.get("usage") if result_payload else None,
    }


def call_gemini_multimodal(
    parts: list[dict[str, Any]],
    *,
    api_key: str,
    model: str = "gemini-2.5-flash",
    effort: str = "medium",
    response_mime_type: str | None = None,
    timeout: int = 120,
) -> str:
    key = api_key.strip()
    if not key:
        raise HTTPException(
            status_code=400,
            detail="Chưa nhập Gemini API Key. Hãy bấm vào badge AI trên Header để nhập key hoặc dùng Antigravity (/hoc-phong-cach, /dung-tiktok).",
        )
    model_id = (model or "gemini-2.5-flash").strip()
    effort_key = effort if effort in GEMINI_EFFORT_BUDGET else "medium"

    gen_cfg: dict[str, Any] = {"temperature": 0.4}
    if response_mime_type:
        gen_cfg["responseMimeType"] = response_mime_type
    if any(tag in model_id for tag in ("2.5", "3")):
        gen_cfg["thinkingConfig"] = {"thinkingBudget": GEMINI_EFFORT_BUDGET[effort_key]}

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={key}"
    resp = requests.post(
        endpoint,
        json={"contents": [{"parts": parts}], "generationConfig": gen_cfg},
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    if resp.status_code >= 400:
        try:
            err_msg = resp.json().get("error", {}).get("message") or resp.text[:300]
        except Exception:
            err_msg = resp.text[:300]
        raise HTTPException(status_code=502, detail=f"Gemini API lỗi ({resp.status_code}): {err_msg}")

    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise HTTPException(status_code=502, detail=f"Gemini không trả về nội dung: {data}")
    out_parts = candidates[0].get("content", {}).get("parts") or []
    texts = [p.get("text", "") for p in out_parts if isinstance(p, dict) and p.get("text") and not p.get("thought")]
    if not texts:
        texts = [p.get("text", "") for p in out_parts if isinstance(p, dict) and p.get("text")]
    result = "\n".join(texts).strip()
    if not result:
        raise HTTPException(status_code=502, detail="Gemini trả về phản hồi rỗng.")
    return result


def select_representative_frames(frame_paths: list[Path], max_frames: int = 6) -> list[Path]:
    if len(frame_paths) <= max_frames:
        return frame_paths
    if max_frames <= 1:
        return [frame_paths[0]]
    # Luôn giữ 3 khung đầu (Hook 3s) + lấy đều phần còn lại tới cuối
    head = frame_paths[: min(3, max_frames)]
    rest = frame_paths[len(head) :]
    need = max_frames - len(head)
    if need <= 0 or not rest:
        return head
    step = max(1, len(rest) // need)
    sampled = [rest[i] for i in range(0, len(rest), step)][:need]
    if rest[-1] not in sampled and len(sampled) == need:
        sampled[-1] = rest[-1]
    return head + sampled


@app.get("/api/overview")
def api_overview():
    cfg = get_public_config()
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    voice_info = get_voice_status_payload()
    agy_path = find_agy_executable()
    agy_ok = bool(agy_path)
    mode_label = (
        "Local + Antigravity CLI"
        if agy_ok
        else ("Local + Gemini API" if cfg["gemini_api_key_set"] else "100% Local (Antigravity Chat)")
    )
    return {
        "project_root": str(PROJECT_ROOT),
        "gpu": get_gpu_name(),
        "ffmpeg_ready": ffmpeg_ok,
        "openreel_online": is_port_open("127.0.0.1", 5173),
        "openreel_url": "http://localhost:5173",
        "counts": {
            "01_video_mau": count_media_in_dir(DIR_VIDEO_MAU),
            "02_video_tho": count_media_in_dir(DIR_VIDEO_THO),
            "01_clips": count_media_in_dir(DIR_CLIPS),
            "05_output": count_media_in_dir(DIR_OUTPUT),
        },
        "voice": voice_info,
        "ai_models": {
            "tts": "hynt/F5-TTS-Vietnamese-100h" if voice_info.get("model_ready") else "F5-TTS-VN (Chưa tải)",
            "stt": "Faster-Whisper (CTranslate2)",
            "agent": "Antigravity CLI (agy.exe)" if agy_ok else "Antigravity Chat (/hoc-phong-cach, /dung-tiktok)",
            "agy_available": agy_ok,
            "agy_path": agy_path or "",
            "agy_model": cfg["agy_model"],
            "agy_effort": cfg["agy_effort"],
            "gemini_model": cfg["gemini_model"],
            "gemini_effort": cfg["gemini_effort"],
            "gemini_ready": cfg["gemini_api_key_set"],
            "mode": mode_label,
            "model_ready": bool(voice_info.get("model_ready")),
        },
        "config": cfg,
    }


@app.get("/api/config")
def api_get_config():
    return get_public_config()


@app.post("/api/config")
def api_save_config(req: ConfigUpdateReq):
    updates: dict[str, Any] = {}
    if req.cobalt_url is not None:
        updates["cobalt_url"] = req.cobalt_url.strip()
    if req.gemini_api_key is not None:
        updates["gemini_api_key"] = req.gemini_api_key.strip()
    if req.gemini_model is not None and req.gemini_model.strip():
        updates["gemini_model"] = req.gemini_model.strip()
    if req.gemini_effort is not None:
        updates["gemini_effort"] = req.gemini_effort
    if req.agy_model is not None and req.agy_model.strip():
        updates["agy_model"] = req.agy_model.strip()
    if req.agy_effort is not None:
        updates["agy_effort"] = req.agy_effort
    save_config(updates)
    return get_public_config()


@app.get("/api/ai/agy-models")
def api_agy_models(refresh: bool = False):
    agy_exe = find_agy_executable()
    return {
        "available": bool(agy_exe),
        "agy_path": agy_exe or "",
        "models": list_agy_models(force_refresh=refresh),
    }


@app.post("/api/ai/test-agy")
def api_test_agy(req: AgyTestReq):
    cfg = load_config()
    model = (req.model or cfg.get("agy_model") or DEFAULT_CONFIG["agy_model"]).strip()
    effort = req.effort or cfg.get("agy_effort") or DEFAULT_CONFIG["agy_effort"]
    t0 = time.monotonic()
    res = call_agy_cli(
        "Reply only with: Ket noi Antigravity CLI thanh cong.",
        model=model,
        effort=effort,
        mode="auto",
        disable_slash_commands=True,
        timeout=75,
    )
    return {
        "ok": True,
        "model": model,
        "effort": effort,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "duration_seconds": res.get("duration_seconds"),
        "reply": res.get("response") or "OK",
    }


@app.post("/api/ai/test-gemini")
def api_test_gemini(req: GeminiTestReq):
    cfg = load_config()
    api_key = (req.api_key if req.api_key is not None and req.api_key.strip() else cfg.get("gemini_api_key", "")).strip()
    model = (req.model or cfg.get("gemini_model") or "gemini-2.5-flash").strip()
    effort = req.effort or cfg.get("gemini_effort") or "medium"
    t0 = time.monotonic()
    reply = call_gemini_multimodal(
        [{"text": "Trả lời ngắn gọn bằng tiếng Việt trong 3 từ: Kết nối thành công."}],
        api_key=api_key,
        model=model,
        effort=effort,
        timeout=30,
    )
    return {
        "ok": True,
        "model": model,
        "effort": effort,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "reply": reply,
    }


@app.get("/api/directories")
def api_list_directories():
    return {"directories": list_selectable_directories()}


def _resolve_project_scoped_dir(target_dir: str, project_id: str = "") -> Path:
    pid = str(project_id or "").strip()
    if pid:
        proj_root = get_project_root(pid)
        if not proj_root.exists():
            raise HTTPException(status_code=404, detail=f"Không tìm thấy Project `{pid}`.")
        pm_ensure_project_dirs(proj_root)
        rel_norm = Path(str(target_dir or "02_video_tho").strip().replace("\\", "/")).as_posix().lstrip("/")
        top_seg = rel_norm.split("/", 1)[0] if rel_norm else "02_video_tho"
        if top_seg in PROJECT_SCOPED_ROOTS:
            dest_dir = (proj_root / rel_norm).resolve()
            if proj_root.resolve() not in dest_dir.parents and dest_dir != proj_root.resolve():
                raise HTTPException(status_code=400, detail="Đường dẫn thư mục không hợp lệ.")
            return dest_dir
    return resolve_safe_path(target_dir)


@app.get("/api/files")
def api_list_files(
    dir: str = Query(default="02_video_tho"),
    project_id: str = Query(default=""),
):
    target = _resolve_project_scoped_dir(dir, project_id)
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy thư mục: {dir}")
    return {"dir": to_rel_posix(target), "project_id": project_id or ACTIVE_PROJECT_ID, "files": list_media_in_dir(target)}


@app.post("/api/files/upload")
async def api_upload_files(
    target_dir: str = Form("02_video_tho"),
    project_id: str = Form(""),
    files: list[UploadFile] = File(...),
):
    dest_dir = _resolve_project_scoped_dir(target_dir, project_id)
    assert_mutable_path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    uploaded: list[dict[str, Any]] = []
    for idx, up in enumerate(files, start=1):
        orig_name = up.filename or "video.mp4"
        ext = Path(orig_name).suffix.lower()
        if ext not in MEDIA_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Định dạng không hỗ trợ ({orig_name}). Chỉ nhận video/audio ({', '.join(sorted(MEDIA_EXTENSIONS))}).",
            )
        safe_stem = sanitize_filename(Path(orig_name).stem, fallback="upload")
        out_path = dest_dir / f"{safe_stem}{ext}"
        if out_path.exists():
            out_path = dest_dir / f"{safe_stem}_{int(time.time())}_{idx}{ext}"
        with open(out_path, "wb") as f:
            while True:
                chunk = await up.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        uploaded.append(probe_media(out_path))

    return {
        "ok": True,
        "count": len(uploaded),
        "target_dir": to_rel_posix(dest_dir),
        "files": uploaded,
    }


UPLOAD_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{6,80}$")


class UploadAbortReq(BaseModel):
    upload_id: str
    project_id: str = ""


def _get_upload_tmp_dir(project_id: str = "") -> Path:
    pid = str(project_id or "").strip()
    if pid:
        proj_root = get_project_root(pid)
        if not proj_root.exists():
            raise HTTPException(status_code=404, detail=f"Không tìm thấy Project `{pid}`.")
    else:
        proj_root = ACTIVE_PROJECT_ROOT
    tmp_dir = (proj_root / "04_workspace" / "_upload_tmp").resolve()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir


def _cleanup_stale_upload_parts(tmp_dir: Path, max_age_sec: float = 7200.0) -> int:
    """Remove leftover `.part` temp files older than `max_age_sec`."""
    if not tmp_dir.exists() or not tmp_dir.is_dir():
        return 0
    now = time.time()
    removed = 0
    for item in tmp_dir.glob("*.part"):
        try:
            if not item.is_file():
                continue
            age = now - float(item.stat().st_mtime)
            if age >= float(max_age_sec):
                item.unlink(missing_ok=True)
                removed += 1
        except Exception:
            pass
    return removed


@app.post("/api/files/upload-chunk")
async def api_upload_file_chunk(
    upload_id: str = Form(...),
    filename: str = Form(...),
    target_dir: str = Form("02_video_tho"),
    project_id: str = Form(""),
    offset: int = Form(0),
    total_size: int = Form(0),
    chunk_index: int = Form(0),
    total_chunks: int = Form(1),
    chunk: UploadFile = File(...),
):
    uid = str(upload_id or "").strip()
    if not UPLOAD_ID_RE.fullmatch(uid):
        raise HTTPException(status_code=400, detail="upload_id không hợp lệ.")
    if offset < 0 or total_size <= 0 or total_chunks < 1 or chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(status_code=400, detail="Tham số phân mảnh upload không hợp lệ.")

    orig_name = Path(str(filename or "video.mp4")).name
    ext = Path(orig_name).suffix.lower()
    if ext not in MEDIA_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Định dạng không hỗ trợ ({orig_name}). Chỉ nhận video/audio ({', '.join(sorted(MEDIA_EXTENSIONS))}).",
        )

    dest_dir = _resolve_project_scoped_dir(target_dir, project_id)
    assert_mutable_path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    tmp_dir = _get_upload_tmp_dir(project_id)
    if chunk_index == 0:
        _cleanup_stale_upload_parts(tmp_dir, max_age_sec=7200.0)

    part_path = (tmp_dir / f"{uid}.part").resolve()
    if part_path.parent != tmp_dir:
        raise HTTPException(status_code=400, detail="Đường dẫn tạm không hợp lệ.")

    data = await chunk.read()
    mode = "wb" if (chunk_index == 0 and offset == 0) or not part_path.exists() else "r+b"
    with open(part_path, mode) as f:
        f.seek(offset)
        f.write(data)

    if chunk_index + 1 < total_chunks:
        return {
            "ok": True,
            "done": False,
            "upload_id": uid,
            "received_bytes": offset + len(data),
        }

    if not part_path.exists() or part_path.stat().st_size < total_size:
        part_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Tệp ghép mảnh chưa đủ dung lượng. Vui lòng thử tải lại.")

    safe_stem = sanitize_filename(Path(orig_name).stem, fallback="upload")
    out_path = dest_dir / f"{safe_stem}{ext}"
    if out_path.exists():
        out_path = dest_dir / f"{safe_stem}_{int(time.time())}{ext}"
    os.replace(str(part_path), str(out_path))
    return {
        "ok": True,
        "done": True,
        "count": 1,
        "target_dir": to_rel_posix(dest_dir),
        "file": probe_media(out_path),
    }


@app.post("/api/files/upload-abort")
def api_upload_file_abort(req: UploadAbortReq):
    uid = str(req.upload_id or "").strip()
    if not UPLOAD_ID_RE.fullmatch(uid):
        raise HTTPException(status_code=400, detail="upload_id không hợp lệ.")
    tmp_dir = _get_upload_tmp_dir(req.project_id)
    part_path = (tmp_dir / f"{uid}.part").resolve()
    if part_path.parent == tmp_dir and part_path.exists():
        part_path.unlink(missing_ok=True)
    return {"ok": True}


@app.post("/api/files/mkdir")
def api_mkdir(req: MkdirReq):
    parent = resolve_safe_path(req.parent_dir)
    assert_mutable_path(parent)
    safe_name = sanitize_filename(req.folder_name, fallback="thu_muc_moi")
    new_dir = (parent / safe_name).resolve()
    assert_mutable_path(new_dir)
    new_dir.mkdir(parents=True, exist_ok=True)
    return {
        "ok": True,
        "rel_path": to_rel_posix(new_dir),
        "directories": list_selectable_directories(),
    }


@app.post("/api/files/rename")
def api_rename_file(req: RenameFileReq):
    src = resolve_safe_path(req.rel_path)
    assert_mutable_path(src)
    if not src.exists() or not src.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy file cần đổi tên.")
    new_stem = sanitize_filename(Path(req.new_name).stem, fallback=src.stem)
    ext = Path(req.new_name).suffix.lower() or src.suffix.lower()
    dst = src.parent / f"{new_stem}{ext}"
    if dst.exists() and dst != src:
        raise HTTPException(status_code=409, detail="Tên file mới đã tồn tại.")
    src.rename(dst)
    return {"ok": True, "file": probe_media(dst)}


@app.post("/api/files/delete")
def api_delete_file(req: DeleteFileReq):
    target = resolve_safe_path(req.rel_path)
    assert_mutable_path(target)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy file cần xóa.")
    target.unlink()
    return {"ok": True, "deleted": req.rel_path}


def _bring_explorer_to_front(folder_name: str) -> None:
    """Tìm cửa sổ Windows Explorer vừa mở và đưa lên trên trình duyệt."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        target_lower = folder_name.lower()

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        for _ in range(10):
            time.sleep(0.18)
            matched_hwnd = None

            def enum_cb(hwnd, _lparam):
                nonlocal matched_hwnd
                if not u32.IsWindowVisible(hwnd):
                    return True
                cls_buf = ctypes.create_unicode_buffer(64)
                u32.GetClassNameW(hwnd, cls_buf, 64)
                if cls_buf.value != "CabinetWClass":
                    return True
                title_buf = ctypes.create_unicode_buffer(512)
                u32.GetWindowTextW(hwnd, title_buf, 512)
                if not target_lower or target_lower in title_buf.value.lower():
                    matched_hwnd = hwnd
                    return False
                return True

            u32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            if matched_hwnd:
                if u32.IsIconic(matched_hwnd):
                    u32.ShowWindow(matched_hwnd, 9)  # SW_RESTORE
                else:
                    u32.ShowWindow(matched_hwnd, 5)  # SW_SHOW
                fg = u32.GetForegroundWindow()
                cur_tid = k32.GetCurrentThreadId()
                fg_tid = u32.GetWindowThreadProcessId(fg, None) if fg else 0
                attached = False
                if fg_tid and fg_tid != cur_tid:
                    attached = bool(u32.AttachThreadInput(cur_tid, fg_tid, True))
                u32.BringWindowToTop(matched_hwnd)
                u32.SetForegroundWindow(matched_hwnd)
                if attached:
                    u32.AttachThreadInput(cur_tid, fg_tid, False)
                return
    except Exception:
        pass


@app.post("/api/system/open-explorer")
def api_open_explorer(req: OpenExplorerReq):
    global _last_explorer_req
    pid_clean = str(req.project_id or "").strip()
    if pid_clean:
        p_root = get_project_root(pid_clean).resolve()
        rel_c = str(req.rel_path or "").strip().lstrip("/\\")
        if ".." in Path(rel_c).parts:
            raise HTTPException(status_code=400, detail="Đường dẫn không hợp lệ.")
        target = (p_root / rel_c).resolve()
        if not target.is_relative_to(p_root):
            raise HTTPException(status_code=400, detail="Đường dẫn ngoài thư mục Project.")
    else:
        target = resolve_safe_path(req.rel_path)
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)

    now = time.monotonic()
    norm_key = os.path.normpath(str(target)).lower()
    if (
        _last_explorer_req is not None
        and _last_explorer_req[0] == norm_key
        and _last_explorer_req[1] == req.select_file
        and (now - _last_explorer_req[2]) < 1.5
    ):
        return {"ok": True, "opened": str(target), "deduped": True}
    _last_explorer_req = (norm_key, req.select_file, now)

    if os.name == "nt":
        norm_target = os.path.normpath(str(target))
        try:
            import ctypes

            u32 = ctypes.windll.user32
            hdesk = u32.GetThreadDesktop(ctypes.windll.kernel32.GetCurrentThreadId())
            buf = ctypes.create_unicode_buffer(256)
            if u32.GetUserObjectInformationW(hdesk, 2, buf, 512, None) and buf.value.lower() != "default":
                return {
                    "ok": False,
                    "reason": "isolated_desktop",
                    "opened": norm_target,
                    "detail": "Server đang chạy trong phiên nền tách biệt nên Explorer không thể hiện lên màn hình chính. Hãy mở trực tiếp bằng start_dashboard.bat.",
                }
        except Exception:
            pass

        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 1  # SW_SHOWNORMAL

        if req.select_file and target.is_file():
            # Pass unquoted /select, with quoted path only so explorer.exe parses spaces & Unicode accurately
            subprocess.Popen(f'explorer.exe /select,"{norm_target}"', startupinfo=si)
            focus_name = target.parent.name
        else:
            open_dir = norm_target if target.is_dir() else os.path.normpath(str(target.parent))
            os.startfile(open_dir)
            focus_name = Path(open_dir).name

        threading.Thread(target=_bring_explorer_to_front, args=(focus_name,), daemon=True).start()
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target if target.is_dir() else target.parent)])
    else:
        subprocess.Popen(["xdg-open", str(target if target.is_dir() else target.parent)])

    return {"ok": True, "opened": str(target)}


# ---------------------------------------------------------------------------
# Tab 1: Multi-Platform Downloader (Dual-Engine: Cobalt API + yt-dlp Fallback)
# ---------------------------------------------------------------------------


@app.post("/api/download")
def api_download(req: DownloadReq):
    target_dir = resolve_safe_path(req.target_dir)
    assert_mutable_path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    urls = [u.strip() for u in req.urls if u and u.strip()]
    if not urls:
        raise HTTPException(status_code=400, detail="Vui lòng nhập ít nhất 1 đường dẫn URL.")

    cfg = load_config()
    cobalt_url = (req.cobalt_url if req.cobalt_url is not None else cfg.get("cobalt_url", "")).strip()

    results: list[dict[str, Any]] = []
    for url in urls:
        cobalt_err = None
        if cobalt_url:
            try:
                item = download_via_cobalt(url, cobalt_url, target_dir, req.mode)
                item["note"] = "Tải thành công qua Cobalt API"
                results.append(item)
                continue
            except Exception as exc:
                cobalt_err = str(exc)

        ytdlp_err = None
        try:
            item = download_via_ytdlp(url, target_dir, req.mode)
            if cobalt_err:
                item["fallback_from"] = f"Cobalt lỗi ({cobalt_err[:90]}), đã tự chuyển yt-dlp"
            else:
                item["fallback_from"] = "Tải trực tiếp bằng yt-dlp"
            results.append(item)
            continue
        except Exception as exc:
            ytdlp_err = str(exc)

        if "tiktok.com" in url.lower():
            try:
                item = download_via_tikwm(url, target_dir, req.mode)
                item["fallback_from"] = f"yt-dlp không lấy được video, đã tự chuyển TikWM HD"
                results.append(item)
                continue
            except Exception as tik_exc:
                ytdlp_err = f"{ytdlp_err} | TikWM: {tik_exc}"

        results.append(
            {
                "ok": False,
                "url": url,
                "engine": "yt-dlp",
                "cobalt_error": cobalt_err,
                "error": ytdlp_err,
            }
        )

    success_count = sum(1 for r in results if r.get("ok"))
    return {
        "ok": success_count > 0,
        "total": len(urls),
        "success_count": success_count,
        "target_dir": to_rel_posix(target_dir),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Tab 2: Voice Studio & Reference Extraction
# ---------------------------------------------------------------------------


@app.get("/api/voice/status")
def api_voice_status():
    sources = []
    for folder in (DIR_VIDEO_MAU, DIR_VIDEO_THO):
        sources.extend(list_media_in_dir(folder))
    return {
        "voice": get_voice_status_payload(),
        "sources": sources,
        "save_dirs": list_voice_save_directories(),
    }


@app.post("/api/voice/ref-text")
def api_save_ref_text(req: RefTextSaveReq):
    text = req.ref_text.strip()
    MODEL_REF_TEXT.write_text((text + "\n") if text else "", encoding="utf-8")
    sync_voice_clone_files()
    return {"ok": True, "voice": get_voice_status_payload()}


@app.post("/api/voice/extract-ffmpeg")
def api_extract_voice_ffmpeg(req: ExtractVoiceReq):
    src = resolve_safe_path(req.source_path)
    if not src.exists() or not src.is_file():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tệp nguồn: {req.source_path}")
    if req.end <= req.start or req.start < 0:
        raise HTTPException(status_code=400, detail="Mốc End phải lớn hơn Start (>= 0).")

    dst_wav, dst_txt, is_default = _resolve_voice_target(req.profile_name, req.save_dir, req.filename)
    ffmpeg_bin = find_binary("ffmpeg")
    cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{req.start:.3f}",
        "-to",
        f"{req.end:.3f}",
        "-i",
        str(src),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "24000",
        "-ac",
        "1",
        str(dst_wav),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise HTTPException(status_code=500, detail=f"FFmpeg trích xuất lỗi: {res.stderr}")

    if is_default:
        sync_voice_clone_files()

    transcribed = None
    backend = ""
    if req.auto_transcribe:
        transcribed, backend = transcribe_wav_with_faster_whisper(dst_wav, model_size="small")
        dst_txt.write_text((transcribed + "\n") if transcribed else "", encoding="utf-8")
        if is_default:
            sync_voice_clone_files()

    return {
        "ok": True,
        "command": " ".join(cmd),
        "saved_profile": dst_wav.stem if not is_default else "default",
        "saved_path": to_rel_posix(dst_wav),
        "transcribed_text": transcribed,
        "whisper_backend": backend,
        "voice": get_voice_status_payload(),
    }


@app.post("/api/voice/extract-upload")
async def api_extract_voice_from_upload(
    file: UploadFile = File(...),
    start: float = Form(0.0),
    end: float = Form(12.0),
    auto_transcribe: bool = Form(True),
    profile_name: str = Form(""),
    save_dir: str = Form(""),
    filename: str = Form(""),
):
    if end <= start or start < 0:
        raise HTTPException(status_code=400, detail="Mốc End phải lớn hơn Start (>= 0).")

    dst_wav, dst_txt, is_default = _resolve_voice_target(profile_name, save_dir, filename)
    ffmpeg_bin = find_binary("ffmpeg")
    suffix = Path(file.filename or "input.mp4").suffix or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(await file.read())

    try:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(tmp_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "24000",
            "-ac",
            "1",
            str(dst_wav),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    if is_default:
        sync_voice_clone_files()

    transcribed = None
    backend = ""
    if auto_transcribe:
        transcribed, backend = transcribe_wav_with_faster_whisper(dst_wav, model_size="small")
        dst_txt.write_text((transcribed + "\n") if transcribed else "", encoding="utf-8")
        if is_default:
            sync_voice_clone_files()

    return {
        "ok": True,
        "saved_profile": dst_wav.stem if not is_default else "default",
        "saved_path": to_rel_posix(dst_wav),
        "transcribed_text": transcribed,
        "whisper_backend": backend,
        "voice": get_voice_status_payload(),
    }


@app.post("/api/voice/record-upload")
async def api_record_upload(
    audio: UploadFile = File(...),
    auto_transcribe: bool = Form(True),
    profile_name: str = Form(""),
    save_dir: str = Form(""),
    filename: str = Form(""),
):
    dst_wav, dst_txt, is_default = _resolve_voice_target(profile_name, save_dir, filename)
    suffix = Path(audio.filename or "recording.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(await audio.read())

    try:
        convert_to_wav_24k_mono(tmp_path, dst_wav, trim_silence=True)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    if is_default:
        sync_voice_clone_files()

    transcribed = None
    backend = ""
    if auto_transcribe:
        transcribed, backend = transcribe_wav_with_faster_whisper(dst_wav, model_size="small")
        dst_txt.write_text((transcribed + "\n") if transcribed else "", encoding="utf-8")
        if is_default:
            sync_voice_clone_files()

    return {
        "ok": True,
        "saved_profile": dst_wav.stem if not is_default else "default",
        "saved_path": to_rel_posix(dst_wav),
        "transcribed_text": transcribed,
        "whisper_backend": backend,
        "voice": get_voice_status_payload(),
    }


@app.post("/api/voice/transcribe")
def api_transcribe_current_voice():
    if not MODEL_VOICE_WAV.exists():
        raise HTTPException(status_code=404, detail="Chưa có file 03_voice_clone/model/giong_mau.wav.")
    text, backend = transcribe_wav_with_faster_whisper(MODEL_VOICE_WAV, model_size="small")
    MODEL_REF_TEXT.write_text((text + "\n") if text else "", encoding="utf-8")
    sync_voice_clone_files()
    return {
        "ok": True,
        "transcribed_text": text,
        "whisper_backend": backend,
        "voice": get_voice_status_payload(),
    }


@app.post("/api/voice/profiles/upload")
async def api_voice_profile_upload(
    file: UploadFile = File(...),
    profile_name: str = Form(""),
    auto_transcribe: bool = Form(True),
):
    raw_name = profile_name.strip() or Path(file.filename or "voice").stem
    slug = _slug_voice_id(raw_name)
    dst_wav = DIR_VOICE_PROFILES / f"{slug}.wav"
    dst_txt = DIR_VOICE_PROFILES / f"{slug}.txt"
    DIR_VOICE_PROFILES.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "voice.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(await file.read())
    try:
        convert_to_wav_24k_mono(tmp_path, dst_wav, trim_silence=True)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    transcribed = None
    backend = ""
    if auto_transcribe:
        transcribed, backend = transcribe_wav_with_faster_whisper(dst_wav, model_size="small")
        dst_txt.write_text((transcribed + "\n") if transcribed else "", encoding="utf-8")
    return {
        "ok": True,
        "profile_id": slug,
        "whisper_backend": backend,
        "voice": get_voice_status_payload(),
    }


@app.post("/api/voice/profiles/set-default")
def api_voice_profile_set_default(req: VoiceProfileIdReq):
    if req.profile_id == "default":
        return {"ok": True, "voice": get_voice_status_payload()}
    src_wav = _resolve_profile_in_voices(req.profile_id)
    if not src_wav.exists():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy giọng mẫu: {req.profile_id}")
    shutil.copy2(src_wav, MODEL_VOICE_WAV)
    src_txt = src_wav.with_suffix(".txt")
    if src_txt.exists():
        shutil.copy2(src_txt, MODEL_REF_TEXT)
    else:
        MODEL_REF_TEXT.write_text("", encoding="utf-8")
    sync_voice_clone_files()
    return {"ok": True, "voice": get_voice_status_payload()}


@app.post("/api/voice/profiles/ref-text")
def api_voice_profile_save_ref_text(req: VoiceProfileRefTextReq):
    if req.profile_id == "default":
        MODEL_REF_TEXT.write_text((req.ref_text.strip() + "\n") if req.ref_text.strip() else "", encoding="utf-8")
        sync_voice_clone_files()
    else:
        wav_p = _resolve_profile_in_voices(req.profile_id)
        if not wav_p.exists():
            raise HTTPException(status_code=404, detail=f"Không tìm thấy giọng mẫu: {req.profile_id}")
        wav_p.with_suffix(".txt").write_text((req.ref_text.strip() + "\n") if req.ref_text.strip() else "", encoding="utf-8")
    return {"ok": True, "voice": get_voice_status_payload()}


@app.post("/api/voice/profiles/transcribe")
def api_voice_profile_transcribe(req: VoiceProfileIdReq):
    if req.profile_id == "default":
        return api_transcribe_current_voice()
    wav_p = _resolve_profile_in_voices(req.profile_id)
    if not wav_p.exists():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy giọng mẫu: {req.profile_id}")
    text, backend = transcribe_wav_with_faster_whisper(wav_p, model_size="small")
    wav_p.with_suffix(".txt").write_text((text + "\n") if text else "", encoding="utf-8")
    return {"ok": True, "transcribed_text": text, "whisper_backend": backend, "voice": get_voice_status_payload()}


@app.delete("/api/voice/profiles/{profile_id:path}")
def api_voice_profile_delete(profile_id: str):
    if profile_id == "default":
        raise HTTPException(status_code=400, detail="Không thể xóa Giọng Mẫu Chính (mặc định).")
    wav_p = _resolve_profile_in_voices(profile_id)
    txt_p = wav_p.with_suffix(".txt")
    if not wav_p.exists():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy giọng mẫu: {profile_id}")
    wav_p.unlink()
    if txt_p.exists():
        txt_p.unlink()
    return {"ok": True, "voice": get_voice_status_payload()}


# ---------------------------------------------------------------------------
# Tab 3: Style Learning (01_video_mau -> phong_cach_kenh.md)
# ---------------------------------------------------------------------------


def collect_style_data() -> dict[str, Any]:
    videos = list_media_in_dir(DIR_VIDEO_MAU)
    frames_bucket = DIR_FRAMES_MAU
    video_frames: list[dict[str, Any]] = []

    if frames_bucket.exists():
        for sub in sorted(frames_bucket.iterdir()):
            if not sub.is_dir():
                continue
            imgs = sorted(sub.glob("frame_*.jpg"))
            if not imgs:
                continue
            meta_file = sub / "metadata.json"
            meta = {}
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8-sig"))
                except Exception:
                    pass
            transcript_file = sub / "transcript.txt"
            transcript_txt = (
                transcript_file.read_text(encoding="utf-8-sig") if transcript_file.exists() else ""
            )
            video_frames.append(
                {
                    "stem": sub.name,
                    "filename": meta.get("filename", sub.name),
                    "duration_sec": meta.get("duration_sec", 0),
                    "resolution": f"{meta.get('width', 0)}x{meta.get('height', 0)}",
                    "transcript": transcript_txt,
                    "frames": [
                        {
                            "name": img.name,
                            "url": f"/style_frames/{sub.name}/{img.name}",
                        }
                        for img in imgs
                    ],
                }
            )

    transcript_md_file = frames_bucket / "loi_thoai_goc.md"
    loi_thoai_goc = (
        transcript_md_file.read_text(encoding="utf-8-sig") if transcript_md_file.exists() else ""
    )
    style_guide = (
        FILE_STYLE_GUIDE.read_text(encoding="utf-8-sig") if FILE_STYLE_GUIDE.exists() else ""
    )
    style_dna = load_style_dna()
    return {
        "videos": videos,
        "video_frames": video_frames,
        "loi_thoai_goc": loi_thoai_goc,
        "phong_cach_kenh": style_guide,
        "style_dna": style_dna,
    }


@app.get("/api/style/data")
def api_style_data():
    return collect_style_data()


@app.post("/api/style/extract")
def api_style_extract(req: StyleExtractReq):
    videos = list_media_in_dir(DIR_VIDEO_MAU)
    if not videos:
        raise HTTPException(
            status_code=400,
            detail="Thư mục 01_video_mau đang trống. Hãy tải hoặc chép video mẫu vào trước.",
        )
    run_res = run_python_script(
        "scripts/extract_frames.py",
        [
            "--source",
            "01_video_mau",
            "--fps",
            str(req.fps),
            "--max-width",
            "540",
            "--transcribe",
            "always",
            "--whisper-model",
            req.whisper_model,
        ],
    )
    update_style_dna()
    return {**run_res, "data": collect_style_data()}


@app.post("/api/style/guide")
def api_save_style_guide(req: StyleGuideSaveReq):
    FILE_STYLE_GUIDE.write_text(req.content, encoding="utf-8")
    return {"ok": True}


@app.post("/api/style/analyze-gemini")
def api_style_analyze_gemini(req: GeminiStyleAnalyzeReq):
    cfg = load_config()
    api_key = str(cfg.get("gemini_api_key") or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Chưa cấu hình Gemini API Key. Bấm vào badge AI trên Header để nhập key.",
        )
    model = (req.model or cfg.get("gemini_model") or "gemini-2.5-flash").strip()
    effort = req.effort or cfg.get("gemini_effort") or "medium"

    videos = list_media_in_dir(DIR_VIDEO_MAU)
    if not videos:
        raise HTTPException(status_code=400, detail="Thư mục 01_video_mau đang trống.")

    frames_base = DIR_FRAMES_MAU
    if not (frames_base / "manifest.json").exists():
        run_python_script(
            "scripts/extract_frames.py",
            ["--source", "01_video_mau", "--fps", "1.0", "--max-width", "540", "--transcribe", "always"],
        )

    style_data = collect_style_data()
    parts: list[dict[str, Any]] = [
        {
            "text": (
                "Bạn là Đạo diễn Dựng Video & Copywriter TikTok Shop chuyên nghiệp. "
                "Hãy phân tích các khung hình (1 ảnh/giây) và lời thoại gốc của các video mẫu bên dưới "
                "để rút ra DNA phong cách kênh và viết thành tài liệu Markdown `phong_cach_kenh.md` hoàn chỉnh "
                "với 6 mục chuẩn: (1) Tổng quan video mẫu, (2) DNA Nhịp độ & Cấu trúc Timeline (thời lượng Hook, "
                "ASL trung bình mỗi clip tính bằng giây, tổng thời lượng lý tưởng, gợi ý `--speed` F5-TTS từ 0.95-1.15), "
                "(3) Công thức Hook 3 giây đầu kèm 3-5 mẫu câu áp dụng ngay, (4) Quy tắc chọn cảnh & thứ tự dựng B-roll, "
                "(5) Style Văn bản & Phụ đề chuẩn OpenReel 9:16 (vùng an toàn), (6) Văn phong xưng hô, từ khóa đắt & CTA giỏ hàng.\n\n"
                f"=== LỜI THOẠI GỐC ===\n{style_data.get('loi_thoai_goc', '')}\n"
            )
        }
    ]

    frames_used = 0
    per_video_limit = max(3, min(6, 18 // max(1, len(videos))))
    for vf in style_data.get("video_frames", []):
        vname = vf.get("stem") or vf.get("filename") or ""
        if not vname:
            continue
        frame_dir = frames_base / vname
        all_jpgs = sorted(frame_dir.glob("frame_*.jpg"))
        chosen = select_representative_frames(all_jpgs, max_frames=per_video_limit)
        if chosen:
            parts.append({"text": f"\n--- Khung hình đại diện của video mẫu: {vname} ---"})
            for jpg in chosen:
                b64 = base64.b64encode(jpg.read_bytes()).decode("ascii")
                parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
                frames_used += 1

    content = call_gemini_multimodal(parts, api_key=api_key, model=model, effort=effort, timeout=120)
    FILE_STYLE_GUIDE.write_text(content + "\n", encoding="utf-8")
    update_style_dna()
    return {
        "ok": True,
        "model": model,
        "effort": effort,
        "frames_used": frames_used,
        "content": content,
        "data": collect_style_data(),
    }


@app.post("/api/style/analyze-agy")
def api_style_analyze_agy(req: AgyStyleAnalyzeReq):
    cfg = load_config()
    model = (req.model or cfg.get("agy_model") or DEFAULT_CONFIG["agy_model"]).strip()
    effort = req.effort or cfg.get("agy_effort") or DEFAULT_CONFIG["agy_effort"]

    videos = list_media_in_dir(DIR_VIDEO_MAU)
    if not videos:
        raise HTTPException(status_code=400, detail="Thư mục 01_video_mau đang trống.")

    frames_base = DIR_FRAMES_MAU
    if not (frames_base / "manifest.json").exists():
        run_python_script(
            "scripts/extract_frames.py",
            ["--source", "01_video_mau", "--fps", "1.0", "--max-width", "540", "--transcribe", "always"],
        )

    prompt = (
        "Hãy thực hiện skill `.agents/skills/hoc-phong-cach/SKILL.md` cho dự án này.\n"
        "Khung hình và lời thoại gốc đã được trích xuất sẵn trong `04_workspace/frames/01_video_mau/` "
        "(`manifest.json`, các ảnh `frame_*.jpg` và `loi_thoai_goc.md`).\n"
        "BẮT BUỘC dùng `view_file` xem các ảnh đại diện trong `04_workspace/frames/01_video_mau/` "
        "và đọc `04_workspace/frames/01_video_mau/loi_thoai_goc.md`, rồi ghi đè file hoàn chỉnh "
        "`phong_cach_kenh.md` ở thư mục gốc dự án với đủ 6 mục chuẩn theo đúng hướng dẫn của skill. "
        "Không cần chạy lại `extract_frames.py` nếu dữ liệu đã đầy đủ. Sau khi ghi file xong, trả lời ngắn gọn: DONE."
    )
    cli_res = call_agy_cli(prompt, model=model, effort=effort, mode="auto", timeout=300)
    if not FILE_STYLE_GUIDE.exists():
        raise HTTPException(
            status_code=502,
            detail="Antigravity CLI chạy xong nhưng chưa tạo được `04_workspace/phong_cach_kenh.md`.",
        )

    update_style_dna()
    return {
        "ok": True,
        "engine": "agy",
        "model": model,
        "effort": effort,
        "duration_seconds": cli_res.get("duration_seconds"),
        "content": FILE_STYLE_GUIDE.read_text(encoding="utf-8-sig"),
        "data": collect_style_data(),
    }


# ---------------------------------------------------------------------------
# Tab 4: Automated Workshop (02_video_tho -> 04_workspace/ready_for_openreel)
# ---------------------------------------------------------------------------


def collect_workshop_state() -> dict[str, Any]:
    raw_videos = list_media_in_dir(DIR_VIDEO_THO)
    clips = list_media_in_dir(DIR_CLIPS)

    script_text = FILE_SCRIPT.read_text(encoding="utf-8-sig") if FILE_SCRIPT.exists() else ""
    srt_text = FILE_TTS_SRT.read_text(encoding="utf-8-sig") if FILE_TTS_SRT.exists() else ""

    edit_plan: dict[str, Any] = {
        "title": "San pham TikTok Shop",
        "target_resolution": [1080, 1920],
        "target_fps": 30,
        "concat_draft": True,
        "keep_clip_audio": False,
        "clips": [],
    }
    if FILE_EDIT_PLAN.exists():
        try:
            edit_plan = json.loads(FILE_EDIT_PLAN.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
    elif raw_videos:
        # Gợi ý kế hoạch cắt mặc định từ clip thô đang có
        edit_plan["clips"] = [
            {
                "source": v["rel_path"],
                "start": 0.0,
                "end": round(min(3.0, max(1.0, v["duration_sec"] or 3.0)), 2),
                "speed": 1.0,
                "mute": True,
                "crop_mode": "center",
                "note": f"Cảnh từ {v['name']}",
            }
            for v in raw_videos[:5]
        ]

    tts_wav = probe_media(FILE_TTS_WAV) if FILE_TTS_WAV.exists() else None
    if tts_wav:
        tts_wav["url"] = f"/files/04_workspace/ready_for_openreel/02_giong_doc_ai.wav?t={tts_wav['mtime']}"

    draft_mp4 = probe_media(FILE_DRAFT_MP4) if FILE_DRAFT_MP4.exists() else None
    if draft_mp4:
        draft_mp4["url"] = f"/files/04_workspace/ready_for_openreel/00_video_nhap_da_ghep.mp4?t={draft_mp4['mtime']}"

    for c in clips:
        c["url"] = f"{c['url']}?t={c['mtime']}"

    voice_beats = None
    if FILE_VOICE_BEATS.exists():
        try:
            voice_beats = json.loads(FILE_VOICE_BEATS.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    script_display = (
        (DIR_WORKSPACE / "kich_ban_hien_thi.md").read_text(encoding="utf-8-sig")
        if (DIR_WORKSPACE / "kich_ban_hien_thi.md").exists()
        else restore_display_text(script_text)
    )
    critic_report = FILE_CRITIC_MD.read_text(encoding="utf-8-sig") if FILE_CRITIC_MD.exists() else ""
    brief = load_brand_brief()
    brief_ready, brief_reason = is_brand_brief_ready(brief)

    return {
        "raw_videos": raw_videos,
        "script_text": script_text,
        "script_display": script_display,
        "script_options": load_script_options(),
        "critic_report": critic_report,
        "tts_wav": tts_wav,
        "srt_text": srt_text,
        "edit_plan": edit_plan,
        "clips": clips,
        "draft_mp4": draft_mp4,
        "brand_brief": brief,
        "brief_ready": brief_ready,
        "brief_reason": brief_reason,
        "voice_beats": voice_beats,
    }


@app.get("/api/workshop/state")
def api_workshop_state():
    return collect_workshop_state()


@app.post("/api/workshop/tts")
def api_workshop_tts(req: TtsGenerateReq):
    raw_text = req.script_text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Vui lòng nhập nội dung kịch bản tiếng Việt.")
    brief = load_brand_brief()
    tts_text = convert_display_to_tts_script(raw_text, brief)
    FILE_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
    FILE_SCRIPT.write_text(tts_text + "\n", encoding="utf-8")
    if re.search(r"[0-9%]", raw_text):
        (DIR_WORKSPACE / "kich_ban_hien_thi.md").write_text(raw_text + "\n", encoding="utf-8")

    # Đảm bảo voice_engine tìm thấy ref text đã lưu trên Dashboard
    sync_voice_clone_files()

    args = [
        "--script",
        "04_workspace/kich_ban.txt",
        "--speed",
        str(req.speed),
        "--nfe-step",
        str(req.nfe_step),
        "--whisper-model",
        req.whisper_model,
    ]
    target_dur = float(brief.get("target_duration_sec") or 0.0)
    if target_dur > 5.0:
        args.extend(["--target-duration", f"{target_dur:.2f}"])

    run_res = run_python_script("scripts/voice_engine.py", args)
    if run_res.get("ok"):
        repair_subtitles_and_beats()
    return {**run_res, "state": collect_workshop_state()}


@app.post("/api/workshop/srt")
def api_workshop_save_srt(req: SrtSaveReq):
    FILE_TTS_SRT.parent.mkdir(parents=True, exist_ok=True)
    FILE_TTS_SRT.write_text(req.content, encoding="utf-8")
    return {"ok": True}


@app.post("/api/workshop/prepare-clips")
def api_workshop_prepare_clips(req: PrepareClipsReq):
    if not req.edit_plan.get("clips"):
        raise HTTPException(status_code=400, detail="Kế hoạch cắt dựng chưa có clip nào.")
    FILE_EDIT_PLAN.parent.mkdir(parents=True, exist_ok=True)
    FILE_EDIT_PLAN.write_text(
        json.dumps(req.edit_plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    args = [
        "--config",
        "04_workspace/edit_plan.json",
        "--concat" if req.concat else "--no-concat",
    ]
    run_res = run_python_script("scripts/prepare_clips.py", args)
    return {**run_res, "state": collect_workshop_state()}


def _format_brand_brief_prompt_block(brief: dict[str, Any]) -> str:
    pm_lines = "\n".join(f"  - {k} -> đọc tiếng Việt: {v}" for k, v in (brief.get("phonetic_map") or {}).items())
    banned_str = ", ".join(get_effective_banned_words(brief))
    return (
        "=== HỒ SƠ NHÃN HÀNG GỬI (BRAND BRIEF) ===\n"
        f"- Thương hiệu (Brand): {brief.get('brand', '')}\n"
        f"- Dòng sản phẩm (Product Line): {brief.get('product_line', '')}\n"
        f"- Danh mục ngắn: {brief.get('category', '')}\n"
        f"- Thời lượng mục tiêu: {brief.get('target_duration_sec', 25.0)} giây\n"
        f"- Điểm mạnh & USP bắt buộc: {brief.get('usps', '')}\n"
        f"- Ưu đãi & CTA: {brief.get('offer_cta', '')}\n"
        f"- Từ ngữ CẤM KỴ tuyệt đối không viết (Toàn app + Brief): {banned_str or 'Không có'}\n"
        f"- Brief gốc nhãn hàng:\n{str(brief.get('raw_brief') or '')[:1500] or '(Chưa dán brief thô)'}\n"
        f"- Từ điển phiên âm (Giọng AI vs Phụ đề):\n{pm_lines}\n"
    )


def _ensure_raw_frames_extracted(raw_videos: list[dict[str, Any]]) -> Path:
    frames_base = DIR_FRAMES / "02_video_tho"
    manifest_file = frames_base / "manifest.json"
    need_extract = not manifest_file.exists()
    if not need_extract:
        try:
            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8-sig"))
            manifest_sources = {item.get("source") for item in manifest_data.get("videos", [])}
            current_sources = {v["rel_path"] for v in raw_videos}
            if not current_sources.issubset(manifest_sources):
                need_extract = True
        except Exception:
            need_extract = True

    if need_extract:
        run_python_script(
            "scripts/extract_frames.py",
            ["--source", "02_video_tho", "--fps", "1.0", "--max-width", "540", "--transcribe", "never"],
        )
    return frames_base


def _sanitize_plan_clips(
    raw_clips: list[Any],
    raw_videos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not raw_videos:
        return []
    dur_map = {v["rel_path"]: float(v["duration_sec"] or 5.0) for v in raw_videos}
    raw_paths = [v["rel_path"] for v in raw_videos]
    by_name = {Path(p).name: p for p in raw_paths}
    rr_idx = 0
    cleaned_clips: list[dict[str, Any]] = []
    for c in raw_clips or []:
        if not isinstance(c, dict):
            continue
        src = str(c.get("source") or "").replace("\\", "/").strip()
        if src not in dur_map:
            matched = by_name.get(Path(src).name) if src else None
            if matched and matched in dur_map:
                src = matched
            else:
                src = raw_paths[rr_idx % len(raw_paths)]
                rr_idx += 1
        max_d = dur_map[src]
        st = max(0.0, min(float(c.get("start", 0.0)), max(0.0, max_d - 0.5)))
        en = min(max_d, max(st + 0.5, float(c.get("end", min(max_d, st + 2.5)))))
        if st < 1.0 and max_d > (en - st) + 3.0:
            span = en - st
            st = 1.5
            en = min(max_d, st + span)
        cleaned_clips.append(
            {
                "source": src,
                "start": round(st, 2),
                "end": round(en, 2),
                "speed": round(max(0.5, min(2.0, float(c.get("speed", 1.0)))), 2),
                "mute": bool(c.get("mute", True)),
                "crop_mode": c.get("crop_mode") if c.get("crop_mode") in ("center", "blur_bg") else "center",
                "note": str(c.get("note") or ""),
            }
        )
    if len(raw_paths) > 1 and len(cleaned_clips) >= 2:
        unique_srcs = {c["source"] for c in cleaned_clips}
        if len(unique_srcs) <= 1:
            cursor_map = {p: (1.5 if dur_map[p] > 8.0 else 0.0) for p in raw_paths}
            for idx, cc in enumerate(cleaned_clips):
                new_src = raw_paths[idx % len(raw_paths)]
                max_d = dur_map[new_src]
                span = max(0.8, min(float(cc["end"]) - float(cc["start"]), max(0.8, max_d - 0.6)))
                st = cursor_map.get(new_src, 0.0)
                if st + span > max_d:
                    st = 1.0 if max_d > span + 1.5 else 0.0
                en = min(max_d, st + span)
                if en - st < 0.5:
                    st = 0.0
                    en = min(max_d, max(0.5, span))
                cc["source"] = new_src
                cc["start"] = round(st, 2)
                cc["end"] = round(en, 2)
                cursor_map[new_src] = en + 0.6
    return cleaned_clips


def _finalize_workshop_plan(
    *,
    raw_parsed: dict[str, Any],
    brief: dict[str, Any],
    target_dur: float,
    raw_videos: list[dict[str, Any]],
    preserve_clips: bool,
    product_note: str = "",
    engine: str = "smart_brief",
) -> dict[str, Any]:
    """Normalize 3 script options, auto-apply AI Critic duration & phonetic fixes, and respect clip lock."""
    fallback_bundle = generate_three_script_options_fallback(brief, target_dur, product_note)
    fallback_opts = fallback_bundle["options"]

    raw_opts = raw_parsed.get("script_options")
    final_options: list[dict[str, Any]] = []
    if isinstance(raw_opts, list) and raw_opts:
        for idx, item in enumerate(raw_opts[:3], start=1):
            if not isinstance(item, dict):
                continue
            disp = str(item.get("script_display") or item.get("script_text") or "").strip()
            tts = str(item.get("script_text") or "").strip()
            if not disp and not tts:
                continue
            fixed_disp, fixed_tts, spoken_cnt = ensure_script_meets_duration(
                disp, tts, target_duration_sec=target_dur, brand_brief=brief, option_index=idx
            )
            fb_ref = fallback_opts[min(idx - 1, len(fallback_opts) - 1)]
            eff_banned = get_effective_banned_words(brief)
            clean_hook = sanitize_banned_text(str(item.get("hook_badge") or fb_ref["hook_badge"]), banned_words=eff_banned)[:48]
            final_options.append(
                {
                    "id": str(item.get("id") or f"opt{idx}"),
                    "title": str(item.get("title") or fb_ref["title"]),
                    "angle": str(item.get("angle") or fb_ref["angle"]),
                    "hook_badge": clean_hook or fb_ref["hook_badge"],
                    "script_display": fixed_disp,
                    "script_text": fixed_tts,
                    "spoken_words": spoken_cnt,
                    "sentence_count": len([s for s in re.split(r"(?<=[.!?])\s+", fixed_disp) if s.strip()]),
                    "estimated_duration_sec": round(spoken_cnt / 4.75, 1),
                }
            )

    # Top up to 3 distinct script options if LLM supplied fewer than 3
    while len(final_options) < 3:
        fb = dict(fallback_opts[len(final_options)])
        if final_options and len(final_options) == 1 and str(raw_parsed.get("script_text") or "").strip():
            pass
        fb["id"] = f"opt{len(final_options) + 1}"
        final_options.append(fb)

    # If LLM only supplied top-level script_display/script_text without script_options, upgrade opt1 with it
    top_disp = str(raw_parsed.get("script_display") or "").strip()
    top_tts = str(raw_parsed.get("script_text") or "").strip()
    if (not isinstance(raw_opts, list) or not raw_opts) and (top_disp or top_tts):
        fixed_disp, fixed_tts, spoken_cnt = ensure_script_meets_duration(
            top_disp or top_tts, top_tts, target_duration_sec=target_dur, brand_brief=brief, option_index=1
        )
        final_options[0].update(
            {
                "script_display": fixed_disp,
                "script_text": fixed_tts,
                "spoken_words": spoken_cnt,
                "estimated_duration_sec": round(spoken_cnt / 4.75, 1),
            }
        )

    rec_id = str(raw_parsed.get("recommended_id") or final_options[0]["id"]).strip()
    chosen = next((o for o in final_options if o["id"] == rec_id), final_options[0])

    # Handle Edit Plan cleanly without overwriting user clips when preserve_clips=True
    existing_plan: dict[str, Any] = {}
    if FILE_EDIT_PLAN.exists():
        try:
            existing_plan = json.loads(FILE_EDIT_PLAN.read_text(encoding="utf-8-sig"))
        except Exception:
            existing_plan = {}
    existing_clips = existing_plan.get("clips") if isinstance(existing_plan.get("clips"), list) else []

    plan_obj = raw_parsed.get("edit_plan") if isinstance(raw_parsed.get("edit_plan"), dict) else {}
    clips_preserved = bool(preserve_clips and existing_clips)
    if not clips_preserved:
        cleaned = _sanitize_plan_clips(plan_obj.get("clips") or [], raw_videos)
        if cleaned:
            new_plan = {
                "title": str(plan_obj.get("title") or brief.get("brand") or "San pham TikTok Shop"),
                "target_resolution": [1080, 1920],
                "target_fps": 30,
                "concat_draft": True,
                "keep_clip_audio": False,
                "clips": cleaned,
            }
            FILE_EDIT_PLAN.parent.mkdir(parents=True, exist_ok=True)
            FILE_EDIT_PLAN.write_text(json.dumps(new_plan, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save chosen active script + separate readable files for all 3 script options
    FILE_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
    FILE_SCRIPT.write_text(chosen["script_text"] + "\n", encoding="utf-8")
    (DIR_WORKSPACE / "kich_ban_hien_thi.md").write_text(chosen["script_display"] + "\n", encoding="utf-8")
    for opt_item in final_options:
        oid = str(opt_item.get("id") or "").strip()
        if not oid:
            continue
        (DIR_WORKSPACE / f"kich_ban_{oid}.txt").write_text(str(opt_item.get("script_text") or "") + "\n", encoding="utf-8")
        (DIR_WORKSPACE / f"kich_ban_{oid}_hien_thi.md").write_text(str(opt_item.get("script_display") or "") + "\n", encoding="utf-8")

    # Sync Hook/CTA & Director metadata if provided
    save_openreel_hook_md(
        hook_text=chosen.get("hook_badge") or "",
        cta_text=sanitize_cta_text(str(raw_parsed.get("cta_text") or brief.get("offer_cta") or ""), 34),
    )
    if isinstance(raw_parsed.get("callouts"), list) or isinstance(raw_parsed.get("floral_badge"), dict):
        cur_dir: dict[str, Any] = {}
        if FILE_DIRECTOR_PLAN.exists():
            try:
                cur_dir = json.loads(FILE_DIRECTOR_PLAN.read_text(encoding="utf-8-sig"))
            except Exception:
                cur_dir = {}
        cur_dir["hook_options"] = [
            {"angle": o.get("angle", ""), "text": o.get("hook_badge", "")} for o in final_options
        ]
        cur_dir["best_hook"] = chosen.get("hook_badge", "")
        if isinstance(raw_parsed.get("callouts"), list):
            cur_dir["callouts"] = raw_parsed["callouts"]
        if isinstance(raw_parsed.get("floral_badge"), dict):
            cur_dir["floral_badge"] = raw_parsed["floral_badge"]
        FILE_DIRECTOR_PLAN.write_text(json.dumps(cur_dir, ensure_ascii=False, indent=2), encoding="utf-8")

    aligned_plan = align_edit_plan_to_voice_beats(
        raw_videos, preserve_clips=True if clips_preserved else False, target_duration_override=target_dur
    )

    raw_fixes = raw_parsed.get("auto_critic_fixes")
    critic_fixes = (
        [str(x).strip() for x in raw_fixes if str(x).strip()]
        if isinstance(raw_fixes, list) and raw_fixes
        else list(fallback_bundle["auto_critic_fixes"])
    )
    if clips_preserved:
        critic_fixes.append(
            f"Đã khóa bảo vệ giữ nguyên {len(aligned_plan.get('clips') or [])} cảnh Clips của bạn (không bị ghi đè khi đổi kịch bản)."
        )

    options_payload = save_script_options(
        {
            "engine": engine,
            "target_duration_sec": target_dur,
            "recommended_id": chosen["id"],
            "selected_id": chosen["id"],
            "clips_preserved": clips_preserved,
            "auto_critic_applied": True,
            "auto_critic_fixes": critic_fixes,
            "options": final_options,
            "updated_at": int(time.time()),
        }
    )

    critic_md = build_auto_critic_report_md(
        target_duration_sec=target_dur,
        options=final_options,
        auto_fixes=critic_fixes,
        preserve_clips=clips_preserved,
        clip_count=len(aligned_plan.get("clips") or []),
    )
    FILE_CRITIC_MD.write_text(critic_md, encoding="utf-8")

    return {
        "script_text": chosen["script_text"],
        "script_display": chosen["script_display"],
        "script_options": options_payload,
        "edit_plan": aligned_plan,
        "critic_report": critic_md,
        "clips_preserved": clips_preserved,
    }


def _build_three_option_planner_prompt(
    *,
    brief: dict[str, Any],
    raw_meta_lines: str,
    product_note: str,
    style_guide: str,
    frames_summary: str,
    target_dur: float,
    preserve_clips: bool,
    short_content_mode: str = "brand_brief",
) -> str:
    target_words, min_words, target_sents = compute_target_word_budget(target_dur)
    clip_rule = (
        "- Người dùng đang BẬT khóa bảo vệ Clips: không cần thay đổi cấu trúc clip có sẵn, vẫn gợi ý 3–4 `callouts` theo giây để hiển thị nhãn đa sắc.\n"
        if preserve_clips
        else (
            f"- Xem kỹ khung hình từng video thô, khớp ĐÚNG cảnh với câu thoại tương ứng, chọn đoạn `start` không tĩnh/rung, "
            f"linh hoạt `speed` từ `0.88` (slow-mo cận cảnh) đến `1.28` (tua nhanh thao tác phụ), `source` PHẢI khớp danh sách video thô bên dưới, tổng ~{target_dur:.0f}s.\n"
        )
    )
    if str(short_content_mode or "brand_brief").strip() == "story_note":
        note_clean = product_note.strip() or "Tự cảm nhận từ khung hình video thô và kể lại một khoảnh khắc đời thường tự nhiên, chân thực."
        return (
            "Bạn là Đạo diễn Tiền Kỳ cho kênh TikTok Story / Đời sống / Vlog ngắn (KHÔNG BÁN HÀNG).\n"
            "TUYỆT ĐỐI KHÔNG nhắc tên thương hiệu ảo, KHÔNG chèn lời kêu gọi mua hàng, giỏ hàng, chốt đơn, giá cả hay giảm giá.\n"
            "Trả về DUY NHẤT một JSON hợp lệ gồm:\n"
            "1. `script_options`: Mảng ĐÚNG 3 phương án kịch bản lồng tiếng Story ngắn tự nhiên, gần gũi, cảm xúc thật, áp dụng 3 góc kể chuyện ĐA DẠNG "
            "(ví dụ: Nhật ký trải nghiệm cá nhân / Góc nhìn chậm rãi & cảm xúc / Chia sẻ khoảnh khắc đáng nhớ). Mỗi item gồm:\n"
            "   - `id`: \"opt1\" / \"opt2\" / \"opt3\"\n"
            "   - `title`: Tiêu đề ngắn mô tả góc tiếp cận\n"
            "   - `angle`: Từ khóa góc (vd: \"Nhật ký\", \"Cảm xúc\", \"Khoảnh khắc\")\n"
            "   - `hook_badge`: Tiêu đề Hook ngắn <= 38 ký tự để hiện 3s đầu video (không giật tít bán hàng)\n"
            f"   - `script_display`: Kịch bản bản ĐẸP cho Phụ đề Karaoke, PHẢI ĐẠT {min_words}–{target_words + 8} âm tiết/từ "
            f"(chia rõ {target_sents} câu bằng dấu `.`) để đọc thực tế đủ {target_dur:.0f} giây (tuyệt đối KHÔNG viết ngắn quá dưới {min_words} từ!).\n"
            "   - `script_text`: Kịch bản phiên âm tiếng Việt thuần 100% tương ứng ĐÚNG TỪNG CÂU 1-1 với `script_display` để đọc bằng TTS (chỉ dùng `.` và `,`, không emoji/markdown).\n"
            "2. `recommended_id`: \"opt1\" / \"opt2\" / \"opt3\"\n"
            "3. `auto_critic_fixes`: Mảng 3-5 gạch đầu dòng những lỗi/điểm yếu bạn đã tự phát hiện và đã TỰ SỬA NGAY vào 3 kịch bản trên.\n"
            f"4. `callouts`: Mảng 3-4 nhãn nổi bật về khoảnh khắc/địa điểm/cảm xúc (`text` <= 20 ký tự, `startTime`, `duration`: 2.2, `y`: 0.17) rải đều trong {target_dur:.0f}s.\n"
            "5. `floral_badge`: Object `brand` (tên chủ đề ngắn), `product_line` (phụ đề mood ngắn), `category` (\"Story\").\n"
            f"6. `edit_plan`: Object gồm `title` và `clips`.\n{clip_rule}\n"
            f"=== MÔ TẢ VIDEO / STORY TỪ NGƯỜI DÙNG ===\n{note_clean}\n\n"
            f"=== DANH SÁCH VIDEO THÔ HỢP LỆ ===\n{raw_meta_lines}\n\n"
            f"=== TÓM TẮT KHUNG HÌNH ===\n{frames_summary[:2200]}\n"
        )
    ch_ctx = load_channel_script_dna_context()
    sample_block = (
        f"=== LỜI THOẠI MẪU THỰC TẾ CỦA KÊNH (BẮT BUỘC HỌC NHỊP CÂU, CÁCH XƯNG HÔ '{ch_ctx['pronoun']}' & CÁCH CHỐT CTA) ===\n"
        f"{ch_ctx['sample_transcripts']}\n\n"
        if ch_ctx.get("sample_transcripts")
        else ""
    )
    return (
        "Bạn là Đạo diễn Tiền Kỳ & AI Critic Tự Sửa Lỗi cho kênh TikTok Shop.\n"
        "TRƯỚC KHI người dùng bấm Tạo Giọng hay Cắt Clip, bạn phải LÊN KẾ HOẠCH + TỰ PHÊ BÌNH VÀ TỰ ÁP DỤNG ĐỀ XUẤT LUÔN.\n"
        "Trả về DUY NHẤT một JSON hợp lệ gồm:\n"
        "1. `script_options`: Mảng ĐÚNG 3 phương án kịch bản lồng tiếng tự nhiên, KHÔNG viết văn mẫu sáo rỗng, áp dụng 3 format kể chuyện ĐA DẠNG "
        "(tự chọn 3 format phù hợp nhất từ: POV Tâm sự đời thường / So sánh Trải nghiệm thật / Bắt trend Hỏi-Đáp / Mở hộp nhanh & Săn Deal). Mỗi item gồm:\n"
        "   - `id`: \"opt1\" / \"opt2\" / \"opt3\"\n"
        "   - `title`: Tiêu đề ngắn mô tả góc tiếp cận\n"
        "   - `angle`: Từ khóa góc (vd: \"Nỗi đau\", \"Trải nghiệm\", \"Combo Deal\")\n"
        "   - `hook_badge`: Tiêu đề Hook ngắn <= 38 ký tự để hiện 3s đầu video\n"
        f"   - `script_display`: Kịch bản bản ĐẸP cho Phụ đề Karaoke, PHẢI ĐẠT {min_words}–{target_words + 8} âm tiết/từ "
        f"(chia rõ {target_sents} câu bằng dấu `.`) để đọc thực tế đủ {target_dur:.0f} giây (tuyệt đối KHÔNG viết ngắn quá dưới {min_words} từ!), "
        "nhắc đầy đủ tất cả sản phẩm & USP trong Brand Brief.\n"
        "   - `script_text`: Kịch bản phiên âm tiếng Việt thuần 100% tương ứng ĐÚNG TỪNG CÂU 1-1 với `script_display` để đọc bằng F5-TTS (chỉ dùng `.` và `,`, không emoji/markdown).\n"
        "2. `recommended_id`: \"opt1\" / \"opt2\" / \"opt3\"\n"
        "3. `auto_critic_fixes`: Mảng 3-5 gạch đầu dòng những lỗi/điểm yếu bạn đã tự phát hiện (thiếu thời lượng, thiếu tên sản phẩm combo, từ tiếng Anh khó đọc...) và đã TỰ SỬA NGAY vào 3 kịch bản trên.\n"
        f"4. `callouts`: Mảng 3-4 nhãn nổi bật (`text` <= 20 ký tự, `startTime`, `duration`: 2.2, `y`: 0.17) rải đều trong {target_dur:.0f}s.\n"
        "5. `floral_badge`: Object `brand`, `product_line`, `category`.\n"
        f"6. `edit_plan`: Object gồm `title` và `clips`.\n{clip_rule}\n"
        f"{_format_brand_brief_prompt_block(brief)}\n"
        f"=== DANH SÁCH VIDEO THÔ HỢP LỆ ===\n{raw_meta_lines}\n\n"
        f"=== GHI CHÚ BỔ SUNG ===\n{product_note.strip() or brief.get('usps') or 'Tự nhận diện từ khung hình video thô.'}\n\n"
        f"=== PHONG CÁCH KÊNH (phong_cach_kenh.md) ===\n{(style_guide or ch_ctx.get('style_guide') or 'Chốt đơn nhanh, Hook 3s đầu, ngôn ngữ tự nhiên.')[:3200]}\n\n"
        f"{sample_block}"
        f"=== TÓM TẮT KHUNG HÌNH ===\n{frames_summary[:2200]}\n"
    )


@app.post("/api/workshop/plan-gemini")
def api_workshop_plan_gemini(req: GeminiWorkshopPlanReq):
    cfg = load_config()
    api_key = str(cfg.get("gemini_api_key") or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Chưa cấu hình Gemini API Key. Bấm vào badge AI trên Header để nhập key.",
        )
    model = (req.model or cfg.get("gemini_model") or "gemini-2.5-flash").strip()
    effort = req.effort or cfg.get("gemini_effort") or "medium"

    raw_videos = list_media_in_dir(DIR_VIDEO_THO)
    if not raw_videos:
        raise HTTPException(status_code=400, detail="Thư mục 02_video_tho đang trống. Hãy tải hoặc kéo thả video thô vào trước.")

    brief = load_brand_brief()
    target_dur = float(req.target_duration or brief.get("target_duration_sec") or 30.0)
    brief = save_brand_brief({"target_duration_sec": target_dur})
    frames_base = _ensure_raw_frames_extracted(raw_videos)

    style_guide = FILE_STYLE_GUIDE.read_text(encoding="utf-8-sig") if FILE_STYLE_GUIDE.exists() else ""
    frames_summary = (frames_base / "tom_tat_khung_hinh.md").read_text(encoding="utf-8-sig") if (frames_base / "tom_tat_khung_hinh.md").exists() else ""
    raw_meta_lines = "\n".join(
        f"- source: \"{v['rel_path']}\" | duration: {v['duration_sec']}s | resolution: {v['width']}x{v['height']}"
        for v in raw_videos
    )
    prompt_text = _build_three_option_planner_prompt(
        brief=brief,
        raw_meta_lines=raw_meta_lines,
        product_note=req.product_note,
        style_guide=style_guide,
        frames_summary=frames_summary,
        target_dur=target_dur,
        preserve_clips=req.preserve_clips,
        short_content_mode=str(getattr(req, "short_content_mode", "brand_brief") or "brand_brief"),
    )

    parts: list[dict[str, Any]] = [{"text": prompt_text}]
    per_video_limit = max(3, min(6, 18 // max(1, len(raw_videos))))
    raw_by_stem = {Path(v["rel_path"]).stem: v for v in raw_videos}

    if frames_base.exists():
        for subdir in sorted(p for p in frames_base.iterdir() if p.is_dir()):
            jpgs = sorted(subdir.glob("frame_*.jpg"))
            chosen = select_representative_frames(jpgs, max_frames=per_video_limit)
            if not chosen:
                continue
            src_info = raw_by_stem.get(subdir.name)
            src_label = src_info["rel_path"] if src_info else subdir.name
            parts.append({"text": f"\n--- Khung hình từ source: {src_label} ---"})
            for jpg in chosen:
                b64 = base64.b64encode(jpg.read_bytes()).decode("ascii")
                parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})

    raw_json = call_gemini_multimodal(
        parts,
        api_key=api_key,
        model=model,
        effort=effort,
        response_mime_type="application/json",
        timeout=120,
    )
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Gemini trả về JSON không hợp lệ: {exc}")

    fin = _finalize_workshop_plan(
        raw_parsed=parsed,
        brief=brief,
        target_dur=target_dur,
        raw_videos=raw_videos,
        preserve_clips=req.preserve_clips,
        product_note=req.product_note,
        engine="gemini",
    )
    return {
        "ok": True,
        "engine": "gemini",
        "model": model,
        "effort": effort,
        **fin,
        "state": collect_workshop_state(),
    }


@app.post("/api/workshop/plan-agy")
def api_workshop_plan_agy(req: AgyWorkshopPlanReq):
    cfg = load_config()
    model = (req.model or cfg.get("agy_model") or DEFAULT_CONFIG["agy_model"]).strip()
    effort = req.effort or cfg.get("agy_effort") or DEFAULT_CONFIG["agy_effort"]

    raw_videos = list_media_in_dir(DIR_VIDEO_THO)
    if not raw_videos:
        raise HTTPException(
            status_code=400,
            detail="Thư mục 02_video_tho đang trống. Hãy tải hoặc kéo thả video thô vào trước.",
        )

    frames_base = _ensure_raw_frames_extracted(raw_videos)
    brief = load_brand_brief()
    target_dur = float(req.target_duration or brief.get("target_duration_sec") or 30.0)
    brief = save_brand_brief({"target_duration_sec": target_dur})
    style_guide = FILE_STYLE_GUIDE.read_text(encoding="utf-8-sig") if FILE_STYLE_GUIDE.exists() else ""
    frames_summary = (frames_base / "tom_tat_khung_hinh.md").read_text(encoding="utf-8-sig") if (frames_base / "tom_tat_khung_hinh.md").exists() else ""

    raw_meta_lines = "\n".join(
        f"- source: \"{v['rel_path']}\" | duration: {v['duration_sec']}s | resolution: {v['width']}x{v['height']}"
        for v in raw_videos
    )
    planner_spec = _build_three_option_planner_prompt(
        brief=brief,
        raw_meta_lines=raw_meta_lines,
        product_note=req.product_note,
        style_guide=style_guide,
        frames_summary=frames_summary,
        target_dur=target_dur,
        preserve_clips=req.preserve_clips,
        short_content_mode=str(getattr(req, "short_content_mode", "brand_brief") or "brand_brief"),
    )
    clip_save_note = (
        "4. KHÔNG ghi đè `04_workspace/edit_plan.json` vì người dùng đang khóa giữ Clips.\n"
        if req.preserve_clips
        else "4. Ghi `04_workspace/edit_plan.json` theo mảng `clips` đã chọn.\n"
    )
    prompt = (
        "Hãy thực hiện Giai đoạn Lập Kế Hoạch & Tự Phê Bình Tiền Kỳ cho TikTok Shop (tương thích skill `.agents/skills/dung-tiktok/SKILL.md`).\n"
        "Dùng `view_file` xem một số ảnh đại diện trong `04_workspace/frames/02_video_tho/`.\n"
        f"{planner_spec}\n\n"
        "Hành động ghi file:\n"
        "1. Ghi kết quả JSON đầy đủ (gồm `script_options` đủ 3 kịch bản, `auto_critic_fixes`, `callouts`, `floral_badge`) vào `04_workspace/script_options.json`.\n"
        "2. Ghi `04_workspace/kich_ban.txt` và `04_workspace/kich_ban_hien_thi.md` theo phương án `recommended_id`.\n"
        f"{clip_save_note}"
        "5. KHÔNG chạy `voice_engine.py`, `prepare_clips.py` hay `remotion_renderer.py`. Trả lời ngắn gọn: DONE."
    )
    cli_res = call_agy_cli(prompt, model=model, effort=effort, mode="auto", timeout=300)

    raw_parsed: dict[str, Any] = load_script_options()
    if not raw_parsed.get("options") and isinstance(cli_res.get("response"), str):
        txt = cli_res["response"]
        si, ei = txt.find("{"), txt.rfind("}")
        if si >= 0 and ei > si:
            try:
                raw_parsed = json.loads(txt[si : ei + 1])
            except Exception:
                pass
    if FILE_SCRIPT.exists() and not raw_parsed.get("script_text"):
        raw_parsed["script_text"] = FILE_SCRIPT.read_text(encoding="utf-8-sig").strip()
    if (DIR_WORKSPACE / "kich_ban_hien_thi.md").exists() and not raw_parsed.get("script_display"):
        raw_parsed["script_display"] = (DIR_WORKSPACE / "kich_ban_hien_thi.md").read_text(encoding="utf-8-sig").strip()
    if not raw_parsed.get("script_options") and isinstance(raw_parsed.get("options"), list):
        raw_parsed["script_options"] = raw_parsed["options"]

    fin = _finalize_workshop_plan(
        raw_parsed=raw_parsed,
        brief=brief,
        target_dur=target_dur,
        raw_videos=raw_videos,
        preserve_clips=req.preserve_clips,
        product_note=req.product_note,
        engine="agy",
    )
    return {
        "ok": True,
        "engine": "agy",
        "model": model,
        "effort": effort,
        "duration_seconds": cli_res.get("duration_seconds"),
        **fin,
        "state": collect_workshop_state(),
    }


@app.post("/api/workshop/plan-auto")
def api_workshop_plan_auto(req: GeminiWorkshopPlanReq):
    """Unified Pre-Production Plan + Self-Applying AI Critic + 3 Script Options (Gemini -> Agy -> Smart Brief)."""
    content_mode = str(getattr(req, "short_content_mode", "brand_brief") or "brand_brief").strip()
    if content_mode != "story_note":
        brief_ready, brief_reason = is_brand_brief_ready()
        if not brief_ready:
            raise HTTPException(status_code=400, detail=brief_reason)
    t_level = str(req.transition_level or "balanced")
    update_style_dna({"transition_level": t_level})
    pacing_hint = (
        "[Nhịp dựng NHẸ: câu văn mạch lạc êm ái, chia 4-6 cảnh dài]"
        if t_level == "gentle"
        else "[Nhịp dựng MẠNH: câu ngắn dứt khoát theo beat, chia 9-12 cảnh nhanh]"
        if t_level == "energetic"
        else "[Nhịp dựng CÂN BẰNG: câu tự nhiên, chia 6-8 cảnh]"
    )
    if pacing_hint not in (req.product_note or ""):
        req.product_note = f"{(req.product_note or '').strip()} {pacing_hint}".strip()
    raw_videos = list_media_in_dir(DIR_VIDEO_THO)
    if not raw_videos:
        raise HTTPException(
            status_code=400,
            detail="Thư mục 02_video_tho đang trống. Hãy tải hoặc kéo thả video thô vào trước.",
        )
    cfg = load_config()
    if str(cfg.get("gemini_api_key") or "").strip():
        try:
            return api_workshop_plan_gemini(req)
        except Exception:
            pass
    if find_agy_executable():
        try:
            return api_workshop_plan_agy(
                AgyWorkshopPlanReq(
                    product_note=req.product_note,
                    target_duration=req.target_duration,
                    preserve_clips=req.preserve_clips,
                    short_content_mode=content_mode,
                )
            )
        except Exception:
            pass

    brief = load_brand_brief()
    target_dur = float(req.target_duration or brief.get("target_duration_sec") or 30.0)
    brief = save_brand_brief({"target_duration_sec": target_dur})
    fb = generate_three_script_options_fallback(
        brief,
        target_dur,
        req.product_note,
        content_vibe="daily_story" if content_mode == "story_note" else "learned_dna",
    )
    fin = _finalize_workshop_plan(
        raw_parsed={
            "script_options": fb["options"],
            "recommended_id": fb["recommended_id"],
            "auto_critic_fixes": fb["auto_critic_fixes"],
        },
        brief=brief,
        target_dur=target_dur,
        raw_videos=raw_videos,
        preserve_clips=req.preserve_clips,
        product_note=req.product_note,
        engine="smart_brief",
    )
    return {
        "ok": True,
        "engine": "smart_brief",
        **fin,
        "state": collect_workshop_state(),
    }


@app.post("/api/workshop/select-script")
def api_workshop_select_script(req: SelectScriptReq):
    """Select one of the 3 generated scripts (without overwriting clips if preserve_clips=True) and optionally export MP4."""
    brief = load_brand_brief()
    if req.target_duration_sec and float(req.target_duration_sec) >= 8.0:
        brief = save_brand_brief({"target_duration_sec": float(req.target_duration_sec)})
    target_dur = float(req.target_duration_sec or brief.get("target_duration_sec") or 30.0)
    bundle = load_script_options()
    options = bundle.get("options") if isinstance(bundle.get("options"), list) else []

    chosen = next((o for o in options if o.get("id") == req.option_id), options[0] if options else None)
    if req.custom_script_display.strip() or req.custom_script_text.strip():
        disp = req.custom_script_display.strip() or restore_display_text(req.custom_script_text.strip(), brief)
        tts = req.custom_script_text.strip() or convert_display_to_tts_script(disp, brief)
    elif chosen:
        disp = str(chosen.get("script_display") or "").strip()
        tts = str(chosen.get("script_text") or "").strip()
    else:
        raise HTTPException(status_code=400, detail="Chưa có bộ 3 kịch bản. Hãy bấm 'AI Lên Kế Hoạch' trước.")

    if not tts:
        tts = convert_display_to_tts_script(disp, brief)
    FILE_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
    FILE_SCRIPT.write_text(tts + "\n", encoding="utf-8")
    (DIR_WORKSPACE / "kich_ban_hien_thi.md").write_text(disp + "\n", encoding="utf-8")

    if bundle:
        bundle["selected_id"] = req.option_id
        bundle["clips_preserved"] = bool(req.preserve_clips)
        save_script_options(bundle)

    if chosen and chosen.get("hook_badge"):
        save_openreel_hook_md(
            hook_text=str(chosen["hook_badge"]),
            cta_text=str(chosen.get("cta_text") or brief.get("offer_cta") or ""),
        )

    raw_videos = list_media_in_dir(DIR_VIDEO_THO)
    if FILE_EDIT_PLAN.exists() and raw_videos:
        align_edit_plan_to_voice_beats(
            raw_videos,
            preserve_clips=req.preserve_clips,
            target_duration_override=target_dur,
        )

    pipeline_status = None
    if req.auto_export_mp4:
        with PIPELINE_LOCK:
            if PIPELINE_STATE["running"]:
                raise HTTPException(status_code=409, detail="Pipeline đang chạy, vui lòng chờ hoàn tất.")
        _reset_pipeline_state()
        p_req = OneClickPipelineReq(
            target_duration_sec=target_dur,
            product_note="",
            regenerate_script=False,
            force_tts=True,
            preserve_clips=req.preserve_clips,
            selected_option_id=req.option_id,
            badge_style=req.badge_style,
            visual_theme=req.visual_theme,
            layout_style=req.layout_style,
            color_preset=req.color_preset,
            creative_mode=req.creative_mode,
            camera_intensity=req.camera_intensity,
            bgm_track=req.bgm_track,
            sync=False,
        )
        t = threading.Thread(target=_run_pipeline_worker, args=(p_req,), daemon=True)
        t.start()
        pipeline_status = api_pipeline_status()

    return {
        "ok": True,
        "selected_id": req.option_id,
        "script_text": tts,
        "script_display": disp,
        "preserve_clips": req.preserve_clips,
        "pipeline": pipeline_status,
        "state": collect_workshop_state(),
    }


# ---------------------------------------------------------------------------
# Tab 5: OpenReel Video & Output Management
# ---------------------------------------------------------------------------
# (FILE_OPENREEL_HOOK_MD, FILE_DIRECTOR_PLAN, FILE_CRITIC_MD được quản lý trong refresh_app_project_paths)
DIR_ASSETS_AUDIO = PROJECT_ROOT / "06_assets_audio"
DIR_ASSETS_BGM = DIR_ASSETS_AUDIO / "bgm"


def wrap_tiktok_text(text: str, max_chars_per_line: int = 18, max_lines: int = 2) -> str:
    """Ngắt dòng thông minh theo từ để chữ không bao giờ tràn khỏi khung 1080px."""
    clean = re.sub(r"\s+", " ", (text or "").replace("\n", " ")).strip()
    if not clean:
        return ""
    words = clean.split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        candidate = f"{cur} {w}".strip() if cur else w
        if len(candidate) <= max_chars_per_line or not cur:
            cur = candidate
        else:
            lines.append(cur)
            cur = w
            if len(lines) >= max_lines - 1:
                break
    if cur:
        # Thêm phần còn lại nếu chưa tới max_lines
        used_words = sum(len(ln.split(" ")) for ln in lines)
        rest_words = words[used_words:]
        if rest_words:
            lines.append(" ".join(rest_words))
    # Nếu dòng cuối vẫn hơi dài, tách đôi nếu còn slot hoặc giữ gọn
    if len(lines) == 1 and len(lines[0]) > max_chars_per_line and max_lines >= 2:
        ws = lines[0].split(" ")
        mid = max(1, len(ws) // 2)
        lines = [" ".join(ws[:mid]), " ".join(ws[mid:])]
    return "\n".join(lines[:max_lines])


def fit_font_size(wrapped_text: str, base_size: int = 50, min_size: int = 32, max_width_px: int = 840) -> int:
    """Tự động thu nhỏ fontSize nếu dòng dài nhất có nguy cơ vượt vùng an toàn 840px (trên 1080px)."""
    lines = [ln.strip() for ln in (wrapped_text or "").split("\n") if ln.strip()]
    if not lines:
        return base_size
    longest = max(len(ln) for ln in lines)
    # Ước lượng bề rộng chữ bold Montserrat ~ 0.62 * fontSize mỗi ký tự
    est_size = int(max_width_px / max(1.0, longest * 0.62))
    return max(min_size, min(base_size, est_size))


class OpenReelDirectorReq(BaseModel):
    product_note: str = ""
    apply_trim: bool = True
    preserve_clips: bool = True


class OpenReelHookSaveReq(BaseModel):
    hook_text: str = ""
    cta_text: str = "CHỐT ĐƠN NGAY GIỎ HÀNG 👇"
    hook_y: float = 0.18
    caption_style: str = "word-highlight"
    transition_type: str = "slide"
    caption_highlight_color: str = "#FFE500"


def load_openreel_hook_md() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "hook_text": "",
        "cta_text": "CHỐT ĐƠN NGAY GIỎ HÀNG 👇",
        "hook_y": 0.18,
        "caption_style": "word-highlight",
        "transition_type": "slide",
        "caption_highlight_color": "#FFE500",
    }
    if not FILE_OPENREEL_HOOK_MD.exists():
        return defaults
    raw = FILE_OPENREEL_HOOK_MD.read_text(encoding="utf-8-sig")
    section = ""
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("## "):
            section = s[3:].strip().lower()
            continue
        if not s or s.startswith("# ") or s.startswith(">"):
            continue
        if section.startswith("hook"):
            defaults["hook_text"] = s if not defaults["hook_text"] else f"{defaults['hook_text']}\n{s}"
        elif section.startswith("cta"):
            defaults["cta_text"] = s
        elif ":" in s:
            k, v = s.lstrip("- ").split(":", 1)
            k = k.strip().lower()
            v = v.strip().strip("`")
            if k == "hook_y":
                try:
                    defaults["hook_y"] = float(v)
                except ValueError:
                    pass
            elif k in ("caption_style", "transition_type", "caption_highlight_color"):
                defaults[k] = v
    return defaults


def save_openreel_hook_md(
    *,
    hook_text: str | None = None,
    cta_text: str | None = None,
    hook_y: float | None = None,
    caption_style: str | None = None,
    transition_type: str | None = None,
    caption_highlight_color: str | None = None,
) -> dict[str, Any]:
    cur = load_openreel_hook_md()
    if hook_text is not None:
        cur["hook_text"] = hook_text.strip()
    if cta_text is not None:
        cur["cta_text"] = cta_text.strip()
    if hook_y is not None:
        cur["hook_y"] = hook_y
    if caption_style is not None:
        cur["caption_style"] = caption_style
    if transition_type is not None:
        cur["transition_type"] = transition_type
    if caption_highlight_color is not None:
        cur["caption_highlight_color"] = caption_highlight_color

    md = (
        "# Hook & CTA OpenReel (`04_workspace/openreel_hook_cta.md`)\n\n"
        "> Tự động lưu từ AI Gợi ý Hook & CTA và bảng cấu hình Tab 5 để không bị mất khi tải lại trang.\n\n"
        "## Hook 3s đầu\n"
        f"{cur['hook_text']}\n\n"
        "## CTA cuối clip\n"
        f"{cur['cta_text']}\n\n"
        "## Cấu hình hiển thị\n"
        f"- hook_y: {cur['hook_y']}\n"
        f"- caption_style: `{cur['caption_style']}`\n"
        f"- transition_type: `{cur['transition_type']}`\n"
        f"- caption_highlight_color: `{cur['caption_highlight_color']}`\n"
    )
    FILE_OPENREEL_HOOK_MD.parent.mkdir(parents=True, exist_ok=True)
    FILE_OPENREEL_HOOK_MD.write_text(md, encoding="utf-8")
    return cur


@app.get("/api/openreel/status")
def api_openreel_status():
    proj_file = DIR_READY / "openreel_project.json"
    hook_cfg = load_openreel_hook_md()
    director_plan: dict[str, Any] = {}
    if FILE_DIRECTOR_PLAN.exists():
        try:
            director_plan = json.loads(FILE_DIRECTOR_PLAN.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
    critic_report = FILE_CRITIC_MD.read_text(encoding="utf-8-sig") if FILE_CRITIC_MD.exists() else ""
    bgm_files = list_media_in_dir(DIR_ASSETS_BGM) if DIR_ASSETS_BGM.exists() else []
    return {
        "online": is_port_open("127.0.0.1", 5173),
        "url": "http://localhost:5173",
        "ready_dir": str(DIR_READY),
        "output_dir": str(DIR_OUTPUT),
        "outputs": list_media_in_dir(DIR_OUTPUT),
        "project_ready": proj_file.exists(),
        "hook_cfg": hook_cfg,
        "director_plan": director_plan,
        "critic_report": critic_report,
        "bgm_count": len(bgm_files),
        "sfx_ready": (DIR_ASSETS_AUDIO / "sfx_whoosh.wav").exists(),
    }


def _parse_srt_timestamp(ts: str) -> float:
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) != 3:
        return 0.0
    try:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return 0.0


def parse_srt_to_openreel_subtitles(
    srt_text: str,
    *,
    animation_style: str = "word-highlight",
    color: str = "#FFFFFF",
    highlight_color: str = "#FFE500",
) -> list[dict[str, Any]]:
    subtitles: list[dict[str, Any]] = []
    blocks = [b.strip() for b in srt_text.replace("\r\n", "\n").split("\n\n") if b.strip()]
    for idx, block in enumerate(blocks, start=1):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if len(lines) < 2:
            continue
        time_idx = 1 if "-->" in lines[1] else (0 if "-->" in lines[0] else -1)
        if time_idx < 0:
            continue
        t_parts = lines[time_idx].split("-->")
        if len(t_parts) != 2:
            continue
        start_t = round(_parse_srt_timestamp(t_parts[0]), 3)
        end_t = round(max(start_t + 0.2, _parse_srt_timestamp(t_parts[1])), 3)
        text = " ".join(lines[time_idx + 1 :]).strip()
        if not text:
            continue

        raw_words = [w for w in text.split() if w]
        words_payload: list[dict[str, Any]] = []
        if raw_words:
            step = (end_t - start_t) / len(raw_words)
            for wi, w in enumerate(raw_words):
                ws = round(start_t + wi * step, 3)
                we = round(start_t + (wi + 1) * step, 3) if wi < len(raw_words) - 1 else end_t
                words_payload.append({"text": w, "startTime": ws, "endTime": max(ws + 0.05, we)})

        subtitles.append(
            {
                "id": f"sub_{idx:03d}",
                "text": text,
                "startTime": start_t,
                "endTime": end_t,
                "animationStyle": animation_style,
                "words": words_payload,
                "style": {
                    "fontFamily": "Montserrat",
                    "fontSize": 44,
                    "color": color,
                    "backgroundColor": "rgba(0,0,0,0.45)",
                    "position": "bottom",
                    "highlightColor": highlight_color,
                    "upcomingColor": "#E4E4E7",
                },
            }
        )
    return subtitles


def _default_hook_from_workspace() -> str:
    if FILE_SCRIPT.exists():
        raw = FILE_SCRIPT.read_text(encoding="utf-8-sig").strip()
        first_sentence = raw.split(".")[0].split(",")[0].strip()
        words = first_sentence.split()
        if words:
            return " ".join(words[:8]).upper()
    return "DEAL HỜI HÔM NAY 🔥"


def _suggest_hook_and_cta_via_ai() -> dict[str, str]:
    cfg = load_config()
    script_txt = FILE_SCRIPT.read_text(encoding="utf-8-sig").strip() if FILE_SCRIPT.exists() else ""
    style_txt = FILE_STYLE_GUIDE.read_text(encoding="utf-8-sig")[:2000] if FILE_STYLE_GUIDE.exists() else ""
    prompt = (
        "Dựa vào kịch bản và phong cách kênh TikTok Shop dưới đây, hãy trả về DUY NHẤT JSON gồm 2 trường:\n"
        "- `hook_text`: Tiêu đề Hook ngắn gọn 5-9 từ (IN HOA hoặc nhấn mạnh, có thể thêm 1 emoji đầu/cuối) đặt ở đầu video 3 giây đầu.\n"
        "- `cta_text`: Dòng chữ CTA ngắn 4-7 từ đặt ở 3 giây cuối (ví dụ: CHỐT ĐƠN NGAY GIỎ HÀNG 👇).\n\n"
        f"Kịch bản:\n{script_txt}\n\nPhong cách kênh:\n{style_txt}"
    )
    api_key = str(cfg.get("gemini_api_key") or "").strip()
    if api_key:
        raw = call_gemini_multimodal(
            [{"text": prompt}],
            api_key=api_key,
            model=cfg.get("gemini_model") or "gemini-2.5-flash",
            effort="low",
            response_mime_type="application/json",
            timeout=45,
        )
        data = json.loads(raw)
        return {
            "hook_text": str(data.get("hook_text") or _default_hook_from_workspace()).strip(),
            "cta_text": str(data.get("cta_text") or "CHỐT ĐƠN NGAY GIỎ HÀNG 👇").strip(),
        }
    if find_agy_executable():
        res = call_agy_cli(
            prompt + "\nChỉ trả về JSON thuần, không giải thích thêm.",
            model=cfg.get("agy_model") or DEFAULT_CONFIG["agy_model"],
            effort=cfg.get("agy_effort") or DEFAULT_CONFIG["agy_effort"],
            mode="auto",
            disable_slash_commands=True,
            timeout=90,
        )
        txt = res.get("response") or ""
        start_i = txt.find("{")
        end_i = txt.rfind("}")
        if start_i >= 0 and end_i > start_i:
            data = json.loads(txt[start_i : end_i + 1])
            return {
                "hook_text": str(data.get("hook_text") or _default_hook_from_workspace()).strip(),
                "cta_text": str(data.get("cta_text") or "CHỐT ĐƠN NGAY GIỎ HÀNG 👇").strip(),
            }
    return {
        "hook_text": _default_hook_from_workspace(),
        "cta_text": "CHỐT ĐƠN NGAY GIỎ HÀNG 👇",
    }


@app.post("/api/openreel/suggest-hook")
def api_openreel_suggest_hook():
    res = _suggest_hook_and_cta_via_ai()
    saved = save_openreel_hook_md(hook_text=res["hook_text"], cta_text=res["cta_text"])
    return {"ok": True, **res, "hook_cfg": saved}


@app.post("/api/openreel/save-hook")
def api_openreel_save_hook(req: OpenReelHookSaveReq):
    saved = save_openreel_hook_md(
        hook_text=req.hook_text,
        cta_text=req.cta_text,
        hook_y=req.hook_y,
        caption_style=req.caption_style,
        transition_type=req.transition_type,
        caption_highlight_color=req.caption_highlight_color,
    )
    return {"ok": True, "hook_cfg": saved, "file": "04_workspace/openreel_hook_cta.md"}


@app.post("/api/openreel/ai-director")
def api_openreel_ai_director(req: OpenReelDirectorReq):
    cfg = load_config()
    raw_videos = list_media_in_dir(DIR_VIDEO_THO)
    if not raw_videos:
        raise HTTPException(status_code=400, detail="Thư mục 02_video_tho đang trống.")

    frames_base = DIR_FRAMES / "02_video_tho"
    if not (frames_base / "manifest.json").exists():
        run_python_script(
            "scripts/extract_frames.py",
            ["--source", "02_video_tho", "--fps", "1.0", "--max-width", "540", "--transcribe", "never"],
        )

    repair_subtitles_and_beats()
    brief = load_brand_brief()
    voice_beats = json.loads(FILE_VOICE_BEATS.read_text(encoding="utf-8-sig")) if FILE_VOICE_BEATS.exists() else {}
    style_txt = FILE_STYLE_GUIDE.read_text(encoding="utf-8-sig")[:3000] if FILE_STYLE_GUIDE.exists() else ""
    script_txt = FILE_SCRIPT.read_text(encoding="utf-8-sig").strip() if FILE_SCRIPT.exists() else ""
    srt_txt = FILE_TTS_SRT.read_text(encoding="utf-8-sig")[:2500] if FILE_TTS_SRT.exists() else ""
    cur_plan = json.loads(FILE_EDIT_PLAN.read_text(encoding="utf-8-sig")) if FILE_EDIT_PLAN.exists() else {}
    voice_dur = probe_media(FILE_TTS_WAV).get("duration_sec", 25.0) if FILE_TTS_WAV.exists() else 25.0
    raw_meta = "\n".join(
        f"- {v['rel_path']} | duration: {v['duration_sec']}s | {v['width']}x{v['height']}"
        for v in raw_videos
    )

    director_prompt = (
        "Bạn là Đạo diễn Hậu kỳ & Chuyên gia Tối ưu Chuyển đổi TikTok Shop.\n"
        "Nhiệm vụ: Học sâu từ `phong_cach_kenh.md` + Hồ sơ Nhãn hàng (`brand_brief`), xem khung hình video thô trong `04_workspace/frames/02_video_tho/`, "
        "kết hợp Kịch bản & Nhịp thời gian từng câu (`voice_beats.json`) để lập KẾ HOẠCH ĐẠO DIỄN HOÀN CHỈNH (trả về DUY NHẤT JSON hợp lệ):\n"
        "1. `hook_options`: Mảng 3 câu Tiêu đề Hook tâm lý mạnh (Nỗi đau / Cảnh báo / So sánh), mỗi câu NGẮN GỌN <= 32 ký tự (dưới 8 từ, có thể 1 emoji cuối) để hiển thị 2 dòng gọn gàng không tràn khung.\n"
        "2. `best_hook`: Câu Hook tốt nhất trong 3 câu trên.\n"
        "3. `cta_text`: Dòng CTA chốt đơn <= 28 ký tự.\n"
        "4. `floral_badge`: Object tách từ khóa theo Brand Brief cho Nhãn Tiêu Đề 2 dòng nghệ thuật: `brand` (1-2 từ IN HOA), `product_line` (1-2 từ nổi bật), `category` (chữ viết tay 2-4 từ tiếng Việt có dấu).\n"
        "5. `callouts`: Mảng 3 đến 5 nhãn chữ nổi bật giữa video khớp đúng thời điểm từng Beat (`text`: 2-4 từ IN HOA <= 20 ký tự, `startTime`: số giây khớp beat tương ứng, `duration`: 2.0-2.5, `y`: 0.16 hoặc 0.20, `color`: '#FFE500' hoặc '#00F2FE').\n"
        "5. `zoom_clip_indices`: Mảng số thứ tự clip (bắt đầu từ 1) nên thêm hiệu ứng Punch-in Zoom nhẹ (1.0 -> 1.08), ví dụ [1, 3, 5, 7].\n"
        "6. `refined_clips`: Mảng cắt tỉa video thô thông minh bám sát từng Beat của `voice_beats.json`: loại bỏ đoạn 0.0s đầu nếu rung/mờ hoặc tĩnh, mỗi cảnh 1.5s-2.5s, gắn `beat_index`, `zoom_from: 1.0`, `zoom_to` (`1.07` hoặc `1.03`), `transition_type` (`'flash'` hoặc `'hard'`), tổng thời lượng khớp sát "
        f"{voice_dur}s (`source` phải khớp chính xác danh sách bên dưới, `start`, `end`, `speed`, `mute: true`, `crop_mode: 'center'`, `note`).\n"
        "7. `critic_report`: Bài nhận xét thẳng thắn bằng tiếng Việt (Markdown) gồm: Điểm mạnh hiện tại, Điểm yếu của video thô/kịch bản hiện tại, và 4-5 đề xuất cải thiện cụ thể.\n\n"
        f"{_format_brand_brief_prompt_block(brief)}\n"
        f"=== DANH SÁCH VIDEO THÔ HỢP LỆ ===\n{raw_meta}\n\n"
        f"=== GHI CHÚ SẢN PHẨM ===\n{req.product_note.strip() or brief.get('usps') or cur_plan.get('title', '')}\n\n"
        f"=== PHONG CÁCH KÊNH ===\n{style_txt}\n\n"
        f"=== NHỊP GIỌNG ĐỌC TỪNG CÂU (voice_beats.json - Tổng {voice_dur}s) ===\n{json.dumps(voice_beats, ensure_ascii=False, indent=2)[:2500]}\n\n"
        f"=== KỊCH BẢN & PHỤ ĐỀ SẠCH ===\n{script_txt}\n\n{srt_txt}\n"
    )

    raw_json_str = ""
    api_key = str(cfg.get("gemini_api_key") or "").strip()
    if find_agy_executable():
        agy_prompt = (
            director_prompt
            + "\nHãy dùng `view_file` xem một số ảnh đại diện trong `04_workspace/frames/02_video_tho/` trước khi trả lời.\n"
            + "Chỉ trả về DUY NHẤT một khối JSON hợp lệ (không bọc giải thích thừa)."
        )
        cli_res = call_agy_cli(
            agy_prompt,
            model=cfg.get("agy_model") or DEFAULT_CONFIG["agy_model"],
            effort=cfg.get("agy_effort") or DEFAULT_CONFIG["agy_effort"],
            mode="auto",
            timeout=300,
        )
        raw_json_str = cli_res.get("response") or ""
    elif api_key:
        parts: list[dict[str, Any]] = [{"text": director_prompt}]
        for subdir in sorted(p for p in frames_base.iterdir() if p.is_dir()):
            for jpg in select_representative_frames(sorted(subdir.glob("frame_*.jpg")), max_frames=4):
                b64 = base64.b64encode(jpg.read_bytes()).decode("ascii")
                parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
        raw_json_str = call_gemini_multimodal(
            parts,
            api_key=api_key,
            model=cfg.get("gemini_model") or "gemini-2.5-flash",
            effort=cfg.get("gemini_effort") or "medium",
            response_mime_type="application/json",
            timeout=120,
        )
    else:
        raise HTTPException(status_code=400, detail="Chưa có Antigravity CLI hoặc Gemini API Key.")

    s_idx = raw_json_str.find("{")
    e_idx = raw_json_str.rfind("}")
    if s_idx < 0 or e_idx <= s_idx:
        raise HTTPException(status_code=502, detail="AI Director không trả về JSON hợp lệ.")
    director_data = json.loads(raw_json_str[s_idx : e_idx + 1])

    FILE_DIRECTOR_PLAN.write_text(json.dumps(director_data, ensure_ascii=False, indent=2), encoding="utf-8")

    best_hook = str(director_data.get("best_hook") or (director_data.get("hook_options") or [""])[0]).strip()
    cta_text = str(director_data.get("cta_text") or "CHỐT ĐƠN NGAY GIỎ HÀNG 👇").strip()
    if best_hook:
        save_openreel_hook_md(hook_text=best_hook, cta_text=cta_text)

    critic_md = str(director_data.get("critic_report") or "").strip()
    if critic_md:
        FILE_CRITIC_MD.write_text(critic_md + "\n", encoding="utf-8")

    trimmed_applied = False
    refined = director_data.get("refined_clips")
    existing_clips = cur_plan.get("clips") if isinstance(cur_plan.get("clips"), list) else []
    if req.apply_trim:
        if req.preserve_clips and existing_clips:
            align_edit_plan_to_voice_beats(raw_videos, preserve_clips=True)
            run_python_script("scripts/prepare_clips.py", ["--config", "04_workspace/edit_plan.json", "--concat"])
            trimmed_applied = True
        elif isinstance(refined, list) and refined:
            dur_map = {v["rel_path"]: float(v["duration_sec"] or 5.0) for v in raw_videos}
            default_src = raw_videos[0]["rel_path"]
            cleaned: list[dict[str, Any]] = []
            for c in refined:
                if not isinstance(c, dict):
                    continue
                src = str(c.get("source") or "").strip()
                if src not in dur_map:
                    src = default_src
                max_d = dur_map[src]
                st = max(0.0, min(float(c.get("start", 0.0)), max(0.0, max_d - 0.5)))
                en = min(max_d, max(st + 0.5, float(c.get("end", min(max_d, st + 2.0)))))
                cleaned.append(
                    {
                        "source": src,
                        "start": round(st, 2),
                        "end": round(en, 2),
                        "speed": round(max(0.5, min(2.0, float(c.get("speed", 1.0)))), 2),
                        "mute": True,
                        "crop_mode": c.get("crop_mode") if c.get("crop_mode") in ("center", "blur_bg") else "center",
                        "note": str(c.get("note") or ""),
                    }
                )
            if cleaned:
                new_plan = {
                    "title": cur_plan.get("title") or brief.get("brand") or "San pham TikTok Shop",
                    "target_resolution": [1080, 1920],
                    "target_fps": 30,
                    "concat_draft": True,
                    "keep_clip_audio": False,
                    "clips": cleaned,
                }
                FILE_EDIT_PLAN.write_text(json.dumps(new_plan, ensure_ascii=False, indent=2), encoding="utf-8")
                align_edit_plan_to_voice_beats(raw_videos, preserve_clips=False)
                run_python_script("scripts/prepare_clips.py", ["--config", "04_workspace/edit_plan.json", "--concat"])
                trimmed_applied = True

    return {
        "ok": True,
        "director_plan": director_data,
        "critic_report": critic_md,
        "trimmed_applied": trimmed_applied,
        "hook_cfg": load_openreel_hook_md(),
    }


@app.post("/api/openreel/build-project")
def api_openreel_build_project(req: OpenReelBuildReq, request: Request):
    clips_info = list_media_in_dir(DIR_CLIPS)
    if not clips_info:
        raise HTTPException(
            status_code=400,
            detail="Chưa có clip nào trong 04_workspace/ready_for_openreel/01_clips/. Hãy chạy bước Cắt & Chuẩn hóa Clip ở Tab 4 trước.",
        )

    origin = str(request.base_url).rstrip("/")
    now_ms = int(time.time() * 1000)
    project_id = f"tiktok_openreel_{now_ms}"

    plan_title = "TikTok Shop Video"
    if FILE_EDIT_PLAN.exists():
        try:
            plan_data = json.loads(FILE_EDIT_PLAN.read_text(encoding="utf-8-sig"))
            plan_title = str(plan_data.get("title") or plan_title).strip()
        except Exception:
            pass
    project_name = req.project_name.strip() or plan_title

    hook_text = req.hook_text.strip()
    cta_text = req.cta_text.strip()
    if req.use_ai_hook and not hook_text:
        ai_res = _suggest_hook_and_cta_via_ai()
        hook_text = ai_res["hook_text"]
        if not cta_text:
            cta_text = ai_res["cta_text"]
    elif not hook_text:
        hook_text = _default_hook_from_workspace()

    save_openreel_hook_md(
        hook_text=hook_text,
        cta_text=cta_text,
        hook_y=req.hook_y,
        caption_style=req.caption_style,
        transition_type=req.transition_type,
        caption_highlight_color=req.caption_highlight_color,
    )

    media_items: list[dict[str, Any]] = []
    video_clips: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    default_transform = {
        "position": {"x": 0.5, "y": 0.5},
        "scale": {"x": 1.0, "y": 1.0},
        "rotation": 0,
        "anchor": {"x": 0.5, "y": 0.5},
        "opacity": 1.0,
        "fitMode": "cover",
        "borderRadius": 0,
    }

    director_data: dict[str, Any] = {}
    if FILE_DIRECTOR_PLAN.exists():
        try:
            director_data = json.loads(FILE_DIRECTOR_PLAN.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
    zoom_indices = set(director_data.get("zoom_clip_indices") or [1, 3, 5, 7])

    cursor = 0.0
    prev_clip_id: str | None = None
    hook_transition_time: float | None = None
    for idx, c in enumerate(clips_info, start=1):
        media_id = f"media_vid_{idx:02d}"
        clip_id = f"clip_vid_{idx:02d}"
        dur = max(0.5, float(c.get("duration_sec") or 2.0))
        media_items.append(
            {
                "id": media_id,
                "name": c["name"],
                "type": "video",
                "fileHandle": None,
                "blob": None,
                "thumbnailUrl": None,
                "waveformData": None,
                "originalUrl": f"{origin}/files/04_workspace/ready_for_openreel/01_clips/{c['name']}?t={int(c.get('mtime') or now_ms)}",
                "metadata": {
                    "duration": dur,
                    "width": int(c.get("width") or 1080),
                    "height": int(c.get("height") or 1920),
                    "frameRate": 30,
                    "codec": "h264",
                    "sampleRate": 44100,
                    "channels": 2,
                    "fileSize": int((c.get("size_mb") or 1.0) * 1024 * 1024),
                    "hasVideo": True,
                    "hasAudio": False,
                },
            }
        )
        clip_keyframes: list[dict[str, Any]] = []
        if idx in zoom_indices and dur >= 1.0:
            clip_keyframes = [
                {"id": f"kf_{idx}_sx0", "time": 0.0, "property": "scale.x", "value": 1.0, "easing": "easeOut"},
                {"id": f"kf_{idx}_sy0", "time": 0.0, "property": "scale.y", "value": 1.0, "easing": "easeOut"},
                {"id": f"kf_{idx}_sx1", "time": round(dur, 3), "property": "scale.x", "value": 1.08, "easing": "easeOut"},
                {"id": f"kf_{idx}_sy1", "time": round(dur, 3), "property": "scale.y", "value": 1.08, "easing": "easeOut"},
            ]
        video_clips.append(
            {
                "id": clip_id,
                "mediaId": media_id,
                "trackId": "track_video_main",
                "startTime": round(cursor, 3),
                "duration": round(dur, 3),
                "inPoint": 0.0,
                "outPoint": round(dur, 3),
                "effects": [],
                "audioEffects": [],
                "transform": default_transform,
                "volume": 0.0,
                "fade": {"fadeIn": 0.0, "fadeOut": 0.0},
                "keyframes": clip_keyframes,
                "speed": 1.0,
                "reversed": False,
                "pitchCorrection": False,
            }
        )
        if idx == 2 and prev_clip_id and req.transition_type and req.transition_type != "none":
            hook_transition_time = round(max(0.0, cursor - 0.15), 3)
            transitions.append(
                {
                    "id": "trans_hook_to_body",
                    "type": req.transition_type,
                    "clipAId": prev_clip_id,
                    "clipBId": clip_id,
                    "duration": 0.25,
                    "params": {"direction": "left", "curve": "ease-out"},
                }
            )
        prev_clip_id = clip_id
        cursor += dur

    audio_clips: list[dict[str, Any]] = []
    voice_dur = 0.0
    if FILE_TTS_WAV.exists():
        wav_info = probe_media(FILE_TTS_WAV)
        voice_dur = max(0.5, float(wav_info.get("duration_sec") or cursor))
        media_items.append(
            {
                "id": "media_voice_01",
                "name": FILE_TTS_WAV.name,
                "type": "audio",
                "fileHandle": None,
                "blob": None,
                "thumbnailUrl": None,
                "waveformData": None,
                "originalUrl": f"{origin}/files/04_workspace/ready_for_openreel/{FILE_TTS_WAV.name}?t={int(wav_info.get('mtime') or now_ms)}",
                "metadata": {
                    "duration": voice_dur,
                    "width": 0,
                    "height": 0,
                    "frameRate": 0,
                    "codec": "pcm_s16le",
                    "sampleRate": int(wav_info.get("sample_rate") or 24000),
                    "channels": int(wav_info.get("channels") or 1),
                    "fileSize": FILE_TTS_WAV.stat().st_size,
                    "hasVideo": False,
                    "hasAudio": True,
                },
            }
        )
        audio_clips.append(
            {
                "id": "clip_voice_01",
                "mediaId": "media_voice_01",
                "trackId": "track_audio_voice",
                "startTime": 0.0,
                "duration": round(voice_dur, 3),
                "inPoint": 0.0,
                "outPoint": round(voice_dur, 3),
                "effects": [],
                "audioEffects": [],
                "transform": default_transform,
                "volume": 1.0,
                "fade": {"fadeIn": 0.0, "fadeOut": 0.0},
                "keyframes": [],
                "speed": 1.0,
                "reversed": False,
                "pitchCorrection": True,
            }
        )

    total_duration = round(max(cursor, voice_dur, 1.0), 3)

    raw_subtitles: list[dict[str, Any]] = []
    if FILE_TTS_SRT.exists():
        srt_raw = FILE_TTS_SRT.read_text(encoding="utf-8-sig")
        raw_subtitles = parse_srt_to_openreel_subtitles(
            srt_raw,
            animation_style=req.caption_style,
            color=req.caption_color,
            highlight_color=req.caption_highlight_color,
        )

    # Tách các câu SRT dài thành cụm 3-5 từ ngắn để nhảy nhịp nhanh và không bao giờ tràn khung 1080px
    dialogue_sub_chunks: list[dict[str, Any]] = []
    for sub in raw_subtitles:
        words = sub["text"].split()
        st = float(sub["startTime"])
        en = float(sub["endTime"])
        if len(words) <= 5:
            dialogue_sub_chunks.append({"text": sub["text"], "start": st, "end": en})
        else:
            step_words = 4
            groups = [" ".join(words[i : i + step_words]) for i in range(0, len(words), step_words)]
            total_chars = sum(len(g) for g in groups) or 1
            cur_t = st
            for gi, g in enumerate(groups):
                share = (en - st) * (len(g) / total_chars)
                g_end = en if gi == len(groups) - 1 else round(cur_t + max(0.35, share), 3)
                dialogue_sub_chunks.append({"text": g, "start": round(cur_t, 3), "end": round(max(cur_t + 0.3, g_end), 3)})
                cur_t = g_end

    text_clips: list[dict[str, Any]] = []

    def _make_text_clip(
        clip_id: str,
        track_id: str,
        text_val: str,
        start_t: float,
        dur_t: float,
        *,
        y_pos: float,
        base_size: int,
        color: str,
        bg_color: str,
        stroke_color: str = "#000000",
        stroke_width: int = 5,
        max_chars_line: int = 18,
    ) -> dict[str, Any]:
        wrapped = wrap_tiktok_text(text_val, max_chars_per_line=max_chars_line, max_lines=2)
        fitted_size = fit_font_size(wrapped, base_size=base_size, min_size=30, max_width_px=840)
        return {
            "id": clip_id,
            "trackId": track_id,
            "startTime": round(max(0.0, start_t), 3),
            "duration": round(max(0.25, dur_t), 3),
            "text": wrapped,
            "style": {
                "fontFamily": "Montserrat",
                "fontSize": fitted_size,
                "fontWeight": 800,
                "fontStyle": "normal",
                "color": color,
                "backgroundColor": bg_color,
                "strokeColor": stroke_color,
                "strokeWidth": stroke_width,
                "shadowColor": "rgba(0,0,0,0.85)",
                "shadowBlur": 8,
                "shadowOffsetX": 0,
                "shadowOffsetY": 3,
                "textAlign": "center",
                "verticalAlign": "middle",
                "lineHeight": 1.25,
                "letterSpacing": 0,
            },
            "transform": {
                "position": {"x": 0.5, "y": y_pos},
                "scale": {"x": 1.0, "y": 1.0},
                "rotation": 0,
                "anchor": {"x": 0.5, "y": 0.5},
                "opacity": 1.0,
            },
            "keyframes": [],
        }

    if hook_text:
        text_clips.append(
            _make_text_clip(
                "text_hook_01",
                "track_text_overlay",
                hook_text,
                0.0,
                min(3.5, total_duration),
                y_pos=max(0.10, min(0.80, req.hook_y)),
                base_size=max(32, min(72, req.hook_font_size)),
                color=req.hook_color,
                bg_color="rgba(0,0,0,0.48)",
                stroke_color=req.hook_stroke_color,
                stroke_width=6,
                max_chars_line=18,
            )
        )

    # Thêm các Callout nổi bật giữa video từ AI Director (nếu có)
    callout_times: list[float] = []
    for ci, co in enumerate(director_data.get("callouts") or [], start=1):
        if not isinstance(co, dict) or not str(co.get("text") or "").strip():
            continue
        co_start = float(co.get("startTime", 4.0 + (ci - 1) * 4.5))
        if co_start >= total_duration - 1.5:
            continue
        co_dur = min(float(co.get("duration", 2.2)), total_duration - co_start)
        co_y = float(co.get("y", 0.27))
        co_color = str(co.get("color") or "#FFE500")
        text_clips.append(
            _make_text_clip(
                f"text_callout_{ci:02d}",
                "track_text_overlay",
                str(co["text"]).strip(),
                co_start,
                co_dur,
                y_pos=max(0.15, min(0.62, co_y)),
                base_size=44,
                color=co_color,
                bg_color="rgba(0,0,0,0.58)",
                stroke_color="#000000",
                stroke_width=5,
                max_chars_line=16,
            )
        )
        callout_times.append(round(co_start, 3))

    cta_start_time: float | None = None
    if cta_text and total_duration > 4.0:
        cta_dur = min(3.2, total_duration - 3.5)
        cta_start_time = round(max(0.0, total_duration - cta_dur), 3)
        text_clips.append(
            _make_text_clip(
                "text_cta_01",
                "track_text_overlay",
                cta_text,
                cta_start_time,
                cta_dur,
                y_pos=0.22,
                base_size=46,
                color="#FFE500",
                bg_color="rgba(0,0,0,0.60)",
                stroke_color="#000000",
                stroke_width=5,
                max_chars_line=18,
            )
        )

    # Phụ đề giọng nói hiển thị trực tiếp ở vùng an toàn Y = 72%
    for si, sub in enumerate(dialogue_sub_chunks, start=1):
        sub_dur = max(0.25, sub["end"] - sub["start"])
        text_clips.append(
            _make_text_clip(
                f"text_sub_{si:03d}",
                "track_subtitles_dialogue",
                sub["text"],
                sub["start"],
                sub_dur,
                y_pos=0.72,
                base_size=42,
                color=req.caption_color or "#FFFFFF",
                bg_color="rgba(0,0,0,0.55)",
                stroke_color="#000000",
                stroke_width=5,
                max_chars_line=20,
            )
        )

    # Tự động nạp BGM + SFX từ 06_assets_audio/
    bgm_clips: list[dict[str, Any]] = []
    sfx_clips: list[dict[str, Any]] = []
    if DIR_ASSETS_BGM.exists():
        custom_bgms = [
            f for f in list_media_in_dir(DIR_ASSETS_BGM)
            if f["name"] != "bgm_upbeat_default.wav"
        ]
        chosen_bgm = custom_bgms[0] if custom_bgms else (
            probe_media(DIR_ASSETS_BGM / "bgm_upbeat_default.wav")
            if (DIR_ASSETS_BGM / "bgm_upbeat_default.wav").exists()
            else None
        )
        if chosen_bgm:
            bgm_dur = min(total_duration, float(chosen_bgm.get("duration_sec") or total_duration))
            media_items.append(
                {
                    "id": "media_bgm_01",
                    "name": chosen_bgm["name"],
                    "type": "audio",
                    "fileHandle": None,
                    "blob": None,
                    "thumbnailUrl": None,
                    "waveformData": None,
                    "originalUrl": f"{origin}/files/06_assets_audio/bgm/{chosen_bgm['name']}?t={int(chosen_bgm.get('mtime') or now_ms)}",
                    "metadata": {
                        "duration": float(chosen_bgm.get("duration_sec") or total_duration),
                        "width": 0,
                        "height": 0,
                        "frameRate": 0,
                        "codec": "pcm_s16le",
                        "sampleRate": int(chosen_bgm.get("sample_rate") or 44100),
                        "channels": int(chosen_bgm.get("channels") or 1),
                        "fileSize": int((chosen_bgm.get("size_mb") or 1.0) * 1024 * 1024),
                        "hasVideo": False,
                        "hasAudio": True,
                    },
                }
            )
            bgm_clips.append(
                {
                    "id": "clip_bgm_01",
                    "mediaId": "media_bgm_01",
                    "trackId": "track_audio_bgm",
                    "startTime": 0.0,
                    "duration": round(bgm_dur, 3),
                    "inPoint": 0.0,
                    "outPoint": round(bgm_dur, 3),
                    "effects": [],
                    "audioEffects": [],
                    "transform": default_transform,
                    "volume": 0.14,
                    "fade": {"fadeIn": 0.8, "fadeOut": 1.2},
                    "keyframes": [],
                    "speed": 1.0,
                    "reversed": False,
                    "pitchCorrection": False,
                }
            )

    sfx_defs = [
        ("sfx_whoosh", DIR_ASSETS_AUDIO / "sfx_whoosh.wav", [hook_transition_time] if hook_transition_time is not None else []),
        ("sfx_pop", DIR_ASSETS_AUDIO / "sfx_pop.wav", callout_times),
        ("sfx_ding", DIR_ASSETS_AUDIO / "sfx_ding.wav", [cta_start_time] if cta_start_time is not None else []),
    ]
    for sfx_key, sfx_path, times_list in sfx_defs:
        valid_times = [t for t in times_list if t is not None and 0.0 <= t < total_duration]
        if not valid_times or not sfx_path.exists():
            continue
        sfx_info = probe_media(sfx_path)
        sfx_dur = max(0.1, float(sfx_info.get("duration_sec") or 0.35))
        sfx_media_id = f"media_{sfx_key}"
        media_items.append(
            {
                "id": sfx_media_id,
                "name": sfx_path.name,
                "type": "audio",
                "fileHandle": None,
                "blob": None,
                "thumbnailUrl": None,
                "waveformData": None,
                "originalUrl": f"{origin}/files/06_assets_audio/{sfx_path.name}?t={int(sfx_info.get('mtime') or now_ms)}",
                "metadata": {
                    "duration": sfx_dur,
                    "width": 0,
                    "height": 0,
                    "frameRate": 0,
                    "codec": "pcm_s16le",
                    "sampleRate": int(sfx_info.get("sample_rate") or 44100),
                    "channels": int(sfx_info.get("channels") or 1),
                    "fileSize": sfx_path.stat().st_size,
                    "hasVideo": False,
                    "hasAudio": True,
                },
            }
        )
        for ti, st_t in enumerate(valid_times, start=1):
            sfx_clips.append(
                {
                    "id": f"clip_{sfx_key}_{ti:02d}",
                    "mediaId": sfx_media_id,
                    "trackId": "track_audio_sfx",
                    "startTime": round(st_t, 3),
                    "duration": round(min(sfx_dur, total_duration - st_t), 3),
                    "inPoint": 0.0,
                    "outPoint": round(min(sfx_dur, total_duration - st_t), 3),
                    "effects": [],
                    "audioEffects": [],
                    "transform": default_transform,
                    "volume": 0.55,
                    "fade": {"fadeIn": 0.0, "fadeOut": 0.05},
                    "keyframes": [],
                    "speed": 1.0,
                    "reversed": False,
                    "pitchCorrection": False,
                }
            )

    tracks_list: list[dict[str, Any]] = [
        {
            "id": "track_text_overlay",
            "type": "text",
            "mode": "standard",
            "role": "general",
            "name": "Tiêu đề Hook & Callout",
            "clips": [],
            "transitions": [],
            "locked": False,
            "hidden": False,
            "muted": False,
            "solo": False,
        },
        {
            "id": "track_subtitles_dialogue",
            "type": "text",
            "mode": "standard",
            "role": "captions",
            "name": "Phụ đề Giọng Nói (72%)",
            "clips": [],
            "transitions": [],
            "locked": False,
            "hidden": False,
            "muted": False,
            "solo": False,
        },
        {
            "id": "track_video_main",
            "type": "video",
            "mode": "standard",
            "role": "general",
            "name": "Video B-Roll (9:16)",
            "clips": video_clips,
            "transitions": transitions,
            "locked": False,
            "hidden": False,
            "muted": False,
            "solo": False,
        },
        {
            "id": "track_audio_voice",
            "type": "audio",
            "mode": "standard",
            "role": "dialogue",
            "name": "Giọng đọc AI (F5-TTS)",
            "clips": audio_clips,
            "transitions": [],
            "locked": False,
            "hidden": False,
            "muted": False,
            "solo": False,
        },
    ]
    if bgm_clips:
        tracks_list.append(
            {
                "id": "track_audio_bgm",
                "type": "audio",
                "mode": "standard",
                "role": "music",
                "name": "Nhạc nền (BGM)",
                "clips": bgm_clips,
                "transitions": [],
                "locked": False,
                "hidden": False,
                "muted": False,
                "solo": False,
            }
        )
    if sfx_clips:
        tracks_list.append(
            {
                "id": "track_audio_sfx",
                "type": "audio",
                "mode": "standard",
                "role": "effects",
                "name": "Hiệu ứng Âm thanh (SFX)",
                "clips": sfx_clips,
                "transitions": [],
                "locked": False,
                "hidden": False,
                "muted": False,
                "solo": False,
            }
        )

    project_doc = {
        "id": project_id,
        "name": project_name,
        "createdAt": now_ms,
        "modifiedAt": now_ms,
        "settings": {
            "width": 1080,
            "height": 1920,
            "frameRate": 30,
            "sampleRate": 44100,
            "channels": 2,
        },
        "mediaLibrary": {"items": media_items},
        "timeline": {
            "tracks": tracks_list,
            "subtitles": [],
            "markers": [],
            "duration": total_duration,
        },
        "textClips": text_clips,
    }

    proj_file = DIR_READY / "openreel_project.json"
    proj_file.write_text(json.dumps(project_doc, ensure_ascii=False, indent=2), encoding="utf-8")

    import_url = f"{origin}/api/openreel/project.json"
    from urllib.parse import quote
    openreel_url = f"http://localhost:5173/#/editor?importUrl={quote(import_url, safe='')}"
    return {
        "ok": True,
        "project_id": project_id,
        "project_name": project_name,
        "clips_count": len(video_clips),
        "subtitles_count": len(dialogue_sub_chunks),
        "text_clips_count": len(text_clips),
        "bgm_count": len(bgm_clips),
        "sfx_count": len(sfx_clips),
        "duration": total_duration,
        "hook_text": hook_text,
        "cta_text": cta_text,
        "openreel_import_url": openreel_url,
    }


@app.get("/api/openreel/project.json")
def api_openreel_get_project():
    proj_file = DIR_READY / "openreel_project.json"
    if not proj_file.exists():
        raise HTTPException(
            status_code=404,
            detail="Chưa tạo openreel_project.json. Hãy bấm 'Tự động Dựng Project OpenReel' trước.",
        )
    return JSONResponse(content=json.loads(proj_file.read_text(encoding="utf-8-sig")))


@app.post("/api/openreel/start")
def api_openreel_start():
    global _openreel_proc
    if is_port_open("127.0.0.1", 5173):
        return {
            "ok": True,
            "online": True,
            "url": "http://localhost:5173",
            "message": "OpenReel Video đang chạy sẵn tại http://localhost:5173.",
        }

    if not (DIR_OPENREEL / "package.json").exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy mã nguồn OpenReel tại openreel_app.")

    log_file = DIR_WORKSPACE / "openreel_server.log"
    fh = open(log_file, "w", encoding="utf-8")
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
        _openreel_proc = subprocess.Popen(
            ["cmd.exe", "/c", "pnpm --filter @openreel/web dev --port 5173"],
            cwd=str(DIR_OPENREEL),
            stdout=fh,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
    else:
        _openreel_proc = subprocess.Popen(
            ["pnpm", "--filter", "@openreel/web", "dev", "--port", "5173"],
            cwd=str(DIR_OPENREEL),
            stdout=fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    online = False
    for _ in range(30):
        if is_port_open("127.0.0.1", 5173, timeout=0.5):
            online = True
            break
        time.sleep(0.5)

    return {
        "ok": online,
        "online": online,
        "url": "http://localhost:5173",
        "message": "OpenReel Video đã khởi chạy." if online else "Server đang khởi động, vui lòng kiểm tra lại sau vài giây.",
    }


# ---------------------------------------------------------------------------
# Tab 5 v2: 100% Automated Remotion Hybrid Graphic Engine & AI Editor
# ---------------------------------------------------------------------------


def _apply_remotion_req_to_overrides(req: RemotionRenderReq) -> dict[str, Any]:
    ov: dict[str, Any] = {
        "badge_style": req.badge_style,
        "visual_theme": req.visual_theme,
        "layout_style": req.layout_style,
        "color_preset": req.color_preset,
        "creative_mode": req.creative_mode,
        "camera_intensity": req.camera_intensity,
        "bgm_track": req.bgm_track,
        "hook_y": req.hook_y,
        "subtitle_active_color": req.subtitle_active_color,
        "render_engine": req.render_engine,
        "innovation_preset": req.innovation_preset,
        "transition_level": req.transition_level,
        "disable_flash_shake": req.disable_flash_shake,
        "icon_density": req.icon_density,
        "sticker_density": req.sticker_density,
        "sfx_level": req.sfx_level,
        "aspect_ratio": req.aspect_ratio,
        "content_vibe": req.content_vibe,
    }
    if req.brand.strip():
        ov["brand"] = req.brand.strip()
    if req.product_line.strip():
        ov["product_line"] = req.product_line.strip()
    if req.category.strip():
        ov["category"] = req.category.strip()
    if req.hook_text.strip():
        ov["hook_text"] = req.hook_text.strip()
    if req.cta_text.strip():
        ov["cta_text"] = sanitize_cta_text(req.cta_text.strip(), 42)
    if req.bgm_volume is not None:
        ov["bgm_volume"] = float(req.bgm_volume)

    update_style_dna(
        {
            "badge_style": req.badge_style,
            "visual_theme": req.visual_theme,
            "layout_style": req.layout_style,
            "color_preset": req.color_preset,
            "creative_mode": req.creative_mode,
            "camera_intensity": req.camera_intensity,
            "bgm_track": req.bgm_track,
            "hook_y": req.hook_y,
            "subtitle_active_color": req.subtitle_active_color,
            "render_engine": req.render_engine,
            "innovation_preset": req.innovation_preset,
            "transition_level": req.transition_level,
            "disable_flash_shake": req.disable_flash_shake,
            **({"bgm_volume": float(req.bgm_volume)} if req.bgm_volume is not None else {}),
        }
    )
    if req.hook_text.strip() or req.cta_text.strip():
        cur_hook = load_openreel_hook_md()
        save_openreel_hook_md(
            hook_text=req.hook_text.strip() or cur_hook.get("hook_text", ""),
            cta_text=req.cta_text.strip() or cur_hook.get("cta_text", ""),
            hook_y=req.hook_y,
            caption_highlight_color=req.subtitle_active_color,
        )
    return ov


def _collect_remotion_preview_frames() -> list[dict[str, str]]:
    if not FILE_PREVIEW_FRAMES_DIR.exists():
        return []
    out: list[dict[str, str]] = []
    label_map = {
        "frame_hook_1s.jpg": "1. Hook (Đầu video)",
        "frame_mid_12s.jpg": "2. Giữa video (Callout + Sub)",
        "frame_cta_end.jpg": "3. Cuối video (CTA)",
    }
    for fname in ("frame_hook_1s.jpg", "frame_mid_12s.jpg", "frame_cta_end.jpg"):
        p = FILE_PREVIEW_FRAMES_DIR / fname
        if p.exists():
            out.append(
                {
                    "name": fname,
                    "label": label_map.get(fname, fname),
                    "url": f"/files/04_workspace/render_preview_frames/{fname}?t={int(p.stat().st_mtime)}",
                }
            )
    return out


@app.get("/api/remotion/status")
def api_remotion_status():
    dna = load_style_dna() if (DIR_WORKSPACE / "style_dna.json").exists() else update_style_dna()
    hook_cfg = load_openreel_hook_md()
    director_plan = None
    if FILE_DIRECTOR_PLAN.exists():
        try:
            director_plan = json.loads(FILE_DIRECTOR_PLAN.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
    critic_report = FILE_CRITIC_MD.read_text(encoding="utf-8-sig") if FILE_CRITIC_MD.exists() else ""
    remotion_props = None
    if FILE_REMOTION_PROPS.exists():
        try:
            remotion_props = json.loads(FILE_REMOTION_PROPS.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    badge_png = DIR_WORKSPACE / "hook_badge_preview.png"
    ref_hook = DIR_WORKSPACE / "style_ref_hook.jpg"
    brief = load_brand_brief()
    brief_ready, brief_reason = is_brand_brief_ready(brief)
    named_out_path, selected_meta = resolve_script_named_output_path(
        float((remotion_props or {}).get("durationSec") or brief.get("target_duration_sec") or 30.0)
    )

    outputs = list_media_in_dir(DIR_OUTPUT)
    if named_out_path.exists():
        latest_output = probe_media(named_out_path)
    elif FILE_DEFAULT_OUTPUT.exists():
        latest_output = probe_media(FILE_DEFAULT_OUTPUT)
    else:
        latest_output = outputs[0] if outputs else None
    if latest_output and "url" not in latest_output:
        latest_output["url"] = f"/files/05_output/{latest_output['name']}?t={int(time.time())}"
    elif latest_output:
        latest_output["url"] = f"{latest_output['url'].split('?')[0]}?t={int(latest_output.get('mtime') or time.time())}"

    voice_beats = None
    if FILE_VOICE_BEATS.exists():
        try:
            voice_beats = json.loads(FILE_VOICE_BEATS.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    return {
        "remotion_ready": (PROJECT_ROOT / "remotion_studio" / "node_modules" / "remotion").exists(),
        "style_dna": dna,
        "brand_brief": brief,
        "brief_ready": brief_ready,
        "brief_reason": brief_reason,
        "selected_script_meta": selected_meta,
        "bgm_tracks": ensure_royalty_free_bgm_library(),
        "voice_beats": voice_beats,
        "hook_cfg": hook_cfg,
        "director_plan": director_plan,
        "critic_report": critic_report,
        "remotion_props": remotion_props,
        "hook_badge_preview_url": f"/files/04_workspace/hook_badge_preview.png?t={int(badge_png.stat().st_mtime)}" if badge_png.exists() else "",
        "style_ref_hook_url": f"/files/04_workspace/style_ref_hook.jpg?t={int(ref_hook.stat().st_mtime)}" if ref_hook.exists() else "",
        "preview_frames": _collect_remotion_preview_frames(),
        "latest_output": latest_output,
        "outputs": outputs,
    }


@app.post("/api/remotion/preview-review")
def api_remotion_preview_review(req: RemotionRenderReq):
    ov = _apply_remotion_req_to_overrides(req)
    try:
        res = render_creative_review_frames(overrides=ov)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    badge_png = DIR_WORKSPACE / "hook_badge_preview.png"
    _, selected_meta = resolve_script_named_output_path(
        float((res.get("remotion_props") or {}).get("durationSec") or 30.0)
    )
    return {
        "ok": True,
        "remotion_props": res.get("remotion_props"),
        "selected_script_meta": selected_meta,
        "hook_badge_preview_url": f"/files/04_workspace/hook_badge_preview.png?t={int(badge_png.stat().st_mtime)}" if badge_png.exists() else "",
        "preview_frames": _collect_remotion_preview_frames(),
    }


@app.post("/api/remotion/ai-director")
def api_remotion_ai_director(req: OpenReelDirectorReq):
    dir_res = api_openreel_ai_director(req)
    props = build_remotion_props()
    badge_res = render_title_badge_preview(props=props)
    badge_png = DIR_WORKSPACE / "hook_badge_preview.png"
    return {
        **dir_res,
        "remotion_props": props,
        "hook_badge_preview_url": f"/files/04_workspace/hook_badge_preview.png?t={int(badge_png.stat().st_mtime)}" if badge_png.exists() else "",
        "badge_preview": badge_res,
    }


@app.get("/api/longform/clips")
def api_longform_clips(project_id: str | None = None):
    import longform_vlog as _lf

    pid = str(project_id or "").strip()
    raw_dir = (get_project_root(pid) / "02_video_tho") if pid else DIR_VIDEO_THO
    clips = _lf.collect_ordered_raw_clips(raw_dir)
    total_dur = round(sum(float(c.get("duration_sec") or 0.0) for c in clips), 2)
    return {
        "ok": True,
        "project_id": pid or ACTIVE_PROJECT_ID,
        "clips": clips,
        "count": len(clips),
        "total_duration_sec": total_dur,
    }


class LongformStateSaveReq(BaseModel):
    project_id: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    chapters_data: dict[str, Any] | None = None


@app.get("/api/longform/state")
def api_longform_state(project_id: str | None = None):
    pid = str(project_id or "").strip() or ACTIVE_PROJECT_ID
    ws_dir = get_project_root(pid) / "04_workspace"
    cfg_p = ws_dir / "longform_config.json"
    ch_p = ws_dir / "longform_chapters.json"
    cfg_data: dict[str, Any] = {}
    ch_data: dict[str, Any] | None = None
    if cfg_p.exists():
        try:
            cfg_data = json.loads(cfg_p.read_text(encoding="utf-8-sig"))
        except Exception:
            cfg_data = {}
    if ch_p.exists():
        try:
            ch_data = json.loads(ch_p.read_text(encoding="utf-8-sig"))
        except Exception:
            ch_data = None
    return {"ok": True, "project_id": pid, "config": cfg_data, "chapters_data": ch_data}


@app.post("/api/longform/save")
def api_longform_save(req: LongformStateSaveReq):
    pid = str(req.project_id or "").strip() or ACTIVE_PROJECT_ID
    ws_dir = get_project_root(pid) / "04_workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)
    cfg_p = ws_dir / "longform_config.json"
    existing_cfg: dict[str, Any] = {}
    if cfg_p.exists():
        try:
            existing_cfg = json.loads(cfg_p.read_text(encoding="utf-8-sig"))
        except Exception:
            existing_cfg = {}
    merged_cfg = {**existing_cfg, **(req.config or {})}
    cfg_p.write_text(json.dumps(merged_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    if isinstance(req.chapters_data, dict):
        ch_p = ws_dir / "longform_chapters.json"
        ch_p.write_text(json.dumps(req.chapters_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "project_id": pid, "config": merged_cfg}


class LongformGenScriptReq(BaseModel):
    project_id: str = ""
    target_duration_sec: float = 300.0
    vlog_title: str = ""
    product_note: str = ""
    content_vibe: str = "outdoor_picnic"
    title_style: str = ""
    subtitle_style: str = ""
    accent_color: str = ""


@app.post("/api/longform/generate-script")
def api_longform_generate_script(req: LongformGenScriptReq):
    import longform_vlog as _lf

    pid = str(req.project_id or "").strip() or ACTIVE_PROJECT_ID
    proj_root = get_project_root(pid)
    raw_dir = proj_root / "02_video_tho"
    ws_dir = proj_root / "04_workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)
    cfg_p = ws_dir / "longform_config.json"
    prev_cfg: dict[str, Any] = {}
    if cfg_p.exists():
        try:
            prev_cfg = json.loads(cfg_p.read_text(encoding="utf-8-sig"))
        except Exception:
            prev_cfg = {}

    ordered = _lf.collect_ordered_raw_clips(raw_dir, ordered_names=prev_cfg.get("ordered_clips") or None)
    if not ordered:
        raise HTTPException(status_code=400, detail="Chưa có video thô nào trong 02_video_tho/.")
    plan = _lf.build_longform_timeline_plan(
        ordered,
        target_duration_sec=float(req.target_duration_sec or prev_cfg.get("target_duration_sec") or 300.0),
        auto_fit_duration=bool(prev_cfg.get("auto_fit_duration", False)),
    )
    app_cfg = load_config()
    api_key = str(app_cfg.get("gemini_api_key") or "").strip()
    agy_caller = None
    if find_agy_executable():
        agy_model = str(app_cfg.get("agy_model") or "").strip() or None
        agy_effort = str(app_cfg.get("agy_effort") or "").strip() or None
        agy_caller = lambda p: str(
            call_agy_cli(p, model=agy_model, effort=agy_effort, mode="auto", disable_slash_commands=True, timeout=240).get("response") or ""
        )
    ch_script = _lf.generate_longform_chapter_script(
        plan=plan,
        ordered_clips=ordered,
        topic_note=req.product_note or str(prev_cfg.get("product_note") or ""),
        content_vibe=req.content_vibe or str(prev_cfg.get("content_vibe") or "outdoor_picnic"),
        vlog_title=req.vlog_title or str(prev_cfg.get("vlog_title") or ""),
        gemini_api_key=api_key,
        agy_caller=agy_caller,
        preview_dir=ws_dir / "frames" / "longform_preview",
        avoid_title_style=str(prev_cfg.get("last_title_style") or ""),
        preferred_title_style=req.title_style,
        preferred_subtitle_style=req.subtitle_style,
        preferred_accent_color=req.accent_color,
    )
    (ws_dir / "longform_chapters.json").write_text(json.dumps(ch_script, ensure_ascii=False, indent=2), encoding="utf-8")
    merged_cfg = {
        **prev_cfg,
        "vlog_title": req.vlog_title or ch_script.get("video_title") or "",
        "product_note": req.product_note or str(prev_cfg.get("product_note") or ""),
        "preferred_title_style": req.title_style,
        "preferred_subtitle_style": req.subtitle_style,
        "preferred_accent_color": req.accent_color,
    }
    cfg_p.write_text(json.dumps(merged_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "project_id": pid, "chapters_data": ch_script, "config": merged_cfg}


VIBE_DISCLAIMER_PRESETS: dict[str, str] = {
    "detective_mystery": "⚠️ LƯU Ý: Phong cách Thám Tử lồng tiếng vui vẻ gia đình — Không phải chuyên án hay sự vụ thật!",
    "field_report": "📢 LƯU Ý: Kịch bản dựng phong cách Phóng Sự giải trí gia đình — Không phải bản tin thời sự!",
    "pov_comedy": "😄 LƯU Ý: Lời bình POV trêu đùa vui vẻ trong gia đình — Chỉ mang tính giải trí!",
    "creative_internet": "✨ LƯU Ý: Nội dung sáng tạo theo trend giải trí gia đình & bạn bè.",
    "cinematic_deep": "🎬 Thước phim kỷ niệm gia đình dựng theo phong cách Điện Ảnh.",
    "default": "🏡 Video lưu giữ kỷ niệm vui vẻ gia đình — Nội dung chỉ mang tính giải trí!",
}


def _resolve_effective_disclaimer(req: OneClickPipelineReq, cur_vibe: str, is_random_variant: bool = False) -> str:
    if not bool(getattr(req, "disclaimer_enabled", False)):
        return ""
    raw_txt = str(getattr(req, "disclaimer_text", "") or "").strip()
    preset_vals = set(VIBE_DISCLAIMER_PRESETS.values())
    if not raw_txt or (is_random_variant and raw_txt in preset_vals):
        return VIBE_DISCLAIMER_PRESETS.get(cur_vibe, VIBE_DISCLAIMER_PRESETS["default"])
    return raw_txt


FACE_SCAN_LOCK = threading.Lock()
FACE_SCAN_JOBS: dict[str, dict[str, Any]] = {}


def _default_face_scan_job() -> dict[str, Any]:
    return {
        "status": "idle",
        "done_clips": 0,
        "total_clips": 0,
        "current_clip": "",
        "error": "",
        "updated_at": 0,
    }


def _get_face_scan_job(pid: str) -> dict[str, Any]:
    with FACE_SCAN_LOCK:
        job = FACE_SCAN_JOBS.get(pid)
        return dict(job) if isinstance(job, dict) else _default_face_scan_job()


class FacePrivacyScanReq(BaseModel):
    project_id: str = ""
    force: bool = True
    background: bool = True


class FacePrivacyConfigReq(BaseModel):
    project_id: str = ""
    enabled: bool = False
    mode: str = "blur_selected"
    style: str = "gaussian"
    icon: str = "cool"
    padding: float = 1.25
    selected_face_ids: list[str] = Field(default_factory=list)


def _attach_face_thumb_urls(faces: list[dict[str, Any]], pid: str, updated_at: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    ts = int(updated_at or int(time.time()))
    for f in faces or []:
        item = dict(f)
        fid = str(item.get("id") or "").strip()
        item["thumb_url"] = (
            f"/api/face-privacy/thumb?project_id={pid}&face_id={fid}&t={ts}"
            if fid and item.get("thumb_name")
            else ""
        )
        out.append(item)
    return out


def _req_face_privacy_dict(req: OneClickPipelineReq) -> dict[str, Any]:
    return {
        "enabled": bool(getattr(req, "face_blur_enabled", False)),
        "mode": str(getattr(req, "face_blur_mode", "blur_selected") or "blur_selected"),
        "style": str(getattr(req, "face_blur_style", "gaussian") or "gaussian"),
        "icon": str(getattr(req, "face_blur_icon", "cool") or "cool"),
        "padding": float(getattr(req, "face_blur_padding", 1.25) or 1.25),
        "selected_face_ids": list(getattr(req, "face_blur_ids", None) or []),
    }


@app.get("/api/face-privacy/state")
def api_face_privacy_state(project_id: str | None = None):
    import face_privacy as _fp

    pid = str(project_id or "").strip() or ACTIVE_PROJECT_ID
    p_root = get_project_root(pid)
    st = _fp.load_face_privacy_state(p_root)
    faces_ui = _fp._strip_embeddings_for_ui(st.get("faces") or [])
    ts = int(st.get("updated_at") or 0)
    clip_sig = st.get("clip_signature") or []
    return {
        "ok": True,
        "project_id": pid,
        "updated_at": ts,
        "clip_count": len(clip_sig) if isinstance(clip_sig, list) else 0,
        "faces": _attach_face_thumb_urls(faces_ui, pid, ts),
        "config": st.get("config") or dict(_fp.DEFAULT_FACE_PRIVACY_CONFIG),
        "scan_job": _get_face_scan_job(pid),
    }


@app.post("/api/face-privacy/scan")
def api_face_privacy_scan(req: FacePrivacyScanReq):
    import face_privacy as _fp

    pid = str(req.project_id or "").strip() or ACTIVE_PROJECT_ID
    p_root = get_project_root(pid)
    force = bool(req.force)

    if not req.background:
        res = _fp.scan_project_faces(p_root, force=force)
        ts = int(res.get("updated_at") or int(time.time()))
        clip_cnt = int(res.get("clip_count") or 0)
        res["faces"] = _attach_face_thumb_urls(res.get("faces") or [], pid, ts)
        job_snap = {
            "status": "done",
            "done_clips": clip_cnt,
            "total_clips": clip_cnt,
            "current_clip": "",
            "error": "",
            "cached": bool(res.get("cached")),
            "faces_count": len(res.get("faces") or []),
            "updated_at": ts,
        }
        with FACE_SCAN_LOCK:
            FACE_SCAN_JOBS[pid] = dict(job_snap)
        return {"ok": True, "project_id": pid, "already_running": False, "scan_job": job_snap, **res}

    with FACE_SCAN_LOCK:
        cur_job = FACE_SCAN_JOBS.get(pid)
        if isinstance(cur_job, dict) and cur_job.get("status") == "running":
            return {"ok": True, "project_id": pid, "already_running": True, "scan_job": dict(cur_job)}
        now_ts = int(time.time())
        FACE_SCAN_JOBS[pid] = {
            "status": "running",
            "done_clips": 0,
            "total_clips": 0,
            "current_clip": "",
            "error": "",
            "started_at": now_ts,
            "updated_at": now_ts,
        }

    def _bg_worker() -> None:
        def _on_prog(done: int, total: int, clip_name: str) -> None:
            with FACE_SCAN_LOCK:
                job = FACE_SCAN_JOBS.get(pid)
                if isinstance(job, dict) and job.get("status") == "running":
                    job["done_clips"] = int(done)
                    job["total_clips"] = int(total)
                    job["current_clip"] = str(clip_name or "")
                    job["updated_at"] = int(time.time())

        try:
            res = _fp.scan_project_faces(p_root, force=force, progress_cb=_on_prog)
            clip_cnt = int(res.get("clip_count") or 0)
            with FACE_SCAN_LOCK:
                FACE_SCAN_JOBS[pid] = {
                    "status": "done",
                    "done_clips": clip_cnt,
                    "total_clips": clip_cnt,
                    "current_clip": "",
                    "error": "",
                    "cached": bool(res.get("cached")),
                    "faces_count": len(res.get("faces") or []),
                    "updated_at": int(time.time()),
                }
        except Exception as exc:
            with FACE_SCAN_LOCK:
                cur = FACE_SCAN_JOBS.get(pid) or {}
                FACE_SCAN_JOBS[pid] = {
                    "status": "error",
                    "done_clips": int(cur.get("done_clips") or 0),
                    "total_clips": int(cur.get("total_clips") or 0),
                    "current_clip": str(cur.get("current_clip") or ""),
                    "error": str(exc),
                    "updated_at": int(time.time()),
                }

    threading.Thread(target=_bg_worker, daemon=True).start()
    return {
        "ok": True,
        "project_id": pid,
        "already_running": False,
        "scan_job": _get_face_scan_job(pid),
    }


@app.post("/api/face-privacy/config")
def api_face_privacy_config(req: FacePrivacyConfigReq):
    import face_privacy as _fp

    pid = str(req.project_id or "").strip() or ACTIVE_PROJECT_ID
    p_root = get_project_root(pid)
    res = _fp.save_face_privacy_config(
        p_root,
        {
            "enabled": req.enabled,
            "mode": req.mode,
            "style": req.style,
            "icon": req.icon,
            "padding": req.padding,
            "selected_face_ids": req.selected_face_ids,
        },
    )
    ts = int(res.get("updated_at") or 0)
    res["faces"] = _attach_face_thumb_urls(res.get("faces") or [], pid, ts)
    return {"ok": True, "project_id": pid, **res}


@app.get("/api/face-privacy/thumb")
def api_face_privacy_thumb(project_id: str = Query(...), face_id: str = Query(...)):
    clean_fid = Path(str(face_id or "").strip()).stem
    if not clean_fid or not re.match(r"^[a-zA-Z0-9_-]+$", clean_fid):
        raise HTTPException(status_code=400, detail="face_id không hợp lệ.")
    p_root = get_project_root(project_id).resolve()
    thumb_fp = (p_root / "04_workspace" / "face_privacy" / "thumbs" / f"{clean_fid}.jpg").resolve()
    if not thumb_fp.is_relative_to(p_root) or not thumb_fp.exists() or not thumb_fp.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh khuôn mặt.")
    return FileResponse(path=str(thumb_fp), media_type="image/jpeg")


@app.get("/api/style/vibes")
def api_style_vibes():
    import style_dna as _sd

    return {"ok": True, "vibes": list(_sd.CONTENT_VIBE_PRESETS.values())}


@app.get("/api/bgm/tracks")
def api_bgm_tracks():
    return {"ok": True, "bgm_tracks": ensure_royalty_free_bgm_library()}


@app.get("/api/voice/catalog")
def api_voice_catalog():
    import voice_engine as _ve

    return {"ok": True, **_ve.list_free_voice_catalog()}


@app.post("/api/remotion/preview-badge")
def api_remotion_preview_badge(req: RemotionRenderReq):
    ov = _apply_remotion_req_to_overrides(req)
    props = build_remotion_props(overrides=ov)
    res = render_title_badge_preview(props=props)
    badge_png = DIR_WORKSPACE / "hook_badge_preview.png"
    return {
        "ok": True,
        "hook_badge_preview_url": f"/files/04_workspace/hook_badge_preview.png?t={int(badge_png.stat().st_mtime)}" if badge_png.exists() else "",
        "remotion_props": props,
        **res,
    }


def _render_by_engine(engine: str) -> dict[str, Any]:
    if str(engine or "").strip() == "hyperframes":
        return render_hyperframes_video(rebuild_props=False)
    return render_remotion_video(rebuild_props=False)


class CreateProjectReq(BaseModel):
    name: str
    switch_to: bool = True
    raw_brief: str = ""
    target_duration_sec: float = 25.0


class SelectProjectReq(BaseModel):
    project_id: str = ""


@app.get("/api/projects")
def api_projects_list():
    return {"ok": True, **pm_list_projects()}


@app.post("/api/projects/create")
def api_projects_create(req: CreateProjectReq):
    with PIPELINE_LOCK:
        is_running = bool(PIPELINE_STATE["running"])
    eff_switch = bool(req.switch_to) and not is_running
    try:
        res = pm_create_project(
            req.name,
            switch_to=eff_switch,
            raw_brief=req.raw_brief,
            target_duration_sec=req.target_duration_sec,
        )
        created_id = str((res.get("project") or {}).get("id") or res.get("created_id") or "")
        if eff_switch:
            refresh_app_project_paths()
            if str(req.raw_brief or "").strip():
                save_brand_brief({"raw_brief": req.raw_brief.strip(), "target_duration_sec": req.target_duration_sec, "brief_ai_extracted": False})
                res = pm_list_projects()
        elif str(req.raw_brief or "").strip() and created_id:
            p_root = get_project_root(created_id)
            pm_ensure_project_dirs(p_root)
            bb_path = p_root / "04_workspace" / "brand_brief.json"
            cur_bb = json.loads(bb_path.read_text(encoding="utf-8-sig")) if bb_path.exists() else {}
            cur_bb.update({
                "raw_brief": req.raw_brief.strip(),
                "target_duration_sec": float(req.target_duration_sec or 25.0),
                "brief_ai_extracted": False,
            })
            bb_path.write_text(json.dumps(cur_bb, ensure_ascii=False, indent=2), encoding="utf-8")
            res = pm_list_projects()
        return {"ok": True, "created_id": created_id, "switched": eff_switch, **res}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/select")
def api_projects_select(req: SelectProjectReq):
    with PIPELINE_LOCK:
        if PIPELINE_STATE["running"]:
            raise HTTPException(status_code=409, detail="Không thể đổi Project khi Pipeline đang chạy.")
    try:
        res = pm_set_active_project(req.project_id)
        refresh_app_project_paths()
        return {"ok": True, **res}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/engines/status")
def api_engines_status():
    return {
        "ok": True,
        "remotion_classic": {"available": True, "composition": "TikTokVideo"},
        "remotion_innovation": {"available": True, "composition": "TikTokInnovation"},
        "hyperframes": get_hyperframes_status(),
    }


@app.post("/api/remotion/render")
def api_remotion_render(req: RemotionRenderReq):
    ov = _apply_remotion_req_to_overrides(req)
    props = build_remotion_props(overrides=ov)
    try:
        res = _render_by_engine(req.render_engine)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        **res,
        "preview_frames": _collect_remotion_preview_frames(),
        "remotion_props": props,
    }


def _apply_deterministic_ai_edit_fallback(instruction: str, props: dict[str, Any]) -> dict[str, Any]:
    """Deterministic parser for instant offline keyword edits when no LLM API key is configured or requested."""
    low = instruction.lower()
    if any(k in low for k in ("colgate", "maxfresh")):
        props["badgeStyle"] = "floral_plus_callouts"
        fb = props.setdefault("floralBadge", {})
        fb["enabled"] = True
        fb["brand"] = "Colgate"
        fb["productLine"] = "MaxFresh"
        fb["category"] = "nước súc miệng"
    if any(k in low for k in ("hoa lá", "floral", "nghệ thuật", "badge")):
        props["badgeStyle"] = "floral_badge" if "chỉ" in low else "floral_plus_callouts"
        props.setdefault("floralBadge", {})["enabled"] = True
    elif any(k in low for k in ("đa sắc", "kênh mẫu", "tối giản")):
        props["badgeStyle"] = "multicolor_pill"
    if "xanh ngọc" in low or "cyan" in low:
        props["subtitleActiveColor"] = "#00F2FE"
    elif "hồng" in low or "pink" in low:
        props["subtitleActiveColor"] = "#FB7185"
    elif "vàng" in low or "yellow" in low:
        props["subtitleActiveColor"] = "#FFE500"
    if "nhạc nhỏ" in low or "giảm nhạc" in low:
        props["bgmVolume"] = 0.08
    elif "nhạc to" in low or "tăng nhạc" in low:
        props["bgmVolume"] = 0.24
    return props


@app.post("/api/remotion/ai-edit")
def api_remotion_ai_edit(req: RemotionAiEditReq):
    instruction = req.instruction.strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="Vui lòng nhập yêu cầu chỉnh sửa cho AI.")

    props = (
        json.loads(FILE_REMOTION_PROPS.read_text(encoding="utf-8-sig"))
        if FILE_REMOTION_PROPS.exists()
        else build_remotion_props()
    )

    cfg = load_config()
    api_key = str(cfg.get("gemini_api_key") or "").strip()

    editable_subset = {
        "badgeStyle": props.get("badgeStyle"),
        "hookY": props.get("hookY"),
        "subtitleY": props.get("subtitleY"),
        "subtitleActiveColor": props.get("subtitleActiveColor"),
        "bgmVolume": props.get("bgmVolume"),
        "floralBadge": props.get("floralBadge"),
        "callouts": props.get("callouts"),
    }

    prompt = (
        "Bạn là AI Video Editor cho hệ thống Remotion TikTok.\n"
        f"Yêu cầu chỉnh sửa của người dùng: \"{instruction}\"\n\n"
        "Dưới đây là cấu hình đồ họa & âm thanh hiện tại của video (JSON):\n"
        f"{json.dumps(editable_subset, ensure_ascii=False, indent=2)}\n\n"
        "Hãy chỉnh sửa các trường phù hợp trong JSON trên để đáp ứng chính xác yêu cầu người dùng "
        "(giữ nguyên cấu trúc object/mảng, giữ màu hex hợp lệ, giữ vị trí `y` trong vùng an toàn 0.14–0.24 cho callout và 0.68–0.76 cho phụ đề).\n"
        "Chỉ trả về DUY NHẤT JSON đã cập nhật."
    )

    used_engine = "rule_fallback"
    updated_subset: dict[str, Any] | None = None
    if api_key:
        try:
            raw = call_gemini_multimodal(
                [{"text": prompt}],
                api_key=api_key,
                model=cfg.get("gemini_model") or "gemini-2.5-flash",
                effort="low",
                response_mime_type="application/json",
                timeout=45,
            )
            updated_subset = json.loads(raw)
            used_engine = "gemini_api"
        except Exception:
            updated_subset = None
    elif find_agy_executable():
        try:
            res = call_agy_cli(
                prompt,
                model=cfg.get("agy_model") or DEFAULT_CONFIG["agy_model"],
                effort="low",
                mode="auto",
                disable_slash_commands=True,
                timeout=90,
            )
            txt = res.get("response") or ""
            s_i, e_i = txt.find("{"), txt.rfind("}")
            if s_i >= 0 and e_i > s_i:
                updated_subset = json.loads(txt[s_i : e_i + 1])
                used_engine = "agy_cli"
        except Exception:
            updated_subset = None

    if isinstance(updated_subset, dict):
        for k in ("badgeStyle", "hookY", "subtitleY", "subtitleActiveColor", "bgmVolume", "floralBadge", "callouts"):
            if k in updated_subset and updated_subset[k] is not None:
                props[k] = updated_subset[k]
    else:
        props = _apply_deterministic_ai_edit_fallback(instruction, props)

    FILE_REMOTION_PROPS.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    update_style_dna(
        {
            "badge_style": props.get("badgeStyle"),
            "hook_y": props.get("hookY"),
            "subtitle_y": props.get("subtitleY"),
            "subtitle_active_color": props.get("subtitleActiveColor"),
            "bgm_volume": props.get("bgmVolume"),
        }
    )

    badge_res = render_title_badge_preview(props=props)
    render_res = None
    if req.auto_render:
        render_res = render_remotion_video(rebuild_props=False)

    badge_png = DIR_WORKSPACE / "hook_badge_preview.png"
    return {
        "ok": True,
        "engine": used_engine,
        "instruction": instruction,
        "remotion_props": props,
        "hook_badge_preview_url": f"/files/04_workspace/hook_badge_preview.png?t={int(badge_png.stat().st_mtime)}" if badge_png.exists() else "",
        "badge_preview": badge_res,
        "render": render_res,
        "preview_frames": _collect_remotion_preview_frames(),
    }


# ---------------------------------------------------------------------------
# Brand Brief, Auto-Critic Fixes & 1-Click Master Pipeline APIs
# ---------------------------------------------------------------------------


@app.get("/api/brand-brief")
def api_get_brand_brief():
    return load_brand_brief()


@app.post("/api/brand-brief")
def api_save_brand_brief(req: BrandBriefReq):
    saved = save_brand_brief(req.model_dump())
    update_style_dna(
        {
            "brand": saved.get("brand"),
            "product_line": saved.get("product_line"),
            "category": saved.get("category"),
        }
    )
    repair_subtitles_and_beats()
    props = None
    try:
        props = build_remotion_props()
    except Exception:
        pass
    return {"ok": True, "brand_brief": saved, "remotion_props": props}


@app.post("/api/brand-brief/extract-ai")
def api_extract_brand_brief(req: BrandBriefExtractReq):
    raw = (req.raw_brief or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Vui lòng dán nội dung brief nhãn hàng trước.")

    extracted = parse_raw_brand_brief_heuristic(raw, target_duration_sec=req.target_duration_sec)
    used_engine = "heuristic"

    cfg = load_config()
    api_key = str(cfg.get("gemini_api_key") or "").strip()
    extract_prompt = (
        "Hãy bóc tách đoạn thông tin sản phẩm / Brief nhãn hàng dưới đây thành DUY NHẤT một JSON hợp lệ gồm đúng các khóa:\n"
        "`brand` (TÊN THƯƠNG HIỆU IN HOA ngắn gọn), `product_line` (tên dòng sản phẩm ngắn 1-3 từ), "
        "`category` (danh mục tiếng Việt 2-4 từ thường để viết tay lên badge), "
        "`usps` (tóm tắt đầy đủ các USP/hoạt chất/công dụng quan trọng bằng tiếng Việt), "
        "`offer_cta` (ưu đãi, quà tặng, CTA chốt đơn), `banned_words` (các từ nhãn cấm nhắc), "
        "`phonetic_map` (object ánh xạ các từ tiếng Anh/con số/đơn vị sang cách đọc tiếng Việt cho F5-TTS, ví dụ {\"Head & Shoulders\": \"Hét en Sâu đơ\", \"50ml\": \"năm mươi mi li lít\"}).\n\n"
        f"=== NỘI DUNG BRIEF NHÃN HÀNG ===\n{raw}\n"
    )

    llm_data: dict[str, Any] | None = None
    if api_key:
        try:
            resp_txt = call_gemini_multimodal(
                [{"text": extract_prompt}],
                api_key=api_key,
                model=cfg.get("gemini_model") or "gemini-2.5-flash",
                effort="low",
                response_mime_type="application/json",
                timeout=45,
            )
            llm_data = json.loads(resp_txt)
            used_engine = "gemini_api"
        except Exception:
            llm_data = None
    elif find_agy_executable():
        try:
            res = call_agy_cli(
                extract_prompt,
                model=cfg.get("agy_model") or DEFAULT_CONFIG["agy_model"],
                effort="low",
                mode="auto",
                disable_slash_commands=True,
                timeout=60,
            )
            txt = res.get("response") or ""
            s_i, e_i = txt.find("{"), txt.rfind("}")
            if s_i >= 0 and e_i > s_i:
                llm_data = json.loads(txt[s_i : e_i + 1])
                used_engine = "agy_cli"
        except Exception:
            llm_data = None

    if isinstance(llm_data, dict):
        for k in ("brand", "product_line", "category", "usps", "offer_cta", "banned_words"):
            if str(llm_data.get(k) or "").strip():
                extracted[k] = str(llm_data[k]).strip()
        if isinstance(llm_data.get("phonetic_map"), dict):
            merged_pm = dict(extracted.get("phonetic_map") or {})
            merged_pm.update({str(k): str(v) for k, v in llm_data["phonetic_map"].items() if str(k).strip() and str(v).strip()})
            extracted["phonetic_map"] = merged_pm

    saved = save_brand_brief(extracted)
    return {"ok": True, "brand_brief": saved, "engine": used_engine}


@app.post("/api/remotion/apply-critic")
def api_remotion_apply_critic():
    raw_videos = list_media_in_dir(DIR_VIDEO_THO)
    rep = repair_subtitles_and_beats(force_rebuild=True)
    aligned_plan = align_edit_plan_to_voice_beats(raw_videos)
    clip_res = None
    if aligned_plan.get("clips") and raw_videos:
        clip_res = run_python_script("scripts/prepare_clips.py", ["--config", "04_workspace/edit_plan.json", "--concat"])
    props = build_remotion_props()
    badge_res = render_title_badge_preview(props=props)
    badge_png = DIR_WORKSPACE / "hook_badge_preview.png"
    return {
        "ok": True,
        "repair": rep,
        "edit_plan": aligned_plan,
        "prepare_clips": clip_res,
        "remotion_props": props,
        "badge_preview": badge_res,
        "hook_badge_preview_url": f"/files/04_workspace/hook_badge_preview.png?t={int(badge_png.stat().st_mtime)}" if badge_png.exists() else "",
        "workshop_state": collect_workshop_state(),
    }


PIPELINE_LOCK = threading.Lock()
PIPELINE_STATE: dict[str, Any] = {
    "running": False,
    "current_step": 0,
    "current_tab": "tab4",
    "percent": 0,
    "message": "Sẵn sàng chạy tự động 1-Click.",
    "steps": [
        {"id": 1, "tab": "tab4", "label": "Bước 1: Nạp Style DNA, Brief & Tự Kiểm Tra AI Critic", "status": "idle", "detail": ""},
        {"id": 2, "tab": "tab4", "label": "Bước 2: Lên 3 Kịch Bản theo Thời Lượng & Chốt Phương Án", "status": "idle", "detail": ""},
        {"id": 3, "tab": "tab4", "label": "Bước 3: Tạo Giọng AI chuẩn Thời Lượng & Phụ Đề Karaoke", "status": "idle", "detail": ""},
        {"id": 4, "tab": "tab4", "label": "Bước 4: Căn Clip 9:16 Bám Beat (Tôn Trọng Khóa Clips)", "status": "idle", "detail": ""},
        {"id": 5, "tab": "tab5", "label": "Bước 5: Xuất Video .MP4 Tự Động (Remotion)", "status": "idle", "detail": ""},
    ],
    "logs": [],
    "error": "",
    "result": None,
}


def _update_pipeline(
    *,
    running: bool | None = None,
    current_step: int | None = None,
    current_tab: str | None = None,
    percent: int | None = None,
    message: str | None = None,
    step_status: tuple[int, str, str] | None = None,
    log_line: str | None = None,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    with PIPELINE_LOCK:
        if running is not None:
            PIPELINE_STATE["running"] = running
        if current_step is not None:
            PIPELINE_STATE["current_step"] = current_step
        if current_tab is not None:
            PIPELINE_STATE["current_tab"] = current_tab
        if percent is not None:
            PIPELINE_STATE["percent"] = percent
        if message is not None:
            PIPELINE_STATE["message"] = message
        if error is not None:
            PIPELINE_STATE["error"] = error
        if result is not None:
            PIPELINE_STATE["result"] = result
        if step_status is not None:
            sid, st, det = step_status
            for item in PIPELINE_STATE["steps"]:
                if item["id"] == sid:
                    item["status"] = st
                    if det:
                        item["detail"] = det
        if log_line:
            PIPELINE_STATE["logs"] = (PIPELINE_STATE["logs"] + [log_line])[-40:]


def _reset_pipeline_state() -> None:
    with PIPELINE_LOCK:
        PIPELINE_STATE["running"] = True
        PIPELINE_STATE["current_step"] = 1
        PIPELINE_STATE["current_tab"] = "tab4"
        PIPELINE_STATE["percent"] = 5
        PIPELINE_STATE["message"] = "Khởi động luồng dựng tự động theo Kế hoạch AI..."
        PIPELINE_STATE["error"] = ""
        PIPELINE_STATE["result"] = None
        PIPELINE_STATE["logs"] = []
        for s in PIPELINE_STATE["steps"]:
            s["status"] = "idle"
            s["detail"] = ""


def _build_fallback_script_from_brief(brief: dict[str, Any], target_dur: float) -> tuple[str, str]:
    brand = str(brief.get("brand") or "Sản phẩm").strip()
    prod = str(brief.get("product_line") or "").strip()
    cat = str(brief.get("category") or "sản phẩm hot").strip()
    usps = str(brief.get("usps") or "thiết kế tiện lợi, dùng là mê").strip()
    cta = str(brief.get("offer_cta") or "Đang có deal hời kèm Freeship, bấm giỏ hàng góc trái chốt liền nha.").strip()
    display_script = (
        f"Bà nào đang tìm {cat} chân ái thì nghía ngay em {brand} {prod} này nha. "
        f"Điểm ăn tiền nhất là {usps}. "
        "Trải nghiệm thực tế cực kỳ ưng ý và tiện lợi mỗi ngày luôn. "
        f"{cta}"
    )
    display_script = re.sub(r"\s+", " ", display_script).strip()
    if display_script[-1] not in ".!?":
        display_script += "."
    tts_script = display_script
    pm = brief.get("phonetic_map") or {}
    for dt, st in sorted(pm.items(), key=lambda kv: -len(str(kv[0]))):
        tts_script = re.sub(re.escape(str(dt)), str(st), tts_script, flags=re.I)
    return tts_script, display_script


def _record_render_history(ws_dir: Path, filename: str, meta: dict[str, Any]) -> None:
    try:
        ws_dir.mkdir(parents=True, exist_ok=True)
        hist_p = ws_dir / "render_history.json"
        hist: dict[str, Any] = {}
        if hist_p.exists():
            try:
                loaded = json.loads(hist_p.read_text(encoding="utf-8-sig"))
                if isinstance(loaded, dict):
                    hist = loaded
            except Exception:
                hist = {}
        hist[str(filename)] = {
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            **meta,
        }
        hist_p.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _thumb_path(p_root: Path, mp4_name: str) -> Path:
    return p_root / "05_output" / "_thumbnails" / f"{Path(mp4_name).stem}.jpg"


def _generate_social_seo_pack(
    *,
    title_hint: str,
    script_text: str,
    mode: str,
    aspect_ratio: str,
    brand_brief: dict[str, Any] | None = None,
    product_note: str = "",
    chapters: list[str] | None = None,
) -> tuple[str, str]:
    """Generate a ready-to-paste Social Title & Description + Hashtags for TikTok/YouTube/Reels."""
    clean_title = str(title_hint or "").strip()
    is_short_shop = mode.startswith("short") and brand_brief and str(brand_brief.get("brand") or "").strip() and "story" not in mode.lower()
    cfg = load_config()
    api_key = str(cfg.get("gemini_api_key") or "").strip()
    if api_key:
        try:
            import urllib.request

            chap_str = " | ".join(chapters[:6]) if chapters else ""
            brand_str = ""
            if is_short_shop and brand_brief:
                brand_str = f"Sản phẩm: {brand_brief.get('brand')} {brand_brief.get('product_line', '')}. USP: {brand_brief.get('usps', '')}. CTA: {brand_brief.get('offer_cta', '')}."
            prompt = (
                "Viết Tiêu đề và Mô tả chuẩn SEO để đăng video lên YouTube, TikTok và Facebook Reels.\n"
                f"Định dạng: {aspect_ratio} ({mode}). Tiêu đề gốc: {clean_title or 'Video mới'}.\n"
                f"{brand_str}\nGhi chú: {product_note[:300]}\n"
                f"Các chương: {chap_str}\n"
                f"Trích đoạn lời thoại: {script_text[:700]}\n\n"
                "Trả về DUY NHẤT JSON: {\"social_title\": \"<= 70 ký tự hấp dẫn\", \"social_description\": \"2-4 dòng mô tả tự nhiên kèm 5-7 #hashtag tiếng Việt/Anh phù hợp\"}."
            )
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            req_http = urllib.request.Request(
                url,
                data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req_http, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                cands = data.get("candidates") or []
                if cands:
                    raw = " ".join(str(p.get("text") or "") for p in ((cands[0].get("content") or {}).get("parts") or []))
                    m = re.search(r"\{[\s\S]*\}", raw)
                    if m:
                        obj = json.loads(m.group(0))
                        st = str(obj.get("social_title") or "").strip()[:90]
                        sd = str(obj.get("social_description") or "").strip()[:900]
                        if st and sd:
                            return st, sd
        except Exception:
            pass

    # Heuristic fallback
    if not clean_title:
        clean_title = (
            f"{brand_brief.get('brand', '')} {brand_brief.get('product_line', '')}".strip()
            if is_short_shop and brand_brief
            else (product_note.splitlines()[0][:55].strip() if product_note.strip() else "Khoảnh khắc đáng nhớ hôm nay")
        )
    s_title = clean_title[:75]
    snippet = " ".join(script_text.split()[:38]).strip()
    if is_short_shop and brand_brief:
        cta = str(brand_brief.get("offer_cta") or "Bấm ngay giỏ hàng góc trái để săn ưu đãi!").strip()
        s_desc = f"{s_title}\n{snippet}...\n👉 {cta}\n\n#tiktokshop #review #xuhuong #muasam"
    else:
        chap_line = ("\n📑 Nội dung: " + " · ".join(c.split(":", 1)[-1].strip() for c in (chapters or [])[:4])) if chapters else ""
        s_desc = f"{s_title}{chap_line}\n{snippet}...\n\n💬 Bạn thích khoảnh khắc nào nhất? Nhớ Follow & Like ủng hộ mình nhé!\n#vlog #dulich #doisong #review #xuhuong"
    return s_title, s_desc


def _generate_video_thumbnail(
    mp4_path: Path,
    dest_jpg: Path,
    *,
    title_text: str = "",
    subtitle_text: str = "",
    badge_text: str = "HIGHLIGHT",
    accent_color: str = "#F59E0B",
    aspect_ratio: str = "16:9",
    seek_sec: float = 2.0,
) -> bool:
    """Extract crisp thumbnail directly from the video's Intro/Hook frame (~2.0s) via FFmpeg."""
    if not mp4_path.exists() or not mp4_path.is_file():
        return False
    dest_jpg.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = find_binary("ffmpeg") or "ffmpeg"
    probe = probe_media(mp4_path)
    dur = float(probe.get("duration_sec") or 10.0)
    w_src = int(probe.get("width") or 1920)
    h_src = int(probe.get("height") or 1080)
    ar_clean = "9:16" if (str(aspect_ratio or "").strip() == "9:16" or h_src > w_src) else "16:9"
    scale_vf = "scale=1080:1920:force_original_aspect_ratio=decrease" if ar_clean == "9:16" else "scale=1280:720:force_original_aspect_ratio=decrease"
    t_seek = max(0.3, min(float(seek_sec or 2.0), max(0.3, dur - 0.5)))
    try:
        subprocess.run(
            [
                ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{t_seek:.2f}", "-i", str(mp4_path),
                "-vf", scale_vf, "-vframes", "1", "-q:v", "2", str(dest_jpg),
            ],
            check=True,
            timeout=30,
        )
        return dest_jpg.exists() and dest_jpg.stat().st_size > 1024
    except Exception:
        return False


def _attach_output_assets(
    proj_root: Path,
    mp4_path: Path,
    meta: dict[str, Any],
    *,
    script_text: str = "",
    brand_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_meta = dict(meta)
    mode = str(out_meta.get("mode") or "")
    ar = str(out_meta.get("aspect_ratio") or "16:9")
    title_hint = str(out_meta.get("title") or "").strip()
    if not out_meta.get("social_title") or not out_meta.get("social_description"):
        st, sd = _generate_social_seo_pack(
            title_hint=title_hint,
            script_text=script_text,
            mode=mode,
            aspect_ratio=ar,
            brand_brief=brand_brief,
            product_note=str(out_meta.get("product_note") or ""),
            chapters=out_meta.get("chapters_summary") if isinstance(out_meta.get("chapters_summary"), list) else None,
        )
        out_meta["social_title"] = st
        out_meta["social_description"] = sd
    t_dest = _thumb_path(proj_root, mp4_path.name)
    if not t_dest.exists():
        _generate_video_thumbnail(
            mp4_path,
            t_dest,
            title_text=str(out_meta.get("social_title") or title_hint or mp4_path.stem),
            subtitle_text=str(out_meta.get("product_note") or "").splitlines()[0][:55] if str(out_meta.get("product_note") or "").strip() else "",
            badge_text="VLOG 4K" if "long" in mode else "TIKTOK",
            accent_color=str(out_meta.get("accent_color") or "#F59E0B"),
            aspect_ratio=ar,
        )
    return out_meta


def _remove_render_history(ws_dir: Path, filename: str) -> None:
    try:
        hist_p = ws_dir / "render_history.json"
        if not hist_p.exists():
            return
        hist = json.loads(hist_p.read_text(encoding="utf-8-sig"))
        if isinstance(hist, dict) and filename in hist:
            hist.pop(filename, None)
            hist_p.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _execute_longform_vlog_pipeline(
    req: OneClickPipelineReq,
    variant_tag: str = "",
    forced_style: tuple[str, str, str] | None = None,
    forced_color_preset: str = "",
    shot_jitter_sec: float = 0.0,
) -> list[dict[str, Any]]:
    """Broadcast-Quality 4K Hybrid Remotion + FFmpeg Master Pipeline for Long-Form Vlog (>90s to 20m)."""
    import longform_vlog as _lf
    import style_dna as _sd
    import voice_engine as _ve

    raw_ar = str(getattr(req, "aspect_ratio", "16:9") or "16:9").strip()
    aspect_list = ["16:9", "9:16"] if raw_ar == "both" else ([raw_ar] if raw_ar in ("9:16", "16:9") else ["16:9"])
    req_aspect = aspect_list[0]
    req_vibe = str(getattr(req, "content_vibe", "outdoor_picnic") or "outdoor_picnic").strip()
    if req_vibe == "learned_dna":
        req_vibe = "outdoor_picnic"
    req_pacing = str(getattr(req, "pacing_preset", "auto") or "auto").strip().lower()
    if req_pacing not in ("auto", "chill", "fast", "turbo"):
        req_pacing = "auto"
    vp_prof = _lf.get_vibe_editing_profile(req_vibe, pacing_preset=req_pacing)
    req_quality = str(getattr(req, "quality_preset", "auto_source") or "auto_source").strip()
    req_vlog_title = str(getattr(req, "vlog_title", "") or "").strip()

    with PIPELINE_LOCK:
        PIPELINE_STATE["steps"] = [
            {"id": 1, "tab": "tab4", "label": "Bước 1: Quét Clip & Cắt Nhịp Highlight Timeline", "status": "idle", "detail": ""},
            {"id": 2, "tab": "tab4", "label": "Bước 2: AI Viết Kịch Bản Theo Chương (Không Lặp)", "status": "idle", "detail": ""},
            {"id": 3, "tab": "tab4", "label": "Bước 3: Tạo 1 Giọng Đọc Có Nhịp Nghỉ & Phụ Đề", "status": "idle", "detail": ""},
            {"id": 4, "tab": "tab4", "label": f"Bước 4: Render Remotion Intro/Ending & Master {req_aspect}", "status": "idle", "detail": ""},
            {"id": 5, "tab": "tab5", "label": f"Bước 5: Xuất MP4 Chất Lượng Cao vào Kho Video", "status": "idle", "detail": ""},
        ]

    pacing_log = f" [Tiết tấu: {req_pacing.upper()}]" if req_pacing != "auto" else ""
    _update_pipeline(
        current_step=1,
        current_tab="tab4",
        percent=10,
        message="Bước 1/5 (Timeline Vlog): Quét video thô 4K & chia shot highlight theo đúng thứ tự...",
        step_status=(1, "running", "Chia shot Highlight"),
        log_line=f"[Clip Dài > 90s]{pacing_log} Quét clip 02_video_tho/ & chia nhịp {float(vp_prof.get('shot_sec') or 6.2):.1f}s/cảnh theo thứ tự thời gian...",
    )
    ordered = _lf.collect_ordered_raw_clips(DIR_VIDEO_THO, ordered_names=req.ordered_clips or None)
    if not ordered:
        raise RuntimeError("Chưa có video thô nào trong 02_video_tho/. Vui lòng upload video trước khi tạo Clip Dài.")

    plan = _lf.build_longform_timeline_plan(
        ordered,
        target_duration_sec=float(req.target_duration_sec or 300.0),
        auto_fit_duration=bool(getattr(req, "auto_fit_duration", False)),
        aspect_ratio=req_aspect,
        quality_preset=req_quality,
        shot_jitter_sec=shot_jitter_sec,
        target_shot_sec=float(vp_prof.get("shot_sec") or 6.2),
    )
    actual_target = float(plan["target_duration_sec"])
    n_shots = len(plan.get("segments") or [])
    n_chaps = len(plan.get("chapters") or [])
    q_label = str(plan.get("quality_label") or req_quality)
    _update_pipeline(
        step_status=(1, "done", f"{n_shots} cảnh · {n_chaps} chương · {q_label}"),
        percent=22,
        log_line=f"[Bước 1/5] Đã chia {n_shots} cảnh vào {n_chaps} chương ({req_aspect} {q_label}, {actual_target:.0f}s).",
    )

    _update_pipeline(
        current_step=2,
        percent=30,
        message=f"Bước 2/5 (Kịch Bản Chương): AI đang xem khung hình & viết {n_chaps} chương có nhịp nghỉ...",
        step_status=(2, "running", f"{n_chaps} Chương · ~{actual_target:.0f}s"),
        log_line="[Bước 2/5] Tạo kịch bản Vlog chia chương (chừa khoảng thở B-roll, chống lặp câu)...",
    )
    cfg = load_config()
    api_key = str(cfg.get("gemini_api_key") or "").strip()
    agy_caller = None
    if find_agy_executable():
        agy_model = str(cfg.get("agy_model") or "").strip() or None
        agy_effort = str(cfg.get("agy_effort") or "").strip() or None
        agy_caller = lambda p: str(
            call_agy_cli(
                p,
                model=agy_model,
                effort=agy_effort,
                mode="auto",
                disable_slash_commands=True,
                timeout=240,
            ).get("response")
            or ""
        )
    lf_cfg_file = DIR_WORKSPACE / "longform_config.json"
    prev_lf_cfg: dict[str, Any] = {}
    if lf_cfg_file.exists():
        try:
            prev_lf_cfg = json.loads(lf_cfg_file.read_text(encoding="utf-8-sig"))
        except Exception:
            prev_lf_cfg = {}
    avoid_ts = str(prev_lf_cfg.get("last_title_style") or "").strip()
    pref_ts = forced_style[0] if forced_style else str(prev_lf_cfg.get("preferred_title_style") or "").strip()
    pref_ss = forced_style[1] if forced_style else str(prev_lf_cfg.get("preferred_subtitle_style") or "").strip()
    pref_ac = forced_style[2] if forced_style else str(prev_lf_cfg.get("preferred_accent_color") or "").strip()
    req_color_raw = str(getattr(req, "color_preset", "") or "natural").strip()
    disable_vf = bool(getattr(req, "disable_vibe_filter", False))
    eff_color_preset = "natural" if disable_vf else (
        forced_color_preset or (
            str(vp_prof.get("color_preset") or "natural") if (req_color_raw == "natural" and vp_prof.get("force_vfx")) else req_color_raw
        )
    )

    ch_json_path = DIR_WORKSPACE / "longform_chapters.json"
    ch_script = None
    if bool(getattr(req, "preserve_longform_script", False)) and ch_json_path.exists():
        try:
            loaded_cs = json.loads(ch_json_path.read_text(encoding="utf-8-sig"))
            if isinstance(loaded_cs, dict) and isinstance(loaded_cs.get("chapters"), list) and loaded_cs["chapters"]:
                plan_chs = plan.get("chapters") or []
                for ci, ch in enumerate(loaded_cs["chapters"]):
                    if ci < len(plan_chs):
                        ch["start_sec"] = float(plan_chs[ci].get("start_sec") or ch.get("start_sec") or 0.0)
                        ch["end_sec"] = float(plan_chs[ci].get("end_sec") or ch.get("end_sec") or actual_target)
                if req_vlog_title:
                    loaded_cs["video_title"] = req_vlog_title
                loaded_cs["ai_source"] = "user_edited"
                ch_script = loaded_cs
        except Exception:
            ch_script = None

    if ch_script is None:
        ch_script = _lf.generate_longform_chapter_script(
            plan=plan,
            ordered_clips=ordered,
            topic_note=req.product_note or "",
            content_vibe=req_vibe,
            vlog_title=req_vlog_title,
            gemini_api_key=api_key,
            agy_caller=agy_caller,
            preview_dir=DIR_WORKSPACE / "frames" / "longform_preview",
            avoid_title_style=avoid_ts,
            preferred_title_style=pref_ts,
            preferred_subtitle_style=pref_ss,
            preferred_accent_color=pref_ac,
            pacing_preset=req_pacing,
        )
    ch_json_path.write_text(
        json.dumps(ch_script, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    vd_saved = ch_script.get("visual_direction") if isinstance(ch_script.get("visual_direction"), dict) else {}
    saved_lf_cfg = {
        **prev_lf_cfg,
        "target_duration_sec": float(req.target_duration_sec or 300.0),
        "quality_preset": req_quality,
        "auto_fit_duration": bool(getattr(req, "auto_fit_duration", False)),
        "keep_clip_audio": bool(getattr(req, "keep_clip_audio", False)),
        "vlog_title": req_vlog_title,
        "product_note": str(req.product_note or "").strip(),
        "ordered_clips": [c["rel_path"] for c in ordered],
        "aspect_ratio": req_aspect,
        "content_vibe": req_vibe,
        "pacing_preset": req_pacing,
        "last_title_style": str(vd_saved.get("title_style") or ""),
        "last_subtitle_style": str(vd_saved.get("subtitle_style") or ""),
    }
    lf_cfg_file.write_text(json.dumps(saved_lf_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    disp_txt = " ".join(
        blk["text"] for ch in ch_script.get("chapters") or [] for blk in ch.get("narration_blocks") or []
    ).strip()
    tts_txt = _sd.convert_display_to_tts_script(disp_txt)
    FILE_SCRIPT.write_text(tts_txt + "\n", encoding="utf-8")
    (DIR_WORKSPACE / "kich_ban_hien_thi.md").write_text(disp_txt + "\n", encoding="utf-8")
    ai_src_lbl = str(ch_script.get("ai_source") or "ai")
    _update_pipeline(
        step_status=(2, "done", f"{len(disp_txt.split())} từ ({ai_src_lbl})"),
        percent=44,
        log_line=f"[Bước 2/5] Xong kịch bản {n_chaps} chương ({ai_src_lbl}): {ch_script.get('video_title')} · {len(disp_txt.split())} từ.",
    )

    _update_pipeline(
        current_step=3,
        percent=50,
        message="Bước 3/5 (Giọng Đọc Nhịp Thở): Đang ghép lời bình đúng mốc chương & chừa khoảng nghỉ B-roll...",
        step_status=(3, "running", "Giọng + Nhịp nghỉ 4-7s"),
        log_line="[Bước 3/5] Tạo 1 giọng đọc xuyên suốt theo mốc chương & đồng bộ phụ đề SRT...",
    )
    req_mute_voice = bool(getattr(req, "mute_voice", False))
    req_hide_subs = bool(getattr(req, "hide_subtitles", False))
    voice_res: dict[str, Any] | None = None
    if req_mute_voice:
        _update_pipeline(
            step_status=(3, "done", "Đã tắt giọng đọc (Story)"),
            percent=66,
            log_line="[Bước 3/5] Đang bật Ẩn giọng đọc AI — giữ nhạc nền & hiệu ứng.",
        )
    else:
        sync_voice_clone_files()
        vp = str(getattr(req, "voice_preset", "") or "edge_hoaimy_koc").strip()
        if vp.startswith("random_"):
            vp = _ve.pick_random_voice_presets(vp, count=1)[0]["id"]
        def _lf_voice_progress(done_i: int, total_n: int, msg_lbl: str) -> None:
            pct = 50 + int((done_i / max(1, total_n)) * 15)
            _update_pipeline(
                percent=min(65, pct),
                message=f"Bước 3/5 (Giọng Đọc): Đang tạo {msg_lbl}...",
                step_status=(3, "running", msg_lbl),
            )

        force_pace_or_vfx = bool(vp_prof.get("force_pacing") or vp_prof.get("force_vfx"))
        eff_pause = float(vp_prof.get("sentence_pause_sec") or 0.85) if force_pace_or_vfx else float(prev_lf_cfg.get("sentence_pause_sec") or vp_prof.get("sentence_pause_sec") or 0.85)
        eff_vrate = str(vp_prof.get("voice_rate_offset") or "") if force_pace_or_vfx else str(prev_lf_cfg.get("voice_rate_offset") or vp_prof.get("voice_rate_offset") or "")
        voice_res = _lf.build_longform_voice_and_srt(
            chapter_script=ch_script,
            plan=plan,
            out_wav_path=FILE_TTS_WAV,
            out_srt_path=FILE_TTS_SRT,
            voice_preset=vp,
            sentence_pause_sec=eff_pause,
            voice_rate_override=eff_vrate,
            phonetic_overrides=prev_lf_cfg.get("phonetic_overrides") or "",
            content_vibe=req_vibe,
            pacing_preset=req_pacing,
            progress_cb=_lf_voice_progress,
        )
        sfx_cnt = int(voice_res.get("sfx_count") or 0)
        sfx_note = f" + {sfx_cnt} SFX" if sfx_cnt > 0 else ""
        _update_pipeline(
            step_status=(3, "done", f"{voice_res['placed_blocks']} đoạn{sfx_note} · {voice_res['srt_lines']} dòng SRT"),
            percent=66,
            log_line=f"[Bước 3/5] Hoàn tất giọng ({voice_res['preset_label']}{sfx_note}), đồng bộ {voice_res['srt_lines']} dòng phụ đề.",
        )

    bgm_name = str(req.bgm_track or "bgm_upbeat_tiktok.wav").strip()
    if bgm_name == "bgm_upbeat_tiktok.wav" and vp_prof.get("force_vfx"):
        if req_vibe in ("detective_mystery", "field_report"):
            cand_bgm = PROJECT_ROOT / "06_assets_audio" / "bgm" / "bgm_tiktok_retro_synth.wav"
        elif req_vibe in ("pov_comedy", "creative_internet"):
            cand_bgm = PROJECT_ROOT / "06_assets_audio" / "bgm" / "bgm_tiktok_dance_bounce.wav"
        else:
            cand_bgm = PROJECT_ROOT / "06_assets_audio" / "bgm" / "bgm_piano_midnight_letters.wav"
        if cand_bgm.exists():
            bgm_name = cand_bgm.name
    bgm_file = PROJECT_ROOT / "06_assets_audio" / "bgm" / Path(bgm_name).name
    if not bgm_file.exists():
        bgm_cand = sorted((PROJECT_ROOT / "06_assets_audio" / "bgm").glob("*.wav"))
        bgm_file = bgm_cand[0] if bgm_cand else bgm_file

    DIR_OUTPUT.mkdir(parents=True, exist_ok=True)
    vd = ch_script.get("visual_direction") if isinstance(ch_script.get("visual_direction"), dict) else {}
    ch_prof = api_get_channel_profile()
    ch_name = str(ch_prof.get("name") or "VLOG JOURNAL").strip()
    exported_list: list[dict[str, Any]] = []
    last_out_mp4: Path | None = None
    last_render_res: dict[str, Any] = {}

    import face_privacy as _fp
    fp_saved = _fp.save_face_privacy_config(ACTIVE_PROJECT_ROOT, _req_face_privacy_dict(req))
    fp_cfg = fp_saved["config"]
    if fp_cfg.get("enabled"):
        _update_pipeline(
            log_line=f"[Che mặt AI] BẬT ({fp_cfg['mode']} · kiểu={fp_cfg['style']} · icon={fp_cfg.get('icon', 'cool')} · đã chọn={len(fp_cfg['selected_face_ids'])} mặt).",
        )
    eff_disclaimer = _resolve_effective_disclaimer(req, req_vibe, is_random_variant=bool(variant_tag))
    if eff_disclaimer:
        _update_pipeline(log_line=f"[Nhãn Cảnh báo đầu clip] {eff_disclaimer}")
    req_sub_lang = str(getattr(req, "subtitle_lang", "vi") or "vi").strip().lower()
    if req_sub_lang not in ("vi", "bilingual", "en"):
        req_sub_lang = "vi"
    if req_sub_lang != "vi" and not req_hide_subs:
        _update_pipeline(log_line=f"[Ngôn ngữ Phụ đề] {req_sub_lang} (Dịch tự động từ SRT tiếng Việt).")

    for ar_idx, cur_ar in enumerate(aspect_list, start=1):
        ar_plan = dict(plan)
        if cur_ar != req_aspect:
            tw, th, _ = _lf.resolve_target_resolution(ordered, aspect_ratio=cur_ar, quality_preset=req_quality)
            ar_plan["target_resolution"] = [tw, th]
            ar_plan["aspect_ratio"] = cur_ar
        _update_pipeline(
            current_step=4,
            percent=72 + (ar_idx - 1) * 12,
            message=f"Bước 4/5 ({ar_idx}/{len(aspect_list)} · {cur_ar} {q_label}): Render Motion & Master...",
            step_status=(4, "running", f"{cur_ar} · {q_label}"),
            log_line=f"[Bước 4/5] Render Motion Graphics & FFmpeg Master cho {cur_ar} {variant_tag}...",
        )
        ov_dir = DIR_WORKSPACE / "vlog_overlays"
        shutil.rmtree(ov_dir, ignore_errors=True)
        overlays = _lf.render_vlog_remotion_overlays(
            plan=ar_plan,
            chapter_script=ch_script,
            out_dir=ov_dir,
            aspect_ratio=cur_ar,
            channel_name=ch_name,
            sticker_density=str(req.sticker_density or "normal"),
            sticker_style=str(getattr(req, "sticker_style", "pill_minimal") or "pill_minimal"),
            disclaimer_text=eff_disclaimer,
        )
        stk_rendered = sum(1 for ov in overlays if "sticker_" in str(ov.get("path") or ""))
        _update_pipeline(
            log_line=f"[Bước 4/5] {cur_ar}: Đã render {len(overlays)} Remotion motion ({stk_rendered} Sticker Lottie).",
        )
        tag_slug = f"_{variant_tag}" if variant_tag else ""
        out_mp4 = DIR_OUTPUT / f"VLOG_{int(round(actual_target))}s_{cur_ar.replace(':', 'x')}_{q_label.split()[0]}{tag_slug}_{int(time.time())}.mp4"
        render_res = _lf.render_longform_ffmpeg_vlog(
            plan=ar_plan,
            voice_wav=(None if req_mute_voice else (FILE_TTS_WAV if FILE_TTS_WAV.exists() else None)),
            srt_path=(None if (req_hide_subs or req_mute_voice) else (FILE_TTS_SRT if FILE_TTS_SRT.exists() else None)),
            bgm_path=bgm_file if bgm_file.exists() else None,
            output_mp4=out_mp4,
            overlays=overlays,
            bgm_volume=0.20,
            subtitle_style=str(vd.get("subtitle_style") or "editorial_clean"),
            accent_color=str(vd.get("accent_color") or "#F59E0B"),
            color_preset=eff_color_preset,
            content_vibe=req_vibe,
            enable_motion_zoom=bool(getattr(req, "enable_motion_zoom", False)),
            disable_vibe_filter=disable_vf,
            face_privacy_cfg=fp_cfg,
            project_root=ACTIVE_PROJECT_ROOT,
            subtitle_lang=req_sub_lang,
            audio_cues=(voice_res.get("audio_cues") if (not req_mute_voice and isinstance(voice_res, dict)) else None),
            pacing_preset=req_pacing,
            keep_clip_audio=bool(getattr(req, "keep_clip_audio", False)),
        )
        lf_meta = _attach_output_assets(
            ACTIVE_PROJECT_ROOT,
            out_mp4,
            {
                "mode": "long_random" if variant_tag else "long_vlog",
                "variant": variant_tag or "standard",
                "engine": "longform_remotion_4k",
                "aspect_ratio": cur_ar,
                "quality": q_label,
                "duration_sec": render_res.get("duration_sec"),
                "voice_preset": "muted" if req_mute_voice else str(getattr(req, "voice_preset", "") or "edge_hoaimy_koc"),
                "bgm_track": bgm_file.name if bgm_file.exists() else "",
                "title": str(ch_script.get("video_title") or req_vlog_title or ""),
                "title_style": str(vd.get("title_style") or "cinematic_glass"),
                "subtitle_style": str(vd.get("subtitle_style") or "editorial_clean"),
                "color_preset": eff_color_preset,
                "content_vibe": req_vibe,
                "pacing_preset": req_pacing,
                "accent_color": str(vd.get("accent_color") or "#F59E0B"),
                "sticker_density": str(req.sticker_density or "normal"),
                "stickers_count": stk_rendered,
                "mute_voice": req_mute_voice,
                "hide_subtitles": req_hide_subs,
                "keep_clip_audio": bool(getattr(req, "keep_clip_audio", False)),
                "product_note": str(req.product_note or "")[:240],
                "chapters_summary": [
                    f"C{c.get('index')}: {c.get('chapter_title')}" for c in (ch_script.get("chapters") or [])
                ],
            },
            script_text=" ".join(
                str(b.get("text") or "")
                for c in (ch_script.get("chapters") or [])
                for b in (c.get("narration_blocks") or [])
            ),
        )
        _record_render_history(DIR_WORKSPACE, out_mp4.name, lf_meta)
        exported_list.append({"filename": out_mp4.name, "aspect_ratio": cur_ar, "duration_sec": render_res.get("duration_sec")})
        last_out_mp4 = out_mp4
        last_render_res = render_res

    _update_pipeline(
        step_status=(4, "done", f"{q_label} · {len(exported_list)} MP4 OK"),
        percent=94,
    )
    out_names = ", ".join(x["filename"] for x in exported_list)
    _update_pipeline(
        running=False,
        current_step=5,
        percent=100,
        message=f"Hoàn tất Vlog {q_label} ({len(exported_list)} MP4 · {out_names})!",
        step_status=(5, "done", f"{q_label} · {len(exported_list)} MP4"),
        result={
            "ok": True,
            "output_file": str(last_out_mp4) if last_out_mp4 else "",
            "output_url": f"/files/05_output/{last_out_mp4.name}" if last_out_mp4 else "",
            "exported": exported_list,
            "duration_sec": last_render_res.get("duration_sec", actual_target),
            "aspect_ratio": raw_ar,
            "quality_label": q_label,
            "ai_source": ai_src_lbl,
            "segments_count": n_shots,
            "chapters_count": n_chaps,
            "overlays_count": last_render_res.get("overlays_count", 0),
        },
        log_line=f"[HOÀN TẤT] Xuất Vlog {q_label} ({n_shots} cảnh, {n_chaps} chương): {out_names}",
    )
    return exported_list


def _run_single_project_pipeline(req: OneClickPipelineReq) -> None:
    try:
        if getattr(req, "pipeline_category", "short_tiktok") == "long_vlog" or float(req.target_duration_sec or 0) > 90.0:
            if bool(getattr(req, "longform_random_mode", False)):
                import random as _rnd
                from audio_bgm import ensure_royalty_free_bgm_library

                n_rand = max(1, min(5, int(getattr(req, "longform_random_count", 1) or 1)))
                all_bgms = ensure_royalty_free_bgm_library()
                vlog_bgms = [
                    b["id"]
                    for b in all_bgms
                    if any(tag in b["label"] for tag in ("[Vlog]", "[Du Lịch]", "[Piano]", "[Lo-Fi]", "[Lifestyle]", "[Jazz]", "[Ambient]", "Chill", "Acoustic", "[TikTok]", "Retro", "Future"))
                ] or [b["id"] for b in all_bgms]
                _rnd.shuffle(vlog_bgms)
                angles = [
                    "🕵️ Thám tử điều tra: soi từng chi tiết như tìm manh mối, đặt câu hỏi bí ẩn & kích thích tò mò",
                    "😂 POV Hài hước dí dỏm: bình luận bất ngờ, duyên dáng, tạo tiếng cười tự nhiên",
                    "🎙️ Phóng sự hiện trường kịch tính: nhịp câu dứt khoát, mở đầu gây tò mò như phim tài liệu",
                    "🌿 Kể chuyện nhật ký trải nghiệm chân thực, gần gũi",
                    "🎬 Phong cách điện ảnh sâu lắng & giàu cảm xúc",
                ]
                _rnd.shuffle(angles)
                style_combos = [
                    ("detective_noir", "highlight_bold", "#EF4444"),
                    ("comic_pop", "highlight_bold", "#FACC15"),
                    ("cinema_letterbox", "cinema_box", "#A78BFA"),
                    ("campfire_warm", "warm_vlog_gold", "#F59E0B"),
                    ("adventure_bold", "mint_nature", "#38BDF8"),
                    ("editorial_minimal", "editorial_clean", "#34D399"),
                    ("pastel_soft", "cinema_box", "#FB7185"),
                    ("cinematic_glass", "highlight_bold", "#A78BFA"),
                ]
                vibe_pool = [
                    "detective_mystery", "pov_comedy", "field_report",
                    "cinematic_deep", "outdoor_picnic", "travel_vlog",
                    "daily_story", "food_cafe", "creative_internet",
                ]
                color_pool = ["warm_sunset", "fresh_cool", "natural", "soft_film", "cinema_contrast"]
                jitter_pool = [0.0, 1.8, 3.4, 1.1, 2.6]
                _rnd.shuffle(style_combos)
                _rnd.shuffle(vibe_pool)
                _rnd.shuffle(color_pool)
                all_exported: list[dict[str, Any]] = []
                for v_idx in range(1, n_rand + 1):
                    pick_bgm = vlog_bgms[(v_idx - 1) % len(vlog_bgms)]
                    pick_stk = "normal" if v_idx % 2 == 1 else "rich"
                    pick_style = style_combos[(v_idx - 1) % len(style_combos)]
                    pick_vibe = vibe_pool[(v_idx - 1) % len(vibe_pool)]
                    pick_color = color_pool[(v_idx - 1) % len(color_pool)]
                    pick_jitter = jitter_pool[(v_idx - 1) % len(jitter_pool)]
                    angle_hint = angles[(v_idx - 1) % len(angles)]
                    base_note = str(req.product_note or "").strip()
                    rand_note = f"{base_note}\n[Đạo diễn biến thể #{v_idx}: {angle_hint}]".strip()
                    rand_req = req.model_copy(
                        update={
                            "preserve_longform_script": False,
                            "vlog_title": "",
                            "bgm_track": pick_bgm,
                            "sticker_density": pick_stk,
                            "content_vibe": pick_vibe,
                            "product_note": rand_note,
                        }
                    )
                    _update_pipeline(
                        running=True,
                        log_line=f"🎲 [Random Vlog #{v_idx}/{n_rand}] Vibe={pick_vibe}, Style={pick_style[0]}, Color={pick_color}, BGM={pick_bgm}, Voice={req.voice_preset}",
                    )
                    res_list = _execute_longform_vlog_pipeline(
                        rand_req,
                        variant_tag=f"R{v_idx}",
                        forced_style=pick_style,
                        forced_color_preset=pick_color,
                        shot_jitter_sec=pick_jitter,
                    )
                    all_exported.extend(res_list)
                names_joined = ", ".join(x["filename"] for x in all_exported)
                _update_pipeline(
                    running=False,
                    current_step=5,
                    current_tab="tab6",
                    percent=100,
                    message=f"🎲 Hoàn tất {len(all_exported)} Video Random: {names_joined}",
                    step_status=(5, "done", f"Xong {len(all_exported)} MP4 Random"),
                )
                return
            _execute_longform_vlog_pipeline(req)
            return

        short_ar = str(getattr(req, "aspect_ratio", "9:16") or "9:16").strip()
        if short_ar not in ("9:16", "16:9"):
            short_ar = "9:16"
        with PIPELINE_LOCK:
            for st_item in PIPELINE_STATE.get("steps") or []:
                if st_item.get("id") == 4:
                    st_item["label"] = f"Bước 4: Căn Clip {short_ar} Bám Beat (Tôn Trọng Khóa Clips)"
        # Step 1: Pre-Production - Nạp Style DNA, Brief nhãn hàng & kiểm tra nguyên liệu
        _update_pipeline(
            current_step=1,
            current_tab="tab4",
            percent=10,
            message="Bước 1/5 (Kế Hoạch AI): Nạp Style DNA, Brief nhãn hàng & kiểm tra khung hình video thô...",
            step_status=(1, "running", f"Target {req.target_duration_sec:.0f}s"),
            log_line="[Bước 1/5] Nạp Style DNA, Brief & Kiểm tra video thô...",
        )
        t_level = str(req.transition_level or "balanced")
        effective_camera = (
            "subtle"
            if t_level == "gentle"
            else ("energetic" if t_level == "energetic" else (req.camera_intensity or "dynamic_ai"))
        )
        dna = update_style_dna(
            {
                "badge_style": req.badge_style,
                "transition_level": t_level,
                "render_engine": req.render_engine or "remotion_classic",
                "innovation_preset": req.innovation_preset or "kinetic_pop",
                "camera_intensity": effective_camera,
                "disable_flash_shake": bool(req.disable_flash_shake),
            }
        )
        is_story_mode = str(getattr(req, "short_content_mode", "brand_brief") or "brand_brief").strip() == "story_note"
        brief = save_brand_brief({"target_duration_sec": req.target_duration_sec})
        raw_b = str(brief.get("raw_brief") or "").strip()
        if not is_story_mode and len(raw_b) >= 12 and not brief.get("brief_ai_extracted"):
            try:
                _update_pipeline(
                    message="Bước 1/5 (Kế Hoạch AI): Đang tự động bóc tách Brief thô (Brand, USP, Phiên âm)...",
                    log_line="[Bước 1/5] Tự động bóc tách Brief thô bằng AI...",
                )
                ext = api_extract_brand_brief(
                    BrandBriefExtractReq(raw_brief=raw_b, target_duration_sec=req.target_duration_sec)
                )
                ext_b = ext.get("brief") or {}
                brief = save_brand_brief(
                    {
                        "brand": ext_b.get("brand") or brief.get("brand"),
                        "product_line": ext_b.get("product_line") or brief.get("product_line"),
                        "category": ext_b.get("category") or brief.get("category"),
                        "usps": ext_b.get("usps") or brief.get("usps"),
                        "offer_cta": ext_b.get("offer_cta") or brief.get("offer_cta"),
                        "banned_words": ext_b.get("banned_words") or brief.get("banned_words"),
                        "phonetic_map": ext_b.get("phonetic_map") or brief.get("phonetic_map"),
                        "brief_ai_extracted": True,
                    }
                )
                update_style_dna(
                    {
                        "brand": brief.get("brand"),
                        "product_line": brief.get("product_line"),
                        "category": brief.get("category"),
                    }
                )
            except Exception:
                pass
        raw_videos = list_media_in_dir(DIR_VIDEO_THO)
        if not raw_videos:
            raise RuntimeError("Thư mục 02_video_tho đang trống. Hãy thêm ít nhất 1 video thô trước.")
        import face_privacy as _fp_short
        fp_short_cfg = _fp_short.save_face_privacy_config(ACTIVE_PROJECT_ROOT, _req_face_privacy_dict(req))["config"]
        if fp_short_cfg.get("enabled"):
            _update_pipeline(
                log_line=f"[Che mặt AI] BẬT ({fp_short_cfg['mode']} · kiểu={fp_short_cfg['style']} · đã chọn={len(fp_short_cfg['selected_face_ids'])} mặt).",
            )
        _ensure_raw_frames_extracted(raw_videos)
        _update_pipeline(
            step_status=(
                1,
                "done",
                f"{'Story / Mô tả' if is_story_mode else brief.get('brand')} · {len(raw_videos)} video thô",
            ),
            percent=20,
        )

        # Step 2: Pre-Production - Tự kiểm tra AI Critic & đảm bảo kịch bản đủ thời lượng mục tiêu
        _update_pipeline(
            current_step=2,
            current_tab="tab4",
            percent=28,
            message="Bước 2/5 (Kế Hoạch AI): Tự kiểm tra AI Critic & chốt kịch bản đủ số từ mục tiêu...",
            step_status=(2, "running", f"~{req.target_duration_sec:.0f}s"),
            log_line="[Bước 2/5] Kiểm tra mật độ từ, Auto-Critic & Bộ 3 kịch bản...",
        )
        cur_script_txt = (
            FILE_SCRIPT.read_text(encoding="utf-8-sig").strip() if FILE_SCRIPT.exists() else ""
        )
        cur_word_count = len(re.findall(r"[^\W_]+", cur_script_txt, flags=re.UNICODE))
        _, min_words, _ = compute_target_word_budget(req.target_duration_sec)
        bundle = load_script_options()
        bundle_dur = float(bundle.get("target_duration_sec") or 0.0)
        bundle_mismatch = bundle_dur > 0 and abs(bundle_dur - req.target_duration_sec) > 2.0

        req_vibe = str(getattr(req, "content_vibe", "learned_dna") or "learned_dna").strip()
        req_aspect = str(getattr(req, "aspect_ratio", "9:16") or "9:16").strip()
        if req_aspect not in ("9:16", "16:9"):
            req_aspect = "9:16"
        import style_dna as _sd
        vibe_meta = _sd.get_content_vibe_meta(req_vibe)
        note = req.product_note.strip() if is_story_mode else (req.product_note.strip() or str(brief.get("usps") or ""))
        if vibe_meta.get("is_vlog") and vibe_meta.get("prompt_hint"):
            note = f"{note}\n[Phong cách nội dung: {vibe_meta['prompt_hint']}]".strip()
        vibe_changed = bool(vibe_meta.get("is_vlog") or is_story_mode) and str(bundle.get("content_vibe") or "learned_dna") != (
            "story_note" if is_story_mode and not vibe_meta.get("is_vlog") else req_vibe
        )
        if req.regenerate_script or not cur_script_txt or cur_word_count < min_words or bundle_mismatch or vibe_changed:
            if (vibe_meta.get("is_vlog") or is_story_mode) and not (find_agy_executable() or str(load_config().get("gemini_api_key") or "").strip()):
                bundle = _sd.generate_three_script_options_fallback(
                    brief,
                    target_duration_sec=req.target_duration_sec,
                    product_note=req.product_note.strip(),
                    content_vibe=("daily_story" if is_story_mode and not vibe_meta.get("is_vlog") else req_vibe),
                )
                bundle["content_vibe"] = "story_note" if is_story_mode and not vibe_meta.get("is_vlog") else req_vibe
                _sd.save_script_options(bundle)
            else:
                plan_res = api_workshop_plan_auto(
                    GeminiWorkshopPlanReq(
                        product_note=note,
                        target_duration=req.target_duration_sec,
                        preserve_clips=req.preserve_clips,
                        short_content_mode="story_note" if is_story_mode else "brand_brief",
                    )
                )
                bundle = plan_res.get("script_options") or load_script_options()
                if (vibe_meta.get("is_vlog") or is_story_mode) and bundle:
                    bundle["content_vibe"] = "story_note" if is_story_mode and not vibe_meta.get("is_vlog") else req_vibe
                    _sd.save_script_options(bundle)
            if req.selected_option_id and req.selected_option_id != bundle.get("selected_id"):
                api_workshop_select_script(
                    SelectScriptReq(
                        option_id=req.selected_option_id,
                        preserve_clips=req.preserve_clips,
                        auto_export_mp4=False,
                        badge_style=req.badge_style,
                    )
                )
        elif req.selected_option_id and bundle and req.selected_option_id != bundle.get("selected_id"):
            api_workshop_select_script(
                SelectScriptReq(
                    option_id=req.selected_option_id,
                    preserve_clips=req.preserve_clips,
                    auto_export_mp4=False,
                    badge_style=req.badge_style,
                )
            )
        else:
            disp_file = DIR_WORKSPACE / "kich_ban_hien_thi.md"
            cur_disp = (
                disp_file.read_text(encoding="utf-8-sig").strip()
                if disp_file.exists()
                else restore_display_text(cur_script_txt, brief)
            )
            fixed_disp, fixed_tts, _ = ensure_script_meets_duration(
                cur_disp, cur_script_txt, req.target_duration_sec, brief, 1
            )
            FILE_SCRIPT.write_text(fixed_tts + "\n", encoding="utf-8")
            disp_file.write_text(fixed_disp + "\n", encoding="utf-8")
            if not FILE_CRITIC_REPORT.exists():
                cur_clips = []
                if FILE_EDIT_PLAN.exists():
                    try:
                        cur_clips = json.loads(FILE_EDIT_PLAN.read_text(encoding="utf-8-sig")).get("clips") or []
                    except Exception:
                        cur_clips = []
                critic_md = build_auto_critic_report_md(
                    target_duration_sec=req.target_duration_sec,
                    options=bundle.get("options") or [],
                    auto_fixes=bundle.get("auto_critic_fixes") or [],
                    preserve_clips=req.preserve_clips,
                    clip_count=len(cur_clips),
                )
                FILE_CRITIC_REPORT.write_text(critic_md, encoding="utf-8")

        final_words = len(re.findall(r"[^\W_]+", FILE_SCRIPT.read_text(encoding="utf-8-sig"), flags=re.UNICODE))
        if is_story_mode:
            try:
                save_openreel_hook_md(cta_text="")
            except Exception:
                pass
        _update_pipeline(
            step_status=(2, "done", f"{final_words} từ · Auto-Critic OK"),
            percent=42,
        )

        # Batch mode: run AI Visual Director once when preserve_clips=False so scenes match real frames & speed-ramps
        if req.batch_all_scripts:
            if not req.preserve_clips and (find_agy_executable() or str(load_config().get("gemini_api_key") or "").strip()):
                try:
                    api_openreel_ai_director(
                        OpenReelDirectorReq(
                            product_note=note,
                            apply_trim=False,
                            preserve_clips=False,
                        )
                    )
                except Exception:
                    pass
            batch_bundle = load_script_options()
            batch_opts = (batch_bundle.get("options") or [])[:3]
            if not batch_opts:
                plan_res = api_workshop_plan_auto(
                    GeminiWorkshopPlanReq(
                        product_note=note,
                        target_duration=req.target_duration_sec,
                        preserve_clips=req.preserve_clips,
                        transition_level=req.transition_level,
                        short_content_mode="story_note" if is_story_mode else "brand_brief",
                    )
                )
                batch_bundle = plan_res.get("script_options") or load_script_options()
                batch_opts = (batch_bundle.get("options") or [])[:3]

            rendered_batch: list[dict[str, Any]] = []
            n_total = max(1, len(batch_opts))
            dur_map_raw = {v["rel_path"]: float(v.get("duration_sec") or 10.0) for v in raw_videos if v.get("rel_path")}
            voice_profiles = list_voice_profiles()
            orig_edit_plan_raw = None
            if FILE_EDIT_PLAN.exists():
                try:
                    _ep_txt = FILE_EDIT_PLAN.read_text(encoding="utf-8-sig")
                    if json.loads(_ep_txt).get("clips"):
                        orig_edit_plan_raw = _ep_txt
                except Exception:
                    orig_edit_plan_raw = None
            random_mix_list = (
                generate_random_batch_mix_profiles(
                    n_total,
                    base_engine=req.render_engine or "remotion_classic",
                    mix_engines=bool(req.mix_engines),
                )
                if req.mix_variants
                else []
            )
            wildcard_cache_key = str(load_config().get("gemini_api_key") or "")
            import voice_engine as _ve
            req_voice_preset = str(getattr(req, "voice_preset", "") or "").strip()
            batch_voice_presets: list[dict[str, Any]] = []
            if req_voice_preset.startswith("random_"):
                batch_voice_presets = _ve.pick_random_voice_presets(req_voice_preset, count=max(1, len(batch_opts)))
            elif req_voice_preset:
                resolved_p = _ve.resolve_voice_preset(req_voice_preset)
                batch_voice_presets = [resolved_p for _ in batch_opts]
            used_wc_archetypes: list[str] = []
            used_wc_palettes: list[str] = []
            used_wc_hooks: list[str] = []
            used_wc_subs: list[str] = []
            try:
                for b_idx, b_opt in enumerate(batch_opts, start=1):
                    opt_id = str(b_opt.get("id") or f"opt{b_idx}")
                    opt_title = str(b_opt.get("title") or opt_id)
                    mix_prof = (
                        random_mix_list[b_idx - 1]
                        if req.mix_variants and b_idx - 1 < len(random_mix_list)
                        else {
                            "name": f"Chung Style ({req.visual_theme})",
                            "render_engine": req.render_engine or "remotion_classic",
                            "innovation_preset": req.innovation_preset or "kinetic_pop",
                            "badge_style": req.badge_style,
                            "visual_theme": req.visual_theme,
                            "layout_style": req.layout_style or "full",
                            "color_preset": req.color_preset or "natural",
                            "creative_mode": req.creative_mode or "breakthrough_ai",
                            "camera_intensity": req.camera_intensity or "dynamic_ai",
                            "bgm_track": req.bgm_track or "bgm_upbeat_tiktok.wav",
                            "subtitle_active_color": "#FFE500",
                            "tts_speed": 1.08,
                            "clip_order_mode": "original",
                            "offset_sec": 0.0,
                        }
                    )
                    base_pct = 42 + int(((b_idx - 1) / n_total) * 52)
                    _update_pipeline(
                        current_step=3,
                        current_tab="tab4",
                        percent=base_pct + 4,
                        message=f"[{b_idx}/{n_total} · {mix_prof['name']}] Tạo giọng AI {req.target_duration_sec:.0f}s cho {opt_id}...",
                        step_status=(3, "running", f"{opt_id} ({b_idx}/{n_total})"),
                        log_line=f"[Batch {b_idx}/{n_total}] {opt_title} · {mix_prof['name']}",
                    )
                    api_workshop_select_script(
                        SelectScriptReq(
                            option_id=opt_id,
                            target_duration_sec=req.target_duration_sec,
                            preserve_clips=req.preserve_clips,
                            auto_export_mp4=False,
                            badge_style=mix_prof["badge_style"],
                            visual_theme=mix_prof["visual_theme"],
                            layout_style=mix_prof.get("layout_style", "full"),
                            color_preset=mix_prof.get("color_preset", "natural"),
                            creative_mode=mix_prof["creative_mode"],
                            camera_intensity=mix_prof["camera_intensity"],
                            bgm_track=mix_prof["bgm_track"],
                        )
                    )
                    sync_voice_clone_files()
                    req_tts_engine = str(getattr(req, "tts_engine", "edge_tts") or "edge_tts").strip()
                    req_edge_voice = str(getattr(req, "edge_voice", "vi-VN-HoaiMyNeural") or "vi-VN-HoaiMyNeural").strip()
                    slot_preset = batch_voice_presets[b_idx - 1] if (b_idx - 1) < len(batch_voice_presets) else None
                    if slot_preset:
                        tts_args = [
                            "--script",
                            "04_workspace/kich_ban.txt",
                            "--voice-preset",
                            str(slot_preset["id"]),
                            "--nfe-step",
                            "48",
                            "--whisper-model",
                            "small",
                            "--target-duration",
                            f"{req.target_duration_sec:.2f}",
                        ]
                    else:
                        slot_edge_voice = req_edge_voice
                        slot_edge_rate = "+4%"
                        if req.mix_variants and req_tts_engine == "edge_tts":
                            edge_mix_pool = [
                                ("vi-VN-HoaiMyNeural", "+4%"),
                                ("vi-VN-NamMinhNeural", "+4%"),
                                ("vi-VN-HoaiMyNeural", "+1%"),
                            ]
                            slot_edge_voice, slot_edge_rate = edge_mix_pool[(b_idx - 1) % len(edge_mix_pool)]
                        tts_args = [
                            "--script",
                            "04_workspace/kich_ban.txt",
                            "--tts-engine",
                            req_tts_engine,
                            "--edge-voice",
                            slot_edge_voice,
                            "--edge-rate",
                            slot_edge_rate,
                            "--speed",
                            str(mix_prof["tts_speed"]),
                            "--nfe-step",
                            "48",
                            "--whisper-model",
                            "small",
                            "--target-duration",
                            f"{req.target_duration_sec:.2f}",
                        ]
                    if req.mix_variants and len(voice_profiles) > 1:
                        vp = voice_profiles[(b_idx - 1) % len(voice_profiles)]
                        tts_args.extend(["--ref-audio", vp["wav_path"]])
                        if vp.get("ref_text_path"):
                            tts_args.extend(["--ref-text", vp["ref_text_path"]])
                    if bool(getattr(req, "mute_voice", False)):
                        vb_total = float(req.target_duration_sec)
                    else:
                        tts_res = run_python_script("scripts/voice_engine.py", tts_args)
                        if not tts_res.get("ok"):
                            raise RuntimeError(f"voice_engine.py lỗi ở {opt_id}: {tts_res.get('log', '')[-300:]}")
                        rep = repair_subtitles_and_beats()
                        vb_total = float((rep.get("voice_beats") or {}).get("total_duration_sec") or req.target_duration_sec)

                    _update_pipeline(
                        current_step=4,
                        current_tab="tab4",
                        percent=base_pct + 10,
                        message=f"[{b_idx}/{n_total} · {mix_prof['name']}] Cắt lệch đoạn & Mix Clips 9:16...",
                        step_status=(4, "running", f"{opt_id} ({mix_prof['clip_order_mode']})"),
                    )
                    if req.mix_variants and orig_edit_plan_raw and (
                        mix_prof["clip_order_mode"] != "original" or float(mix_prof.get("offset_sec") or 0.0) > 0.1
                    ):
                        try:
                            base_plan = json.loads(orig_edit_plan_raw)
                            base_clips = base_plan.get("clips") if isinstance(base_plan.get("clips"), list) else []
                            if base_clips:
                                base_plan["clips"] = reorder_clips_for_variant(
                                    base_clips,
                                    mix_prof["clip_order_mode"],
                                    dur_map=dur_map_raw,
                                    offset_sec=float(mix_prof.get("offset_sec") or 0.0),
                                )
                                FILE_EDIT_PLAN.write_text(json.dumps(base_plan, ensure_ascii=False, indent=2), encoding="utf-8")
                        except Exception:
                            pass
                    align_edit_plan_to_voice_beats(
                        raw_videos,
                        preserve_clips=req.preserve_clips,
                        target_duration_override=vb_total,
                        transition_level=req.transition_level,
                    )
                    if not orig_edit_plan_raw and FILE_EDIT_PLAN.exists():
                        orig_edit_plan_raw = FILE_EDIT_PLAN.read_text(encoding="utf-8-sig")
                    clip_res = run_python_script(
                        "scripts/prepare_clips.py", ["--config", "04_workspace/edit_plan.json", "--concat", "--aspect-ratio", req_aspect]
                    )
                    if not clip_res.get("ok"):
                        raise RuntimeError(f"prepare_clips.py lỗi ở {opt_id}: {clip_res.get('log', '')[-300:]}")

                    _update_pipeline(
                        current_step=5,
                        current_tab="tab5",
                        percent=base_pct + 14,
                        message=f"[{b_idx}/{n_total} · {mix_prof['name']}] Remotion đang Render {opt_id}...",
                        step_status=(5, "running", f"{mix_prof['layout_style']} · {mix_prof['visual_theme']}"),
                        log_line=f"[Batch {b_idx}/{n_total}] Render {opt_id} ({mix_prof['layout_style']} + {mix_prof['color_preset']} + {mix_prof['visual_theme']})...",
                    )
                    slot_engine = mix_prof.get("render_engine") or req.render_engine or "remotion_classic"
                    slot_wildcard = (
                        generate_ai_wildcard_style_spec(
                            brief,
                            gemini_api_key=wildcard_cache_key,
                            sticker_density=req.sticker_density or "normal",
                            icon_density=req.icon_density or "balanced",
                            exclude_archetypes=used_wc_archetypes,
                            exclude_palettes=used_wc_palettes,
                            exclude_hook_layouts=used_wc_hooks,
                            exclude_sub_variants=used_wc_subs,
                        )
                        if slot_engine in ("remotion_innovation", "hyperframes")
                        else None
                    )
                    if slot_wildcard:
                        if slot_wildcard.get("layoutArchetype"):
                            used_wc_archetypes.append(str(slot_wildcard["layoutArchetype"]))
                        if slot_wildcard.get("bgGradient"):
                            used_wc_palettes.append(str(slot_wildcard["bgGradient"]))
                        if slot_wildcard.get("hookLayout"):
                            used_wc_hooks.append(str(slot_wildcard["hookLayout"]))
                        if slot_wildcard.get("subtitleVariant"):
                            used_wc_subs.append(str(slot_wildcard["subtitleVariant"]))
                        _update_pipeline(log_line=f"✨ [Out-of-Box {b_idx}/{n_total}] {slot_wildcard.get('styleName')} ({slot_engine})")
                    slot_cam = (
                        mix_prof["camera_intensity"]
                        if req.mix_variants
                        else ("subtle" if t_level == "gentle" else ("energetic" if t_level == "energetic" else mix_prof["camera_intensity"]))
                    )
                    build_remotion_props(
                        {
                            "hook_text": str(b_opt.get("hook_badge") or "").strip(),
                            "badge_style": mix_prof["badge_style"],
                            "visual_theme": mix_prof["visual_theme"],
                            "layout_style": mix_prof.get("layout_style", "full"),
                            "color_preset": mix_prof.get("color_preset", "natural"),
                            "creative_mode": mix_prof["creative_mode"],
                            "camera_intensity": slot_cam,
                            "font_heading": mix_prof.get("font_heading"),
                            "overlay_effect": mix_prof.get("overlay_effect"),
                            "hook_y": mix_prof.get("hook_y"),
                            "subtitle_y": mix_prof.get("subtitle_y"),
                            "bgm_track": mix_prof["bgm_track"],
                            "subtitle_active_color": mix_prof["subtitle_active_color"],
                            "render_engine": slot_engine,
                            "innovation_preset": mix_prof.get("innovation_preset") or req.innovation_preset or "kinetic_pop",
                            "transition_level": req.transition_level or "balanced",
                            "disable_flash_shake": bool(req.disable_flash_shake),
                            "icon_density": req.icon_density or "balanced",
                            "sticker_density": req.sticker_density or "normal",
                            "sfx_level": getattr(req, "sfx_level", "subtle") or "subtle",
                            "aspect_ratio": req_aspect,
                            "content_vibe": req_vibe,
                            "disclaimer_text": _resolve_effective_disclaimer(req, req_vibe, is_random_variant=False),
                            "subtitle_lang": str(getattr(req, "subtitle_lang", "vi") or "vi"),
                            "mute_voice": bool(getattr(req, "mute_voice", False)),
                            "hide_subtitles": bool(getattr(req, "hide_subtitles", False)),
                            **({"wildcard_spec": slot_wildcard} if slot_wildcard else {}),
                        }
                    )
                    r_res = _render_by_engine(slot_engine)
                    b_out_name = str(r_res.get("output_filename") or "")
                    b_meta = _attach_output_assets(
                        ACTIVE_PROJECT_ROOT,
                        DIR_OUTPUT / b_out_name,
                        {
                            "mode": "short_story" if is_story_mode else "short_batch",
                            "engine": slot_engine,
                            "aspect_ratio": req_aspect,
                            "duration_sec": r_res.get("duration_sec"),
                            "voice_preset": "muted" if bool(getattr(req, "mute_voice", False)) else str(slot_preset["id"] if slot_preset else req.voice_preset),
                            "bgm_track": mix_prof.get("bgm_track"),
                            "title": opt_title,
                            "visual_theme": mix_prof.get("visual_theme"),
                            "badge_style": mix_prof.get("badge_style"),
                            "sticker_density": req.sticker_density or "normal",
                            "mute_voice": bool(getattr(req, "mute_voice", False)),
                            "hide_subtitles": bool(getattr(req, "hide_subtitles", False)),
                            "product_note": str(req.product_note or "")[:240],
                        },
                        script_text=str(b_opt.get("script_display") or b_opt.get("script_text") or ""),
                        brand_brief=None if is_story_mode else brief,
                    )
                    _record_render_history(DIR_WORKSPACE, b_out_name, b_meta)
                    rendered_batch.append(
                        {
                            "option_id": opt_id,
                            "mix_profile": mix_prof["name"],
                            "output_filename": r_res.get("output_filename"),
                            "duration_sec": r_res.get("duration_sec"),
                        }
                    )
            finally:
                if req.preserve_clips and orig_edit_plan_raw and req.mix_variants:
                    FILE_EDIT_PLAN.write_text(orig_edit_plan_raw, encoding="utf-8")

            names_str = ", ".join(str(x.get("output_filename") or "") for x in rendered_batch)
            frames = _collect_remotion_preview_frames()
            _update_pipeline(
                running=False,
                current_step=5,
                current_tab="tab5",
                percent=100,
                message=f"Hoàn tất Batch {len(rendered_batch)} kịch bản! Đã xuất: {names_str}",
                step_status=(3, "done", f"Xong {len(rendered_batch)} giọng AI"),
                log_line=f"[HOÀN TẤT BATCH x{len(rendered_batch)}] {names_str}",
                result={"batch": rendered_batch, "preview_frames": frames, "style_dna": dna},
            )
            _update_pipeline(step_status=(4, "done", "10 clip 9:16 (Cache Hit)"))
            _update_pipeline(step_status=(5, "done", f"Đã xuất {len(rendered_batch)} MP4"))
            return

        # Step 3: Thực Thi - Tạo Giọng AI chuẩn Thời Lượng & Phụ đề Karaoke sạch
        _update_pipeline(
            current_step=3,
            current_tab="tab4",
            percent=50,
            message=f"Bước 3/5 (Thực Thi Giọng): Đang chạy F5-TTS hiệu chỉnh đúng {req.target_duration_sec:.0f}s & làm sạch SRT...",
            step_status=(3, "running", f"F5-TTS -> {req.target_duration_sec:.0f}s"),
            log_line=f"[Bước 3/5] Tạo giọng đọc chuẩn {req.target_duration_sec:.0f}s & đồng bộ phụ đề...",
        )
        if bool(getattr(req, "mute_voice", False)):
            vb_total = float(req.target_duration_sec)
            _update_pipeline(
                step_status=(3, "done", "Đã tắt giọng đọc (Story)"),
                percent=65,
                log_line="[Bước 3/5] Đang bật Ẩn giọng đọc AI — bỏ qua tổng hợp giọng.",
            )
        else:
            existing_wav_dur = probe_media(FILE_TTS_WAV).get("duration_sec", 0.0) if FILE_TTS_WAV.exists() else 0.0
            duration_mismatch = abs(existing_wav_dur - req.target_duration_sec) > 1.8
            script_newer = (
                FILE_SCRIPT.exists()
                and FILE_TTS_WAV.exists()
                and FILE_SCRIPT.stat().st_mtime > FILE_TTS_WAV.stat().st_mtime + 1.0
            )
            if req.force_tts or not FILE_TTS_WAV.exists() or not FILE_VOICE_BEATS.exists() or script_newer or duration_mismatch:
                sync_voice_clone_files()
                import voice_engine as _ve
                single_vp = str(getattr(req, "voice_preset", "") or "").strip()
                if single_vp.startswith("random_"):
                    single_vp = _ve.pick_random_voice_presets(single_vp, count=1)[0]["id"]
                if single_vp:
                    single_tts_args = [
                        "--script",
                        "04_workspace/kich_ban.txt",
                        "--voice-preset",
                        single_vp,
                        "--nfe-step",
                        "48",
                        "--whisper-model",
                        "small",
                        "--target-duration",
                        f"{req.target_duration_sec:.2f}",
                    ]
                else:
                    single_tts_args = [
                        "--script",
                        "04_workspace/kich_ban.txt",
                        "--tts-engine",
                        str(getattr(req, "tts_engine", "edge_tts") or "edge_tts"),
                        "--edge-voice",
                        str(getattr(req, "edge_voice", "vi-VN-HoaiMyNeural") or "vi-VN-HoaiMyNeural"),
                        "--speed",
                        "1.04",
                        "--nfe-step",
                        "48",
                        "--whisper-model",
                        "small",
                        "--target-duration",
                        f"{req.target_duration_sec:.2f}",
                    ]
                tts_res = run_python_script(
                    "scripts/voice_engine.py",
                    single_tts_args,
                )
                if not tts_res.get("ok"):
                    raise RuntimeError(f"voice_engine.py lỗi: {tts_res.get('log', '')[-400:]}")
            rep = repair_subtitles_and_beats()
            vb_total = float((rep.get("voice_beats") or {}).get("total_duration_sec") or 0.0)
            _update_pipeline(
                step_status=(3, "done", f"Voice {vb_total:.2f}s · {rep.get('words_count', 0)} từ sạch"),
                percent=65,
            )

        # Step 4: Thực Thi - Khớp & Cắt Clip 9:16 bám Beat (tôn trọng Khóa Clips)
        _update_pipeline(
            current_step=4,
            current_tab="tab4",
            percent=72,
            message="Bước 4/5 (Thực Thi Hình Ảnh): Đang khớp & cắt Clip 9:16 bám sát từng Beat...",
            step_status=(4, "running", "Khóa Clips: BẬT" if req.preserve_clips else "AI Trim Mới"),
            log_line="[Bước 4/5] Khớp cảnh cắt với voice_beats.json & chạy prepare_clips.py...",
        )
        cfg = load_config()
        if (not req.preserve_clips or not FILE_EDIT_PLAN.exists()) and (
            req.regenerate_script or not FILE_DIRECTOR_PLAN.exists()
        ) and (find_agy_executable() or str(cfg.get("gemini_api_key") or "").strip()):
            try:
                api_openreel_ai_director(
                    OpenReelDirectorReq(
                        product_note=note,
                        apply_trim=False,
                        preserve_clips=req.preserve_clips,
                    )
                )
            except Exception as exc:
                _update_pipeline(log_line=f"[Cảnh báo AI Director] Dùng align beat chuẩn: {exc}")

        aligned = align_edit_plan_to_voice_beats(
            raw_videos,
            preserve_clips=req.preserve_clips,
            target_duration_override=vb_total or req.target_duration_sec,
        )
        clip_res = run_python_script(
            "scripts/prepare_clips.py", ["--config", "04_workspace/edit_plan.json", "--concat", "--aspect-ratio", req_aspect]
        )
        if not clip_res.get("ok"):
            raise RuntimeError(f"prepare_clips.py lỗi: {clip_res.get('log', '')[-400:]}")
        _update_pipeline(
            step_status=(4, "done", f"{len(aligned.get('clips') or [])} clip 9:16 ({'Giữ Clips' if req.preserve_clips else 'Cắt mới'})"),
            percent=82,
        )

        # Step 5: Tab 5 - Remotion Render MP4
        _update_pipeline(
            current_step=5,
            current_tab="tab5",
            percent=88,
            message="Bước 5/5 (Tab 5): Remotion đang Render 1080×1920 + Hoa Lá + Callout + Karaoke + Audio...",
            step_status=(5, "running", "Remotion Headless"),
            log_line="[Bước 5/5] Render Remotion MP4...",
        )
        single_engine = req.render_engine or "remotion_classic"
        single_wildcard = (
            generate_ai_wildcard_style_spec(
                brief,
                gemini_api_key=str(load_config().get("gemini_api_key") or ""),
                sticker_density=req.sticker_density or "normal",
                icon_density=req.icon_density or "balanced",
            )
            if single_engine in ("remotion_innovation", "hyperframes")
            else None
        )
        build_remotion_props(
            {
                "badge_style": req.badge_style,
                "visual_theme": req.visual_theme or "auto",
                "layout_style": req.layout_style or "full",
                "color_preset": req.color_preset or "natural",
                "creative_mode": req.creative_mode or "breakthrough_ai",
                "camera_intensity": effective_camera,
                "bgm_track": req.bgm_track or "bgm_upbeat_tiktok.wav",
                "render_engine": single_engine,
                "innovation_preset": req.innovation_preset or "kinetic_pop",
                "transition_level": req.transition_level or "balanced",
                "disable_flash_shake": bool(req.disable_flash_shake),
                "icon_density": req.icon_density or "balanced",
                "sticker_density": req.sticker_density or "normal",
                "sfx_level": getattr(req, "sfx_level", "subtle") or "subtle",
                "aspect_ratio": req_aspect,
                "content_vibe": req_vibe,
                "disclaimer_text": _resolve_effective_disclaimer(req, req_vibe, is_random_variant=False),
                "subtitle_lang": str(getattr(req, "subtitle_lang", "vi") or "vi"),
                "mute_voice": bool(getattr(req, "mute_voice", False)),
                "hide_subtitles": bool(getattr(req, "hide_subtitles", False)),
                **({"wildcard_spec": single_wildcard} if single_wildcard else {}),
            }
        )
        render_res = _render_by_engine(req.render_engine or "remotion_classic")
        out_fname = str(render_res.get("output_filename") or "final_tiktok.mp4")
        sel_meta = render_res.get("selected_script") or {}
        s_meta = _attach_output_assets(
            ACTIVE_PROJECT_ROOT,
            DIR_OUTPUT / out_fname,
            {
                "mode": "short_story" if is_story_mode else "short_tiktok",
                "engine": single_engine,
                "aspect_ratio": req_aspect,
                "duration_sec": render_res.get("duration_sec"),
                "voice_preset": "muted" if bool(getattr(req, "mute_voice", False)) else str(getattr(req, "voice_preset", "") or "random_neural"),
                "bgm_track": req.bgm_track or "bgm_upbeat_tiktok.wav",
                "title": str(sel_meta.get("label") or ""),
                "visual_theme": req.visual_theme or "auto",
                "badge_style": req.badge_style,
                "sticker_density": req.sticker_density or "normal",
                "mute_voice": bool(getattr(req, "mute_voice", False)),
                "hide_subtitles": bool(getattr(req, "hide_subtitles", False)),
                "product_note": str(req.product_note or "")[:240],
            },
            script_text=(FILE_SCRIPT.read_text(encoding="utf-8-sig") if FILE_SCRIPT.exists() else ""),
            brand_brief=None if is_story_mode else brief,
        )
        _record_render_history(DIR_WORKSPACE, out_fname, s_meta)
        frames = _collect_remotion_preview_frames()
        _update_pipeline(
            running=False,
            current_step=5,
            current_tab="tab5",
            percent=100,
            message=f"Hoàn tất! {sel_meta.get('label', 'Video')} -> {out_fname} ({render_res.get('duration_sec', 0)}s).",
            step_status=(5, "done", f"{out_fname} ({render_res.get('duration_sec', 0)}s)"),
            log_line=f"[HOÀN TẤT] Xuất thành công 05_output/{out_fname}",
            result={"render": render_res, "preview_frames": frames, "style_dna": dna},
        )
    except Exception as exc:
        cur_step = PIPELINE_STATE.get("current_step") or 1
        _update_pipeline(
            running=False,
            error=str(exc),
            message=f"Lỗi ở bước {cur_step}: {exc}",
            step_status=(int(cur_step), "error", str(exc)[:120]),
            log_line=f"[LỖI] {exc}",
        )


def _req_for_project(req: OneClickPipelineReq, pid: str, multi_projects: bool) -> OneClickPipelineReq:
    cfgs = getattr(req, "project_configs", None) or {}
    is_long = getattr(req, "pipeline_category", "short_tiktok") == "long_vlog" or float(req.target_duration_sec or 0) > 90.0
    if isinstance(cfgs.get(pid), dict):
        pc = cfgs[pid]
        upd: dict[str, Any] = {}
        if isinstance(pc.get("ordered_clips"), list):
            upd["ordered_clips"] = [str(x) for x in pc["ordered_clips"] if str(x).strip()]
        str_fields = (
            "vlog_title", "product_note", "quality_preset", "aspect_ratio", "content_vibe", "pacing_preset",
            "short_content_mode", "voice_preset", "tts_engine", "edge_voice", "bgm_track", "sticker_density", "sticker_style",
            "render_engine", "innovation_preset", "sfx_level", "transition_level",
            "icon_density", "visual_theme", "subtitle_lang", "disclaimer_text", "face_blur_mode", "face_blur_style", "face_blur_icon",
        )
        for sf_k in str_fields:
            if sf_k in pc and pc[sf_k] is not None:
                upd[sf_k] = str(pc[sf_k]).strip()
        bool_fields = (
            "auto_fit_duration", "keep_clip_audio", "preserve_longform_script",
            "longform_random_mode", "mute_voice", "hide_subtitles", "enable_motion_zoom", "disable_vibe_filter",
            "disclaimer_enabled",
            "batch_all_scripts", "mix_variants", "mix_engines",
            "preserve_clips", "regenerate_script", "force_tts", "disable_flash_shake",
            "face_blur_enabled",
        )
        for bf_k in bool_fields:
            if bf_k in pc:
                upd[bf_k] = bool(pc[bf_k])
        if "face_blur_padding" in pc and pc["face_blur_padding"] is not None:
            upd["face_blur_padding"] = float(pc["face_blur_padding"])
        if isinstance(pc.get("face_blur_ids"), list):
            upd["face_blur_ids"] = [str(x) for x in pc["face_blur_ids"] if str(x).strip()]
        if "target_duration_sec" in pc and pc["target_duration_sec"]:
            upd["target_duration_sec"] = float(pc["target_duration_sec"])
        if "longform_random_count" in pc and pc["longform_random_count"]:
            upd["longform_random_count"] = max(1, min(5, int(pc["longform_random_count"])))
        if upd:
            return req.model_copy(update=upd)
    if multi_projects and is_long:
        return req.model_copy(update={"ordered_clips": []})
    return req


def _run_pipeline_worker(req: OneClickPipelineReq) -> None:
    target_pids = [str(p).strip() for p in (req.project_ids or []) if str(p).strip()] or [ACTIVE_PROJECT_ID]
    if len(target_pids) <= 1:
        if target_pids[0] != ACTIVE_PROJECT_ID:
            pm_set_active_project(target_pids[0])
            refresh_app_project_paths()
        _run_single_project_pipeline(_req_for_project(req, target_pids[0], False))
        return

    batch_summary: list[dict[str, Any]] = []
    n_proj = len(target_pids)
    for p_idx, pid in enumerate(target_pids, start=1):
        try:
            pm_set_active_project(pid)
            refresh_app_project_paths()
            _update_pipeline(
                running=True,
                error=None,
                current_step=1,
                percent=max(5, int(((p_idx - 1) / n_proj) * 100)),
                message=f"[Project {p_idx}/{n_proj}: {pid}] Đang xử lý tuần tự...",
                log_line=f"=== [Project {p_idx}/{n_proj}] Bắt đầu xử lý `{pid}` ===",
            )
            _run_single_project_pipeline(_req_for_project(req, pid, True))
            err = PIPELINE_STATE.get("error")
            batch_summary.append({"project_id": pid, "ok": not bool(err), "error": err or ""})
        except Exception as exc:
            batch_summary.append({"project_id": pid, "ok": False, "error": str(exc)})
            _update_pipeline(log_line=f"[Project {p_idx}/{n_proj} · {pid} LỖI] {exc}")

    ok_cnt = sum(1 for x in batch_summary if x["ok"])
    fail_list = [x["project_id"] for x in batch_summary if not x["ok"]]
    summary_msg = f"Hoàn tất hàng đợi {ok_cnt}/{n_proj} Project" + (f" (Lỗi: {', '.join(fail_list)})" if fail_list else " thành công!")
    _update_pipeline(
        running=False,
        error=None if ok_cnt > 0 else "Tất cả Project đều lỗi",
        current_step=5,
        current_tab="tab5",
        percent=100,
        message=summary_msg,
        log_line=f"[HOÀN TẤT HÀNG ĐỢI] {summary_msg}",
        result={"multi_project": batch_summary},
    )


class GlobalBannedWordsReq(BaseModel):
    words: Any = ""
    reset_default: bool = False


@app.get("/api/banned-words")
def api_get_global_banned_words():
    words = load_global_banned_words()
    return {"ok": True, "words": words, "count": len(words)}


@app.post("/api/banned-words")
def api_save_global_banned_words(req: GlobalBannedWordsReq):
    words = save_global_banned_words(req.words, reset_default=req.reset_default)
    return {"ok": True, "words": words, "count": len(words)}


@app.post("/api/pipeline/run-all")
def api_pipeline_run_all(req: OneClickPipelineReq):
    target_pids = [str(p).strip() for p in (req.project_ids or []) if str(p).strip()]
    is_long_mode = getattr(req, "pipeline_category", "short_tiktok") == "long_vlog" or float(req.target_duration_sec or 0) > 90.0
    if target_pids:
        all_projs = {p["id"]: p for p in pm_list_projects().get("projects", [])}
        if is_long_mode:
            not_ready = [pid for pid in target_pids if pid not in all_projs or int(all_projs[pid].get("raw_video_count") or 0) <= 0]
            if not_ready:
                raise HTTPException(
                    status_code=400,
                    detail=f"Các Project chưa có video thô trong 02_video_tho/: {', '.join(not_ready)}",
                )
        else:
            cfgs = getattr(req, "project_configs", None) or {}
            base_scm = str(getattr(req, "short_content_mode", "brand_brief") or "brand_brief").strip()
            not_ready = []
            for pid in target_pids:
                p_obj = all_projs.get(pid)
                if not p_obj:
                    not_ready.append(pid)
                    continue
                p_scm = str((cfgs.get(pid) or {}).get("short_content_mode") or base_scm).strip()
                if p_scm == "story_note":
                    if int(p_obj.get("raw_video_count") or 0) <= 0:
                        not_ready.append(pid)
                elif not p_obj.get("ready"):
                    not_ready.append(pid)
            if not_ready:
                raise HTTPException(
                    status_code=400,
                    detail=f"Các Project chưa đủ điều kiện (Video thô / Brief Nhãn Hàng): {', '.join(not_ready)}",
                )
    elif not is_long_mode and str(getattr(req, "short_content_mode", "brand_brief") or "brand_brief").strip() != "story_note":
        brief_ready, brief_reason = is_brand_brief_ready()
        if not brief_ready:
            raise HTTPException(status_code=400, detail=brief_reason)
    with PIPELINE_LOCK:
        if PIPELINE_STATE["running"]:
            raise HTTPException(status_code=409, detail="Pipeline 1-Click đang chạy, vui lòng chờ hoàn tất.")
    _reset_pipeline_state()
    if req.sync:
        _run_pipeline_worker(req)
    else:
        t = threading.Thread(target=_run_pipeline_worker, args=(req,), daemon=True)
        t.start()
    return api_pipeline_status()


@app.get("/api/pipeline/status")
def api_pipeline_status():
    with PIPELINE_LOCK:
        return json.loads(json.dumps(PIPELINE_STATE))


# ==============================================================================
# CHANNEL IDENTITY · LAN / CLOUDFLARE TUNNEL · IPHONE DOWNLOAD & LOG SILENCER
# ==============================================================================

FILE_CHANNEL_PROFILE = PROJECT_ROOT / "channel_profile.json"
DEFAULT_CHANNEL_SUBTITLE = "Zero-Copy Local Studio · F5-TTS Vietnamese · Faster-Whisper"


def _make_avatar_text(name: str) -> str:
    words = [w for w in re.split(r"\s+", (name or "").strip()) if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    if len(words) == 1:
        clean = re.sub(r"[^A-Za-zÀ-ỹ0-9]", "", words[0])
        return (clean[:2] or "OR").upper()
    return "OR"


def _resolve_server_port(request: Request) -> int:
    env_p = os.environ.get("PORT")
    if env_p and str(env_p).isdigit():
        return int(env_p)
    host_hdr = request.headers.get("host") or ""
    if ":" in host_hdr and not host_hdr.endswith(".trycloudflare.com"):
        maybe_port = host_hdr.rsplit(":", 1)[-1]
        if maybe_port.isdigit():
            return int(maybe_port)
    if request.url.port and request.url.port not in (80, 443):
        return int(request.url.port)
    return int(tunnel_service.active_port or 8000)


@app.on_event("startup")
async def _install_win_socket_silencer() -> None:
    try:
        loop = asyncio.get_running_loop()
        orig_handler = loop.get_exception_handler()

        def _quiet_win_reset(cur_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
            exc = context.get("exception")
            msg = str(context.get("message") or "")
            if isinstance(exc, ConnectionResetError) and (getattr(exc, "winerror", None) == 10054 or "_call_connection_lost" in msg or "Proactor" in str(context.get("handle", ""))):
                return
            if orig_handler is not None:
                orig_handler(cur_loop, context)
            else:
                cur_loop.default_exception_handler(context)

        loop.set_exception_handler(_quiet_win_reset)
    except Exception:
        pass


@app.get("/favicon.ico")
def api_favicon():
    return Response(status_code=204)


class ChannelProfileReq(BaseModel):
    channel_name: str = ""
    channel_subtitle: str = ""
    avatar_text: str = ""
    accent_color: str = "from-indigo-500 to-rose-500"


@app.get("/api/system/channel-profile")
def api_get_channel_profile():
    data: dict[str, Any] = {}
    if FILE_CHANNEL_PROFILE.exists():
        try:
            loaded = json.loads(FILE_CHANNEL_PROFILE.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
    name = str(data.get("channel_name") or "").strip()
    subtitle = str(data.get("channel_subtitle") or DEFAULT_CHANNEL_SUBTITLE).strip() or DEFAULT_CHANNEL_SUBTITLE
    avatar = str(data.get("avatar_text") or "").strip().upper() or _make_avatar_text(name)
    accent = str(data.get("accent_color") or "from-indigo-500 to-rose-500").strip()
    return {
        "ok": True,
        "configured": bool(name),
        "channel_name": name,
        "channel_subtitle": subtitle,
        "avatar_text": avatar,
        "accent_color": accent,
    }


@app.post("/api/system/channel-profile")
def api_save_channel_profile(req: ChannelProfileReq):
    name = (req.channel_name or "").strip()[:60]
    if not name:
        raise HTTPException(status_code=400, detail="Vui lòng nhập Tên Kênh TikTok.")
    subtitle = (req.channel_subtitle or "").strip()[:110] or DEFAULT_CHANNEL_SUBTITLE
    avatar = (req.avatar_text or "").strip().upper()[:3] or _make_avatar_text(name)
    allowed_accents = {
        "from-indigo-500 to-rose-500",
        "from-emerald-500 to-teal-500",
        "from-amber-500 to-rose-500",
        "from-purple-500 to-pink-500",
        "from-cyan-500 to-blue-600",
    }
    accent = req.accent_color if req.accent_color in allowed_accents else "from-indigo-500 to-rose-500"
    payload = {
        "channel_name": name,
        "channel_subtitle": subtitle,
        "avatar_text": avatar,
        "accent_color": accent,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    FILE_CHANNEL_PROFILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "configured": True, **payload}


@app.get("/api/system/network-status")
def api_network_status(request: Request):
    port = _resolve_server_port(request)
    status = tunnel_service.get_status(port=port)
    status["channel"] = api_get_channel_profile()
    return {"ok": True, **status}


@app.post("/api/system/tunnel/start")
def api_tunnel_start(request: Request):
    port = _resolve_server_port(request)
    res = tunnel_service.start_tunnel(port=port)
    status = tunnel_service.get_status(port=port)
    return {**res, "status_info": status}


@app.post("/api/system/tunnel/stop")
def api_tunnel_stop(request: Request):
    port = _resolve_server_port(request)
    res = tunnel_service.stop_tunnel()
    status = tunnel_service.get_status(port=port)
    return {**res, "status_info": status}


def _git_output(args: list[str], timeout: int = 15) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    except Exception as exc:
        return 1, str(exc)


def _current_boot_commit() -> str:
    rc, out = _git_output(["rev-parse", "--short", "HEAD"], timeout=8)
    return out.splitlines()[0].strip() if rc == 0 and out else ""


BOOT_GIT_COMMIT = _current_boot_commit()


@app.get("/api/system/check-update")
def api_system_check_update():
    if not shutil.which("git"):
        return {"ok": False, "has_update": False, "message": "Chưa cài Git trong PATH."}
    if not (PROJECT_ROOT / ".git").exists():
        return {"ok": True, "has_update": True, "current_commit": "", "remote_commit": "", "boot_commit": BOOT_GIT_COMMIT, "needs_restart": False, "behind_count": 1, "message": "Thư mục ZIP chưa gắn Git — bấm Update để đồng bộ bản mới."}
    rc_f, out_f = _git_output(["fetch", "origin", "main", "--prune"], timeout=20)
    if rc_f != 0:
        return {"ok": False, "has_update": False, "message": f"Không kiểm tra được GitHub: {out_f[:160]}"}
    rc_h, cur_h = _git_output(["rev-parse", "--short", "HEAD"])
    rc_r, rem_h = _git_output(["rev-parse", "--short", "origin/main"])
    cur_commit = cur_h.splitlines()[0].strip() if rc_h == 0 and cur_h else ""
    rem_commit = rem_h.splitlines()[0].strip() if rc_r == 0 and rem_h else ""
    behind = 0
    if cur_commit and rem_commit and cur_commit != rem_commit:
        rc_b, cnt_s = _git_output(["rev-list", "--count", "HEAD..origin/main"])
        if rc_b == 0 and cnt_s.strip().isdigit():
            behind = int(cnt_s.strip())
    elif not cur_commit and rem_commit:
        behind = 1
    needs_restart = bool(BOOT_GIT_COMMIT and cur_commit and BOOT_GIT_COMMIT != cur_commit)
    has_upd = bool((rem_commit and (not cur_commit or cur_commit != rem_commit)) or needs_restart)
    return {
        "ok": True,
        "has_update": has_upd,
        "current_commit": cur_commit,
        "remote_commit": rem_commit,
        "boot_commit": BOOT_GIT_COMMIT,
        "needs_restart": needs_restart,
        "behind_count": behind,
    }


@app.post("/api/system/update")
def api_system_update(request: Request):
    with PIPELINE_LOCK:
        if PIPELINE_STATE.get("running"):
            raise HTTPException(
                status_code=409,
                detail="Đang có tiến trình dựng video chạy dở. Vui lòng chờ xong rồi mới cập nhật App!",
            )

    updater_ps1 = PROJECT_ROOT / "scripts" / "updater.ps1"
    if not updater_ps1.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy scripts/updater.ps1.")

    port = _resolve_server_port(request)
    _, old_h = _git_output(["rev-parse", "--short", "HEAD"])
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(updater_ps1)],
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "OPENREEL_WEB_UPDATER": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=240,
    )
    full_log = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Cập nhật thất bại:\n{full_log[-800:]}")

    _, new_h = _git_output(["rev-parse", "--short", "HEAD"])

    def _restart_later() -> None:
        time.sleep(0.9)
        if os.environ.get("OPENREEL_SUPERVISOR") != "24_7":
            py_exe = sys.executable
            if os.name == "nt":
                flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
                cmd_str = (
                    f"title TikTok OpenReel AI - Server && ping -n 4 127.0.0.1 >nul && "
                    f"03_voice_clone\\venv\\Scripts\\python.exe -m uvicorn scripts.webapp.app:app --host 0.0.0.0 --port {int(port)}"
                )
                subprocess.Popen(
                    f'cmd.exe /k "{cmd_str}"',
                    cwd=str(PROJECT_ROOT),
                    creationflags=flags,
                    close_fds=True,
                )
            else:
                subprocess.Popen(
                    ["sh", "-c", f'sleep 2 && "{py_exe}" -m uvicorn scripts.webapp.app:app --host 0.0.0.0 --port {int(port)}'],
                    cwd=str(PROJECT_ROOT),
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        os._exit(0)

    threading.Thread(target=_restart_later, daemon=True).start()
    return {
        "ok": True,
        "restarting": True,
        "old_commit": old_h.splitlines()[0].strip() if old_h else "",
        "new_commit": new_h.splitlines()[0].strip() if new_h else "",
        "log": full_log[-1500:],
    }


@app.get("/api/files/download")
def api_download_file(
    path: str = Query(..., description="Relative path or /files/... URL"),
    project_id: str = Query("", description="Optional project ID"),
):
    raw = unquote(str(path or "")).strip().lstrip("/")
    if raw.startswith("files/"):
        raw = raw[len("files/"):]
    if not raw or ".." in Path(raw).parts:
        raise HTTPException(status_code=400, detail="Đường dẫn không hợp lệ.")
    pid_clean = str(project_id or "").strip()
    active_proj = (get_project_root(pid_clean) if pid_clean else get_project_root()).resolve()
    candidates = [
        (active_proj / raw).resolve(),
        (PROJECT_ROOT / raw).resolve(),
    ]
    resolved: Path | None = None
    for cand in candidates:
        if (cand.is_relative_to(active_proj) or cand.is_relative_to(PROJECT_ROOT.resolve())) and cand.exists() and cand.is_file():
            resolved = cand
            break
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file: {raw}")
    safe_name = resolved.name.replace('"', "")
    return FileResponse(
        path=str(resolved),
        media_type="application/octet-stream",
        filename=safe_name,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


REVIEW_360_LOCK = threading.Lock()
REVIEW_360_JOBS: dict[str, dict[str, Any]] = {}


def _review_360_path(p_root: Path, src_name: str) -> Path:
    stem = Path(src_name).stem
    return p_root / "05_output" / "_review_360p" / f"{stem}_360p.mp4"


def _run_review_360_transcode(job_key: str, src_path: Path, dest_path: Path) -> None:
    tmp_path = dest_path.with_name(f".tmp_{dest_path.name}")
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_bin = find_binary("ffmpeg") or "ffmpeg"
        vf = "scale='if(gte(iw,ih),-2,360)':'if(gte(iw,ih),360,-2)'"
        cmds = [
            [
                ffmpeg_bin, "-y", "-i", str(src_path), "-vf", vf,
                "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "27",
                "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(tmp_path),
            ],
            [
                ffmpeg_bin, "-y", "-i", str(src_path), "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "27",
                "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(tmp_path),
            ],
        ]
        ok = False
        last_err = ""
        for cmd in cmds:
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
                if proc.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 1024:
                    ok = True
                    break
                last_err = (proc.stderr or "")[-300:]
            except Exception as exc:
                last_err = str(exc)
        if not ok:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            with REVIEW_360_LOCK:
                REVIEW_360_JOBS[job_key] = {"status": "error", "error": last_err or "FFmpeg 360p failed"}
            return
        tmp_path.replace(dest_path)
        with REVIEW_360_LOCK:
            REVIEW_360_JOBS[job_key] = {"status": "ready", "error": ""}
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        with REVIEW_360_LOCK:
            REVIEW_360_JOBS[job_key] = {"status": "error", "error": str(exc)}


@app.get("/api/projects/outputs")
def api_list_project_outputs(project_id: str = Query("all")):
    proj_bundle = pm_list_projects()
    all_projs = proj_bundle.get("projects") or []
    active_id = proj_bundle.get("active_id") or ""
    target_pid = str(project_id or "all").strip()
    outputs: list[dict[str, Any]] = []
    with REVIEW_360_LOCK:
        jobs_snap = dict(REVIEW_360_JOBS)
    for pr in all_projs:
        pid = str(pr.get("id") or "")
        if not pid or (target_pid != "all" and pid != target_pid):
            continue
        p_root = get_project_root(pid)
        out_dir = p_root / "05_output"
        if not out_dir.exists():
            continue
        mp4s = sorted(
            [p for p in out_dir.glob("*.mp4") if p.is_file()],
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        hist_file = p_root / "04_workspace" / "render_history.json"
        hist_map: dict[str, Any] = {}
        if hist_file.exists():
            try:
                loaded_h = json.loads(hist_file.read_text(encoding="utf-8-sig"))
                if isinstance(loaded_h, dict):
                    hist_map = loaded_h
            except Exception:
                hist_map = {}
        for mp4 in mp4s:
            meta = probe_media(mp4)
            stat = mp4.stat()
            r360 = _review_360_path(p_root, mp4.name)
            j_key = f"{pid}::{mp4.name}"
            j_info = jobs_snap.get(j_key) or {}
            if r360.exists() and r360.is_file() and r360.stat().st_size > 1024:
                r360_status = "ready"
                r360_size = round(r360.stat().st_size / (1024 * 1024), 2)
            elif j_info.get("status") == "running":
                r360_status = "running"
                r360_size = 0.0
            elif j_info.get("status") == "error":
                r360_status = "error"
                r360_size = 0.0
            else:
                r360_status = "none"
                r360_size = 0.0
            t_file = _thumb_path(p_root, mp4.name)
            t_ready = t_file.exists() and t_file.is_file() and t_file.stat().st_size > 1024
            outputs.append(
                {
                    "project_id": pid,
                    "project_name": str(pr.get("name") or pid),
                    "name": mp4.name,
                    "rel_path": f"05_output/{mp4.name}",
                    "stream_url": f"/api/projects/outputs/stream?project_id={pid}&name={mp4.name}&t={int(stat.st_mtime)}",
                    "download_url": f"/api/files/download?project_id={pid}&path=05_output/{mp4.name}",
                    "size_mb": meta.get("size_mb", round(stat.st_size / (1024 * 1024), 2)),
                    "duration_sec": meta.get("duration_sec", 0.0),
                    "width": meta.get("width", 1080),
                    "height": meta.get("height", 1920),
                    "mtime": int(stat.st_mtime),
                    "render_meta": hist_map.get(mp4.name),
                    "thumbnail_ready": t_ready,
                    "thumbnail_url": f"/api/projects/outputs/thumbnail?project_id={pid}&name={mp4.name}&t={int(t_file.stat().st_mtime)}" if t_ready else "",
                    "thumbnail_rel_path": f"05_output/_thumbnails/{t_file.name}",
                    "thumbnail_name": t_file.name,
                    "review_360_status": r360_status,
                    "review_360_size_mb": r360_size,
                    "review_360_rel_path": f"05_output/_review_360p/{r360.name}",
                    "review_360_error": str(j_info.get("error") or ""),
                }
            )
    outputs.sort(key=lambda x: x["mtime"], reverse=True)
    return {
        "ok": True,
        "active_project_id": active_id,
        "selected_project_id": target_pid,
        "projects": [{"id": p["id"], "name": p["name"], "output_count": p.get("output_count", 0)} for p in all_projs],
        "outputs": outputs,
    }


@app.get("/api/projects/outputs/stream")
def api_stream_project_output(project_id: str = Query(...), name: str = Query(...)):
    safe_name = Path(name).name
    if not safe_name or ".." in name or not safe_name.lower().endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Tên file không hợp lệ.")
    p_root = get_project_root(project_id).resolve()
    fp = (p_root / "05_output" / safe_name).resolve()
    if not fp.is_relative_to(p_root) or not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy video output.")
    return FileResponse(path=str(fp), media_type="video/mp4")


@app.get("/api/projects/outputs/zip")
def api_download_project_outputs_zip(project_id: str = Query(...)):
    import zipfile

    pid = str(project_id or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="Thiếu project_id.")
    p_root = get_project_root(pid).resolve()
    out_dir = p_root / "05_output"
    mp4s = sorted([p for p in out_dir.glob("*.mp4") if p.is_file()]) if out_dir.exists() else []
    if not mp4s:
        raise HTTPException(status_code=404, detail=f"Project {pid} chưa có video output nào.")
    tmp_zip = Path(tempfile.gettempdir()) / f"{pid}_outputs_{int(time.time())}.zip"
    with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_STORED) as zf:
        for mp4 in mp4s:
            zf.write(mp4, arcname=mp4.name)
    dl_name = f"{pid}_outputs.zip"
    return FileResponse(
        path=str(tmp_zip),
        media_type="application/zip",
        filename=dl_name,
        headers={"Content-Disposition": f'attachment; filename="{dl_name}"'},
    )


@app.post("/api/projects/outputs/prepare-360p")
def api_prepare_project_output_360p(payload: dict[str, Any]):
    pid = str(payload.get("project_id") or "").strip()
    name = Path(str(payload.get("name") or "")).name
    if not pid or not name or not name.lower().endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Thiếu project_id hoặc tên file mp4.")
    p_root = get_project_root(pid).resolve()
    src_fp = (p_root / "05_output" / name).resolve()
    if not src_fp.is_relative_to(p_root) or not src_fp.exists() or not src_fp.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy video gốc.")
    dest_fp = _review_360_path(p_root, name)
    if dest_fp.exists() and dest_fp.is_file() and dest_fp.stat().st_size > 1024:
        return {
            "ok": True,
            "status": "ready",
            "size_mb": round(dest_fp.stat().st_size / (1024 * 1024), 2),
            "rel_path": f"05_output/_review_360p/{dest_fp.name}",
        }
    j_key = f"{pid}::{name}"
    with REVIEW_360_LOCK:
        cur = REVIEW_360_JOBS.get(j_key) or {}
        if cur.get("status") == "running":
            return {"ok": True, "status": "running"}
        REVIEW_360_JOBS[j_key] = {"status": "running", "error": ""}
    t = threading.Thread(target=_run_review_360_transcode, args=(j_key, src_fp, dest_fp), daemon=True)
    t.start()
    return {"ok": True, "status": "running"}


@app.get("/api/projects/outputs/thumbnail")
def api_get_project_output_thumbnail(project_id: str = Query(...), name: str = Query(...)):
    safe_name = Path(name).name
    if not safe_name or ".." in name:
        raise HTTPException(status_code=400, detail="Tên file không hợp lệ.")
    p_root = get_project_root(project_id).resolve()
    t_fp = _thumb_path(p_root, safe_name).resolve()
    if not t_fp.is_relative_to(p_root) or not t_fp.exists() or not t_fp.is_file():
        raise HTTPException(status_code=404, detail="Chưa có thumbnail cho video này.")
    return FileResponse(path=str(t_fp), media_type="image/jpeg")


@app.post("/api/projects/outputs/generate-meta")
def api_generate_project_output_meta(payload: dict[str, Any]):
    pid = str(payload.get("project_id") or "").strip()
    name = Path(str(payload.get("name") or "")).name
    if not pid or not name or not name.lower().endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Thiếu project_id hoặc tên file mp4.")
    p_root = get_project_root(pid).resolve()
    mp4_fp = (p_root / "05_output" / name).resolve()
    if not mp4_fp.is_relative_to(p_root) or not mp4_fp.exists() or not mp4_fp.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy video gốc.")
    ws_dir = p_root / "04_workspace"
    hist_p = ws_dir / "render_history.json"
    cur_hist: dict[str, Any] = {}
    if hist_p.exists():
        try:
            cur_hist = json.loads(hist_p.read_text(encoding="utf-8-sig"))
        except Exception:
            cur_hist = {}
    existing = dict(cur_hist.get(name) or {})
    probe = probe_media(mp4_fp)
    w, h = int(probe.get("width") or 1080), int(probe.get("height") or 1920)
    ar = "16:9" if w > h else "9:16"
    existing.setdefault("aspect_ratio", ar)
    existing.setdefault("mode", "long_vlog" if "_16x9" in name or "VLOG_" in name else "short_tiktok")
    bb_p = ws_dir / "brand_brief.json"
    bb = json.loads(bb_p.read_text(encoding="utf-8-sig")) if bb_p.exists() else {}
    sc_p = ws_dir / "kich_ban_hien_thi.md"
    sc_txt = sc_p.read_text(encoding="utf-8-sig") if sc_p.exists() else ""
    if bool(payload.get("force")):
        existing.pop("social_title", None)
        existing.pop("social_description", None)
        t_old = _thumb_path(p_root, name)
        if t_old.exists():
            t_old.unlink(missing_ok=True)
    updated_meta = _attach_output_assets(p_root, mp4_fp, existing, script_text=sc_txt, brand_brief=bb)
    _record_render_history(ws_dir, name, updated_meta)
    t_fp = _thumb_path(p_root, name)
    return {
        "ok": True,
        "render_meta": updated_meta,
        "thumbnail_ready": t_fp.exists(),
        "thumbnail_url": f"/api/projects/outputs/thumbnail?project_id={pid}&name={name}&t={int(time.time())}" if t_fp.exists() else "",
        "thumbnail_rel_path": f"05_output/_thumbnails/{t_fp.name}",
    }


@app.post("/api/projects/outputs/delete")
def api_delete_project_output(payload: dict[str, Any]):
    pid = str(payload.get("project_id") or "").strip()
    name = Path(str(payload.get("name") or "")).name
    if not pid or not name:
        raise HTTPException(status_code=400, detail="Thiếu project_id hoặc tên file.")
    p_root = get_project_root(pid).resolve()
    fp = (p_root / "05_output" / name).resolve()
    if not fp.is_relative_to(p_root) or not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy file để xóa.")
    fp.unlink()
    r360 = _review_360_path(p_root, name)
    if r360.exists() and r360.is_file():
        r360.unlink(missing_ok=True)
    t_fp = _thumb_path(p_root, name)
    if t_fp.exists() and t_fp.is_file():
        t_fp.unlink(missing_ok=True)
    _remove_render_history(p_root / "04_workspace", name)
    return {"ok": True, "deleted": name, "project_id": pid}
