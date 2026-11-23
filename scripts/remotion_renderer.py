#!/usr/bin/env python3
"""Headless Remotion Hybrid Graphic Renderer & Props Builder."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "scripts"))

from audio_bgm import ensure_royalty_free_bgm_library
from project_manager import get_project_root
import style_dna as _style_dna_mod
from style_dna import (
    DIR_READY,
    DIR_WORKSPACE,
    FILE_STYLE_DNA,
    _assign_camera_motion,
    _brief_mentions_haircare,
    _extract_feature_pill_from_text,
    _is_legacy_shampoo_pill,
    ensure_words_json_from_srt,
    load_brand_brief,
    load_script_options,
    load_style_dna,
    repair_subtitles_and_beats,
    update_style_dna,
)

DIR_ASSETS = ROOT_DIR / "assets"
DIR_CLIPS = DIR_READY / "01_clips"
PROJECT_ROOT_DIR = get_project_root()
DIR_OUTPUT = PROJECT_ROOT_DIR / "05_output"
DIR_ASSETS_AUDIO = ROOT_DIR / "06_assets_audio"
DIR_ASSETS_BGM = DIR_ASSETS_AUDIO / "bgm"
DIR_REMOTION = ROOT_DIR / "remotion_studio"
DIR_REMOTION_PUBLIC = DIR_REMOTION / "public"
DIR_REMOTION_WS = DIR_REMOTION_PUBLIC / "workspace"

FILE_TTS_WAV = DIR_READY / "02_giong_doc_ai.wav"
FILE_TTS_SRT = DIR_READY / "03_phu_de.srt"
FILE_WORDS_JSON = DIR_READY / "03_words.json"
FILE_CLIPS_MANIFEST = DIR_READY / "clips_manifest.json"
FILE_DIRECTOR_PLAN = DIR_WORKSPACE / "director_plan.json"
FILE_HOOK_CTA_MD = DIR_WORKSPACE / "openreel_hook_cta.md"
FILE_EDIT_PLAN = DIR_WORKSPACE / "edit_plan.json"
FILE_REMOTION_PROPS = DIR_WORKSPACE / "remotion_props.json"
FILE_PREVIEW_FRAMES_DIR = DIR_WORKSPACE / "render_preview_frames"
FILE_DEFAULT_OUTPUT = DIR_OUTPUT / "final_tiktok.mp4"


def refresh_project_paths(project_root: Path | None = None) -> Path:
    global PROJECT_ROOT_DIR, DIR_WORKSPACE, DIR_READY, DIR_CLIPS, DIR_OUTPUT
    global FILE_STYLE_DNA, FILE_TTS_WAV, FILE_TTS_SRT, FILE_WORDS_JSON
    global FILE_CLIPS_MANIFEST, FILE_DIRECTOR_PLAN, FILE_HOOK_CTA_MD
    global FILE_EDIT_PLAN, FILE_REMOTION_PROPS, FILE_PREVIEW_FRAMES_DIR, FILE_DEFAULT_OUTPUT
    PROJECT_ROOT_DIR = _style_dna_mod.refresh_project_paths(project_root)
    DIR_WORKSPACE = _style_dna_mod.DIR_WORKSPACE
    DIR_READY = _style_dna_mod.DIR_READY
    FILE_STYLE_DNA = _style_dna_mod.FILE_STYLE_DNA
    DIR_CLIPS = DIR_READY / "01_clips"
    DIR_OUTPUT = PROJECT_ROOT_DIR / "05_output"
    FILE_TTS_WAV = DIR_READY / "02_giong_doc_ai.wav"
    FILE_TTS_SRT = DIR_READY / "03_phu_de.srt"
    FILE_WORDS_JSON = DIR_READY / "03_words.json"
    FILE_CLIPS_MANIFEST = DIR_READY / "clips_manifest.json"
    FILE_DIRECTOR_PLAN = DIR_WORKSPACE / "director_plan.json"
    FILE_HOOK_CTA_MD = DIR_WORKSPACE / "openreel_hook_cta.md"
    FILE_EDIT_PLAN = DIR_WORKSPACE / "edit_plan.json"
    FILE_REMOTION_PROPS = DIR_WORKSPACE / "remotion_props.json"
    FILE_PREVIEW_FRAMES_DIR = DIR_WORKSPACE / "render_preview_frames"
    FILE_DEFAULT_OUTPUT = DIR_OUTPUT / "final_tiktok.mp4"
    return PROJECT_ROOT_DIR


def find_npx() -> str:
    for cand in ("npx.cmd", "npx"):
        found = shutil.which(cand)
        if found:
            return found
    raise FileNotFoundError("Không tìm thấy `npx` / Node.js trong PATH.")


def find_browser_executable() -> str | None:
    """Resolve system Chrome or Edge executable to avoid Remotion chrome-headless-shell EFTYPE on Windows."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for cand in candidates:
        if cand and Path(cand).exists():
            return cand
    for bin_name in ("chrome", "google-chrome", "msedge", "chromium"):
        found = shutil.which(bin_name)
        if found:
            return found
    return None


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if exe:
        return exe
    winget_root = Path(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"))
    if winget_root.exists():
        for cand in winget_root.rglob("ffmpeg.exe"):
            return str(cand)
    raise FileNotFoundError("Không tìm thấy ffmpeg.")


def find_ffprobe() -> str:
    exe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if exe:
        return exe
    winget_root = Path(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"))
    if winget_root.exists():
        for cand in winget_root.rglob("ffprobe.exe"):
            return str(cand)
    raise FileNotFoundError("Không tìm thấy ffprobe.")


def probe_duration_sec(media_path: Path) -> float:
    if not media_path.exists():
        return 0.0
    try:
        out = subprocess.check_output(
            [
                find_ffprobe(),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(media_path),
            ],
            text=True,
            encoding="utf-8",
            timeout=15,
        ).strip()
        return round(float(out), 3) if out else 0.0
    except Exception:
        return 0.0


def _wrap_two_lines(text: str, max_chars: int = 24) -> list[str]:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if not clean:
        return []
    words = clean.split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if cur and len(cand) > max_chars and len(lines) < 1:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines[:2]


def tokenize_multicolor_line(
    line: str,
    palette: list[str] | None = None,
    stroke_color: str = "#000000",
    offset: int = 0,
) -> list[dict[str, str]]:
    """Split a Vietnamese line into 2-4 high-contrast colored spans matching @vievie090398 style."""
    colors = palette or ["#FFF380", "#FFFFFF", "#FF4D6D", "#FF9F1C", "#A8DADC", "#95D5B2"]
    # Split on comma boundaries first, else group 2-3 words
    raw_clauses = [c.strip() for c in re.split(r"(?<=,)\s+", line.strip()) if c.strip()]
    chunks: list[str] = []
    if len(raw_clauses) >= 2:
        chunks = raw_clauses
    else:
        words = line.strip().split()
        if len(words) <= 3:
            chunks = [" ".join(words)] if words else []
        else:
            step = 2 if len(words) <= 6 else 3
            for i in range(0, len(words), step):
                chunks.append(" ".join(words[i : i + step]))

    tokens: list[dict[str, str]] = []
    for idx, ch in enumerate(chunks):
        c = colors[(idx + offset) % len(colors)]
        sc = "#FFFFFF" if c.upper() in ("#FF4D6D", "#EF4444", "#E11D48") and idx % 2 == 1 else stroke_color
        tokens.append({"text": ch, "color": c, "strokeColor": sc})
    return tokens


def text_to_callout_lines(
    text: str,
    palette: list[str] | None = None,
    stroke_color: str = "#000000",
) -> list[dict[str, Any]]:
    lines = _wrap_two_lines(text, max_chars=24)
    out: list[dict[str, Any]] = []
    for idx, ln in enumerate(lines):
        out.append({"tokens": tokenize_multicolor_line(ln, palette=palette, stroke_color=stroke_color, offset=idx * 2)})
    return out


def _read_hook_cta_md() -> dict[str, Any]:
    if not FILE_HOOK_CTA_MD.exists():
        return {}
    try:
        raw = FILE_HOOK_CTA_MD.read_text(encoding="utf-8-sig")
        m = re.search(r"```json\s*(\{.*?\})\s*```", raw, flags=re.S)
        if m:
            return json.loads(m.group(1))
    except Exception:
        pass
    return {}


def _infer_floral_parts(
    hook_text: str,
    title: str = "",
    brand_brief: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    brief = brand_brief or {}
    b_brand = str(brief.get("brand") or "").strip()
    raw_info = str(brief.get("usps") or brief.get("raw_brief") or "").strip()
    if raw_info:
        first_seg = re.split(r"[\n;]+", raw_info)[0]
        first_seg = re.sub(r"\[[^\]]+\]", " ", first_seg)
        if b_brand:
            first_seg = re.sub(re.escape(b_brand), " ", first_seg, flags=re.I)
        first_seg = re.sub(r"^\s*[\-:|•]+\s*", "", first_seg)
        seg_words = [w for w in re.sub(r"[^\w\sÀ-ỹà-ỹ0-9%+\-]", " ", first_seg).split() if w]
        if seg_words:
            inf_brand = b_brand.upper() if b_brand else seg_words[0].upper()
            split_idx = 5 if (len(seg_words) >= 5 and seg_words[3].lower() in ("trong", "in", "&", "/")) else 4
            inf_prod = " ".join(seg_words[:split_idx]).upper()
            inf_cat = " ".join(seg_words[split_idx : split_idx + 4]).lower() if len(seg_words) > split_idx else "chính hãng deal hời"
            return inf_brand, inf_prod, inf_cat

    combined = f"{title} {hook_text}".lower()
    if "dell" in combined and "laptop" in combined:
        return "LAPTOP", "DELL", "bền mượt giá hời"
    src = hook_text.strip() or title.strip()
    clean = re.sub(r"[^\w\sÀ-ỹà-ỹ0-9-]", " ", src).strip()
    words = [w for w in clean.split() if len(w) > 1]
    if b_brand and words:
        return b_brand.upper(), " ".join(words[:3]).upper(), "deal hời giỏ hàng"
    if len(words) >= 4:
        return words[0].upper(), " ".join(words[1:4]).upper(), "deal hời giỏ hàng"
    if len(words) >= 2:
        return words[0].upper(), " ".join(words[:2]).upper(), "deal hời giỏ hàng"
    return "DEAL HỜI", "TIKTOK", "giá siêu mềm"


def sync_media_to_remotion_public(bgm_track: str | None = None) -> dict[str, Any]:
    """Copy workspace media & assets into remotion_studio/public/ for zero-error staticFile() loading."""
    DIR_REMOTION_PUBLIC.mkdir(parents=True, exist_ok=True)
    pub_assets = DIR_REMOTION_PUBLIC / "assets"
    for sub in ("fonts", "stickers", "emojis", "animated_stickers", "lottie_stickers", "overlays"):
        src_sub = DIR_ASSETS / sub
        dst_sub = pub_assets / sub
        dst_sub.mkdir(parents=True, exist_ok=True)
        if src_sub.exists():
            src_names = {f.name for f in src_sub.iterdir() if f.is_file()}
            for old_dst in dst_sub.iterdir():
                if old_dst.is_file() and old_dst.name not in src_names:
                    old_dst.unlink(missing_ok=True)
            for f in src_sub.iterdir():
                if f.is_file():
                    dst_f = dst_sub / f.name
                    if not dst_f.exists() or dst_f.stat().st_size != f.stat().st_size:
                        shutil.copy2(f, dst_f)
    lottie_js = DIR_ASSETS / "lottie.min.js"
    if lottie_js.exists():
        dst_ljs = pub_assets / "lottie.min.js"
        if not dst_ljs.exists() or dst_ljs.stat().st_size != lottie_js.stat().st_size:
            shutil.copy2(lottie_js, dst_ljs)

    ws_clips_dir = DIR_REMOTION_WS / "clips"
    ws_audio_dir = DIR_REMOTION_WS / "audio"
    ws_clips_dir.mkdir(parents=True, exist_ok=True)
    ws_audio_dir.mkdir(parents=True, exist_ok=True)

    # Clear stale clips before syncing active 01_clips
    for old in ws_clips_dir.glob("*.mp4"):
        old.unlink()

    synced_clips: list[str] = []
    if DIR_CLIPS.exists():
        for mp4 in sorted(DIR_CLIPS.glob("*.mp4")):
            shutil.copy2(mp4, ws_clips_dir / mp4.name)
            synced_clips.append(f"workspace/clips/{mp4.name}")

    # Clear stale voice.wav before syncing active project's 02_giong_doc_ai.wav
    pub_voice = ws_audio_dir / "voice.wav"
    if pub_voice.exists():
        pub_voice.unlink()

    voice_rel = ""
    if FILE_TTS_WAV.exists():
        shutil.copy2(FILE_TTS_WAV, pub_voice)
        voice_rel = "workspace/audio/voice.wav"

    bgm_rel = ""
    ensure_royalty_free_bgm_library()
    if DIR_ASSETS_BGM.exists():
        bgm_files = [
            p for p in sorted(DIR_ASSETS_BGM.iterdir())
            if p.is_file() and p.suffix.lower() in (".wav", ".mp3", ".m4a")
        ]
        chosen_bgm = None
        if bgm_track:
            cand = DIR_ASSETS_BGM / Path(bgm_track).name
            if cand.exists() and cand.is_file():
                chosen_bgm = cand
        if chosen_bgm is None:
            for pref_name in ("bgm_upbeat_tiktok.wav", "bgm_chill_lofi.wav", "bgm_flash_sale.wav"):
                pref_p = DIR_ASSETS_BGM / pref_name
                if pref_p.exists():
                    chosen_bgm = pref_p
                    break
        if chosen_bgm is None and bgm_files:
            custom = [p for p in bgm_files if p.name != "bgm_upbeat_default.wav"]
            chosen_bgm = custom[0] if custom else bgm_files[0]
        if chosen_bgm:
            bgm_name = f"bgm{chosen_bgm.suffix.lower()}"
            shutil.copy2(chosen_bgm, ws_audio_dir / bgm_name)
            bgm_rel = f"workspace/audio/{bgm_name}"

    sfx_map: dict[str, str] = {}
    if DIR_ASSETS_AUDIO.exists():
        src_sfx_names = {src.name for src in DIR_ASSETS_AUDIO.glob("sfx_*.wav")}
        for old_sfx in ws_audio_dir.glob("sfx_*.wav"):
            if old_sfx.name not in src_sfx_names:
                old_sfx.unlink(missing_ok=True)
        for src in sorted(DIR_ASSETS_AUDIO.glob("sfx_*.wav")):
            dst_sfx = ws_audio_dir / src.name
            if not dst_sfx.exists() or dst_sfx.stat().st_size != src.stat().st_size:
                shutil.copy2(src, dst_sfx)
            sfx_map[src.name] = f"workspace/audio/{src.name}"

    return {
        "clips": synced_clips,
        "voice": voice_rel,
        "bgm": bgm_rel,
        "sfx": sfx_map,
    }


def _slug_ascii(text: str, max_len: int = 24) -> str:
    norm = unicodedata.normalize("NFD", (text or "").replace("đ", "d").replace("Đ", "D"))
    ascii_str = "".join(ch for ch in norm if unicodedata.category(ch) != "Mn")
    words = re.findall(r"[A-Za-z0-9]+", ascii_str)
    joined = "".join(w[:1].upper() + w[1:] for w in words if w)
    return (joined or "SanPham")[:max_len]


def resolve_script_named_output_path(total_duration: float | None = None) -> tuple[Path, dict[str, Any]]:
    """Build a script-identifiable output filename in 05_output/ matching the chosen script option."""
    bundle = load_script_options()
    brief = load_brand_brief()
    options = bundle.get("options") if isinstance(bundle.get("options"), list) else []
    sel_id = str(bundle.get("selected_id") or (options[0].get("id") if options else "opt1"))
    chosen = next((o for o in options if o.get("id") == sel_id), options[0] if options else None)

    num_m = re.search(r"(\d+)", sel_id)
    kb_tag = f"KB{num_m.group(1)}" if num_m else "KB1"
    angle_raw = str((chosen or {}).get("angle") or (chosen or {}).get("title") or "NoiDau")
    angle_slug = _slug_ascii(angle_raw, 22)
    brand_slug = _slug_ascii(str(brief.get("brand") or "TikTokShop"), 18)
    dur_int = max(5, int(round(float(total_duration or brief.get("target_duration_sec") or 30.0))))

    filename = f"tiktok_{kb_tag}_{angle_slug}_{brand_slug}_{dur_int}s.mp4"
    label = (
        f"{kb_tag}: {(chosen or {}).get('title') or angle_raw}"
        if chosen
        else f"{kb_tag}: Kịch bản hiện tại ({dur_int}s)"
    )
    meta = {
        "selected_id": sel_id,
        "kb_tag": kb_tag,
        "title": str((chosen or {}).get("title") or label),
        "angle": angle_raw,
        "hook_badge": str((chosen or {}).get("hook_badge") or "").strip(),
        "cta_text": str((chosen or {}).get("cta_text") or "").strip(),
        "duration_sec": dur_int,
        "output_filename": filename,
        "label": label,
    }
    return DIR_OUTPUT / filename, meta


THEME_CALLOUT_PALETTES: dict[str, list[str]] = {
    "floral_rose": ["#FFF380", "#FFFFFF", "#FF4D6D", "#FF9F1C", "#A8DADC", "#95D5B2"],
    "fresh_mint": ["#67E8F9", "#FFFFFF", "#34D399", "#A7F3D0", "#38BDF8", "#FDE047"],
    "flash_gold": ["#FFE500", "#FFFFFF", "#FB7185", "#F97316", "#FEF08A", "#34D399"],
    "luxury_dark": ["#FDE68A", "#FFFFFF", "#FBBF24", "#E2E8F0", "#F59E0B", "#94A3B8"],
    "ribbon_sticker": ["#FFFFFF", "#FFE500", "#FF4D6D", "#38BDF8", "#34D399", "#F472B6"],
}


def build_remotion_props(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Assemble remotion_props.json from style_dna, brand_brief, voice_beats, director_plan, clips_manifest, and 03_words.json."""
    ov = overrides or {}
    dna = load_style_dna() if FILE_STYLE_DNA.exists() else update_style_dna()
    bgm_track = str(ov.get("bgm_track") or dna.get("bgm_track") or "bgm_upbeat_tiktok.wav")
    synced = sync_media_to_remotion_public(bgm_track=bgm_track)
    brand_brief = load_brand_brief()
    rep_res = repair_subtitles_and_beats()
    words = ensure_words_json_from_srt()

    director_plan: dict[str, Any] = {}
    if FILE_DIRECTOR_PLAN.exists():
        try:
            director_plan = json.loads(FILE_DIRECTOR_PLAN.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    hook_cfg = _read_hook_cta_md()
    edit_plan: dict[str, Any] = {}
    if FILE_EDIT_PLAN.exists():
        try:
            edit_plan = json.loads(FILE_EDIT_PLAN.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    # Build clip sequence from clips_manifest or 01_clips
    clip_items: list[dict[str, Any]] = []
    manifest_clips: list[dict[str, Any]] = []
    if FILE_CLIPS_MANIFEST.exists():
        try:
            manifest = json.loads(FILE_CLIPS_MANIFEST.read_text(encoding="utf-8-sig"))
            manifest_clips = manifest.get("clips") or []
        except Exception:
            pass

    plan_clips = edit_plan.get("clips") if isinstance(edit_plan.get("clips"), list) else []
    cursor = 0.0
    if manifest_clips:
        for idx, mc in enumerate(manifest_clips):
            out_file = Path(str(mc.get("clip") or mc.get("output") or "")).name
            src_rel = f"workspace/clips/{out_file}"
            if not out_file or src_rel not in synced["clips"]:
                continue
            pc = plan_clips[idx] if idx < len(plan_clips) and isinstance(plan_clips[idx], dict) else {}
            dur = float(
                mc.get("actual_duration_sec")
                or mc.get("duration")
                or mc.get("actual_duration")
                or probe_duration_sec(DIR_CLIPS / out_file)
                or 2.5
            )
            spoken = str(mc.get("spoken_text") or pc.get("spoken_text") or "").strip()
            c_callout = str(mc.get("callout_text") or pc.get("callout_text") or "").strip()
            cam_fallback = _assign_camera_motion(idx, max(1, len(manifest_clips)), spoken)

            z_mode = str(mc.get("zoom_mode") or pc.get("zoom_mode") or cam_fallback["zoom_mode"])
            z_from = float(
                mc.get("zoom_from")
                if mc.get("zoom_from") is not None
                else (pc.get("zoom_from") if pc.get("zoom_from") is not None else cam_fallback["zoom_from"])
            )
            z_to = float(
                mc.get("zoom_to")
                if mc.get("zoom_to") is not None
                else (pc.get("zoom_to") if pc.get("zoom_to") is not None else cam_fallback["zoom_to"])
            )
            if abs(z_to - z_from) < 0.08:
                z_from = float(cam_fallback["zoom_from"])
                z_to = float(cam_fallback["zoom_to"])
            pan_x = int(mc.get("pan_x") if mc.get("pan_x") is not None else (pc.get("pan_x") or cam_fallback["pan_x"]))
            pan_y = int(mc.get("pan_y") if mc.get("pan_y") is not None else (pc.get("pan_y") or cam_fallback["pan_y"]))
            trans_type = str(mc.get("transition_type") or pc.get("transition_type") or cam_fallback["transition_type"])
            raw_pill = str(mc.get("feature_pill") or pc.get("feature_pill") or "").strip()
            if not raw_pill or _is_legacy_shampoo_pill(raw_pill, brand_brief):
                f_pill = _extract_feature_pill_from_text(spoken or c_callout, brand_brief, idx)
            else:
                f_pill = raw_pill

            clip_entry: dict[str, Any] = {
                "id": f"clip_{idx+1}",
                "src": src_rel,
                "startInTimeline": round(cursor, 3),
                "duration": round(dur, 3),
                "zoomMode": z_mode,
                "zoomFrom": z_from,
                "zoomTo": z_to,
                "panX": pan_x,
                "panY": pan_y,
                "transitionType": trans_type,
                "featurePill": f_pill,
            }
            beat_idx = mc.get("beat_index") if mc.get("beat_index") is not None else pc.get("beat_index")
            if beat_idx is not None:
                clip_entry["beatIndex"] = int(beat_idx)
            if spoken:
                clip_entry["spokenText"] = spoken
            if c_callout:
                clip_entry["calloutText"] = c_callout
            c_note = str(mc.get("note") or pc.get("note") or "").strip()
            if c_note:
                clip_entry["note"] = c_note
            clip_items.append(clip_entry)
            cursor += dur
    if not clip_items:
        for idx, src_rel in enumerate(synced["clips"]):
            fname = Path(src_rel).name
            dur = probe_duration_sec(DIR_CLIPS / fname) or 2.5
            cam_fb = _assign_camera_motion(idx, max(1, len(synced["clips"])), "")
            clip_items.append(
                {
                    "id": f"clip_{idx+1}",
                    "src": src_rel,
                    "startInTimeline": round(cursor, 3),
                    "duration": round(dur, 3),
                    "zoomMode": cam_fb["zoom_mode"],
                    "zoomFrom": cam_fb["zoom_from"],
                    "zoomTo": cam_fb["zoom_to"],
                    "panX": cam_fb["pan_x"],
                    "panY": cam_fb["pan_y"],
                    "transitionType": cam_fb["transition_type"],
                    "featurePill": _extract_feature_pill_from_text("", brand_brief, idx),
                }
            )
            cursor += dur

    voice_dur = probe_duration_sec(FILE_TTS_WAV) if FILE_TTS_WAV.exists() else 0.0
    # Loop clips gently if total video is shorter than voiceover
    if clip_items and voice_dur > cursor + 0.5:
        base_clips = list(clip_items)
        rep = 0
        while cursor < voice_dur and rep < 20:
            src_c = base_clips[rep % len(base_clips)]
            add_dur = min(src_c["duration"], round(voice_dur - cursor + 0.3, 3))
            if add_dur < 0.5:
                break
            clip_items.append(
                {
                    "id": f"clip_ext_{rep}",
                    "src": src_c["src"],
                    "startInTimeline": round(cursor, 3),
                    "duration": round(add_dur, 3),
                    "zoomMode": "zoom_out" if rep % 2 == 0 else "punch_in",
                    "zoomFrom": 1.18 if rep % 2 == 0 else 1.0,
                    "zoomTo": 1.02 if rep % 2 == 0 else 1.2,
                    "transitionType": "flash",
                    "featurePill": src_c.get("featurePill") or "",
                }
            )
            cursor += add_dur
            rep += 1

    total_duration = round(max(cursor, voice_dur, 4.0), 3)

    badge_style = str(ov.get("badge_style") or dna.get("badge_style") or "floral_plus_callouts")
    raw_theme = str(ov.get("visual_theme") or dna.get("visual_theme") or "auto")
    named_out_path, selected_meta = resolve_script_named_output_path(total_duration)
    if raw_theme == "auto":
        auto_theme_map = {"opt1": "fresh_mint", "opt2": "floral_rose", "opt3": "flash_gold"}
        resolved_theme = auto_theme_map.get(selected_meta.get("selected_id", ""), "floral_rose")
    elif raw_theme in THEME_CALLOUT_PALETTES:
        resolved_theme = raw_theme
    else:
        resolved_theme = "floral_rose"

    def _clean_non_stale(val: Any) -> str:
        txt = str(val or "").strip()
        if not txt:
            return ""
        has_active_brand = bool(str(brand_brief.get("brand") or "").strip())
        if has_active_brand and not _brief_mentions_haircare(brand_brief):
            low = txt.lower()
            if any(k in low for k in ("head", "shoulder", "5in1 tonic", "niacinamide", "menthol", "sạch gàu", "dầu gội", "không cần xả")):
                return ""
        return txt

    brief_hook_fb = " - ".join(
        p for p in (str(brand_brief.get("brand") or "").strip(), str(brand_brief.get("product_line") or "").strip()) if p
    )
    hook_text = (
        str(ov.get("hook_text") or "").strip()
        or str(selected_meta.get("hook_badge") or "").strip()
        or _clean_non_stale(hook_cfg.get("hook_text"))
        or _clean_non_stale(director_plan.get("best_hook"))
        or brief_hook_fb
        or "Deal hời siêu xịn đừng bỏ lỡ!"
    )
    cta_text = (
        str(ov.get("cta_text") or "").strip()
        or str(selected_meta.get("cta_text") or "").strip()
        or str(brand_brief.get("offer_cta") or "").strip()
        or _clean_non_stale(hook_cfg.get("cta_text"))
        or _clean_non_stale(director_plan.get("cta_text"))
        or "Chốt đơn ngay giỏ hàng góc trái 👇"
    )

    palette = list(THEME_CALLOUT_PALETTES.get(resolved_theme) or dna.get("palette") or ["#FFF380", "#FFFFFF", "#FF4D6D"])
    if badge_style == "multicolor_pill" and raw_theme == "auto":
        palette = list(dna.get("palette") or palette)
    hook_y = float(ov.get("hook_y") or hook_cfg.get("hook_y") or dna.get("hook_y") or 0.16)
    subtitle_y = float(ov.get("subtitle_y") or dna.get("subtitle_y") or 0.72)
    subtitle_active_color = str(
        ov.get("subtitle_active_color")
        or hook_cfg.get("caption_highlight_color")
        or dna.get("subtitle_active_color")
        or "#FFE500"
    )

    fb_dir = director_plan.get("floral_badge") if isinstance(director_plan.get("floral_badge"), dict) else {}
    safe_plan_title = _clean_non_stale(edit_plan.get("title"))
    inf_brand, inf_prod, inf_cat = _infer_floral_parts(hook_text, safe_plan_title, brand_brief=brand_brief)
    floral_badge = {
        "enabled": badge_style in ("floral_badge", "floral_plus_callouts"),
        "brand": str(ov.get("brand") or brand_brief.get("brand") or _clean_non_stale(fb_dir.get("brand")) or inf_brand),
        "productLine": str(ov.get("product_line") or brand_brief.get("product_line") or _clean_non_stale(fb_dir.get("product_line")) or inf_prod),
        "category": str(ov.get("category") or brand_brief.get("category") or _clean_non_stale(fb_dir.get("category")) or inf_cat),
        "brandColor": "#FFFFFF",
        "productColor": "#38BDF8",
        "categoryColor": "#FFF380",
        "accentStrokeColor": "#BE185D",
        "outerStrokeColor": "#FFFFFF",
        "start": 0.0,
        "end": round(min(4.0, total_duration * 0.4), 2),
        "y": hook_y,
    }

    # Build multicolor callouts: Hook (0-3.8s), mid-video callouts, and CTA (last 3.5s)
    callouts: list[dict[str, Any]] = [
        {
            "id": "callout_hook",
            "start": 0.1,
            "end": round(min(3.8, total_duration * 0.35), 2),
            "y": hook_y,
            "lines": text_to_callout_lines(hook_text, palette=palette, stroke_color=str(dna.get("stroke_color") or "#000000")),
        }
    ]
    raw_callouts = director_plan.get("callouts") or []
    for ci, c in enumerate(raw_callouts):
        if not isinstance(c, dict):
            continue
        c_text = _clean_non_stale(c.get("text"))
        if not c_text:
            continue
        raw_start = c.get("start") if c.get("start") is not None else c.get("startTime")
        c_start = max(
            4.1 if badge_style == "floral_plus_callouts" else 3.8,
            float(raw_start if raw_start is not None else (5.0 + ci * 4.5)),
        )
        if c.get("end") is not None:
            raw_end = float(c["end"])
        elif c.get("duration") is not None:
            raw_end = c_start + float(c["duration"])
        else:
            raw_end = c_start + 3.0
        c_end = min(total_duration - 3.6, raw_end)
        if c_end - c_start < 1.2:
            continue
        raw_y = float(c.get("y") or 0.17)
        safe_y = round(min(0.24, max(0.14, raw_y)), 2)
        callouts.append(
            {
                "id": f"callout_mid_{ci+1}",
                "start": round(c_start, 2),
                "end": round(c_end, 2),
                "y": safe_y,
                "lines": text_to_callout_lines(c_text, palette=palette, stroke_color=str(dna.get("stroke_color") or "#000000")),
            }
        )

    content_vibe = str(ov.get("content_vibe") or "learned_dna").strip()
    vibe_meta = _style_dna_mod.get_content_vibe_meta(content_vibe)
    if vibe_meta["is_vlog"]:
        cta_text = str(ov.get("cta_text") or vibe_meta["cta_default"])

    cta_start = round(max(4.0, total_duration - 3.6), 2)
    if total_duration > 5.0:
        callouts.append(
            {
                "id": "callout_cta",
                "start": cta_start,
                "end": round(total_duration - 0.1, 2),
                "y": 0.22,
                "lines": text_to_callout_lines(cta_text, palette=["#FFE500", "#FFFFFF", "#34D399"], stroke_color="#000000"),
            }
        )

    sfx_level = str(ov.get("sfx_level") or dna.get("sfx_level") or "subtle").strip().lower()
    if sfx_level not in ("subtle", "balanced", "off"):
        sfx_level = "subtle"

    # Audio SFX events locked to Hook, Beat Callouts, Transitions, and CTA (clean subtle pool, no corny game/bell SFX)
    sfx_events: list[dict[str, Any]] = []
    sfx_map = synced["sfx"]
    if sfx_level != "off":
        hook_sfx = sfx_map.get("sfx_bubble_pop.wav") or sfx_map.get("sfx_pop.wav")
        callout_sfx_pool = [
            k for k in ("sfx_bubble_pop.wav", "sfx_pop.wav", "sfx_sparkle_chime.wav") if sfx_map.get(k)
        ]
        trans_sfx_pool = [
            k for k in ("sfx_swoosh_soft.wav", "sfx_pop.wav") if sfx_map.get(k)
        ]
        vol_scale = 0.72 if sfx_level == "subtle" else 1.0

        if hook_sfx:
            sfx_events.append(
                {"id": "sfx_hook_pop", "src": hook_sfx, "start": 0.08, "duration": 0.45, "volume": round(0.28 * vol_scale, 3)}
            )

        if sfx_level == "balanced" and callout_sfx_pool:
            for ci, co in enumerate(callouts):
                co_id = str(co.get("id") or "")
                co_start = float(co.get("start") or 0.0)
                if co_id.startswith("callout_mid_") and 1.0 < co_start < total_duration - 0.8:
                    chosen_c_sfx = sfx_map[callout_sfx_pool[ci % len(callout_sfx_pool)]]
                    sfx_events.append(
                        {
                            "id": f"sfx_callout_pop_{ci}",
                            "src": chosen_c_sfx,
                            "start": round(co_start, 2),
                            "duration": 0.50,
                            "volume": 0.24,
                        }
                    )

        if trans_sfx_pool and len(clip_items) > 1:
            max_trans = 2 if sfx_level == "subtle" else 4
            trans_added = 0
            for wi, cl in enumerate(clip_items[1:], start=1):
                if trans_added >= max_trans:
                    break
                if (cl.get("transitionType") == "flash" or wi in (1, 3, 5, 7)) and cl["startInTimeline"] < total_duration - 1.0:
                    chosen_t_sfx = sfx_map[trans_sfx_pool[wi % len(trans_sfx_pool)]]
                    sfx_events.append(
                        {
                            "id": f"sfx_whoosh_{wi}",
                            "src": chosen_t_sfx,
                            "start": max(0.0, round(cl["startInTimeline"] - 0.12, 2)),
                            "duration": 0.60,
                            "volume": round(0.26 * vol_scale, 3),
                        }
                    )
                    trans_added += 1

        cta_sfx = sfx_map.get("sfx_sparkle_chime.wav") or sfx_map.get("sfx_bubble_pop.wav")
        if cta_sfx and total_duration > 5.0:
            sfx_events.append(
                {"id": "sfx_cta_chime", "src": cta_sfx, "start": cta_start, "duration": 0.75, "volume": round(0.26 * vol_scale, 3)}
            )
        if sfx_level == "subtle" and len(sfx_events) > 4:
            sfx_events = sfx_events[:3] + [sfx_events[-1]]

    creative_mode = str(ov.get("creative_mode") or dna.get("creative_mode") or "breakthrough_ai")
    camera_intensity = str(ov.get("camera_intensity") or dna.get("camera_intensity") or "dynamic_ai")
    layout_style = str(ov.get("layout_style") or dna.get("layout_style") or "full")
    color_preset = str(ov.get("color_preset") or dna.get("color_preset") or "natural")
    render_engine = str(ov.get("render_engine") or dna.get("render_engine") or "remotion_classic")
    innovation_preset = str(ov.get("innovation_preset") or dna.get("innovation_preset") or "kinetic_pop")
    transition_level = str(ov.get("transition_level") or dna.get("transition_level") or "balanced")
    icon_density = str(ov.get("icon_density") or dna.get("icon_density") or "balanced")
    sticker_density = str(ov.get("sticker_density") or dna.get("sticker_density") or "normal")
    disable_flash_shake = ov.get("disable_flash_shake") if ov.get("disable_flash_shake") is not None else dna.get("disable_flash_shake", True)
    named_out_path, selected_meta = resolve_script_named_output_path(total_duration)
    bgm_vol_val = ov.get("bgm_volume") if ov.get("bgm_volume") is not None else dna.get("bgm_volume")
    aspect_ratio = str(ov.get("aspect_ratio") or dna.get("aspect_ratio") or "9:16").strip()
    if aspect_ratio not in ("9:16", "16:9"):
        aspect_ratio = "9:16"
    target_w, target_h = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
    resolved_wildcard = ov.get("wildcard_spec")
    if not resolved_wildcard and render_engine in ("remotion_innovation", "hyperframes"):
        resolved_wildcard = _style_dna_mod.generate_ai_wildcard_style_spec(
            brand_brief,
            sticker_density=sticker_density,
            icon_density=icon_density,
            content_vibe=content_vibe,
            aspect_ratio=aspect_ratio,
        )

    eff_hook_y = float(ov.get("hook_y") if ov.get("hook_y") is not None else hook_y)
    eff_sub_y = float(ov.get("subtitle_y") if ov.get("subtitle_y") is not None else subtitle_y)
    if aspect_ratio == "16:9":
        eff_hook_y = min(eff_hook_y, 0.11)
        eff_sub_y = max(eff_sub_y, 0.82)

    props = {
        "title": str(edit_plan.get("title") or ("Vlog Story" if vibe_meta["is_vlog"] else "TikTok Shop Review")),
        "disclaimerText": str(ov.get("disclaimer_text") or "").strip(),
        "durationSec": total_duration,
        "aspectRatio": aspect_ratio,
        "width": target_w,
        "height": target_h,
        "contentVibe": content_vibe,
        "badgeStyle": badge_style,
        "visualTheme": resolved_theme,
        "rawVisualTheme": raw_theme,
        "layoutStyle": layout_style,
        "colorPreset": color_preset,
        "creativeMode": creative_mode,
        "cameraIntensity": camera_intensity,
        "renderEngine": render_engine,
        "innovationPreset": innovation_preset,
        "transitionLevel": transition_level,
        "iconDensity": icon_density,
        "stickerDensity": sticker_density,
        "overlayEffect": str(ov.get("overlay_effect") or dna.get("overlay_effect") or "auto"),
        "disableFlashShake": bool(disable_flash_shake),
        **({"wildcardSpec": resolved_wildcard} if resolved_wildcard else {}),
        "selectedScriptId": selected_meta["selected_id"],
        "selectedScriptLabel": selected_meta["label"],
        "outputFilename": named_out_path.name,
        "bgmTrack": bgm_track,
        "transparentBg": False,
        "badgeOnly": False,
        "hookY": eff_hook_y,
        "subtitleY": eff_sub_y,
        "fontHeading": str(ov.get("font_heading") or dna.get("font_heading") or "Baloo 2"),
        "fontBrand": str(dna.get("font_brand") or "Montserrat Black"),
        "fontScript": str(dna.get("font_script") or "Dancing Script"),
        "subtitleActiveColor": subtitle_active_color,
        "floralBadge": floral_badge,
        "callouts": callouts,
        "words": [] if bool(ov.get("hide_subtitles")) else words,
        "clips": clip_items,
        "voiceSrc": "" if bool(ov.get("mute_voice")) else synced["voice"],
        "bgmSrc": synced["bgm"],
        "bgmVolume": float(bgm_vol_val if bgm_vol_val is not None else 0.16),
        "sfxEvents": sfx_events,
        "sfxLevel": sfx_level,
        "sfxVolume": float(ov.get("sfx_volume") or dna.get("sfx_volume") or 0.42),
    }

    # Global + Brand Banned Words guardrail across all rendered visual text & captions
    banned_list = _style_dna_mod.get_effective_banned_words(brand_brief)
    if banned_list:
        props["title"] = _style_dna_mod.sanitize_banned_text(props["title"], banned_words=banned_list) or "TikTok Shop Review"
        if isinstance(props.get("floralBadge"), dict):
            for fk in ("brand", "productLine", "category"):
                if props["floralBadge"].get(fk):
                    props["floralBadge"][fk] = _style_dna_mod.sanitize_banned_text(props["floralBadge"][fk], banned_words=banned_list)
        for co in props.get("callouts") or []:
            for ln in co.get("lines") or []:
                for tk in ln.get("tokens") or []:
                    if tk.get("text"):
                        tk["text"] = _style_dna_mod.sanitize_banned_text(tk["text"], banned_words=banned_list)
        for cl in props.get("clips") or []:
            if cl.get("featurePill"):
                cleaned_fp = _style_dna_mod.sanitize_banned_text(cl["featurePill"], banned_words=banned_list)
                cl["featurePill"] = (
                    (_style_dna_mod.strip_slop_emojis(cleaned_fp) if icon_density == "minimal" else cleaned_fp)
                    or "🔥 Deal Hot"
                )
        for wd in props.get("words") or []:
            if wd.get("word"):
                cleaned_w = _style_dna_mod.sanitize_banned_text(wd["word"], banned_words=banned_list)
                wd["word"] = cleaned_w if cleaned_w else "•"
        if isinstance(props.get("wildcardSpec"), dict):
            wc_obj = props["wildcardSpec"]
            wc_obj["showRatingBadge"] = False
            if sticker_density == "off":
                wc_obj["stickerEvents"] = []
            if wc_obj.get("tickerText"):
                cleaned_tk = _style_dna_mod.sanitize_banned_text(wc_obj["tickerText"], banned_words=banned_list)
                wc_obj["tickerText"] = _style_dna_mod.strip_slop_emojis(cleaned_tk) if icon_density == "minimal" else cleaned_tk
            if wc_obj.get("ctaLabel"):
                cleaned_cta = _style_dna_mod.sanitize_banned_text(wc_obj["ctaLabel"], banned_words=banned_list)
                wc_obj["ctaLabel"] = cleaned_cta or "🛒 Giỏ Hàng Góc Trái"
            for si, st in enumerate(wc_obj.get("stickerEvents") or []):
                if isinstance(st, dict) and st.get("label"):
                    st["label"] = _style_dna_mod.strip_slop_emojis(
                        _style_dna_mod.sanitize_banned_text(st["label"], banned_words=banned_list)
                    ) or "DEAL HOT"
                    if not st.get("stickerAsset"):
                        st["stickerAsset"] = _style_dna_mod.resolve_animated_sticker_asset(str(st.get("emoji") or ""), si)

    FILE_REMOTION_PROPS.parent.mkdir(parents=True, exist_ok=True)
    FILE_REMOTION_PROPS.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    return props


def render_title_badge_preview(
    props: dict[str, Any] | None = None,
    output_png: Path = DIR_WORKSPACE / "hook_badge_preview.png",
) -> dict[str, Any]:
    """Render a transparent high-res PNG still of the Hook Badge / Callout."""
    sync_media_to_remotion_public()
    base_props = props or (
        json.loads(FILE_REMOTION_PROPS.read_text(encoding="utf-8-sig"))
        if FILE_REMOTION_PROPS.exists()
        else build_remotion_props()
    )
    badge_props = dict(base_props)
    badge_props["transparentBg"] = True
    badge_props["badgeOnly"] = True
    if isinstance(badge_props.get("floralBadge"), dict):
        badge_props["floralBadge"] = {**badge_props["floralBadge"], "enabled": True}
    if badge_props.get("badgeStyle") == "multicolor_pill":
        # Show first callout centered for preview
        badge_props["badgeOnly"] = False
        badge_props["clips"] = []
        badge_props["words"] = []

    tmp_props = DIR_WORKSPACE / "_badge_preview_props.json"
    tmp_props.write_text(json.dumps(badge_props, ensure_ascii=False, indent=2), encoding="utf-8")

    output_png.parent.mkdir(parents=True, exist_ok=True)
    npx = find_npx()
    browser_exe = find_browser_executable()
    rel_out = os.path.relpath(output_png, DIR_REMOTION)
    rel_props = os.path.relpath(tmp_props, DIR_REMOTION)
    cmd = [
        npx,
        "remotion",
        "still",
        "src/index.ts",
        "TikTokVideo",
        rel_out,
        f"--props={rel_props}",
        "--frame=25",
        "--image-format=png",
    ]
    if browser_exe:
        cmd.append(f"--browser-executable={browser_exe}")
    proc = subprocess.run(
        cmd,
        cwd=str(DIR_REMOTION),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Remotion still failed:\n{proc.stdout}\n{proc.stderr}")
    return {"ok": True, "output": str(output_png), "size_bytes": output_png.stat().st_size}


def extract_verification_frames(mp4_path: Path) -> list[dict[str, str]]:
    """Extract 3 verification frames (Hook 1s, Mid ~45%, CTA end) for user preview & AI Self-Check."""
    FILE_PREVIEW_FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    dur = probe_duration_sec(mp4_path) or 10.0
    timestamps = [
        ("frame_hook_1s.jpg", min(1.0, max(0.3, dur * 0.08))),
        ("frame_mid_12s.jpg", round(dur * 0.45, 2)),
        ("frame_cta_end.jpg", max(0.5, round(dur - 1.5, 2))),
    ]
    ffmpeg = find_ffmpeg()
    frames_out: list[dict[str, str]] = []
    ts_q = int(time.time())
    for fname, sec in timestamps:
        dst = FILE_PREVIEW_FRAMES_DIR / fname
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{sec:.2f}",
                "-i",
                str(mp4_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(dst),
            ],
            check=True,
            timeout=30,
        )
        frames_out.append(
            {
                "name": fname,
                "time_sec": f"{sec:.1f}s",
                "url": f"/files/04_workspace/render_preview_frames/{fname}?t={ts_q}",
            }
        )
    return frames_out


def render_creative_review_frames(
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render 3 Remotion timeline stills + Hook Badge PNG for creative review before full MP4 export."""
    props = build_remotion_props(overrides=overrides)
    if not props.get("clips"):
        raise RuntimeError("Chưa có clip video nào để dựng xem trước. Hãy chạy Bước cắt clip trước.")

    badge_res = render_title_badge_preview(props=props)
    FILE_PREVIEW_FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    dur = max(4.0, float(props.get("durationSec") or 25.0))
    fps = 30
    total_frames = max(30, int(round(dur * fps)))
    targets = [
        ("frame_hook_1s.jpg", min(total_frames - 1, max(10, int(round(min(1.0, dur * 0.08) * fps))))),
        ("frame_mid_12s.jpg", min(total_frames - 1, max(15, int(round(dur * 0.45 * fps))))),
        ("frame_cta_end.jpg", min(total_frames - 1, max(20, int(round(max(0.5, dur - 1.5) * fps))))),
    ]

    npx = find_npx()
    browser_exe = find_browser_executable()
    rel_props = os.path.relpath(FILE_REMOTION_PROPS, DIR_REMOTION)
    frames_out: list[dict[str, str]] = []
    ts_q = int(time.time())

    for fname, frame_no in targets:
        dst = FILE_PREVIEW_FRAMES_DIR / fname
        rel_dst = os.path.relpath(dst, DIR_REMOTION)
        cmd = [
            npx,
            "remotion",
            "still",
            "src/index.ts",
            "TikTokVideo",
            rel_dst,
            f"--props={rel_props}",
            f"--frame={frame_no}",
            "--image-format=jpeg",
        ]
        if browser_exe:
            cmd.append(f"--browser-executable={browser_exe}")
        proc = subprocess.run(
            cmd,
            cwd=str(DIR_REMOTION),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if proc.returncode != 0 or not dst.exists():
            raise RuntimeError(f"Remotion review still failed ({fname}):\n{proc.stdout}\n{proc.stderr}")
        sec = frame_no / float(fps)
        frames_out.append(
            {
                "name": fname,
                "time_sec": f"{sec:.1f}s",
                "url": f"/files/04_workspace/render_preview_frames/{fname}?t={ts_q}",
            }
        )

    return {
        "ok": True,
        "remotion_props": props,
        "badge_preview": badge_res,
        "preview_frames": frames_out,
    }


def render_remotion_video(
    output_path: Path | None = None,
    rebuild_props: bool = True,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render full 1080x1920 MP4 via headless Remotion using a script-named output file."""
    if rebuild_props or not FILE_REMOTION_PROPS.exists():
        props = build_remotion_props(overrides=overrides)
    else:
        sync_media_to_remotion_public()
        props = json.loads(FILE_REMOTION_PROPS.read_text(encoding="utf-8-sig"))

    if not props.get("clips"):
        raise RuntimeError("Chưa có clip video nào trong `04_workspace/ready_for_openreel/01_clips/`. Hãy chạy Bước cắt clip trước.")

    named_out_path, selected_meta = resolve_script_named_output_path(float(props.get("durationSec") or 30.0))
    use_script_naming = output_path is None or Path(output_path) == FILE_DEFAULT_OUTPUT
    target_output_path = named_out_path if use_script_naming else Path(output_path)

    target_output_path.parent.mkdir(parents=True, exist_ok=True)
    npx = find_npx()
    browser_exe = find_browser_executable()
    rel_out = os.path.relpath(target_output_path, DIR_REMOTION)
    rel_props = os.path.relpath(FILE_REMOTION_PROPS, DIR_REMOTION)
    composition_id = "TikTokInnovation" if props.get("renderEngine") == "remotion_innovation" else "TikTokVideo"
    cmd = [
        npx,
        "remotion",
        "render",
        "src/index.ts",
        composition_id,
        rel_out,
        f"--props={rel_props}",
        "--codec=h264",
        "--pixel-format=yuv420p",
    ]
    if browser_exe:
        cmd.append(f"--browser-executable={browser_exe}")
    t0 = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(DIR_REMOTION),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    elapsed = round(time.time() - t0, 2)
    if proc.returncode != 0 or not target_output_path.exists():
        raise RuntimeError(f"Remotion render failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}")

    if target_output_path != FILE_DEFAULT_OUTPUT:
        FILE_DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_output_path, FILE_DEFAULT_OUTPUT)

    frames = extract_verification_frames(target_output_path)
    out_dur = probe_duration_sec(target_output_path)
    return {
        "ok": True,
        "output": str(target_output_path),
        "output_filename": target_output_path.name,
        "output_url": f"/files/05_output/{target_output_path.name}?t={int(time.time())}",
        "selected_script": selected_meta,
        "size_bytes": target_output_path.stat().st_size,
        "duration_sec": out_dur,
        "render_seconds": elapsed,
        "preview_frames": frames,
        "props": props,
    }


if __name__ == "__main__":
    p = build_remotion_props()
    print(f"Built props: duration={p['durationSec']}s, clips={len(p['clips'])}, words={len(p['words'])}, callouts={len(p['callouts'])}")
